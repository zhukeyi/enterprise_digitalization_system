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

from fastapi import APIRouter, FastAPI, Query, Request, Response
from pydantic import BaseModel, Field

from agents.observability_agent.alerting import (
    delete_alert_rule,
    evaluate_alerts,
    get_alert_rules,
    get_alerts,
    get_drift_report,
    set_alert_rule,
)
from agents.observability_agent.api_keys import (
    create_api_key,
    delete_api_key,
    get_external_apis,
    list_api_keys,
    update_api_key,
)
from agents.observability_agent.audit_store import (
    export_audit_logs,
    get_audit_logs,
    record_audit_event,
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


def _actor(request: Request | None = None) -> str:
    """Derive the audit actor from the authenticated API key, else 'admin'."""
    if request is not None:
        name = getattr(request.state, "api_key_name", None)
        uid = getattr(request.state, "api_user_id", None)
        if name:
            return f"{name}" + (f"({uid})" if uid else "")
    return "admin"


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
async def set_budget_endpoint(req: BudgetRequest, request: Request) -> dict[str, Any]:
    """Set or update the daily budget for an agent module."""
    result = set_budget(req.agent_module, req.daily_limit_usd)
    record_audit_event(
        actor=_actor(request),
        action="budget.set",
        resource_type="agent_module",
        resource_id=req.agent_module,
        detail=f"daily_limit_usd={req.daily_limit_usd}",
    )
    return result


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
async def create_key(req: CreateKeyRequest, request: Request) -> dict[str, Any]:
    """Create a new API key."""
    result = create_api_key(
        name=req.name,
        user_id=req.user_id,
        quota_tpm=req.quota_tpm,
        quota_rpm=req.quota_rpm,
    )
    record_audit_event(
        actor=_actor(request),
        action="api_key.create",
        resource_type="api_key",
        resource_id=result["key_id"],
        detail=f"name={req.name}",
    )
    return result


@router.get("/api/keys")
async def list_keys() -> list[dict[str, Any]]:
    """List all API keys (without raw key values)."""
    return list_api_keys()


@router.put("/api/keys/{key_id}")
async def update_key(key_id: str, req: UpdateKeyRequest, request: Request) -> dict[str, Any]:
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
    record_audit_event(
        actor=_actor(request),
        action="api_key.update",
        resource_type="api_key",
        resource_id=key_id,
        detail=f"name={req.name},enabled={req.enabled}",
    )
    return result


@router.delete("/api/keys/{key_id}")
async def delete_key(key_id: str, request: Request) -> dict[str, Any]:
    """Delete an API key."""
    success = delete_api_key(key_id)
    if not success:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail=f"API key not found: {key_id}")
    record_audit_event(
        actor=_actor(request),
        action="api_key.delete",
        resource_type="api_key",
        resource_id=key_id,
    )
    return {"deleted": True, "key_id": key_id}


# ── External API registry ─────────────────────────────────────────


@router.get("/api/external")
async def external_apis() -> list[dict[str, Any]]:
    """Get external API integration registry."""
    return get_external_apis()


# ── RAG inspector (Phase 3) ──────────────────────────────────────


@router.get("/rag/docs")
async def rag_docs(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    doc_type: str | None = None,
    source: str | None = None,
) -> dict[str, Any]:
    """List documents in RAG store (Phase 3)."""
    from agents.observability_agent.rag_inspector import list_documents

    return await list_documents(page=page, page_size=page_size, doc_type=doc_type, source=source)


@router.get("/rag/docs/{doc_id}/chunks")
async def rag_doc_chunks(
    doc_id: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
) -> dict[str, Any]:
    """Get all chunks for a document (Phase 3)."""
    from agents.observability_agent.rag_inspector import get_document_chunks

    return await get_document_chunks(doc_id=doc_id, page=page, page_size=page_size)


@router.get("/rag/chunks/{chunk_id}")
async def rag_chunk_detail(chunk_id: str) -> dict[str, Any]:
    """Get detailed chunk info including vector preview (Phase 3)."""
    from agents.observability_agent.rag_inspector import get_chunk_detail

    detail = await get_chunk_detail(chunk_id)
    if detail is None:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail=f"Chunk not found: {chunk_id}")
    return detail


@router.delete("/rag/docs/{doc_id}")
async def rag_delete_doc(doc_id: str, confirm: str | None = Query(None, description="Must be 'DELETE'"), request: Request = None) -> dict[str, Any]:
    """Delete a document: cascade Qdrant + Postgres + FTS (Phase 3)."""
    if confirm != "DELETE":
        from fastapi import HTTPException

        raise HTTPException(status_code=400, detail="Require confirm=DELETE in query string")
    from agents.observability_agent.rag_inspector import delete_document

    result = await delete_document(doc_id)
    record_audit_event(
        actor=_actor(request),
        action="rag.document.delete",
        resource_type="document",
        resource_id=doc_id,
        status="ok" if result.get("deleted") else "failed",
    )
    return result


@router.post("/rag/docs/{doc_id}/reindex")
async def rag_reindex_doc(doc_id: str, request: Request = None) -> dict[str, Any]:
    """Re-chunk + re-embed + re-upsert a document (Phase 3)."""
    from agents.observability_agent.rag_inspector import reindex_document

    try:
        result = await reindex_document(doc_id)
        record_audit_event(
            actor=_actor(request),
            action="rag.document.reindex",
            resource_type="document",
            resource_id=doc_id,
            status="ok" if result.get("reindexed") else "failed",
        )
        return result
    except Exception as e:
        logger.exception("reindex failed for %s", doc_id)
        record_audit_event(
            actor=_actor(request),
            action="rag.document.reindex",
            resource_type="document",
            resource_id=doc_id,
            status="failed",
            detail=str(e),
        )
        from fastapi import HTTPException

        raise HTTPException(status_code=500, detail=f"Reindex failed: {e}")


