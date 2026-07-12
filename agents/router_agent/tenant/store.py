"""In-memory tenant store (P0-A / L-4).

Consistent with the observability_agent pattern: a bounded in-memory store
(single-instance deployment, no DB persistence needed for the gateway's
tenant registry). Tenant records are small and change infrequently, so a
dict + ring-buffer event log is sufficient and avoids introducing a migration
surface. Swap for SQLite/Postgres later if multi-instance is required.
"""

from __future__ import annotations

import logging
import time
import uuid
from collections import deque
from typing import Any

from agents.router_agent.tenant.models import Tenant, TenantKey

logger = logging.getLogger("fde.router.tenant.store")

_EVENT_MAXLEN = 10_000


class TenantStore:
    """Bounded in-memory store for tenants and their LiteLLM keys."""

    def __init__(self, event_maxlen: int = _EVENT_MAXLEN) -> None:
        self._tenants: dict[str, Tenant] = {}
        self._keys: dict[str, TenantKey] = {}  # keyed by key_id
        self._events: deque[dict[str, Any]] = deque(maxlen=event_maxlen)

    # ── Tenants ─────────────────────────────────────────────────

    def create_tenant(self, tenant: Tenant) -> Tenant:
        if tenant.tenant_id in self._tenants:
            raise ValueError(f"Tenant {tenant.tenant_id} already exists")
        self._tenants[tenant.tenant_id] = tenant
        self._record("tenant.create", tenant_id=tenant.tenant_id, name=tenant.name)
        return tenant

    def get_tenant(self, tenant_id: str) -> Tenant | None:
        t = self._tenants.get(tenant_id)
        if t is None or t.status == "deleted":
            return None
        return t

    def list_tenants(self) -> list[Tenant]:
        return [t for t in self._tenants.values() if t.status != "deleted"]

    def update_tenant(self, tenant_id: str, **changes: Any) -> Tenant:
        t = self.get_tenant(tenant_id)
        if t is None:
            raise KeyError(f"Tenant {tenant_id} not found")
        # Apply non-None scalar changes immutably (Pydantic model is immutable-ish)
        update = t.model_dump()
        for k, v in changes.items():
            if v is not None:
                update[k] = v
        updated = Tenant(**update)
        self._tenants[tenant_id] = updated
        self._record("tenant.update", tenant_id=tenant_id, changes=list(changes.keys()))
        return updated

    def delete_tenant(self, tenant_id: str) -> None:
        t = self.get_tenant(tenant_id)
        if t is None:
            raise KeyError(f"Tenant {tenant_id} not found")
        t.status = "deleted"
        self._tenants[tenant_id] = t
        self._record("tenant.delete", tenant_id=tenant_id)

    # ── Keys ────────────────────────────────────────────────────

    def put_key(self, key: TenantKey) -> TenantKey:
        self._keys[key.key_id] = key
        self._record("key.create", tenant_id=key.tenant_id, key_id=key.key_id)
        return key

    def get_key(self, key_id: str) -> TenantKey | None:
        k = self._keys.get(key_id)
        if k is None or k.status == "deleted":
            return None
        return k

    def get_keys_for_tenant(self, tenant_id: str) -> list[TenantKey]:
        return [k for k in self._keys.values() if k.tenant_id == tenant_id and k.status != "deleted"]

    def revoke_key(self, key_id: str) -> None:
        k = self._keys.get(key_id)
        if k is None:
            raise KeyError(f"Key {key_id} not found")
        k.status = "deleted"
        self._keys[key_id] = k
        self._record("key.revoke", key_id=key_id, tenant_id=k.tenant_id)

    # ── Events ──────────────────────────────────────────────────

    def _record(self, action: str, **fields: Any) -> None:
        self._events.append(
            {
                "event_id": uuid.uuid4().hex[:12],
                "action": action,
                "ts": time.time(),
                **fields,
            }
        )

    def get_events(self, limit: int = 100, tenant_id: str | None = None) -> list[dict[str, Any]]:
        events = list(self._events)
        if tenant_id:
            events = [e for e in events if e.get("tenant_id") == tenant_id]
        return events[-limit:][::-1]

    def stats(self) -> dict[str, int]:
        return {
            "tenants": len(self.list_tenants()),
            "active_keys": sum(1 for k in self._keys.values() if k.status != "deleted"),
            "events": len(self._events),
        }


# Module-level singleton (per process) — mirrors observability_agent usage.
tenant_store = TenantStore()
