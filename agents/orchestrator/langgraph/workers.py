"""Worker Nodes — domain-specific agent nodes for LangGraph.

Each worker is a LangGraph node that:
1. Receives task instructions from the supervisor
2. Executes the appropriate tool(s)
3. Returns results back to the supervisor for evaluation

Workers are deterministic — they execute backend code, not LLM calls.
This ensures reliability and observability.

M1-T6: Worker node base + RAG worker
"""

from __future__ import annotations

import logging
from typing import Any

from langchain_core.messages import AIMessage

from agents.orchestrator.langgraph.state import OrchestratorState
from agents.orchestrator.tools.registry import ToolRegistry

logger = logging.getLogger("fde.orchestrator.workers")


# ══════════════════════════════════════════════════════════════════
# Base Worker
# ══════════════════════════════════════════════════════════════════


class BaseWorker:
    """Abstract base for worker nodes.

    Each worker must implement the execute() method which:
    - Reads the current plan step from state
    - Dispatches to the appropriate tool
    - Returns structured results
    """

    name: str = ""
    description: str = ""

    def __init__(self, tool_registry: ToolRegistry) -> None:
        self.tool_registry = tool_registry

    def __call__(self, state: OrchestratorState) -> dict[str, Any]:
        """Execute the worker node.

        Args:
            state: Current orchestrator state with plan and task info.

        Returns:
            State updates (worker_outputs, messages, etc.)
        """
        if state.plan is None or not state.plan.steps:
            logger.warning("Worker '%s' called without a plan", self.name)
            return {
                "worker_outputs": {self.name: "No plan available"},
                "messages": [AIMessage(content=f"[{self.name}] No task assigned")],
            }

        # Get the first step targeting this worker
        step = None
        for s in state.plan.steps:
            if s.worker == self.name:
                step = s
                break

        if step is None:
            logger.warning("Worker '%s' called but no step assigned", self.name)
            return {
                "worker_outputs": {self.name: "No step assigned to this worker"},
                "messages": [AIMessage(content=f"[{self.name}] No step assigned")],
            }

        logger.info("Worker '%s' executing: task=%s tool=%s", self.name, step.task, step.tool)

        try:
            result = self.execute(step, state)
            logger.info("Worker '%s' completed successfully", self.name)

            return {
                "worker_outputs": {self.name: result},
                "messages": [AIMessage(content=f"[{self.name}] Result: {str(result)[:500]}")],
                "error": None,
            }

        except Exception as e:
            logger.error("Worker '%s' failed: %s", self.name, e)
            return {
                "worker_outputs": {self.name: f"Error: {e}"},
                "messages": [AIMessage(content=f"[{self.name}] Error: {e}")],
                "error": str(e),
            }

    def execute(self, step: Any, state: OrchestratorState) -> Any:
        """Execute the worker's task. Must be overridden by subclasses.

        Args:
            step: PlanStep with task details.
            state: Current state for context.

        Returns:
            Task execution result.
        """
        # Default: try to dispatch via tool registry
        if step.tool:
            return self.tool_registry.dispatch(step.tool, **step.tool_args)

        # No specific tool — return task description as acknowledgment
        return f"Worker '{self.name}' acknowledged task: {step.task}"


# ══════════════════════════════════════════════════════════════════
# RAG Worker
# ══════════════════════════════════════════════════════════════════


class RAGWorker(BaseWorker):
    """RAG (Retrieval-Augmented Generation) worker.

    Handles knowledge retrieval tasks:
    - Search enterprise documents
    - Answer questions with citations
    - Ingest new documents into the vector store
    """

    name = "rag"
    description = (
        "Knowledge retrieval — search enterprise documents, answer questions with citations"
    )

    def execute(self, step: Any, state: OrchestratorState) -> Any:
        """Execute RAG task.

        Supported tools:
        - rag_search: Hybrid search (BM25 + vector + RRF)
        - rag_ingest: Ingest documents into vector store
        - rag_answer: Generate answer from retrieved context
        """
        if step.tool == "rag_search":
            query = step.tool_args.get("query", "")
            if not query:
                # Fall back to last user message
                from langchain_core.messages import HumanMessage

                for msg in reversed(state.messages):
                    if isinstance(msg, HumanMessage):
                        query = msg.content
                        break

            return self.tool_registry.dispatch("rag_search", query=query)

        if step.tool == "rag_ingest":
            return self.tool_registry.dispatch("rag_ingest", **step.tool_args)

        # Default: search with task description as query
        if step.tool is None and step.task:
            query = step.task
            try:
                return self.tool_registry.dispatch("rag_search", query=query)
            except KeyError:
                return f"RAG worker acknowledged: {step.task}"

        return super().execute(step, state)


# ══════════════════════════════════════════════════════════════════
# HR Worker
# ══════════════════════════════════════════════════════════════════


class HRWorker(BaseWorker):
    """HR analysis worker.

    Handles HR-related tasks:
    - Employee profiling
    - Risk assessment
    - Layoff simulation (with foolproof checks)
    """

    name = "hr"
    description = "HR analysis — employee profiling, risk assessment, layoff simulation"


# ══════════════════════════════════════════════════════════════════
# Data Worker
# ══════════════════════════════════════════════════════════════════


class DataWorker(BaseWorker):
    """Data pipeline worker.

    Handles data collection tasks:
    - Web scraping
    - RSS feed processing
    - Data quality validation
    """

    name = "data"
    description = "Data pipeline — web scraping, data collection, RSS feeds"


# ══════════════════════════════════════════════════════════════════
# Analysis Worker
# ══════════════════════════════════════════════════════════════════


class AnalysisWorker(BaseWorker):
    """Data analysis worker.

    Handles analytical tasks:
    - NL2SQL conversion
    - Statistical analysis
    - Interactive chart generation
    """

    name = "analysis"
    description = "Data analysis — NL2SQL, interactive charts, statistical reports"


# ══════════════════════════════════════════════════════════════════
# Router Worker
# ══════════════════════════════════════════════════════════════════


class RouterWorker(BaseWorker):
    """Model gateway worker.

    Handles LLM routing tasks:
    - Route to appropriate LLM provider
    - Fallback chain execution
    - Model selection
    """

    name = "router"
    description = "Model gateway — route to different LLM providers, fallback chain"


# ══════════════════════════════════════════════════════════════════
# Governance Worker
# ══════════════════════════════════════════════════════════════════


class GovernanceWorker(BaseWorker):
    """Access control worker.

    Handles governance tasks:
    - User management
    - RBAC enforcement
    - Audit logging
    """

    name = "governance"
    description = "Access control — user management, RBAC, audit logging"
