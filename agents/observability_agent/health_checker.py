"""Health checker — probes platform components for readiness.

Checks: Qdrant, Postgres/SQLite, Dify, Embedding Model.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time

from agents.observability_agent.models import ComponentStatus, HealthCheckResult

logger = logging.getLogger("fde.observability.health")


async def _check_qdrant() -> ComponentStatus:
    """Probe Qdrant vector store connectivity."""
    start = time.monotonic()
    try:
        from agents.ingestion_agent.store import get_vector_store

        vs = get_vector_store()
        info = await vs.get_collection_info()
        latency = (time.monotonic() - start) * 1000
        return ComponentStatus(
            name="qdrant",
            type="vector_db",
            status="healthy",
            latency_ms=round(latency, 1),
            details={
                "collection": os.getenv("QDRANT_COLLECTION", "fde_documents"),
                "points_count": getattr(info, "points_count", 0),
            },
        )
    except Exception as e:
        latency = (time.monotonic() - start) * 1000
        return ComponentStatus(
            name="qdrant",
            type="vector_db",
            status="unhealthy",
            latency_ms=round(latency, 1),
            details={"error": str(e)[:200]},
        )


async def _check_database() -> ComponentStatus:
    """Probe Postgres/SQLite connectivity."""
    start = time.monotonic()
    try:
        from sqlalchemy import text

        from agents.governance_agent.database.session import get_engine

        engine = get_engine()
        if engine.is_async:
            async with engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
        else:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
        latency = (time.monotonic() - start) * 1000
        db_type = "sqlite" if "sqlite" in str(engine.url) else "postgres"
        return ComponentStatus(
            name="database",
            type=db_type,
            status="healthy",
            latency_ms=round(latency, 1),
            details={"url_scheme": str(engine.url).split("://")[0]},
        )
    except Exception as e:
        latency = (time.monotonic() - start) * 1000
        return ComponentStatus(
            name="database",
            type="unknown",
            status="unhealthy",
            latency_ms=round(latency, 1),
            details={"error": str(e)[:200]},
        )


async def _check_dify() -> ComponentStatus:
    """Probe Dify connectivity (best-effort, non-blocking)."""
    start = time.monotonic()
    dify_url = os.getenv("DIFY_API_URL", "")
    if not dify_url:
        return ComponentStatus(
            name="dify",
            type="llm_platform",
            status="unknown",
            details={"reason": "DIFY_API_URL not set"},
        )
    try:
        import urllib.request

        req = urllib.request.Request(f"{dify_url.rstrip('/')}/health", method="GET")
        urllib.request.urlopen(req, timeout=3)
        latency = (time.monotonic() - start) * 1000
        return ComponentStatus(
            name="dify",
            type="llm_platform",
            status="healthy",
            latency_ms=round(latency, 1),
            details={"url": dify_url},
        )
    except Exception:
        latency = (time.monotonic() - start) * 1000
        return ComponentStatus(
            name="dify",
            type="llm_platform",
            status="degraded",
            latency_ms=round(latency, 1),
            details={"url": dify_url, "note": "non-critical, may be behind firewall"},
        )


async def _check_embedding() -> ComponentStatus:
    """Probe embedding model availability."""
    start = time.monotonic()
    try:
        from agents.ingestion_agent.store import get_embedding_model

        model = get_embedding_model()
        dim = model.get_dimension()
        backend = os.getenv("FDE_EMBEDDING_BACKEND", "pytorch")
        model_name = os.getenv("FDE_RAG_EMBEDDING_MODEL", "BAAI/bge-m3")
        latency = (time.monotonic() - start) * 1000
        return ComponentStatus(
            name="embedding",
            type="ml_model",
            status="healthy",
            latency_ms=round(latency, 1),
            details={
                "model": model_name,
                "dimension": dim,
                "backend": backend,
            },
        )
    except Exception as e:
        latency = (time.monotonic() - start) * 1000
        return ComponentStatus(
            name="embedding",
            type="ml_model",
            status="unhealthy",
            latency_ms=round(latency, 1),
            details={"error": str(e)[:200]},
        )


async def check_all_components() -> HealthCheckResult:
    """Run all component checks in parallel and aggregate results."""
    tasks = [_check_qdrant(), _check_database(), _check_dify(), _check_embedding()]
    components: list[ComponentStatus] = await asyncio.gather(*tasks)

    unhealthy = sum(1 for c in components if c.status == "unhealthy")
    degraded = sum(1 for c in components if c.status == "degraded")

    if unhealthy > 0:
        overall = "unhealthy"
    elif degraded > 0:
        overall = "degraded"
    else:
        overall = "healthy"

    return HealthCheckResult(status=overall, components=components)


def check_liveness(error_rate: float = 0.0) -> bool:
    """Quick liveness check — process is alive and not in error storm."""
    return error_rate < 0.5  # 50% error rate threshold
