"""Tests for Worker Nodes."""

from __future__ import annotations

from langchain_core.messages import HumanMessage

from agents.orchestrator.langgraph.state import OrchestratorState, PlanStep, SupervisorPlan
from agents.orchestrator.langgraph.workers import (
    AnalysisWorker,
    BaseWorker,
    DataWorker,
    GovernanceWorker,
    HRWorker,
    RAGWorker,
    RouterWorker,
)
from agents.orchestrator.tools.registry import ToolDefinition, ToolRegistry

# ══════════════════════════════════════════════════════════════════
# Helper
# ══════════════════════════════════════════════════════════════════


def _make_registry_with_rag_tool() -> ToolRegistry:
    """Create a registry with a RAG search tool."""
    registry = ToolRegistry()

    def rag_search_handler(query: str = "") -> str:
        return f"Found results for: {query}"

    registry.register(
        ToolDefinition(
            name="rag_search",
            description="Search knowledge base",
            worker="rag",
            handler=rag_search_handler,
            parameters={"query": {"type": "string", "required": True}},
        )
    )
    return registry


def _make_state_with_rag_plan() -> OrchestratorState:
    """Create a state with a RAG plan."""
    plan = SupervisorPlan(
        steps=[
            PlanStep(
                worker="rag",
                task="Search for financial reports",
                tool="rag_search",
                tool_args={"query": "financial reports"},
            )
        ],
        reasoning="User needs financial data",
        requires_rag=True,
    )
    return OrchestratorState(
        messages=[HumanMessage(content="查找财务报告")],
        plan=plan,
        next_worker="rag",
    )


# ══════════════════════════════════════════════════════════════════
# BaseWorker Tests
# ══════════════════════════════════════════════════════════════════


class TestBaseWorker:
    """Tests for BaseWorker."""

    def test_worker_names(self) -> None:
        """All worker subclasses should have proper names."""
        registry = ToolRegistry()
        assert RAGWorker(registry).name == "rag"
        assert HRWorker(registry).name == "hr"
        assert DataWorker(registry).name == "data"
        assert AnalysisWorker(registry).name == "analysis"
        assert RouterWorker(registry).name == "router"
        assert GovernanceWorker(registry).name == "governance"

    def test_worker_without_plan(self) -> None:
        """Worker called without a plan should return warning."""
        registry = ToolRegistry()
        worker = RAGWorker(registry)

        state = OrchestratorState(messages=[HumanMessage(content="test")])
        result = worker(state)

        assert "rag" in result["worker_outputs"]
        assert result["messages"][0].content == "[rag] No task assigned"

    def test_worker_without_matching_step(self) -> None:
        """Worker called with plan but no step for it."""
        registry = ToolRegistry()
        worker = HRWorker(registry)

        plan = SupervisorPlan(
            steps=[PlanStep(worker="rag", task="Search")],
        )
        state = OrchestratorState(messages=[], plan=plan, next_worker="hr")

        result = worker(state)
        assert "hr" in result["worker_outputs"]

    def test_worker_with_tool_dispatch(self) -> None:
        """Worker should dispatch tools via registry."""
        registry = ToolRegistry()

        def handler(query: str = "") -> str:
            return f"Results: {query}"

        registry.register(
            ToolDefinition(
                name="test_tool",
                description="Test",
                worker="rag",
                handler=handler,
            )
        )

        worker = BaseWorker(tool_registry=registry)
        worker.name = "rag"

        plan = SupervisorPlan(
            steps=[
                PlanStep(worker="rag", task="Test", tool="test_tool", tool_args={"query": "hello"})
            ],
        )
        state = OrchestratorState(messages=[], plan=plan, next_worker="rag")

        result = worker(state)
        assert result["worker_outputs"]["rag"] == "Results: hello"

    def test_worker_error_handling(self) -> None:
        """Worker should handle tool execution errors gracefully."""
        registry = ToolRegistry()

        def failing_handler(**kwargs: object) -> str:
            raise RuntimeError("Tool crashed")

        registry.register(
            ToolDefinition(
                name="failing_tool",
                description="Fails",
                worker="rag",
                handler=failing_handler,
            )
        )

        worker = BaseWorker(tool_registry=registry)
        worker.name = "rag"

        plan = SupervisorPlan(
            steps=[PlanStep(worker="rag", task="Fail", tool="failing_tool")],
        )
        state = OrchestratorState(messages=[], plan=plan, next_worker="rag")

        result = worker(state)
        assert result["error"] is not None
        assert "Tool crashed" in result["error"]


# ══════════════════════════════════════════════════════════════════
# RAGWorker Tests
# ══════════════════════════════════════════════════════════════════


class TestRAGWorker:
    """Tests for RAGWorker."""

    def test_rag_search_with_tool(self) -> None:
        """RAG worker should execute rag_search tool."""
        registry = _make_registry_with_rag_tool()
        worker = RAGWorker(registry)

        state = _make_state_with_rag_plan()
        result = worker(state)

        assert "rag" in result["worker_outputs"]
        assert "Found results for" in result["worker_outputs"]["rag"]

    def test_rag_search_fallback_to_user_message(self) -> None:
        """RAG worker should use last user message if no query in tool_args."""
        registry = _make_registry_with_rag_tool()
        worker = RAGWorker(registry)

        plan = SupervisorPlan(
            steps=[PlanStep(worker="rag", task="Search", tool="rag_search")],
        )
        state = OrchestratorState(
            messages=[HumanMessage(content="什么是数字化转型？")],
            plan=plan,
            next_worker="rag",
        )

        result = worker(state)
        assert "rag" in result["worker_outputs"]

    def test_rag_search_no_tool_with_task(self) -> None:
        """RAG worker without specific tool should search with task description."""
        registry = _make_registry_with_rag_tool()
        worker = RAGWorker(registry)

        plan = SupervisorPlan(
            steps=[PlanStep(worker="rag", task="Find financial data")],
        )
        state = OrchestratorState(
            messages=[HumanMessage(content="查找财务数据")],
            plan=plan,
            next_worker="rag",
        )

        result = worker(state)
        # Should attempt to search with task as query
        assert "rag" in result["worker_outputs"]
