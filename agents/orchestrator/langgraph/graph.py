"""Orchestrator Graph — LangGraph StateGraph with Supervisor-Worker pattern.

Builds the complete multi-agent orchestration graph:
  START → Supervisor → Worker(s) → Supervisor → ... → END

The supervisor decides which worker to route to based on its plan.
Workers execute and return results. The supervisor then evaluates
and either routes to another worker or finishes.

M1-T6: LangGraph graph construction
"""

from __future__ import annotations

import logging
from typing import Any

from langgraph.graph import END, StateGraph
from langgraph.graph.state import CompiledStateGraph

from agents.orchestrator.langgraph.state import OrchestratorState
from agents.orchestrator.langgraph.supervisor import SupervisorNode
from agents.orchestrator.langgraph.workers import (
    AnalysisWorker,
    BaseWorker,
    DataWorker,
    GovernanceWorker,
    HRWorker,
    RAGWorker,
    RouterWorker,
)
from agents.orchestrator.tools.registry import ToolRegistry

logger = logging.getLogger("fde.orchestrator.graph")


# ══════════════════════════════════════════════════════════════════
# Graph Builder
# ══════════════════════════════════════════════════════════════════


def build_orchestrator_graph(
    tool_registry: ToolRegistry | None = None,
    llm: Any | None = None,
    max_iterations: int = 10,
) -> CompiledStateGraph:  # type: ignore[type-arg]
    """Build the complete Supervisor-Worker orchestration graph.

    Args:
        tool_registry: Tool registry for worker dispatch. Created if None.
        llm: LLM instance for supervisor planning. None uses mock heuristics.
        max_iterations: Safety limit for supervisor iterations.

    Returns:
        Compiled LangGraph graph ready for execution.
    """
    if tool_registry is None:
        tool_registry = ToolRegistry()

    # ── Create nodes ────────────────────────────────────────────────
    supervisor = SupervisorNode(
        tool_registry=tool_registry,
        llm=llm,
        max_iterations=max_iterations,
    )

    workers: dict[str, BaseWorker] = {
        "rag": RAGWorker(tool_registry),
        "hr": HRWorker(tool_registry),
        "data": DataWorker(tool_registry),
        "analysis": AnalysisWorker(tool_registry),
        "router": RouterWorker(tool_registry),
        "governance": GovernanceWorker(tool_registry),
    }

    # ── Build StateGraph ────────────────────────────────────────────
    graph = StateGraph(OrchestratorState)

    # Add supervisor node
    graph.add_node("supervisor", supervisor)

    # Add worker nodes
    for worker_name, worker in workers.items():
        graph.add_node(worker_name, worker)

    # ── Add edges ───────────────────────────────────────────────────
    # All workers return to supervisor after execution
    for worker_name in workers:
        graph.add_edge(worker_name, "supervisor")

    # Supervisor routes to workers or END based on plan
    def route_from_supervisor(state: OrchestratorState) -> str:
        """Determine which node the supervisor routes to.

        Returns:
            Worker name string or "__end__" to finish.
        """
        next_worker = state.next_worker

        if next_worker == "__end__" or next_worker == END:
            return END

        # Validate worker exists
        if next_worker in workers:
            return next_worker

        logger.warning("Supervisor routed to unknown worker '%s', ending", next_worker)
        return END

    # Conditional edge from supervisor to workers or END
    graph.add_conditional_edges(
        "supervisor",
        route_from_supervisor,
        {worker_name: worker_name for worker_name in workers} | {END: END},  # type: ignore[arg-type]
    )

    # ── Set entry point ────────────────────────────────────────────
    graph.set_entry_point("supervisor")

    logger.info(
        "Built orchestrator graph: supervisor + %d workers (%s)",
        len(workers),
        ", ".join(workers.keys()),
    )

    return graph.compile()


# ══════════════════════════════════════════════════════════════════
# Quick Start Helper
# ══════════════════════════════════════════════════════════════════


def create_default_graph() -> CompiledStateGraph:  # type: ignore[type-arg]
    """Create a default orchestrator graph with mock supervisor.

    Uses mock heuristics (no LLM) for development and testing.
    All workers are registered with their base implementations.
    """
    return build_orchestrator_graph()


def create_graph_with_llm(llm: Any) -> CompiledStateGraph:  # type: ignore[type-arg]
    """Create an orchestrator graph with a real LLM for the supervisor.

    Args:
        llm: LangChain-compatible LLM instance.

    Returns:
        Compiled graph with LLM-backed supervisor.
    """
    return build_orchestrator_graph(llm=llm)
