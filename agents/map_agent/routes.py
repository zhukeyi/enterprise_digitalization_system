"""MapAI FastAPI routes — spatial analysis endpoints (Module L).

Provides REST APIs for geographic entity querying, correlation analysis,
and region data. Voice features suspended per user request.
"""

from __future__ import annotations

import logging
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
