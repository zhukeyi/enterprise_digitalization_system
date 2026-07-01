"""M3-T13: End-to-end integration tests for the analysis pipeline.

Tests the full NL2SQL pipeline through the orchestrator:
- Supervisor routes analysis queries to AnalysisWorker
- AnalysisWorker dispatches to analysis tools via ToolRegistry
- Tools execute and return results through the orchestrator state

Covers:
- NL2SQL full pipeline (query → rule engine → safety check → execution → result)
- Schema listing through orchestrator
- Chart data generation through orchestrator
- Multi-step plan with analysis worker
- HR + Analysis multi-worker plan
- SQL safety enforcement through orchestrator
"""

from __future__ import annotations

import asyncio
from typing import Any

from langchain_core.messages import HumanMessage

from agents.analysis_agent.integration import register_analysis_tools
from agents.hr_agent.integration import register_hr_tools
from agents.orchestrator.langgraph.graph import create_default_graph
from agents.orchestrator.langgraph.state import OrchestratorState
from agents.orchestrator.langgraph.supervisor import SupervisorNode
from agents.orchestrator.langgraph.workers import AnalysisWorker, HRWorker
from agents.orchestrator.tools.registry import ToolRegistry

# ══════════════════════════════════════════════════════════════════
# Helpers
# ══════════════════════════════════════════════════════════════════


