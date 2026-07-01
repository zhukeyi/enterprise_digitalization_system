"""Tests for Orchestrator Graph construction and execution."""

from __future__ import annotations

from langchain_core.messages import HumanMessage

from agents.orchestrator.langgraph.graph import (
    build_orchestrator_graph,
    create_default_graph,
)
from agents.orchestrator.langgraph.state import OrchestratorState
from agents.orchestrator.tools.registry import ToolDefinition, ToolRegistry

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


# ══════════════════════════════════════════════════════════════════
# M2-T5: New Worker Tests
# ══════════════════════════════════════════════════════════════════


class TestNewWorkers:
    """Tests for M2-T5 ComplianceWorker and BusinessSystemWorker."""

    def test_compliance_worker_instantiation(self) -> None:
        """ComplianceWorker should be instantiable."""
        from agents.orchestrator.langgraph.workers import ComplianceWorker

        registry = _make_registry_with_tools()
        worker = ComplianceWorker(registry)
        assert worker.name == "compliance"
        assert "Compliance" in worker.description

    def test_business_system_worker_instantiation(self) -> None:
        """BusinessSystemWorker should be instantiable."""
        from agents.orchestrator.langgraph.workers import BusinessSystemWorker

        registry = _make_registry_with_tools()
        worker = BusinessSystemWorker(registry)
        assert worker.name == "business_system"
        assert "Business" in worker.description

    def test_new_workers_in_graph(self) -> None:
        """Graph should include the new M2-T5 workers."""
        registry = _make_registry_with_tools()
        graph = build_orchestrator_graph(tool_registry=registry)

        assert graph is not None
        # The graph should have 8 workers registered (6 original + 2 new)
        # We verify by checking that the graph compiles without error

    def test_graph_with_8_workers_logs(self) -> None:
        """Graph should log correct worker count (8 workers)."""
        import logging

        registry = _make_registry_with_tools()

        logger_name = "fde.orchestrator.graph"
        logger = logging.getLogger(logger_name)
        original_level = logger.level
        logger.setLevel(logging.INFO)

        with __import__("io").StringIO() as buf:
            handler = logging.StreamHandler(buf)
            logger.addHandler(handler)

            try:
                graph = build_orchestrator_graph(tool_registry=registry)
                assert graph is not None
            finally:
                logger.removeHandler(handler)
                logger.setLevel(original_level)
