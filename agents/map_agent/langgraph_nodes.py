"""MapAI LangGraph Nodes — pipeline nodes for spatial analysis.

Three-node pipeline:
1. fetch_entities — retrieve entity data from demo/data sources
2. compute_correlation — run statistical correlation engine
3. generate_interpretation — produce AI natural language interpretation

Each node is a pure function that takes and returns a dict (node state),
making them easy to compose in LangGraph or call independently.

M3-T10-1/2/3: LangGraph nodes
"""

from __future__ import annotations

import logging
import time
from typing import Any

from agents.map_agent.demo_data import get_all_demo_regions
from agents.map_agent.engine import get_correlation_engine
from agents.map_agent.interpreter import get_interpreter
from agents.map_agent.models import (
    AnalysisContext,
    CorrelationMethod,
    CorrelationRequest,
    CorrelationResponse,
    GeoEntity,
    GeoPoint,
)

logger = logging.getLogger("fde.map.langgraph_nodes")


# ══════════════════════════════════════════════════════════════════
# Node State Type
# ══════════════════════════════════════════════════════════════════


class NodeState(dict[str, Any]):
    """Typed dict for pipeline node state.

    Keys:
        entity_ids: list[str] — IDs of entities to analyze
        method: str — correlation method
        query: str — user's natural language query
        entities: list[GeoEntity] — fetched entities (node 1 output)
        correlation: CorrelationResponse — correlation result (node 2 output)
        interpretation: str — AI interpretation (node 3 output)
        errors: list[str] — accumulated errors
        nodes_traced: list[str] — execution trace
        timing_ms: dict[str, int] — per-node timing
    """

    pass


# ══════════════════════════════════════════════════════════════════
# Node 1: Fetch Entities
# ══════════════════════════════════════════════════════════════════


def fetch_entities(state: NodeState) -> NodeState:
    """Node 1: Fetch entity data from demo data or use provided inline entities.

    If state contains 'provided_entities' (from frontend markers),
    uses those directly. Otherwise looks up entity_ids in demo data.
    """
    start = time.monotonic()
    entity_ids: list[str] = state.get("entity_ids", [])
    provided: list[dict[str, object]] = state.get("provided_entities", [])
    errors: list[str] = state.get("errors", [])
    nodes_traced: list[str] = state.get("nodes_traced", [])
    timing: dict[str, int] = state.get("timing_ms", {})

    nodes_traced.append("fetch_entities")

    # If frontend provided inline entity data, use it directly
    if provided:
        state["entities"] = [
            GeoEntity(
                entity_id=str(e.get("id", "")),
                name=str(e.get("name", "")),
                entity_type=str(e.get("type", "unknown")),
                location=GeoPoint(
                    lng=float(e.get("lng", 0)), lat=float(e.get("lat", 0)),
                ),
                properties=e.get("metadata", {}),
            )
            for e in provided
        ]
        timing["fetch_entities"] = int((time.monotonic() - start) * 1000)
        state["errors"] = errors
        state["nodes_traced"] = nodes_traced
        state["timing_ms"] = timing
        return state

    # Fallback: lookup from demo data
    all_entities: dict[str, GeoEntity] = {}
    for region in get_all_demo_regions():
        for e in region.entities:
            all_entities[e.entity_id] = e

    fetched: list[GeoEntity] = []
    for eid in entity_ids:
        if eid in all_entities:
            fetched.append(all_entities[eid])
        else:
            msg = f"Entity '{eid}' not found in demo data"
            logger.warning(msg)
            errors.append(msg)

    logger.info("Fetched %d/%d entities", len(fetched), len(entity_ids))

    state["entities"] = fetched
    state["errors"] = errors
    state["nodes_traced"] = nodes_traced
    timing["fetch_entities"] = int((time.monotonic() - start) * 1000)
    state["timing_ms"] = timing
    return state


# ══════════════════════════════════════════════════════════════════
# Node 2: Compute Correlation
# ══════════════════════════════════════════════════════════════════


