"""MapAI Worker — LangGraph node for spatial analysis (Module L).

Registered as 'map' worker in the orchestrator graph.
Handles map/spatial analysis tasks dispatched by the supervisor.
"""

from __future__ import annotations

import logging
from typing import Any

from agents.orchestrator.langgraph.workers import BaseWorker
from agents.orchestrator.tools.registry import ToolDefinition, ToolRegistry

logger = logging.getLogger("fde.map.worker")


class MapWorker(BaseWorker):
    """Spatial analysis worker for geographic intelligence.

    Handles map-related tasks:
    - Spatial query: find entities within geographic bounds
    - Correlation analysis: cross-entity statistical correlation
    - Region data: load predefined demo regions
    """

    name = "map"
    description = "Spatial analysis — geographic query, correlation, region data"


def register_map_tools(registry: ToolRegistry) -> None:
    """Register MapAI tools with the orchestrator ToolRegistry.

    Args:
        registry: The orchestrator's ToolRegistry instance.
    """
    from agents.map_agent.demo_data import get_entities_in_bounds

    def _spatial_query_handler(
        west: float = 116.0,
        south: float = 39.5,
        east: float = 117.0,
        north: float = 40.5,
    ) -> dict[str, Any]:
        """Query entities in a bounding box."""
        entities = get_entities_in_bounds(west, south, east, north)
        return {
            "bounds": [west, south, east, north],
            "total": len(entities),
            "entities": [
                {
                    "id": e.entity_id,
                    "name": e.name,
                    "lng": e.location.lng,
                    "lat": e.location.lat,
                    "type": e.entity_type,
                }
                for e in entities
            ],
        }

    def _correlate_handler(
        entity_ids: list[str],
        property_name: str = "population",
    ) -> dict[str, Any]:
        """Run correlation analysis on specified entities."""
        engine = __import__("agents.map_agent.engine", fromlist=["get_correlation_engine"])
        corr_engine = engine.get_correlation_engine()

        from agents.map_agent.demo_data import get_all_demo_regions
        from agents.map_agent.models import AnalysisContext, CorrelationRequest

        all_entities = []
        for region in get_all_demo_regions():
            all_entities.extend(region.entities)

        selected = [e for e in all_entities if e.entity_id in entity_ids]

        if len(selected) < 2:
            return {"error": "Need at least 2 entities", "entity_count": len(selected)}

        ctx = AnalysisContext(session_id="map_tool", entities=selected)
        request = CorrelationRequest(context=ctx)
        response = corr_engine.compute(request)

        return {
            "entity_count": response.entity_count,
            "pair_count": response.pair_count,
            "results": [
                f"{r.entity_a} ↔ {r.entity_b}: r={r.coefficient} ({r.strength})"
                for r in response.results
            ],
            "summary": response.summary,
        }

    registry.register(
        ToolDefinition(
            name="map_spatial_query",
            description="Query geographic entities within a bounding box (west, south, east, north)",
            worker="map",
            handler=_spatial_query_handler,
            parameters={
                "west": {"type": "number", "required": False, "default": 116.0},
                "south": {"type": "number", "required": False, "default": 39.5},
                "east": {"type": "number", "required": False, "default": 117.0},
                "north": {"type": "number", "required": False, "default": 40.5},
            },
            category="map",
        )
    )

    registry.register(
        ToolDefinition(
            name="map_correlate",
            description="Run spatial correlation analysis between selected geographic entities",
            worker="map",
            handler=_correlate_handler,
            parameters={
                "entity_ids": {
                    "type": "array",
                    "required": True,
                    "description": "List of entity IDs to analyze",
                },
                "property_name": {
                    "type": "string",
                    "required": False,
                    "default": "population",
                },
            },
            category="map",
        )
    )

    logger.info(
        "Registered %d MapAI tools",
        len(registry.get_tools_for_worker("map")),
    )