@router.post("/rag/debug/retrieve")
async def rag_debug_retrieve(
    body: dict[str, Any],
) -> dict[str, Any]:
    """Replay a retrieval: QueryRewrite + HybridSearch + Reranker (Phase 3)."""
    from agents.observability_agent.rag_inspector import debug_retrieve

    query = body.get("query", "")
    top_k = int(body.get("top_k", 10))
    doc_type = body.get("doc_type")

    if not query:
        from fastapi import HTTPException

        raise HTTPException(status_code=400, detail="query is required")

    try:
        return await debug_retrieve(query=query, top_k=top_k, doc_type=doc_type)
    except Exception as e:
        logger.exception("retrieve debug failed")
        from fastapi import HTTPException

        raise HTTPException(status_code=500, detail=f"Retrieve failed: {e}")


# ── Traces (Phase 3) ─────────────────────────────────────────────


@router.get("/traces")
async def traces(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    service: str | None = None,
    status: str | None = None,
    min_duration_ms: float | None = Query(None, description="Minimum span duration in ms"),
) -> dict[str, Any]:
    """List traces (Phase 3)."""
    from agents.observability_agent.trace_store import get_traces

    return get_traces(
        page=page,
        page_size=page_size,
        service=service,
        status=status,
        min_duration_ms=min_duration_ms,
    )


# NOTE: /traces/stats MUST be registered before /traces/{trace_id} so the
# static "stats" path is not captured by the dynamic {trace_id} parameter.
@router.get("/traces/stats")
async def trace_stats() -> dict[str, Any]:
    """Get trace statistics: P50/P95/P99 + error rate + hot paths (Phase 3)."""
    from agents.observability_agent.trace_store import get_span_types, get_trace_stats

    stats = get_trace_stats()
    stats["span_types"] = get_span_types()
    return stats


@router.get("/traces/{trace_id}")
async def trace_detail(trace_id: str) -> dict[str, Any]:
    """Get full span tree for a trace (Phase 3)."""
    from agents.observability_agent.trace_store import get_trace_tree

    tree = get_trace_tree(trace_id)
    if tree is None:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail=f"Trace not found: {trace_id}")
    return tree


# ── Alerting & Drift Detection (Phase 4) ────────────────────────


class AlertRuleRequest(BaseModel):
    """Request body for creating/updating an alert rule."""

    metric: str = Field(..., description="error_rate|p95_ms|daily_cost_usd|budget_exceeded")
    operator: str = Field("gt", description="gt|gte|lt|lte")
    threshold: float = Field(..., description="Trigger threshold")
    severity: str = Field("warning", description="info|warning|critical")
    enabled: bool = True
    description: str = ""


@router.get("/alerts")
async def alerts_endpoint(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    severity: str | None = None,
) -> dict[str, Any]:
    """List fired alerts (Phase 4)."""
    return get_alerts(page=page, page_size=page_size, severity=severity)


@router.post("/alerts/evaluate")
async def alerts_evaluate() -> dict[str, Any]:
    """Evaluate all alert rules against current metrics + compute drift (Phase 4)."""
    return evaluate_alerts()


@router.get("/alerts/rules")
async def alert_rules_get() -> list[dict[str, Any]]:
    """Get all alert rule definitions (Phase 4)."""
    return get_alert_rules()


@router.post("/alerts/rules")
async def alert_rules_set(req: AlertRuleRequest) -> dict[str, Any]:
    """Create or update an alert rule (Phase 4)."""
    rule_id = req.metric + "_" + req.operator
    return set_alert_rule(
        rule_id=rule_id,
        metric=req.metric,
        operator=req.operator,
        threshold=req.threshold,
        severity=req.severity,
        enabled=req.enabled,
        description=req.description,
    )


@router.delete("/alerts/rules/{rule_id}")
async def alert_rules_delete(rule_id: str) -> dict[str, Any]:
    """Delete an alert rule (Phase 4)."""
    deleted = delete_alert_rule(rule_id)
    if not deleted:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail=f"Alert rule not found: {rule_id}")
    return {"deleted": True, "rule_id": rule_id}


@router.get("/drift")
async def drift_endpoint() -> dict[str, Any]:
    """Get metric drift report (Phase 4)."""
    return get_drift_report()


# ── Audit (Phase 4) ──────────────────────────────────────────────


@router.get("/audit/logs")
async def audit_logs(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    actor: str | None = None,
    action: str | None = None,
    resource_type: str | None = None,
    status: str | None = None,
    since: str | None = None,
) -> dict[str, Any]:
    """List audit log entries (Phase 4) with optional filters."""
    return get_audit_logs(
        page=page,
        page_size=page_size,
        actor=actor,
        action=action,
        resource_type=resource_type,
        status=status,
        since=since,
    )


@router.get("/audit/export")
async def audit_export(
    format: str = Query("csv", description="Export format: csv"),
    actor: str | None = None,
    action: str | None = None,
    resource_type: str | None = None,
    status: str | None = None,
) -> Response:
    """Export audit log as CSV (Phase 4)."""
    from fastapi.responses import PlainTextResponse

    csv_text = export_audit_logs(
        format=format,
        actor=actor,
        action=action,
        resource_type=resource_type,
        status=status,
    )
    return PlainTextResponse(csv_text, media_type="text/csv")