def _run(coro: Any) -> Any:
    """Run an async coroutine synchronously."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_closed():
            raise RuntimeError("loop closed")
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    return loop.run_until_complete(coro)


def _build_registry_with_tools() -> ToolRegistry:
    """Build a ToolRegistry with analysis and HR tools registered."""
    registry = ToolRegistry()
    register_analysis_tools(registry)
    register_hr_tools(registry)
    return registry


# ══════════════════════════════════════════════════════════════════
# Test: Analysis Worker Direct Dispatch
# ══════════════════════════════════════════════════════════════════


class TestAnalysisWorkerDispatch:
    """Test AnalysisWorker execute() with real tool dispatch."""

    def test_worker_dispatches_nl2sql(self):
        """AnalysisWorker routes NL2SQL query through tool registry."""
        registry = _build_registry_with_tools()
        worker = AnalysisWorker(registry)

        from agents.orchestrator.langgraph.state import PlanStep

        step = PlanStep(
            worker="analysis",
            task="NL2SQL query for: 查询所有销售额",
            tool="nl2sql",
            tool_args={"query": "查询所有销售额"},
        )

        state = OrchestratorState(messages=[HumanMessage(content="查询所有销售额")])
        result = worker.execute(step, state)

        assert isinstance(result, dict)
        assert result["success"] is True
        assert "SELECT" in result["sql"]

    def test_worker_dispatches_schema_list(self):
        """AnalysisWorker routes schema_list through tool registry."""
        registry = _build_registry_with_tools()
        worker = AnalysisWorker(registry)

        from agents.orchestrator.langgraph.state import PlanStep

        step = PlanStep(
            worker="analysis",
            task="List database schema",
            tool="schema_list",
            tool_args={},
        )

        state = OrchestratorState(messages=[HumanMessage(content="show schema")])
        result = worker.execute(step, state)

        assert isinstance(result, dict)
        assert "tables" in result
        assert len(result["tables"]) == 4

    def test_worker_dispatches_chart_data(self):
        """AnalysisWorker routes chart data query through tool registry."""
        registry = _build_registry_with_tools()
        worker = AnalysisWorker(registry)

        from agents.orchestrator.langgraph.state import PlanStep

        step = PlanStep(
            worker="analysis",
            task="Generate chart data for: 查询销售额",
            tool="query_chart_data",
            tool_args={"query": "查询销售额", "chart_type": "bar"},
        )

        state = OrchestratorState(messages=[HumanMessage(content="chart")])
        result = worker.execute(step, state)

        assert isinstance(result, dict)
        assert result["chart_type"] == "bar"
        assert len(result["labels"]) > 0

    def test_worker_infers_nl2sql_from_task(self):
        """AnalysisWorker infers nl2sql tool when no tool specified."""
        registry = _build_registry_with_tools()
        worker = AnalysisWorker(registry)

        from agents.orchestrator.langgraph.state import PlanStep

        step = PlanStep(
            worker="analysis",
            task="查询所有销售额",
            tool=None,
            tool_args={},
        )

        state = OrchestratorState(messages=[HumanMessage(content="查询销售额")])
        result = worker.execute(step, state)

        assert isinstance(result, dict)
        assert result["success"] is True

    def test_worker_infers_schema_from_task(self):
        """AnalysisWorker infers schema_list when task mentions schema."""
        registry = _build_registry_with_tools()
        worker = AnalysisWorker(registry)

        from agents.orchestrator.langgraph.state import PlanStep

        step = PlanStep(
            worker="analysis",
            task="Show database schema",
            tool=None,
            tool_args={},
        )

        state = OrchestratorState(messages=[HumanMessage(content="schema")])
        result = worker.execute(step, state)

        assert isinstance(result, dict)
        assert "tables" in result


# ══════════════════════════════════════════════════════════════════
# Test: HR Worker Direct Dispatch
# ══════════════════════════════════════════════════════════════════


class TestHRWorkerDispatch:
    """Test HRWorker execute() with real tool dispatch."""

    def test_worker_dispatches_employee_profile(self):
        """HRWorker routes employee profile query through tool registry."""
        registry = _build_registry_with_tools()
        worker = HRWorker(registry)

        from agents.orchestrator.langgraph.state import PlanStep

        step = PlanStep(
            worker="hr",
            task="Employee profile for EMP-001",
            tool="hr_employee_profile",
            tool_args={"employee_id": "EMP-001"},
        )

        state = OrchestratorState(messages=[HumanMessage(content="employee profile")])
        result = worker.execute(step, state)

        assert isinstance(result, dict)
        assert result["employee_id"] == "EMP-001"

    def test_worker_infers_profile_from_task(self):
        """HRWorker infers employee profile when task mentions profile."""
        registry = _build_registry_with_tools()
        worker = HRWorker(registry)

        from agents.orchestrator.langgraph.state import PlanStep

        step = PlanStep(
            worker="hr",
            task="生成员工画像",
            tool=None,
            tool_args={},
        )

        state = OrchestratorState(messages=[HumanMessage(content="员工画像")])
        result = worker.execute(step, state)

        assert isinstance(result, dict)
        assert "employee_id" in result

    def test_worker_infers_org_health_from_task(self):
        """HRWorker infers org health when task mentions health."""
        registry = _build_registry_with_tools()
        worker = HRWorker(registry)

        from agents.orchestrator.langgraph.state import PlanStep

        step = PlanStep(
            worker="hr",
            task="部门健康度报告",
            tool=None,
            tool_args={},
        )

        state = OrchestratorState(messages=[HumanMessage(content="组织健康")])
        result = worker.execute(step, state)

        assert isinstance(result, dict)
        assert "health_score" in result


# ══════════════════════════════════════════════════════════════════
# Test: Supervisor Routing to Analysis Worker
# ══════════════════════════════════════════════════════════════════


class TestSupervisorAnalysisRouting:
    """Test supervisor routes analysis queries correctly."""

    def test_supervisor_routes_nl2sql_query(self):
        """Supervisor creates analysis plan step for NL2SQL queries."""
        registry = _build_registry_with_tools()
        supervisor = SupervisorNode(tool_registry=registry)

        state = OrchestratorState(
            messages=[HumanMessage(content="查询所有销售额大于100万的记录")],
        )

        plan = supervisor._mock_plan(state)
        assert len(plan.steps) >= 1
        analysis_steps = [s for s in plan.steps if s.worker == "analysis"]
        assert len(analysis_steps) >= 1
        assert analysis_steps[0].tool == "nl2sql"
        assert "query" in analysis_steps[0].tool_args

    def test_supervisor_routes_schema_query(self):
        """Supervisor routes schema queries to analysis worker."""
        registry = _build_registry_with_tools()
        supervisor = SupervisorNode(tool_registry=registry)

        state = OrchestratorState(
            messages=[HumanMessage(content="show database schema")],
        )

        plan = supervisor._mock_plan(state)
        analysis_steps = [s for s in plan.steps if s.worker == "analysis"]
        assert len(analysis_steps) >= 1
        assert analysis_steps[0].tool == "schema_list"

    def test_supervisor_routes_chart_query(self):
        """Supervisor routes chart queries to analysis worker."""
        registry = _build_registry_with_tools()
        supervisor = SupervisorNode(tool_registry=registry)

        state = OrchestratorState(
            messages=[HumanMessage(content="生成销售额chart图表")],
        )

        plan = supervisor._mock_plan(state)
        analysis_steps = [s for s in plan.steps if s.worker == "analysis"]
        assert len(analysis_steps) >= 1
        assert analysis_steps[0].tool == "query_chart_data"

    def test_supervisor_routes_statistics_query(self):
        """Supervisor routes statistics queries to analysis worker."""
        registry = _build_registry_with_tools()
        supervisor = SupervisorNode(tool_registry=registry)

        state = OrchestratorState(
            messages=[HumanMessage(content="统计销售额总数")],
        )

        plan = supervisor._mock_plan(state)
        analysis_steps = [s for s in plan.steps if s.worker == "analysis"]
        assert len(analysis_steps) >= 1

    def test_supervisor_routes_sql_query(self):
        """Supervisor routes SQL queries to analysis worker."""
        registry = _build_registry_with_tools()
        supervisor = SupervisorNode(tool_registry=registry)

        state = OrchestratorState(
            messages=[HumanMessage(content="执行SQL查询分析")],
        )

        plan = supervisor._mock_plan(state)
        analysis_steps = [s for s in plan.steps if s.worker == "analysis"]
        assert len(analysis_steps) >= 1


# ══════════════════════════════════════════════════════════════════
# Test: Full Graph Execution (E2E)
# ══════════════════════════════════════════════════════════════════


class TestFullGraphExecution:
    """Test full orchestrator graph execution with analysis tools."""

    def test_graph_builds_with_tools(self):
        """Default graph builds successfully with analysis + HR tools."""
        graph = create_default_graph()
        assert graph is not None

    def test_graph_executes_analysis_query(self):
        """Full graph executes an analysis query end-to-end."""
        graph = create_default_graph()

        state = OrchestratorState(
            messages=[HumanMessage(content="查询所有销售额")],
        )

        result = graph.invoke(state, debug=False)

        # Graph should complete and produce worker outputs
        assert result is not None
        # The supervisor should have routed to analysis
        if "worker_outputs" in result:
            assert (
                "analysis" in result["worker_outputs"] or len(result.get("worker_outputs", {})) > 0
            )

    def test_graph_executes_schema_query(self):
        """Full graph executes a schema listing query."""
        graph = create_default_graph()

        state = OrchestratorState(
            messages=[HumanMessage(content="show database schema")],
        )

        result = graph.invoke(state, debug=False)
        assert result is not None

    def test_graph_executes_hr_query(self):
        """Full graph executes an HR query."""
        graph = create_default_graph()

        state = OrchestratorState(
            messages=[HumanMessage(content="查询员工画像")],
        )

        result = graph.invoke(state, debug=False)
        assert result is not None


# ══════════════════════════════════════════════════════════════════
# Test: Tool Registry Integration
# ══════════════════════════════════════════════════════════════════


class TestToolRegistryIntegration:
    """Test tool registry has all analysis and HR tools."""

    def test_registry_has_analysis_tools(self):
        """ToolRegistry contains all 4 analysis tools."""
        registry = _build_registry_with_tools()
        analysis_tools = registry.get_tools_for_worker("analysis")
        assert len(analysis_tools) == 4

        tool_names = {t.name for t in analysis_tools}
        assert "nl2sql" in tool_names
        assert "sql_execute" in tool_names
        assert "schema_list" in tool_names
        assert "query_chart_data" in tool_names

    def test_registry_has_hr_tools(self):
        """ToolRegistry contains all 6 HR tools."""
        registry = _build_registry_with_tools()
        hr_tools = registry.get_tools_for_worker("hr")
        assert len(hr_tools) == 6

    def test_registry_workers_summary(self):
        """ToolRegistry workers summary includes analysis and hr."""
        registry = _build_registry_with_tools()
        summary = registry.get_workers_summary()
        assert "analysis" in summary
        assert "hr" in summary
        assert len(summary["analysis"]) == 4
        assert len(summary["hr"]) == 6

    def test_registry_dispatch_nl2sql_e2e(self):
        """End-to-end: dispatch nl2sql through registry → result."""
        registry = _build_registry_with_tools()
        result = _run(registry.dispatch("nl2sql", query="查询所有销售额大于100万的记录"))

        assert result["success"] is True
        assert ">" in result["sql"]
        assert "1000000" in result["sql"]
        assert result["result"] is not None
        assert result["safety_check_passed"] is True

    def test_registry_dispatch_schema_list_e2e(self):
        """End-to-end: dispatch schema_list through registry → result."""
        registry = _build_registry_with_tools()
        result = _run(registry.dispatch("schema_list"))

        assert "tables" in result
        assert len(result["tables"]) == 4
        table_names = {t["table_name"] for t in result["tables"]}
        assert "employees" in table_names
        assert "sales" in table_names

    def test_registry_dispatch_chart_data_e2e(self):
        """End-to-end: dispatch query_chart_data through registry → result."""
        registry = _build_registry_with_tools()
        result = _run(
            registry.dispatch(
                "query_chart_data",
                query="查询销售额",
                chart_type="bar",
            )
        )

        assert result["chart_type"] == "bar"
        assert len(result["labels"]) > 0
        assert len(result["datasets"]) > 0
        assert result["datasets"][0]["label"] is not None

    def test_registry_dispatch_hr_profile_e2e(self):
        """End-to-end: dispatch hr_employee_profile through registry → result."""
        registry = _build_registry_with_tools()
        result = _run(registry.dispatch("hr_employee_profile", employee_id="EMP-001"))

        assert result["employee_id"] == "EMP-001"
        assert "employee_name" in result


# ══════════════════════════════════════════════════════════════════
# Test: SQL Safety Enforcement Through Pipeline
# ══════════════════════════════════════════════════════════════════


class TestSQLSafetyE2E:
    """Test SQL safety is enforced through the full pipeline."""

    def test_delete_blocked_through_pipeline(self):
        """DELETE statement is blocked when executed through pipeline."""
        registry = _build_registry_with_tools()
        result = _run(registry.dispatch("sql_execute", sql="DELETE FROM employees"))

        assert result["row_count"] == 0
        assert result["rows"] == []

    def test_drop_blocked_through_pipeline(self):
        """DROP statement is blocked when executed through pipeline."""
        registry = _build_registry_with_tools()
        result = _run(registry.dispatch("sql_execute", sql="DROP TABLE employees"))

        assert result["row_count"] == 0

    def test_safe_select_passes_pipeline(self):
        """Safe SELECT statement passes through pipeline."""
        registry = _build_registry_with_tools()
        result = _run(registry.dispatch("sql_execute", sql="SELECT * FROM employees LIMIT 5"))

        assert result["row_count"] == 5
        assert len(result["columns"]) > 0

    def test_nl2sql_generates_safe_sql(self):
        """NL2SQL engine generates SQL that passes safety validation."""
        registry = _build_registry_with_tools()
        result = _run(registry.dispatch("nl2sql", query="查询所有员工"))

        assert result["success"] is True
        assert result["safety_check_passed"] is True
        assert result["sql"].upper().startswith("SELECT")


# ══════════════════════════════════════════════════════════════════
# Test: AC Acceptance Criteria
# ══════════════════════════════════════════════════════════════════


class TestAcceptanceCriteria:
    """Verify M3-T3 acceptance criteria through E2E tests."""

    def test_ac001_nl2sql_sales_query(self):
        """AC-001: 查询所有销售额大于100万的记录 → SELECT ... WHERE amount > 1000000."""
        registry = _build_registry_with_tools()
        result = _run(registry.dispatch("nl2sql", query="查询所有销售额大于100万的记录"))

        assert result["success"] is True
        assert ">" in result["sql"]
        assert "1000000" in result["sql"]
        assert result["result"] is not None
        assert result["result"]["row_count"] >= 0

    def test_ac002_delete_blocked(self):
        """AC-002: DELETE FROM table → blocked by safety check."""
        registry = _build_registry_with_tools()
        result = _run(registry.dispatch("sql_execute", sql="DELETE FROM employees WHERE id = 1"))
        assert result["row_count"] == 0

    def test_ac003_drop_blocked(self):
        """AC-003: DROP → blocked by safety check."""
        registry = _build_registry_with_tools()
        result = _run(registry.dispatch("sql_execute", sql="DROP TABLE employees"))
        assert result["row_count"] == 0

    def test_ac004_llm_fallback(self):
        """AC-004: Unmatched query → LLM fallback with prompt."""
        registry = _build_registry_with_tools()
        result = _run(registry.dispatch("nl2sql", query="今天天气怎么样"))

        assert result["success"] is False
        assert result["source"] == "llm_fallback"
        assert "LLM prompt" in result["error"]

    def test_ac005_empty_result_handled(self):
        """AC-005: Query with no results → rows=[], row_count=0."""
        registry = _build_registry_with_tools()
        result = _run(
            registry.dispatch("sql_execute", sql="SELECT * FROM employees WHERE salary > 999999999")
        )

        assert result["row_count"] == 0
        assert result["rows"] == []

    def test_ac006_schema_list(self):
        """AC-006: schema_list → returns tables and columns."""
        registry = _build_registry_with_tools()
        result = _run(registry.dispatch("schema_list"))

        assert "tables" in result
        assert len(result["tables"]) == 4
        for table in result["tables"]:
            assert "table_name" in table
            assert "columns" in table
            assert len(table["columns"]) > 0
