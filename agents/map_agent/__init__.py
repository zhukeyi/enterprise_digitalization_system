"""MapAI — Spatial Analysis Engine (Module L).

Geographic entity marking, spatial correlation analysis, and region data.
Voice features suspended per user request.

Tools: map_spatial_query, map_correlate
Routes: /map/regions, /map/spatial-query, /map/context, /map/correlate,
        /map/analysis (M3-T10 full pipeline)
"""

from agents.map_agent.engine import SpatialCorrelationEngine, get_correlation_engine
from agents.map_agent.interpreter import AnalysisInterpreter, get_interpreter
from agents.map_agent.langgraph_nodes import (
    NodeState,
    compute_correlation,
    fetch_entities,
    generate_interpretation,
    run_pipeline,
)
from agents.map_agent.models import (
    AnalysisContext,
    AnalysisRequest,
    AnalysisResult,
    CorrelationMethod,
    CorrelationPair,
    CorrelationPairResult,
    CorrelationRequest,
    CorrelationResponse,
    GeoEntity,
    GeoPoint,
    MapRegion,
    SpatialQueryRequest,
    SpatialQueryResponse,
)
from agents.map_agent.routes import router as map_router
from agents.map_agent.worker import MapWorker, register_map_tools

__all__ = [
    "AnalysisContext",
    "AnalysisInterpreter",
    "AnalysisRequest",
    "AnalysisResult",
    "CorrelationMethod",
    "CorrelationPair",
    "CorrelationPairResult",
    "CorrelationRequest",
    "CorrelationResponse",
    "GeoEntity",
    "GeoPoint",
    "MapRegion",
    "MapWorker",
    "NodeState",
    "SpatialCorrelationEngine",
    "SpatialQueryRequest",
    "SpatialQueryResponse",
    "compute_correlation",
    "fetch_entities",
    "generate_interpretation",
    "get_correlation_engine",
    "get_interpreter",
    "map_router",
    "register_map_tools",
    "run_pipeline",
]
