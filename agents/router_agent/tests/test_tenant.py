"""Tests for the tenant store + LiteLLM key client (P0-A / L-4)."""

from __future__ import annotations

import httpx
import pytest

from agents.router_agent.tenant.litellm_keys import LiteLLMKeyClient, LiteLLMKeyError
from agents.router_agent.tenant.models import SubscriptionTier, Tenant
from agents.router_agent.tenant.store import TenantStore

# ── Tenant model ────────────────────────────────────────────────


def test_tenant_from_tier_defaults():
    t = Tenant.from_tier(name="acme", tier=SubscriptionTier.BASE)
    assert t.tier == SubscriptionTier.BASE
    assert t.budget_usd == 5.0
    assert "fde-default" in t.model_allowlist
    assert t.module_grants == []


def test_tenant_from_tier_rejects_unknown_module():
    with pytest.raises(ValueError):
        Tenant.from_tier(name="x", tier=SubscriptionTier.ADDON, module_grants=["bogus"])


def test_tenant_from_tier_addon_with_grants():
    t = Tenant.from_tier(
        name="acme",
        tier=SubscriptionTier.ADDON,
        module_grants=["intelligence", "pricing"],
    )
    assert set(t.module_grants) == {"intelligence", "pricing"}
    assert t.budget_usd == 50.0


# ── Store CRUD ──────────────────────────────────────────────────


def test_store_crud_lifecycle():
    store = TenantStore()
    t = Tenant.from_tier(name="acme", tier=SubscriptionTier.BASE)
    store.create_tenant(t)
    assert store.get_tenant(t.tenant_id) is not None
    assert len(store.list_tenants()) == 1

    store.update_tenant(t.tenant_id, name="acme2", budget_usd=9.0)
    assert store.get_tenant(t.tenant_id).name == "acme2"
    assert store.get_tenant(t.tenant_id).budget_usd == 9.0

    store.delete_tenant(t.tenant_id)
    assert store.get_tenant(t.tenant_id) is None  # soft-deleted
    assert len(store.list_tenants()) == 0


def test_store_key_lifecycle():
    store = TenantStore()
    t = Tenant.from_tier(name="acme", tier=SubscriptionTier.BASE)
    store.create_tenant(t)
    from agents.router_agent.tenant.models import TenantKey

    key = TenantKey(
        key_id="kid1",
        tenant_id=t.tenant_id,
        virtual_key_masked="sk-...abcd",
        budget_usd=t.budget_usd,
        models=t.model_allowlist,
    )
    store.put_key(key)
    assert len(store.get_keys_for_tenant(t.tenant_id)) == 1
    store.revoke_key("kid1")
    assert store.get_key("kid1") is None
    assert store.get_keys_for_tenant(t.tenant_id) == []


def test_store_events_recorded():
    store = TenantStore()
    t = Tenant.from_tier(name="acme", tier=SubscriptionTier.BASE)
    store.create_tenant(t)
    store.delete_tenant(t.tenant_id)
    events = store.get_events()
    actions = [e["action"] for e in events]
    assert "tenant.create" in actions
    assert "tenant.delete" in actions
    assert store.stats()["events"] >= 2


# ── LiteLLM key client ──────────────────────────────────────────


def _mock_client(handler) -> LiteLLMKeyClient:
    c = LiteLLMKeyClient(proxy_url="http://litellm:4000", master_key="master")
    c._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return c


async def test_key_client_generate_parses_response():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["auth"] = request.headers.get("Authorization")
        return httpx.Response(
            200,
            json={"key": "sk-litellm-rawsecret", "token_id": "tok_abc", "key_name": "fde-tnt_1"},
        )

    c = _mock_client(handler)
    t = Tenant.from_tier(name="acme", tier=SubscriptionTier.BASE)
    key = await c.generate_key(t)

    assert str(captured["url"]).endswith("/key/generate")
    assert captured["auth"] == "Bearer master"
    assert key.key_id == "tok_abc"
    assert key.virtual_key_masked == "sk-...cret"
    assert key.tenant_id == t.tenant_id
    await c.aclose()


async def test_key_client_delete():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["body"] = request.content
        return httpx.Response(200, json={"status": "ok"})

    c = _mock_client(handler)
    await c.delete_key("tok_abc")
    assert str(captured["url"]).endswith("/key/delete")
    assert b"tok_abc" in captured["body"]
    await c.aclose()


async def test_key_client_disabled_raises():
    c = LiteLLMKeyClient(proxy_url="", master_key="")
    t = Tenant.from_tier(name="acme", tier=SubscriptionTier.BASE)
    with pytest.raises(LiteLLMKeyError):
        await c.generate_key(t)


async def test_key_client_error_status_raises():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="proxy down")

    c = _mock_client(handler)
    t = Tenant.from_tier(name="acme", tier=SubscriptionTier.BASE)
    with pytest.raises(LiteLLMKeyError):
        await c.generate_key(t)
    await c.aclose()
