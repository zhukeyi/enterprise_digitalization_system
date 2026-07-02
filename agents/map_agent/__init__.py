"""MapAI — Spatial Analysis Engine (Module L).

Geographic entity marking, spatial correlation analysis, and region data.
Voice features suspended per user request.

Tools: map_spatial_query, map_correlate
Routes: /map/regions, /map/spatial-query, /map/context, /map/correlate,
        /map/analysis (M3-T10 full pipeline)
WebSocket: /map/ws/analysis/{session_id} (M3-T11 real-time push)
Async Tasks: run_analysis_async (M3-T11 background execution)
Foolproof: validate_analysis_request (M3-T11 pre-flight checks)
"""

from agents.map_agent.engine import SpatialCorrelationEngine, get_correlation_engine
from agents.map_agent.foolproof import (
    FoolproofResult,
    validate_analysis_request,
    validate_entity_ids,
    validate_voice_input,
)
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
from agents.map_agent.tasks import (
    TaskInfo,
    TaskStore,
    get_task_store,
    run_analysis_async,
    run_analysis_background,
)
from agents.map_agent.websocket import (
    ConnectionManager,
    get_manager,
    ws_router,
)
from agents.map_agent.worker import MapWorker, register_map_tools

__all__ = [
    "AnalysisContext",
    "AnalysisInterpreter",
    "AnalysisRequest",
    "AnalysisResult",
    "ConnectionManager",
    "CorrelationMethod",
    "CorrelationPair",
    "CorrelationPairResult",
    "CorrelationRequest",
    "CorrelationResponse",
    "FoolproofResult",
    "GeoEntity",
    "GeoPoint",
    "MapRegion",
    "MapWorker",
    "NodeState",
    "SpatialCorrelationEngine",
    "SpatialQueryRequest",
    "SpatialQueryResponse",
    "TaskInfo",
    "TaskStore",
    "compute_correlation",
    "fetch_entities",
    "generate_interpretation",
    "get_correlation_engine",
    "get_interpreter",
    "get_manager",
    "get_task_store",
    "map_router",
    "register_map_tools",
    "run_analysis_async",
    "run_analysis_background",
    "run_pipeline",
    "validate_analysis_request",
    "validate_entity_ids",
    "validate_voice_input",
    "ws_router",
]
