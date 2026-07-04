"""MapAI FastAPI routes — spatial analysis endpoints (Module L).

Provides REST APIs for geographic entity querying, correlation analysis,
and region data. Voice features suspended per user request.
"""

from __future__ import annotations

import logging
import time
import uuid

from fastapi import APIRouter, HTTPException, Query

from agents.map_agent.demo_data import (
    get_all_demo_regions,
    get_demo_region,
    get_entities_in_bounds,
)
from agents.map_agent.engine import get_correlation_engine
from agents.map_agent.models import (
    AnalysisContext,
    AnalysisRequest,
    AnalysisResult,
    CorrelationRequest,
    CorrelationResponse,
    GeoEntity,
    MapRegion,
    SpatialQueryRequest,
    SpatialQueryResponse,
)

logger = logging.getLogger("fde.map.router")

router = APIRouter(prefix="/map", tags=["map"])

# Module-level analysis context (one per session)
_sessions: dict[str, AnalysisContext] = {}


def _get_or_create_session(session_id: str | None = None) -> AnalysisContext:
    """Get existing or create new analysis session."""
    sid = session_id or str(uuid.uuid4())
    if sid not in _sessions:
        _sessions[sid] = AnalysisContext(session_id=sid)
    return _sessions[sid]


# ══════════════════════════════════════════════════════════════════
# Region & Entity Endpoints
# ══════════════════════════════════════════════════════════════════


@router.get("/regions", response_model=list[MapRegion])
async def list_regions() -> list[MapRegion]:
    """List all available demo regions with their entities."""
    return get_all_demo_regions()


@router.get("/regions/{region_id}", response_model=MapRegion)
async def get_region(region_id: str) -> MapRegion:
    """Get a specific region by ID."""
    region = get_demo_region(region_id)
    if region is None:
        raise HTTPException(404, f"Region '{region_id}' not found")
    return region


@router.post("/spatial-query", response_model=SpatialQueryResponse)
async def spatial_query(body: SpatialQueryRequest) -> SpatialQueryResponse:
    """Query entities within a geographic bounding box."""
    entities = get_entities_in_bounds(
        west=body.bounds[0],
        south=body.bounds[1],
        east=body.bounds[2],
        north=body.bounds[3],
        entity_types=body.entity_types or None,
    )
    return SpatialQueryResponse(
        bounds=body.bounds,
        total=len(entities),
        entities=entities[: body.limit],
    )


# ══════════════════════════════════════════════════════════════════
# Analysis Context Endpoints
# ══════════════════════════════════════════════════════════════════


@router.get("/context", response_model=AnalysisContext)
async def get_context(
    session_id: str = Query(default="", description="Session ID"),
) -> AnalysisContext:
    """Get or create the analysis context (收纳盒)."""
    return _get_or_create_session(session_id if session_id else None)


@router.post("/context/entities", response_model=AnalysisContext)
async def add_entity_to_context(
    entity: GeoEntity,
    session_id: str = Query(default="", description="Session ID"),
) -> AnalysisContext:
    """Add an entity to the analysis context."""
    ctx = _get_or_create_session(session_id if session_id else None)
    ctx.add_entity(entity)
    return ctx


@router.delete("/context/entities/{entity_id}", response_model=AnalysisContext)
async def remove_entity_from_context(
    entity_id: str,
    session_id: str = Query(default="", description="Session ID"),
) -> AnalysisContext:
    """Remove an entity from the analysis context."""
    ctx = _get_or_create_session(session_id if session_id else None)
    removed = ctx.remove_entity(entity_id)
    if not removed:
        raise HTTPException(404, f"Entity '{entity_id}' not in context")
    return ctx


@router.delete("/context", response_model=dict)
async def clear_context(
    session_id: str = Query(default="", description="Session ID"),
) -> dict:
    """Clear the entire analysis context."""
    sid = session_id or str(uuid.uuid4())
    _sessions[sid] = AnalysisContext(session_id=sid)
    return {"status": "cleared", "session_id": sid}


# ══════════════════════════════════════════════════════════════════
# Correlation Analysis Endpoint
# ══════════════════════════════════════════════════════════════════


