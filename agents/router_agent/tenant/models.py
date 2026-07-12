"""Tenant data models for multi-tenant gateway (P0-A / L-4).

Maps the V5 commercial model (基础版 / 增值单模块 / 全家桶) onto LiteLLM
virtual keys: each tenant gets a key bound to a model allowlist + budget +
rate limit, and is granted access to a subset of the value-add modules
(④ intelligence / ⑤ marketing / ⑥ hr / ⑦ pricing).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class SubscriptionTier(StrEnum):
    """V5 commercial subscription tiers."""

    BASE = "base"          # 基础版 ①②③
    ADDON = "addon"        # 增值单模块（④/⑤/⑥/⑦ 任选）
    ENTERPRISE = "enterprise"  # 全家桶 ①-⑦


# V5 value-add module codes → ④ intelligence / ⑤ marketing / ⑥ hr / ⑦ pricing
MODULE_CODES: dict[str, str] = {
    "intelligence": "④ 情报增幅器",
    "marketing": "⑤ GEO 营销",
    "hr": "⑥ HR 智能评估",
    "pricing": "⑦ 动态定价",
}

# Default model allowlists per tier (LiteLLM model aliases).
TIER_MODEL_ALLOWLIST: dict[SubscriptionTier, list[str]] = {
    SubscriptionTier.BASE: ["fde-economy", "fde-default"],
    SubscriptionTier.ADDON: ["fde-economy", "fde-default", "fde-premium"],
    SubscriptionTier.ENTERPRISE: ["fde-economy", "fde-default", "fde-premium", "fde-frontier"],
}

TIER_BUDGET_USD: dict[SubscriptionTier, float] = {
    SubscriptionTier.BASE: 5.0,
    SubscriptionTier.ADDON: 50.0,
    SubscriptionTier.ENTERPRISE: 500.0,
}

TIER_RPM: dict[SubscriptionTier, int] = {
    SubscriptionTier.BASE: 10,
    SubscriptionTier.ADDON: 60,
    SubscriptionTier.ENTERPRISE: 300,
}


class Tenant(BaseModel):
    """A commercial tenant (yearly-subscription unit)."""

    tenant_id: str = Field(default_factory=lambda: f"tnt_{uuid.uuid4().hex[:12]}")
    name: str
    tier: SubscriptionTier = SubscriptionTier.BASE
    model_allowlist: list[str] = Field(default_factory=list)
    budget_usd: float = 0.0
    rpm_limit: int = 10
    module_grants: list[str] = Field(default_factory=list)
    status: str = "active"  # active | suspended | deleted
    created_at: str = Field(
        default_factory=lambda: datetime.now(UTC).isoformat(timespec="seconds")
    )
    notes: str = ""

    @classmethod
    def from_tier(
        cls,
        name: str,
        tier: SubscriptionTier,
        module_grants: list[str] | None = None,
        model_allowlist: list[str] | None = None,
        budget_usd: float | None = None,
        rpm_limit: int | None = None,
        notes: str = "",
    ) -> Tenant:
        """Build a tenant with tier-default budgets/allowlists (overridable)."""
        unknown = set(module_grants or []) - set(MODULE_CODES)
        if unknown:
            raise ValueError(f"Unknown module grant(s): {sorted(unknown)}")
        return cls(
            name=name,
            tier=tier,
            model_allowlist=model_allowlist or list(TIER_MODEL_ALLOWLIST[tier]),
            budget_usd=budget_usd if budget_usd is not None else TIER_BUDGET_USD[tier],
            rpm_limit=rpm_limit if rpm_limit is not None else TIER_RPM[tier],
            module_grants=module_grants or [],
            notes=notes,
        )


class TenantKey(BaseModel):
    """A LiteLLM virtual key bound to a tenant."""

    key_id: str
    tenant_id: str
    virtual_key_masked: str
    budget_usd: float
    models: list[str] = Field(default_factory=list)
    created_at: str = Field(
        default_factory=lambda: datetime.now(UTC).isoformat(timespec="seconds")
    )
    status: str = "active"


class TenantCreateRequest(BaseModel):
    """API payload to create a tenant."""

    name: str
    tier: SubscriptionTier = SubscriptionTier.BASE
    module_grants: list[str] = Field(default_factory=list)
    model_allowlist: list[str] | None = None
    budget_usd: float | None = None
    rpm_limit: int | None = None
    notes: str = ""


class TenantUpdateRequest(BaseModel):
    """API payload to update a tenant (partial)."""

    name: str | None = None
    tier: SubscriptionTier | None = None
    model_allowlist: list[str] | None = None
    budget_usd: float | None = None
    rpm_limit: int | None = None
    module_grants: list[str] | None = None
    status: str | None = None
    notes: str | None = None


def mask_key(raw: str, visible: int = 4) -> str:
    """Mask a virtual key for display: keep last ``visible`` chars."""
    if not raw:
        return ""
    if len(raw) <= visible + 3:
        return "*" * len(raw)
    return f"sk-...{raw[-visible:]}"


def tenant_to_litellm_metadata(tenant: Tenant) -> dict[str, Any]:
    """Build LiteLLM key metadata from a tenant (for audit/visibility)."""
    return {
        "tenant_id": tenant.tenant_id,
        "tier": tenant.tier.value,
        "module_grants": tenant.module_grants,
        "budget_usd": tenant.budget_usd,
        "rpm_limit": tenant.rpm_limit,
    }
