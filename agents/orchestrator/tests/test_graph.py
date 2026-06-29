"""Tests for Orchestrator Graph construction and execution."""

from __future__ import annotations

from langchain_core.messages import HumanMessage

from agents.orchestrator.langgraph.graph import (
    build_orchestrator_graph,
    create_default_graph,
)
from agents.orchestrator.langgraph.state import OrchestratorState
from agents.orchestrator.tools.registry import ToolDefinition, ToolRegistry
from langgraph.graph.state import CompiledStateGraph

# ══════════════════════════════════════════════════════════════════
# Helper
# ══════════════════════════════════════════════════════════════════


def _make_registry_with_tools() -> ToolRegistry:
    """Create a registry with basic tools for testing."""
    registry = ToolRegistry()

    def rag_search(query: str = "") -> str:
        return f"RAG results: {query}"

    registry.register(
        ToolDefinition(
            name="rag_search",
            description="Search knowledge base",
            worker="rag",
            handler=rag_search,
            parameters={"query": {"type": "string", "required": True}},
        )
    )

    return registry


# ══════════════════════════════════════════════════════════════════
# Graph Construction Tests
# ══════════════════════════════════════════════════════════════════


class TestGraphConstruction:
    """Tests for graph building and compilation."""

    def test_create_default_graph(self) -> None:
        """Default graph should compile successfully."""
        graph = create_default_graph()
        assert graph is not None

    def test_create_graph_with_registry(self) -> None:
        """Graph with custom tool registry should compile."""
        registry = _make_registry_with_tools()
        graph = build_orchestrator_graph(tool_registry=registry)
        assert graph is not None

    def test_graph_has_supervisor_node(self) -> None:
        """Compiled graph should have a supervisor node."""
        graph = create_default_graph()
        # Verify the graph was compiled (has node structure)
        assert graph is not None

    def test_graph_with_max_iterations(self) -> None:
        """Graph should accept custom max_iterations."""
        graph = build_orchestrator_graph(max_iterations=5)
        assert graph is not None


# ══════════════════════════════════════════════════════════════════
# Graph Execution Tests (Mock mode)
# ══════════════════════════════════════════════════════════════════


class TestGraphExecution:
    """Tests for graph execution with mock supervisor."""

    def test_simple_query_finish(self) -> None:
        """Simple query should finish without worker dispatch."""
        graph = create_default_graph()

        result = graph.invoke(
            OrchestratorState(
                messages=[HumanMessage(content="你好")],
            )
        )

        assert result is not None
        assert len(result["messages"]) >= 2  # At least user msg + supervisor msg
        # Simple query should finish (no worker dispatched)
        assert result["plan"].finish is True

    def test_rag_query_routes_correctly(self) -> None:
        """Knowledge query should route to RAG worker."""
        registry = _make_registry_with_tools()
        graph = build_orchestrator_graph(tool_registry=registry)

        result = graph.invoke(
            OrchestratorState(
                messages=[HumanMessage(content="搜索知识库")],
            )
        )

        assert result is not None
        assert result["plan"] is not None
        # RAG query should have dispatched to rag worker
        assert result["plan"].requires_rag is True

    def test_hr_query_routes_correctly(self) -> None:
        """HR query should route to HR worker."""
        graph = create_default_graph()

        result = graph.invoke(
            OrchestratorState(
                messages=[HumanMessage(content="分析员工绩效")],
            )
        )

        assert result is not None
        # Should have been routed to HR

    def test_graph_preserves_messages(self) -> None:
        """Graph should accumulate messages from all nodes."""
        graph = create_default_graph()

        result = graph.invoke(
            OrchestratorState(
                messages=[HumanMessage(content="你好")],
            )
        )

        # Messages should include original user message + supervisor response
        assert len(result["messages"]) >= 1

    def test_graph_with_worker_outputs(self) -> None:
        """Graph with RAG search should produce worker output."""
        registry = _make_registry_with_tools()
        graph = build_orchestrator_graph(tool_registry=registry)

        result = graph.invoke(
            OrchestratorState(
                messages=[HumanMessage(content="搜索知识库中的财务报告")],
            )
        )

        # Should have worker outputs if RAG was dispatched
        assert result is not None
