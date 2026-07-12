"""Observability Agent — FastAPI router.

Provides platform-wide monitoring endpoints:
- /healthz, /readyz, /livez — three-tier health probes
- /api/observability/overview — aggregated platform health
- /api/observability/health/components — component status matrix
- /api/observability/health/service-map — module dependency graph
- /api/observability/api/endpoints — auto-scanned API directory
- /api/observability/api/stats — API call statistics
- /api/observability/tokens/* — token usage, cost, routing, budget
- /api/observability/api/keys — API Key CRUD
- /api/observability/api/external — external API registry
"""

from __future__ import annotations

import logging
import time
from collections import defaultdict
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, FastAPI, Query
from pydantic import BaseModel, Field

from agents.observability_agent.api_keys import (
    create_api_key,
    delete_api_key,
    get_external_apis,
    list_api_keys,
    update_api_key,
)
from agents.observability_agent.budget import (
    get_budget,
    get_budget_events,
    set_budget,
)
from agents.observability_agent.health_checker import check_all_components, check_liveness
from agents.observability_agent.middleware import get_api_calls, get_api_stats_summary
from agents.observability_agent.models import (
    APIEndpointInfo,
    HealthCheckResult,
    KPICard,
    ModuleStatusCard,
    OverviewStats,
)
from agents.observability_agent.token_tracker import (
    get_cost_report,
    get_failover_events,
    get_model_pricing,
    get_routing_distribution,
    get_token_usage_grouped,
    get_token_usage_summary,
)

logger = logging.getLogger("fde.observability")

router = APIRouter(prefix="/api/observability", tags=["Observability"])

# Reference to the FastAPI app (set during registration)
_app: FastAPI | None = None

# Known agent modules for service map
_AGENT_MODULES = [
    "router_agent",
    "orchestrator",
    "rag_agent",
    "ingestion_agent",
    "analysis_agent",
    "hr_agent",
    "data_agent",
    "pricing_agent",
    "marketing_agent",
    "map_agent",
    "im_agent",
    "client_agent",
    "dify_bridge",
    "governance_agent",
    "compliance_agent",
    "business_agent",
    "observability_agent",
]

# Simple module dependency map (for service-map endpoint)
_DEPENDENCY_MAP: dict[str, list[str]] = {
    "router_agent": ["governance_agent", "orchestrator"],
    "orchestrator": ["rag_agent", "hr_agent", "data_agent", "analysis_agent", "map_agent", "compliance_agent", "business_agent"],
    "rag_agent": ["ingestion_agent"],
    "ingestion_agent": [],
    "data_agent": [],
    "hr_agent": [],
    "pricing_agent": [],
    "marketing_agent": [],
    "map_agent": [],
    "im_agent": [],
    "dify_bridge": ["orchestrator"],
    "governance_agent": [],
    "observability_agent": [],
}


def set_app(app: FastAPI) -> None:
    """Store reference to the FastAPI app for endpoint scanning."""
    global _app
    _app = app


# ── Three-tier health probes ─────────────────────────────────────


@router.get("/healthz", response_model=HealthCheckResult)
async def healthz() -> HealthCheckResult:
    """Liveness probe — process is alive."""
    return HealthCheckResult(status="healthy", components=[])


@router.get("/readyz", response_model=HealthCheckResult)
async def readyz() -> HealthCheckResult:
    """Readiness probe — all dependencies are reachable."""
    return await check_all_components()


@router.get("/livez")
async def livez() -> dict[str, Any]:
    """Liveness with error-rate check."""
    stats = get_api_stats_summary()
    alive = check_liveness(stats["error_rate"])
    return {
        "status": "alive" if alive else "degraded",
        "error_rate": stats["error_rate"],
        "checked_at": datetime.now(UTC).isoformat(),
    }


# ── Component health ──────────────────────────────────────────────


@router.get("/health/components", response_model=HealthCheckResult)
async def health_components() -> HealthCheckResult:
    """Get detailed component health status."""
    return await check_all_components()


@router.get("/health/service-map")
async def service_map() -> dict[str, Any]:
    """Get module dependency graph for service map visualization."""
    nodes = [
        {"id": m, "label": m, "status": "online"}
        for m in _AGENT_MODULES
    ]
    edges: list[dict[str, str]] = []
    for mod, deps in _DEPENDENCY_MAP.items():
        for dep in deps:
            edges.append({"source": mod, "target": dep})
    return {"nodes": nodes, "edges": edges}


# ── Overview ──────────────────────────────────────────────────────


