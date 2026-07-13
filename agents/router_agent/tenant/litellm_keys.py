"""LiteLLM virtual key management client (P0-A / L-4).

Thin httpx wrapper around the LiteLLM proxy's key-management API
(https://docs.litellm.ai/docs/proxy/virtual_keys). Each tenant maps to one
virtual key bound to a model allowlist + spend budget + rate limit; LiteLLM
enforces these server-side, so the FDE gateway offloads multi-tenant auth +
billing to the proxy.

Endpoints used:
- POST /key/generate   → create a virtual key
- GET  /key/info       → inspect a key
- POST /key/delete     → revoke key(s)

Graceful: every method raises :class:`LiteLLMKeyError` on proxy failure so
callers can decide between hard-fail and soft-degrade (e.g. keep the tenant
record even if key provisioning is temporarily unavailable).
"""

from __future__ import annotations

import logging
import os

import httpx

from agents.router_agent.tenant.models import (
    Tenant,
    TenantKey,
    mask_key,
    tenant_to_litellm_metadata,
)

logger = logging.getLogger("fde.router.tenant.litellm_keys")


class LiteLLMKeyError(Exception):
    """Raised when LiteLLM key management fails."""


class LiteLLMKeyClient:
    """Client for LiteLLM proxy virtual-key management."""

    def __init__(
        self,
        proxy_url: str | None = None,
        master_key: str | None = None,
        timeout_seconds: float = 20.0,
    ) -> None:
        self.proxy_url = (proxy_url or os.getenv("LITELLM_PROXY_URL", "")).rstrip("/")
        self.master_key = master_key or os.getenv("LITELLM_MASTER_KEY", "")
        self.timeout = timeout_seconds
        self._client: httpx.AsyncClient | None = None

    @property
    def enabled(self) -> bool:
        return bool(self.proxy_url and self.master_key)

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=httpx.Timeout(self.timeout))
        return self._client

    async def aclose(self) -> None:
        if self._client is not None and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.master_key}",
            "Content-Type": "application/json",
        }

    async def generate_key(self, tenant: Tenant) -> TenantKey:
        """Create a LiteLLM virtual key bound to the tenant's policy."""
        if not self.enabled:
            raise LiteLLMKeyError("LiteLLM proxy URL / master key not configured")

        # Rate limiting: tenant.rpm_limit is *requests per minute* — map it to
        # LiteLLM's ``rpm_limit`` (not ``max_parallel_requests``, which is a
        # concurrency cap). We also set a modest concurrency cap to stop a
        # single tenant from saturating the proxy.
        concurrency = min(max(tenant.rpm_limit, 1), 20)
        payload = {
            "key_alias": f"fde-{tenant.tenant_id}",
            "spend": tenant.budget_usd,
            "models": list(tenant.model_allowlist),
            "rpm_limit": tenant.rpm_limit,
            "max_parallel_requests": concurrency,
            "metadata": tenant_to_litellm_metadata(tenant),
        }
        url = f"{self.proxy_url}/key/generate"
        try:
            resp = await self._get_client().post(url, json=payload, headers=self._headers())
        except httpx.HTTPError as e:
            raise LiteLLMKeyError(f"LiteLLM proxy unreachable: {e}") from e

        if resp.status_code not in (200, 201):
            raise LiteLLMKeyError(f"/key/generate {resp.status_code}: {resp.text[:400]}")

        data = resp.json()
        raw_key = data.get("key")
        if not raw_key:
            raise LiteLLMKeyError(f"No key returned by proxy: {data}")
        key_id = data.get("token_id") or data.get("key_name") or f"kid_{raw_key[-8:]}"

        return TenantKey(
            key_id=str(key_id),
            tenant_id=tenant.tenant_id,
            virtual_key_masked=mask_key(raw_key),
            budget_usd=tenant.budget_usd,
            models=list(tenant.model_allowlist),
            raw_key=raw_key,  # returned once to the caller; excluded from dumps
            status="active",
        )

    async def get_key_info(self, key_id: str) -> dict:
        """Fetch key info from the proxy by token id or hashed key."""
        if not self.enabled:
            raise LiteLLMKeyError("LiteLLM proxy not configured")
        url = f"{self.proxy_url}/key/info"
        try:
            resp = await self._get_client().get(
                url, params={"key": key_id}, headers=self._headers()
            )
        except httpx.HTTPError as e:
            raise LiteLLMKeyError(f"LiteLLM proxy unreachable: {e}") from e
        if resp.status_code != 200:
            raise LiteLLMKeyError(f"/key/info {resp.status_code}: {resp.text[:400]}")
        return resp.json()

    async def delete_key(self, key_id: str) -> None:
        """Revoke a virtual key by token id (or hashed key)."""
        if not self.enabled:
            raise LiteLLMKeyError("LiteLLM proxy not configured")
        url = f"{self.proxy_url}/key/delete"
        try:
            resp = await self._get_client().post(
                url, json={"keys": [key_id]}, headers=self._headers()
            )
        except httpx.HTTPError as e:
            raise LiteLLMKeyError(f"LiteLLM proxy unreachable: {e}") from e
        if resp.status_code not in (200, 204):
            raise LiteLLMKeyError(f"/key/delete {resp.status_code}: {resp.text[:400]}")