def compute_correlation(state: NodeState) -> NodeState:
    """Node 2: Run spatial correlation analysis on fetched entities.

    Uses the SpatialCorrelationEngine to compute pairwise correlations
    between entity properties. Requires at least 2 entities.
    """
    start = time.monotonic()
    entities: list[GeoEntity] = state.get("entities", [])
    method_str: str = state.get("method", "pearson")
    errors: list[str] = state.get("errors", [])
    nodes_traced: list[str] = state.get("nodes_traced", [])
    timing: dict[str, int] = state.get("timing_ms", {})

    nodes_traced.append("compute_correlation")

    if len(entities) < 2:
        errors.append(f"Need at least 2 entities for correlation, got {len(entities)}")
        state["correlation"] = None
        state["errors"] = errors
        state["nodes_traced"] = nodes_traced
        timing["compute_correlation"] = int((time.monotonic() - start) * 1000)
        state["timing_ms"] = timing
        return state

    # Map method string to enum
    try:
        method = CorrelationMethod(method_str)
    except ValueError:
        method = CorrelationMethod.PEARSON
        logger.warning("Unknown method '%s', defaulting to pearson", method_str)

    # Build request
    session_id = f"pipeline-{int(start * 1000)}"
    ctx = AnalysisContext(session_id=session_id, entities=entities)
    request = CorrelationRequest(context=ctx, method=method)

    # Compute
    engine = get_correlation_engine()
    response = engine.compute(request)

    logger.info(
        "Correlation computed: %d entities, %d pairs in %dms",
        response.entity_count,
        response.pair_count,
        response.execution_time_ms,
    )

    state["correlation"] = response
    state["errors"] = errors
    state["nodes_traced"] = nodes_traced
    timing["compute_correlation"] = int((time.monotonic() - start) * 1000)
    state["timing_ms"] = timing
    return state


# ══════════════════════════════════════════════════════════════════
# Node 3: Generate Interpretation
# ══════════════════════════════════════════════════════════════════


def generate_interpretation(state: NodeState) -> NodeState:
    """Node 3: Generate AI interpretation of correlation results.

    Uses rule-based templates by default. Falls back gracefully
    if correlation data is missing.
    """
    start = time.monotonic()
    correlation: CorrelationResponse | None = state.get("correlation")
    entities: list[GeoEntity] = state.get("entities", [])
    query: str = state.get("query", "")
    errors: list[str] = state.get("errors", [])
    nodes_traced: list[str] = state.get("nodes_traced", [])
    timing: dict[str, int] = state.get("timing_ms", {})

    nodes_traced.append("generate_interpretation")

    interpreter = get_interpreter()

    if correlation is None:
        if errors:
            interpretation = "分析未能完成: " + "; ".join(errors[-3:])
        else:
            interpretation = "无相关性数据可用于生成解读."
    else:
        interpretation = interpreter.interpret(correlation, entities, query)

    logger.info("Interpretation generated: %d chars", len(interpretation))

    state["interpretation"] = interpretation
    state["errors"] = errors
    state["nodes_traced"] = nodes_traced
    timing["generate_interpretation"] = int((time.monotonic() - start) * 1000)
    state["timing_ms"] = timing
    return state


# ══════════════════════════════════════════════════════════════════
# Pipeline (sequential execution of all 3 nodes)
# ══════════════════════════════════════════════════════════════════

_PIPELINE_NODES = [
    ("fetch_entities", fetch_entities),
    ("compute_correlation", compute_correlation),
    ("generate_interpretation", generate_interpretation),
]


def run_pipeline(
    entity_ids: list[str],
    method: str = "pearson",
    query: str = "",
    provided_entities: list[dict[str, object]] | None = None,
) -> NodeState:
    """Run the full 3-node analysis pipeline.

    Args:
        entity_ids: List of entity IDs.
        method: Correlation method.
        query: Optional NL query.
        provided_entities: Inline entity data from frontend (skips demo lookup).

    Returns:
        Final node state with all outputs populated.
    """
    state = NodeState(
        entity_ids=entity_ids,
        method=method,
        query=query,
        errors=[],
        nodes_traced=[],
        timing_ms={},
    )
    if provided_entities:
        state["provided_entities"] = provided_entities

    for name, node_fn in _PIPELINE_NODES:
        state = node_fn(state)

    return state


__all__ = [
    "NodeState",
    "compute_correlation",
    "fetch_entities",
    "generate_interpretation",
    "run_pipeline",
]
