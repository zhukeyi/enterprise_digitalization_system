"""Integration tests for the tenant API router (P0-A / L-4).

Mounts the tenant router on a minimal FastAPI app and drives it with
TestClient. The module-level ``tenant_store`` singleton is reset between
tests to avoid cross-test pollution (D6). The LiteLLM key client is mocked
so the router logic (including one-time raw-key return) is exercised without
a live proxy.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from agents.router_agent.tenant.models import Tenant, TenantKey
from agents.router_agent.tenant.router import router
from agents.router_agent.tenant.store import tenant_store


class _FakeKeyClient:
    """Enabled key client that records calls and returns a raw key once."""

    enabled = True

    def __init__(self) -> None:
        self.generated: list[Tenant] = []
        self.deleted: list[str] = []

    async def generate_key(self, tenant: Tenant) -> TenantKey:
        self.generated.append(tenant)
        return TenantKey(
            key_id=f"tok_{tenant.tenant_id}",
            tenant_id=tenant.tenant_id,
            virtual_key_masked="sk-...abcd",
            budget_usd=tenant.budget_usd,
            models=list(tenant.model_allowlist),
            raw_key="sk-live-secret-for-tenant",
            status="active",
        )

    async def delete_key(self, key_id: str) -> None:
        self.deleted.append(key_id)


@pytest.fixture()
def client(monkeypatch):
    # Reset the singleton store between tests (D6 isolation).
    tenant_store._tenants.clear()
    tenant_store._keys.clear()
    tenant_store._events.clear()

    fake = _FakeKeyClient()
    monkeypatch.setattr("agents.router_agent.tenant.router._key_client", fake)

    app = FastAPI()
    app.include_router(router)
    return TestClient(app), fake


def test_create_tenant_returns_raw_key_once(client):
    c, fake = client
    resp = c.post("/api/tenants", json={"name": "Acme", "tier": "base"})
    assert resp.status_code == 201
    body = resp.json()
    assert body["key_provisioned"] is True
    assert body["raw_key"] == "sk-live-secret-for-tenant"  # one-time secret
    # list/get must NOT leak raw_key
    tid = body["tenant"]["tenant_id"]
    get_resp = c.get(f"/api/tenants/{tid}")
    assert "raw_key" not in get_resp.json()
    assert fake.generated and fake.generated[0].name == "Acme"


def test_create_tenant_rejects_unknown_module(client):
    c, _ = client
    resp = c.post("/api/tenants", json={"name": "X", "tier": "addon", "module_grants": ["bogus"]})
    assert resp.status_code == 400


def test_list_and_get_tenant(client):
    c, _ = client
    c.post("/api/tenants", json={"name": "Acme", "tier": "base"})
    lst = c.get("/api/tenants")
    assert lst.status_code == 200
    assert lst.json()["total"] == 1
    tid = lst.json()["data"][0]["tenant_id"]
    assert c.get(f"/api/tenants/{tid}").status_code == 200
    assert c.get("/api/tenants/nonexistent").status_code == 404


def test_patch_tenant(client):
    c, _ = client
    tid = c.post("/api/tenants", json={"name": "Acme", "tier": "base"}).json()["tenant"]["tenant_id"]
    resp = c.patch(f"/api/tenants/{tid}", json={"budget_usd": 9.0})
    assert resp.status_code == 200
    assert resp.json()["tenant"]["budget_usd"] == 9.0


def test_delete_tenant_revokes_keys(client):
    c, fake = client
    tid = c.post("/api/tenants", json={"name": "Acme", "tier": "base"}).json()["tenant"]["tenant_id"]
    resp = c.delete(f"/api/tenants/{tid}")
    assert resp.status_code == 200
    assert resp.json()["keys_revoked"] == 1
    assert fake.deleted  # key revoke reached the proxy client
    assert c.get(f"/api/tenants/{tid}").status_code == 404


def test_rotate_key_returns_new_raw_key(client):
    c, _ = client
    tid = c.post("/api/tenants", json={"name": "Acme", "tier": "base"}).json()["tenant"]["tenant_id"]
    resp = c.post(f"/api/tenants/{tid}/key/rotate")
    assert resp.status_code == 201
    assert resp.json()["raw_key"] == "sk-live-secret-for-tenant"