@router.get("/overview", response_model=OverviewStats)
async def overview() -> OverviewStats:
    """Get aggregated platform overview statistics."""
    # Health check
    health = await check_all_components()
    unhealthy = sum(1 for c in health.components if c.status == "unhealthy")
    degraded = sum(1 for c in health.components if c.status == "degraded")
    health_score = max(0.0, 100.0 - (unhealthy * 30 + degraded * 10))

    # KPIs from API metrics
    stats = get_api_stats_summary()
    kpis = [
        KPICard(label="QPS", value=stats["qps"], unit="req/s"),
        KPICard(label="Error Rate", value=stats["error_rate"] * 100, unit="%"),
        KPICard(label="Avg Latency", value=stats["avg_latency_ms"], unit="ms"),
        KPICard(label="Total Calls", value=float(stats["total_calls"]), unit=""),
    ]

    # Module status cards (simplified — all online if health is ok)
    modules = [
        ModuleStatusCard(
            name=m,
            status="online" if health.status != "unhealthy" else "degraded",
        )
        for m in _AGENT_MODULES
    ]

    return OverviewStats(
        health_score=round(health_score, 1),
        kpis=kpis,
        modules=modules,
        events=[],
    )


# ── API endpoint auto-scan ────────────────────────────────────────


@router.get("/api/endpoints", response_model=list[APIEndpointInfo])
async def list_api_endpoints() -> list[APIEndpointInfo]:
    """Auto-scan all registered FastAPI routes and return endpoint directory."""
    if _app is None:
        return []

    endpoints: list[APIEndpointInfo] = []

    def _scan_routes(routes: list[Any]) -> None:
        for route in routes:
            # Direct route (has methods + path)
            if hasattr(route, "methods") and hasattr(route, "path"):
                path = route.path
                if path in ("/docs", "/redoc", "/openapi.json", "/metrics", "/docs/oauth2-redirect"):
                    continue
                if path.startswith("/docs/") or path.startswith("/redoc/"):
                    continue
                for method in sorted(route.methods):
                    if method in ("HEAD", "OPTIONS"):
                        continue
                    path_parts = path.strip("/").split("/")
                    module = path_parts[1] if len(path_parts) > 1 else "root"
                    summary = ""
                    if hasattr(route, "endpoint") and route.endpoint.__doc__:
                        summary = route.endpoint.__doc__.strip().split("\n")[0][:120]
                    tags = list(getattr(route, "tags", []) or [])
                    endpoints.append(
                        APIEndpointInfo(
                            path=path,
                            method=method,
                            summary=summary,
                            module=module,
                            tags=tags,
                        )
                    )
            # Included router (FastAPI 0.115+ wraps in _IncludedRouter)
            elif hasattr(route, "original_router"):
                _scan_routes(route.original_router.routes)
            # Nested router (older FastAPI)
            elif hasattr(route, "routes"):
                _scan_routes(route.routes)

    _scan_routes(_app.routes)
    return endpoints


@router.get("/api/stats")
async def api_stats(
    path: str | None = Query(None, description="Filter by path prefix"),
) -> dict[str, Any]:
    """Get API call statistics, optionally filtered by path."""
    calls = get_api_calls()
    if path:
        calls = [c for c in calls if c[2].startswith(path)]

    if not calls:
        return {"total_calls": 0, "avg_latency_ms": 0.0, "error_rate": 0.0, "qps": 0.0}

    total = len(calls)
    errors = sum(1 for c in calls if c[3] >= 400)
    avg_latency = sum(c[4] for c in calls) / total
    now = time.time()
    recent_60s = [c for c in calls if now - c[0] < 60]
    qps = len(recent_60s) / 60.0

    # Per-path breakdown
    per_path: dict[str, dict[str, Any]] = defaultdict(lambda: {"count": 0, "errors": 0, "latency_sum": 0.0})
    for c in calls:
        key = f"{c[1]} {c[2]}"
        per_path[key]["count"] += 1
        if c[3] >= 400:
            per_path[key]["errors"] += 1
        per_path[key]["latency_sum"] += c[4]

    breakdown = [
        {
            "endpoint": k,
            "count": v["count"],
            "errors": v["errors"],
            "avg_latency_ms": round(v["latency_sum"] / v["count"], 1),
        }
        for k, v in sorted(per_path.items(), key=lambda x: x[1]["count"], reverse=True)[:20]
    ]

    return {
        "total_calls": total,
        "avg_latency_ms": round(avg_latency, 1),
        "error_rate": round(errors / total, 4),
        "qps": round(qps, 2),
        "breakdown": breakdown,
    }


# ── Token usage & cost ────────────────────────────────────────────


@router.get("/tokens/usage")
async def token_usage(
    group_by: str = Query("model", description="Group by: model|user|agent|hour"),
    hours: int = Query(24, ge=1, le=168, description="Lookback window in hours"),
) -> dict[str, Any]:
    """Get token usage statistics grouped by dimension."""
    summary = get_token_usage_summary()
    grouped = get_token_usage_grouped(group_by=group_by, hours=hours)
    return {
        "group_by": group_by,
        "hours": hours,
        "summary": summary,
        "data": grouped,
    }


