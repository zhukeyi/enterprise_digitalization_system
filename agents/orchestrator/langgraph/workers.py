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

import asyncio
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
            # execute() may return a coroutine if it calls async dispatch
            result = self.execute(step, state)
            if isinstance(result, dict) and "worker_outputs" in result:
                return result

            logger.info("Worker '%s' completed successfully", self.name)

            return {
                "worker_outputs": {self.name: result},
                "messages": [AIMessage(content=f"[{self.name}] Result: {str(result)[:500]}")],
                "error": None,
            }

        except (
            RuntimeError,
            ValueError,
            TypeError,
            KeyError,
            AttributeError,
            ConnectionError,
            OSError,
        ) as e:
            logger.error("Worker '%s' failed: %s", self.name, e)
            return {
                "worker_outputs": {self.name: f"Error: {e}"},
                "messages": [AIMessage(content=f"[{self.name}] Error: {e}")],
                "error": str(e),
            }

    def _run_dispatch(self, tool_name: str, **kwargs: Any) -> Any:
        """Dispatch a tool, running async handlers synchronously.

        ToolRegistry.dispatch() is async; this wraps it for sync callers.
        """

        coro = self.tool_registry.dispatch(tool_name, **kwargs)
        return asyncio.run(coro)

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
            return self._run_dispatch(step.tool, **step.tool_args)

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
                        # content can be str | list[str | dict], coerce to str
                        content = msg.content
                        query = content if isinstance(content, str) else str(content)
                        break

            return self._run_dispatch("rag_search", query=query)

        if step.tool == "rag_ingest":
            return self._run_dispatch("rag_ingest", **step.tool_args)

        # Default: search with task description as query
        if step.tool is None and step.task:
            query = step.task
            try:
                return self._run_dispatch("rag_search", query=query)
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


# ══════════════════════════════════════════════════════════════════
# M2-T5: New Sub-Agent Workers
# ══════════════════════════════════════════════════════════════════


class ComplianceWorker(BaseWorker):
    """Compliance auditor worker.

    Handles compliance-related tasks:
    - Audit log querying and filtering
    - Compliance report generation
    - Risk assessment and validation
    - Regulatory policy checks

    M2-T5: Added as part of the sub-agent worker expansion.
    """

    name = "compliance"
    description = "Compliance auditing — audit logs, risk checks, regulatory validation"


class BusinessSystemWorker(BaseWorker):
    """Business system integration worker.

    Handles enterprise system integration tasks:
    - CRM/ERP data queries
    - Business workflow status checks
    - System health monitoring
    - Data synchronization operations

    M2-T5: Added as part of the sub-agent worker expansion.
    """

    name = "business_system"
    description = "Business system integration — CRM, ERP, workflow, data sync"


class IMWorker(BaseWorker):
    """Message hub worker for cross-platform IM operations.

    Handles messaging tasks:
    - Send messages to users/groups on WeCom/Feishu/DingTalk
    - Broadcast announcements to multiple targets/platforms
    - Query and sync cross-platform session context

    M2-T3: Added as part of the IM message hub.
    """

    name = "im"
    description = "Message hub — send, broadcast, session sync (WeCom/Feishu/DingTalk)"


class MapWorker(BaseWorker):
    """Spatial analysis worker for geographic intelligence.

    Handles map-related tasks:
    - Spatial query within geographic bounding boxes
    - Cross-entity correlation analysis
    - Region data and entity management

    Module L: MapAI spatial analysis engine.
    """

    name = "map"
    description = "Spatial analysis — geographic query, correlation, region data"
