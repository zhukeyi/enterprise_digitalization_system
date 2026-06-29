"""Tests for Supervisor Node."""

from __future__ import annotations

from langchain_core.messages import HumanMessage

from agents.orchestrator.langgraph.state import OrchestratorState, PlanStep, SupervisorPlan
from agents.orchestrator.langgraph.supervisor import SupervisorNode
from agents.orchestrator.tools.registry import ToolDefinition, ToolRegistry

# ══════════════════════════════════════════════════════════════════
# Helper
# ══════════════════════════════════════════════════════════════════


def _make_registry_with_rag_tool() -> ToolRegistry:
    """Create a registry with a basic RAG search tool."""
    registry = ToolRegistry()
    registry.register(
        ToolDefinition(
            name="rag_search",
            description="Search knowledge base",
            worker="rag",
            handler=lambda query="": f"Results for: {query}",
            parameters={"query": {"type": "string", "required": True}},
        )
    )
    return registry


# ══════════════════════════════════════════════════════════════════
# SupervisorNode Tests (Mock mode — no LLM)
# ══════════════════════════════════════════════════════════════════


class TestSupervisorNode:
    """Tests for SupervisorNode in mock mode."""

    def test_init_default(self) -> None:
        registry = ToolRegistry()
        supervisor = SupervisorNode(tool_registry=registry)
        assert supervisor.llm is None
        assert supervisor.max_iterations == 10

    def test_init_custom(self) -> None:
        registry = ToolRegistry()
        supervisor = SupervisorNode(tool_registry=registry, max_iterations=5)
        assert supervisor.max_iterations == 5

    def test_route_rag_query(self) -> None:
        """Supervisor should route knowledge queries to RAG worker."""
        registry = _make_registry_with_rag_tool()
        supervisor = SupervisorNode(tool_registry=registry)

        state = OrchestratorState(messages=[HumanMessage(content="搜索知识库中的财务报告")])

        result = supervisor(state)
        assert result["plan"] is not None
        assert result["next_worker"] == "rag"
        assert result["plan"].requires_rag is True

    def test_route_hr_query(self) -> None:
        """Supervisor should route HR queries to HR worker."""
        registry = ToolRegistry()
        supervisor = SupervisorNode(tool_registry=registry)

        state = OrchestratorState(messages=[HumanMessage(content="分析员工绩效")])

        result = supervisor(state)
        assert result["next_worker"] == "hr"

    def test_route_data_query(self) -> None:
        """Supervisor should route data collection queries to data worker."""
        registry = ToolRegistry()
        supervisor = SupervisorNode(tool_registry=registry)

        state = OrchestratorState(messages=[HumanMessage(content="启动RSS爬虫")])

        result = supervisor(state)
        assert result["next_worker"] == "data"

    def test_route_analysis_query(self) -> None:
        """Supervisor should route analysis queries to analysis worker."""
        registry = ToolRegistry()
        supervisor = SupervisorNode(tool_registry=registry)

        state = OrchestratorState(messages=[HumanMessage(content="生成季度统计报表")])

        result = supervisor(state)
        assert result["next_worker"] == "analysis"

    def test_simple_query_finish(self) -> None:
        """Supervisor should finish for simple non-specialized queries."""
        registry = ToolRegistry()
        supervisor = SupervisorNode(tool_registry=registry)

        state = OrchestratorState(messages=[HumanMessage(content="你好")])

        result = supervisor(state)
        assert result["next_worker"] == "__end__"
        assert result["plan"].finish is True

    def test_max_iterations_safety(self) -> None:
        """Supervisor should force finish when max iterations reached."""
        registry = ToolRegistry()
        supervisor = SupervisorNode(tool_registry=registry, max_iterations=3)

        state = OrchestratorState(
            messages=[HumanMessage(content="搜索文档")],
            iteration=3,  # Already at max
        )

        result = supervisor(state)
        assert result["next_worker"] == "__end__"
        assert result["plan"].finish is True

    def test_iteration_increment(self) -> None:
        """Supervisor should increment iteration counter."""
        registry = ToolRegistry()
        supervisor = SupervisorNode(tool_registry=registry)

        state = OrchestratorState(
            messages=[HumanMessage(content="搜索知识库")],
            iteration=0,
        )

        result = supervisor(state)
        assert result["iteration"] == 1

    def test_worker_outputs_in_context(self) -> None:
        """Supervisor should include previous worker outputs in context."""
        registry = _make_registry_with_rag_tool()
        supervisor = SupervisorNode(tool_registry=registry)

        state = OrchestratorState(
            messages=[HumanMessage(content="继续分析")],
            worker_outputs={"rag": "Found 5 documents"},
            iteration=1,
        )

        result = supervisor(state)
        assert result["plan"] is not None

    def test_system_prompt_contains_tools(self) -> None:
        """System prompt should list available tools."""
        registry = _make_registry_with_rag_tool()
        supervisor = SupervisorNode(tool_registry=registry)

        prompt = supervisor._build_system_prompt()
        assert "rag_search" in prompt
        assert "Search knowledge base" in prompt

    def test_system_prompt_contains_workers(self) -> None:
        """System prompt should list available workers."""
        registry = ToolRegistry()
        supervisor = SupervisorNode(tool_registry=registry)

        prompt = supervisor._build_system_prompt()
        assert "rag" in prompt
        assert "hr" in prompt

    def test_parse_llm_response_json(self) -> None:
        """Supervisor should parse valid JSON LLM responses."""
        registry = ToolRegistry()
        supervisor = SupervisorNode(tool_registry=registry)

        json_response = """
        {
            "steps": [{"worker": "rag", "task": "Search for docs", "tool": "rag_search", "tool_args": {"query": "test"}}],
            "reasoning": "User wants to search",
            "requires_rag": true,
            "complexity": "medium",
            "finish": false
        }
        """
        plan = supervisor._parse_llm_response(json_response)
        assert len(plan.steps) == 1
        assert plan.steps[0].worker == "rag"
        assert plan.requires_rag is True

    def test_parse_llm_response_markdown_json(self) -> None:
        """Supervisor should parse JSON wrapped in markdown code blocks."""
        registry = ToolRegistry()
        supervisor = SupervisorNode(tool_registry=registry)

        md_response = """
Here's the plan:
```json
{
    "steps": [{"worker": "hr", "task": "Analyze performance"}],
    "reasoning": "HR request",
    "requires_rag": false,
    "complexity": "medium",
    "finish": false
}
```
"""
        plan = supervisor._parse_llm_response(md_response)
        assert len(plan.steps) == 1
        assert plan.steps[0].worker == "hr"

    def test_parse_llm_response_fallback(self) -> None:
        """Supervisor should fallback for unparseable responses."""
        registry = ToolRegistry()
        supervisor = SupervisorNode(tool_registry=registry)

        plan = supervisor._parse_llm_response("I can't parse this as JSON")
        assert plan.finish is True
        assert plan.steps == []

    def test_determine_next_worker_with_steps(self) -> None:
        """Supervisor should route to first step's worker."""
        registry = ToolRegistry()
        supervisor = SupervisorNode(tool_registry=registry)

        plan = SupervisorPlan(
            steps=[PlanStep(worker="rag", task="Search")],
            finish=False,
        )
        next_worker = supervisor._determine_next_worker(plan)
        assert next_worker == "rag"

    def test_determine_next_worker_finish(self) -> None:
        """Supervisor should return __end__ for finished plans."""
        registry = ToolRegistry()
        supervisor = SupervisorNode(tool_registry=registry)

        plan = SupervisorPlan(finish=True)
        next_worker = supervisor._determine_next_worker(plan)
        assert next_worker == "__end__"

    def test_determine_next_worker_empty_steps(self) -> None:
        """Supervisor should return __end__ for plans with no steps."""
        registry = ToolRegistry()
        supervisor = SupervisorNode(tool_registry=registry)

        plan = SupervisorPlan(steps=[], finish=False)
        next_worker = supervisor._determine_next_worker(plan)
        assert next_worker == "__end__"
