"""Tenant management API (P0-A / L-4).

Mounted at ``/api/tenants``. Each tenant is provisioned a LiteLLM virtual
key (when the proxy is enabled) that enforces the tenant's model allowlist,
budget and rate limit server-side.

Auth: the app-level APIKeyMiddleware already gates every route when
``FDE_ENABLE_AUTH=1``. Role-based admin authorization is a hardening item
tracked for P0-B; for now any valid API key may manage tenants (sufficient
for single-operator deployments).
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Request

from agents.router_agent.tenant.litellm_keys import LiteLLMKeyClient, LiteLLMKeyError
from agents.router_agent.tenant.models import (
    Tenant,
    TenantCreateRequest,
    TenantUpdateRequest,
)
from agents.router_agent.tenant.store import tenant_store

logger = logging.getLogger("fde.router.tenant.router")

router = APIRouter(prefix="/api/tenants", tags=["tenants"])

_key_client = LiteLLMKeyClient()


@router.post("", response_model=None, status_code=201)
async def create_tenant(payload: TenantCreateRequest, request: Request) -> dict:
    """Create a tenant and (if proxy enabled) provision its virtual key."""
    try:
        tenant = Tenant.from_tier(
            name=payload.name,
            tier=payload.tier,
            module_grants=payload.module_grants,
            model_allowlist=payload.model_allowlist,
            budget_usd=payload.budget_usd,
            rpm_limit=payload.rpm_limit,
            notes=payload.notes,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    tenant_store.create_tenant(tenant)

    key = None
    if _key_client.enabled:
        try:
            key = await _key_client.generate_key(tenant)
            tenant_store.put_key(key)
        except LiteLLMKeyError as e:
            logger.warning("Key provisioning failed for %s: %s", tenant.tenant_id, e)

    return {
        "tenant": tenant.model_dump(),
        "virtual_key": key.virtual_key_masked if key else None,
        "key_provisioned": key is not None,
    }


@router.get("", response_model=None)
async def list_tenants(request: Request) -> dict:
    tenants = tenant_store.list_tenants()
    return {"total": len(tenants), "data": [t.model_dump() for t in tenants]}


@router.get("/{tenant_id}", response_model=None)
async def get_tenant(tenant_id: str, request: Request) -> dict:
    tenant = tenant_store.get_tenant(tenant_id)
    if tenant is None:
        raise HTTPException(status_code=404, detail="Tenant not found")
    keys = tenant_store.get_keys_for_tenant(tenant_id)
    return {
        "tenant": tenant.model_dump(),
        "keys": [k.model_dump() for k in keys],
    }


@router.patch("/{tenant_id}", response_model=None)
async def update_tenant(tenant_id: str, payload: TenantUpdateRequest, request: Request) -> dict:
    try:
        tenant = tenant_store.update_tenant(tenant_id, **payload.model_dump(exclude_unset=True))
    except KeyError:
        raise HTTPException(status_code=404, detail="Tenant not found") from None
    return {"tenant": tenant.model_dump()}


@router.delete("/{tenant_id}", response_model=None, status_code=200)
async def delete_tenant(tenant_id: str, request: Request) -> dict:
    tenant = tenant_store.get_tenant(tenant_id)
    if tenant is None:
        raise HTTPException(status_code=404, detail="Tenant not found")
    # Best-effort revoke all active keys
    revoked = 0
    for key in tenant_store.get_keys_for_tenant(tenant_id):
        try:
            await _key_client.delete_key(key.key_id)
            tenant_store.revoke_key(key.key_id)
            revoked += 1
        except LiteLLMKeyError as e:
            logger.warning("Key revoke failed %s: %s", key.key_id, e)
    tenant_store.delete_tenant(tenant_id)
    return {"deleted": tenant_id, "keys_revoked": revoked}


@router.get("/{tenant_id}/key", response_model=None)
async def get_tenant_key(tenant_id: str, request: Request) -> dict:
    keys = tenant_store.get_keys_for_tenant(tenant_id)
    if not keys:
        raise HTTPException(status_code=404, detail="No active key for tenant")
    return {"key": keys[-1].model_dump()}


@router.post("/{tenant_id}/key/rotate", response_model=None, status_code=201)
async def rotate_key(tenant_id: str, request: Request) -> dict:
    tenant = tenant_store.get_tenant(tenant_id)
    if tenant is None:
        raise HTTPException(status_code=404, detail="Tenant not found")
    # Revoke existing
    for key in tenant_store.get_keys_for_tenant(tenant_id):
        try:
            await _key_client.delete_key(key.key_id)
        except LiteLLMKeyError as e:
            logger.warning("Key revoke failed %s: %s", key.key_id, e)
        tenant_store.revoke_key(key.key_id)
    # Generate new
    new_key = None
    if _key_client.enabled:
        try:
            new_key = await _key_client.generate_key(tenant)
            tenant_store.put_key(new_key)
        except LiteLLMKeyError as e:
            raise HTTPException(status_code=502, detail=f"Key rotation failed: {e}") from e
    return {
        "tenant_id": tenant_id,
        "virtual_key": new_key.virtual_key_masked if new_key else None,
        "key_provisioned": new_key is not None,
    }