@router.post("/correlate", response_model=CorrelationResponse)
async def correlate(body: CorrelationRequest) -> CorrelationResponse:
    """Run spatial correlation analysis on marked entities.

    This is the core analysis endpoint. Accepts an AnalysisContext
    with marked entities and runs statistical correlation.

    Safety: minimum 2 entities required.
    """
    if body.context.entity_count < 2:
        raise HTTPException(
            400,
            f"需要至少 2 个实体才能进行相关性分析（当前: {body.context.entity_count}）。",
        )

    engine = get_correlation_engine()
    response = engine.compute(body)

    logger.info(
        "Correlation: %d entities, %d pairs, %dms",
        response.entity_count,
        response.pair_count,
        response.execution_time_ms,
    )

    return response


# ══════════════════════════════════════════════════════════════════
# Full Analysis Pipeline Endpoint (M3-T10)
# ══════════════════════════════════════════════════════════════════


@router.post("/analysis", response_model=AnalysisResult)
async def run_analysis(body: AnalysisRequest) -> AnalysisResult:
    """Run the full spatial analysis pipeline (3 LangGraph nodes).

    Pipeline: fetch_entities -> compute_correlation -> generate_interpretation

    Accepts a list of entity IDs and returns correlation results
    with AI-generated interpretation text.

    Safety: minimum 2 entity IDs required.
    """
    if len(body.entity_ids) < 2:
        raise HTTPException(
            400,
            f"需要至少 2 个实体 ID 才能进行相关性分析 (当前: {len(body.entity_ids)}).",
        )

    from agents.map_agent.langgraph_nodes import run_pipeline

    start = time.monotonic()
    logger.info("Analysis: %d entity_ids, %d inline entities, method=%s",
                len(body.entity_ids), len(body.entities), body.method)
    state = run_pipeline(
        entity_ids=body.entity_ids,
        method=body.method,
        query=body.query,
        provided_entities=body.entities if body.entities else None,
    )
    total_ms = int((time.monotonic() - start) * 1000)

    correlation = state.get("correlation")
    entities = state.get("entities", [])

    logger.info(
        "Analysis pipeline complete: %d entities, %d pairs, %dms total",
        len(entities),
        correlation.pair_count if correlation else 0,
        total_ms,
    )

    return AnalysisResult(
        entity_ids=body.entity_ids,
        entities=entities,
        correlation=correlation,
        interpretation=state.get("interpretation", ""),
        execution_time_ms=total_ms,
        nodes_traced=state.get("nodes_traced", []),
        errors=state.get("errors", []),
    )


# ══════════════════════════════════════════════════════════════════
# Async Analysis Endpoint (M3-T11)
# ══════════════════════════════════════════════════════════════════


@router.post("/analysis/async")
async def start_async_analysis(
    body: AnalysisRequest,
    session_id: str = Query(default="", description="WebSocket session ID"),
) -> dict:
    """Start an async analysis task with WebSocket progress push.

    The task runs in the background and pushes progress updates
    to the WebSocket connection identified by session_id.

    Returns the task_id for polling status via GET /map/tasks/{task_id}.
    """
    from agents.map_agent.foolproof import validate_analysis_request

    # Pre-flight validation
    validation = validate_analysis_request(body.entity_ids)
    if not validation.ok:
        raise HTTPException(400, validation.message)

    sid = session_id if session_id else str(uuid.uuid4())

    # We can't inject BackgroundTasks into a non-dependency route easily,
    # so use the asyncio task approach
    from agents.map_agent.tasks import run_analysis_background

    task_id = await run_analysis_background(body, session_id=sid)

    return {
        "task_id": task_id,
        "session_id": sid,
        "status": "started",
        "entity_count": len(body.entity_ids),
    }


@router.get("/tasks/{task_id}")
async def get_task_status(task_id: str) -> dict:
    """Get the status of an async analysis task."""
    from agents.map_agent.tasks import get_task_store

    store = get_task_store()
    info = store.get(task_id)
    if info is None:
        raise HTTPException(404, f"Task '{task_id}' not found")

    result_data = None
    if info.result is not None:
        result_data = info.result.model_dump()

    return {
        "task_id": info.task_id,
        "status": info.status,
        "progress": info.progress,
        "entity_ids": info.entity_ids,
        "result": result_data,
        "error": info.error,
        "created_at": info.created_at,
        "completed_at": info.completed_at,
    }


# ══════════════════════════════════════════════════════════════════
# Health
# ══════════════════════════════════════════════════════════════════


@router.get("/health")
async def map_health() -> dict:
    """MapAI service health check."""
    regions = len(get_all_demo_regions())
    entities = sum(len(r.entities) for r in get_all_demo_regions())
    return {
        "status": "ok",
        "regions": regions,
        "demo_entities": entities,
        "active_sessions": len(_sessions),
    }