@router.get("/tokens/cost")
async def token_cost(
    period: str = Query("daily", description="Period: daily|weekly|monthly"),
) -> dict[str, Any]:
    """Get token cost report aggregated by time period."""
    data = get_cost_report(period=period)
    summary = get_token_usage_summary()
    return {
        "period": period,
        "summary": summary,
        "data": data,
    }


@router.get("/tokens/routing")
async def token_routing() -> dict[str, Any]:
    """Get routing rule hit distribution — which models were selected."""
    distribution = get_routing_distribution()
    pricing = get_model_pricing()
    return {
        "distribution": distribution,
        "pricing": pricing,
    }


@router.get("/tokens/failover")
async def token_failover() -> dict[str, Any]:
    """Get failover events — when requests were retried on a different model."""
    events = get_failover_events()
    return {
        "total": len(events),
        "events": events,
    }


# ── Budget (Cost Canary) ──────────────────────────────────────────


class BudgetRequest(BaseModel):
    """Request body for setting a budget."""

    agent_module: str = Field(..., description="Agent module name")
    daily_limit_usd: float = Field(..., gt=0, description="Daily spending limit in USD")


@router.get("/tokens/budget")
async def get_budget_endpoint(
    agent_module: str | None = Query(None, description="Filter by agent module"),
) -> dict[str, Any]:
    """Get budget info for one or all agent modules."""
    return get_budget(agent_module)


@router.post("/tokens/budget")
async def set_budget_endpoint(req: BudgetRequest) -> dict[str, Any]:
    """Set or update the daily budget for an agent module."""
    return set_budget(req.agent_module, req.daily_limit_usd)


@router.get("/tokens/budget/events")
async def budget_events(
    hours: int = Query(24, ge=1, le=168),
) -> dict[str, Any]:
    """Get budget events (warnings, exceeded) from the last N hours."""
    events = get_budget_events(hours=hours)
    return {
        "hours": hours,
        "total": len(events),
        "events": events,
    }


# ── API Key management ────────────────────────────────────────────


class CreateKeyRequest(BaseModel):
    """Request body for creating an API key."""

    name: str = Field(..., description="Human-readable key name")
    user_id: str = Field("", description="Owner user ID")
    quota_tpm: int = Field(100000, gt=0, description="Tokens per minute limit")
    quota_rpm: int = Field(60, gt=0, description="Requests per minute limit")


class UpdateKeyRequest(BaseModel):
    """Request body for updating an API key."""

    name: str | None = None
    quota_tpm: int | None = Field(None, gt=0)
    quota_rpm: int | None = Field(None, gt=0)
    enabled: bool | None = None


@router.post("/api/keys")
async def create_key(req: CreateKeyRequest) -> dict[str, Any]:
    """Create a new API key."""
    return create_api_key(
        name=req.name,
        user_id=req.user_id,
        quota_tpm=req.quota_tpm,
        quota_rpm=req.quota_rpm,
    )


@router.get("/api/keys")
async def list_keys() -> list[dict[str, Any]]:
    """List all API keys (without raw key values)."""
    return list_api_keys()


@router.put("/api/keys/{key_id}")
async def update_key(key_id: str, req: UpdateKeyRequest) -> dict[str, Any]:
    """Update an API key's attributes."""
    result = update_api_key(
        key_id=key_id,
        name=req.name,
        quota_tpm=req.quota_tpm,
        quota_rpm=req.quota_rpm,
        enabled=req.enabled,
    )
    if result is None:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail=f"API key not found: {key_id}")
    return result


@router.delete("/api/keys/{key_id}")
async def delete_key(key_id: str) -> dict[str, Any]:
    """Delete an API key."""
    success = delete_api_key(key_id)
    if not success:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail=f"API key not found: {key_id}")
    return {"deleted": True, "key_id": key_id}


# ── External API registry ─────────────────────────────────────────


@router.get("/api/external")
async def external_apis() -> list[dict[str, Any]]:
    """Get external API integration registry."""
    return get_external_apis()


# ── RAG inspector (stub — Phase 3 will implement) ────────────────


@router.get("/rag/docs")
async def rag_docs(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    doc_type: str | None = None,
) -> dict[str, Any]:
    """List documents in RAG store (Phase 3)."""
    return {
        "page": page,
        "page_size": page_size,
        "total": 0,
        "data": [],
        "note": "Phase 3 will implement RAG inspector",
    }


# ── Traces (stub — Phase 3 will implement) ───────────────────────


@router.get("/traces")
async def traces(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: str | None = None,
) -> dict[str, Any]:
    """List traces (Phase 3)."""
    return {
        "page": page,
        "page_size": page_size,
        "total": 0,
        "data": [],
        "note": "Phase 3 will implement trace store",
    }


# ── Audit (stub — Phase 4 will implement) ────────────────────────


@router.get("/audit/logs")
async def audit_logs(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> dict[str, Any]:
    """List audit log entries (Phase 4)."""
    return {
        "page": page,
        "page_size": page_size,
        "total": 0,
        "data": [],
        "note": "Phase 4 will implement audit trail",
    }
