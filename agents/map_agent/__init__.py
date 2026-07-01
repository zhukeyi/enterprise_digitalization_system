"""MapAI — Spatial Analysis Engine (Module L).

Geographic entity marking, spatial correlation analysis, and region data.
Voice features suspended per user request.

Tools: map_spatial_query, map_correlate
Routes: /map/regions, /map/spatial-query, /map/context, /map/correlate
"""

from agents.map_agent.routes import router as map_router
from agents.map_agent.worker import MapWorker, register_map_tools

__all__ = ["MapWorker", "map_router", "register_map_tools"]
