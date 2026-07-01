"""M2-T8 End-to-End Integration Tests.

Verifies the complete pipeline: Supervisor -> Worker(s) -> ConflictDetector
-> ConflictResolver -> ResponseGenerator -> END.

Cross-module collaboration tests for the M2 milestone sign-off.

M2-T8: Strengthened assertions to verify actual worker dispatch, multi-step
plan execution, and full conflict pipeline traversal.
"""

from __future__ import annotations

import pytest
from langchain_core.messages import HumanMessage

from agents.orchestrator.langgraph.state import OrchestratorState
from agents.orchestrator.tools.registry import ToolRegistry

# ══════════════════════════════════════════════════════════════════
# Helpers
# ══════════════════════════════════════════════════════════════════


def _build_full_graph():
    """Build orchestrator graph with ALL worker tools registered."""
    from agents.business_agent.integration import register_business_tools
    from agents.compliance_agent.integration import register_compliance_tools
    from agents.im_agent.worker import register_im_tools
    from agents.orchestrator.langgraph.graph import build_orchestrator_graph
    from agents.rag_agent.integration import register_rag_tools

    registry = ToolRegistry()
    register_rag_tools(registry)
    register_compliance_tools(registry)
    register_business_tools(registry)
    register_im_tools(registry)

    return build_orchestrator_graph(tool_registry=registry)


def _build_registry() -> ToolRegistry:
    """Build a registry with all M2 worker tools."""
    from agents.business_agent.integration import register_business_tools
    from agents.compliance_agent.integration import register_compliance_tools
    from agents.im_agent.worker import register_im_tools
    from agents.rag_agent.integration import register_rag_tools

    registry = ToolRegistry()
    register_rag_tools(registry)
    register_compliance_tools(registry)
    register_business_tools(registry)
    register_im_tools(registry)
    return registry


# ══════════════════════════════════════════════════════════════════
# E2E: Graph Compilation & Worker Discovery
# ══════════════════════════════════════════════════════════════════


class TestGraphCompilation:
    def test_full_graph_compiles(self) -> None:
        """Graph with 10 workers should compile without error."""
        graph = _build_full_graph()
        assert graph is not None

    def test_workers_discoverable(self) -> None:
        """All registered worker names should have tools."""
        registry = _build_registry()

        expected_workers = {"rag", "compliance", "business_system", "im"}

        for worker in expected_workers:
            tools = registry.get_tools_for_worker(worker)
            assert len(tools) > 0, f"Worker '{worker}' has no tools registered"

    def test_total_tool_count(self) -> None:
        """Registry should have at least 11 tools (2 RAG + 3 compliance + 3 business + 3 IM)."""
        registry = _build_registry()
        all_tools = registry.list_all()
        assert len(all_tools) >= 11, f"Expected >=11 tools, got {len(all_tools)}"


# ══════════════════════════════════════════════════════════════════
# E2E: Full Orchestration Flow (Mock Supervisor)
# ══════════════════════════════════════════════════════════════════


class TestFullOrchestrationFlow:
    def test_simple_query_completes(self) -> None:
        """Simple query should flow through graph and produce final_response."""
        graph = _build_full_graph()
        result = graph.invoke(
            OrchestratorState(messages=[HumanMessage(content="你好，当前系统状态如何？")])
        )
        assert result is not None
        assert result.get("final_response", "") != ""

    def test_rag_query_routes_to_rag_worker(self) -> None:
        """RAG query should route to the rag worker specifically."""
        graph = _build_full_graph()
        result = graph.invoke(
            OrchestratorState(messages=[HumanMessage(content="搜索知识库中的技术文档")])
        )
        worker_outputs = result.get("worker_outputs", {})
        assert (
            "rag" in worker_outputs
        ), f"Expected 'rag' in workers, got: {list(worker_outputs.keys())}"
        # RAG result should be a dict with search results
        rag_result = worker_outputs["rag"]
        assert isinstance(rag_result, dict)
        assert "query" in rag_result or "error" in rag_result

    def test_compliance_query_triggers_worker(self) -> None:
        """Compliance keyword should route to compliance worker."""
        graph = _build_full_graph()
        result = graph.invoke(
            OrchestratorState(messages=[HumanMessage(content="检查系统合规状态")])
        )
        worker_outputs = result.get("worker_outputs", {})
        assert (
            "compliance" in worker_outputs
        ), f"Expected 'compliance' in workers, got: {list(worker_outputs.keys())}"

    def test_multi_worker_query_dispatches_all(self) -> None:
        """Query matching multiple worker keywords should dispatch to all matched workers."""
        graph = _build_full_graph()
        result = graph.invoke(
            OrchestratorState(messages=[HumanMessage(content="分析当前业务系统的状态和合规风险")])
        )
        worker_outputs = result.get("worker_outputs", {})
        # "业务系统" matches business_system, "合规" matches compliance
        assert (
            "business_system" in worker_outputs
        ), f"Expected 'business_system' in workers, got: {list(worker_outputs.keys())}"
        assert (
            "compliance" in worker_outputs
        ), f"Expected 'compliance' in workers, got: {list(worker_outputs.keys())}"

    def test_error_not_propagated_to_user(self) -> None:
        """Worker errors should be caught, not crash the graph."""
        graph = _build_full_graph()
        # "消息" triggers IM worker which may error on missing args, but graph should survive
        result = graph.invoke(
            OrchestratorState(messages=[HumanMessage(content="发送消息给所有用户")])
        )
        assert result is not None
        assert result.get("final_response", "") != ""


# ══════════════════════════════════════════════════════════════════
# E2E: Multi-Step Plan Execution
# ══════════════════════════════════════════════════════════════════


class TestMultiStepPlan:
    def test_crm_and_im_both_execute(self) -> None:
        """Query for CRM data + IM notification should trigger both workers."""
        graph = _build_full_graph()
        result = graph.invoke(
            OrchestratorState(messages=[HumanMessage(content="查询CRM数据并通知相关群组")])
        )
        worker_outputs = result.get("worker_outputs", {})
        assert (
            "business_system" in worker_outputs
        ), f"Expected business_system, got: {list(worker_outputs.keys())}"
        assert "im" in worker_outputs, f"Expected im, got: {list(worker_outputs.keys())}"
        # Should take 3 iterations: supervisor -> business -> supervisor -> im -> supervisor -> end
        assert result.get("iteration", 0) >= 3

    def test_rag_and_compliance_both_execute(self) -> None:
        """Query for knowledge + compliance should trigger both workers."""
        graph = _build_full_graph()
        result = graph.invoke(
            OrchestratorState(messages=[HumanMessage(content="检索知识库，检查合规性")])
        )
        worker_outputs = result.get("worker_outputs", {})
        assert "rag" in worker_outputs, f"Expected rag, got: {list(worker_outputs.keys())}"
        assert (
            "compliance" in worker_outputs
        ), f"Expected compliance, got: {list(worker_outputs.keys())}"

    def test_multi_step_preserves_all_outputs(self) -> None:
        """Multi-step plan should accumulate outputs from all workers."""
        graph = _build_full_graph()
        result = graph.invoke(
            OrchestratorState(messages=[HumanMessage(content="检查业务系统状态并审计合规风险")])
        )
        worker_outputs = result.get("worker_outputs", {})
        # Both workers should have outputs
        assert len(worker_outputs) >= 2, f"Expected >=2 workers, got: {list(worker_outputs.keys())}"
        # Each output should be a dict (tool result)
        for worker_name, output in worker_outputs.items():
            assert isinstance(
                output, dict
            ), f"Worker '{worker_name}' output should be dict, got {type(output)}"


# ══════════════════════════════════════════════════════════════════
# E2E: Conflict Pipeline (Full Traversal)
# ══════════════════════════════════════════════════════════════════


class TestConflictPipeline:
    def test_status_conflict_detected_and_resolved(self) -> None:
        """Two workers returning different overall_status should trigger conflict."""
        graph = _build_full_graph()
        # "业务系统" -> business_system (system_status -> overall_status: degraded)
        # "审计" -> compliance (compliance_summary -> overall_status: warning)
        result = graph.invoke(
            OrchestratorState(messages=[HumanMessage(content="检查业务系统状态并审计合规风险")])
        )
        worker_outputs = result.get("worker_outputs", {})
        conflicts = result.get("conflicts", [])
        resolutions = result.get("conflict_resolutions", [])

        # Both workers must have executed
        assert "compliance" in worker_outputs
        assert "business_system" in worker_outputs

        # Both should have overall_status with different values
        comp_status = worker_outputs.get("compliance", {}).get("overall_status")
        biz_status = worker_outputs.get("business_system", {}).get("overall_status")
        assert comp_status is not None
        assert biz_status is not None
        assert (
            comp_status != biz_status
        ), f"Statuses should differ for conflict: {comp_status} vs {biz_status}"

        # Conflict should be detected
        assert len(conflicts) >= 1, "Expected at least 1 conflict"
        assert any(
            c.field == "status" for c in conflicts
        ), f"Expected status conflict, got fields: {[c.field for c in conflicts]}"

        # Conflict should be resolved
        assert len(resolutions) >= 1, "Expected at least 1 resolution"
        assert all(r.resolved for r in resolutions), "All conflicts should be resolved"

    def test_conflict_resolution_uses_source_priority(self) -> None:
        """Status conflict should use source_priority strategy."""
        graph = _build_full_graph()
        result = graph.invoke(
            OrchestratorState(messages=[HumanMessage(content="检查业务系统状态并审计合规风险")])
        )
        conflicts = result.get("conflicts", [])
        status_conflicts = [c for c in conflicts if c.field == "status"]
        if status_conflicts:
            assert status_conflicts[0].resolution_strategy == "source_priority"

    def test_no_conflict_with_single_worker(self) -> None:
        """Single worker output should not trigger conflicts."""
        graph = _build_full_graph()
        result = graph.invoke(
            OrchestratorState(messages=[HumanMessage(content="搜索知识库中的技术文档")])
        )
        assert len(result.get("conflicts", [])) == 0

    def test_final_response_contains_conflict_info(self) -> None:
        """When conflicts exist, final response should mention them."""
        graph = _build_full_graph()
        result = graph.invoke(
            OrchestratorState(messages=[HumanMessage(content="检查业务系统状态并审计合规风险")])
        )
        conflicts = result.get("conflicts", [])
        if conflicts:
            response = result.get("final_response", "")
            assert "冲突" in response, "Final response should mention conflicts"

    def test_response_generator_includes_all_workers(self) -> None:
        """Final response should list all worker outputs."""
        graph = _build_full_graph()
        result = graph.invoke(
            OrchestratorState(messages=[HumanMessage(content="检索知识库，检查合规性")])
        )
        worker_outputs = result.get("worker_outputs", {})
        response = result.get("final_response", "")
        for worker_name in worker_outputs:
            assert (
                worker_name in response
            ), f"Worker '{worker_name}' should be mentioned in response"


# ══════════════════════════════════════════════════════════════════
# E2E: Cross-Module Integration
# ══════════════════════════════════════════════════════════════════


class TestCrossModuleIntegration:
    def test_rag_compliance_chain(self) -> None:
        """RAG + Compliance should coexist and both produce outputs."""
        graph = _build_full_graph()
        result = graph.invoke(
            OrchestratorState(messages=[HumanMessage(content="检索知识库，检查合规性")])
        )
        outputs = result.get("worker_outputs", {})
        assert "rag" in outputs
        assert "compliance" in outputs

    def test_business_im_chain(self) -> None:
        """Business + IM workers should both execute."""
        graph = _build_full_graph()
        result = graph.invoke(
            OrchestratorState(messages=[HumanMessage(content="查询CRM数据并通知相关群组")])
        )
        outputs = result.get("worker_outputs", {})
        assert "business_system" in outputs
        assert "im" in outputs

    def test_auth_filter_integration_point(self) -> None:
        """Auth filter module should be importable and functional."""
        from agents.rag_agent.auth_filter import (
            RESOURCE_DOCUMENT,
            RESOURCE_KNOWLEDGE_BASE,
            filter_by_permission,
        )

        assert RESOURCE_DOCUMENT == "document"
        assert RESOURCE_KNOWLEDGE_BASE == "knowledge_base"
        assert callable(filter_by_permission)

    def test_decision_log_module_importable(self) -> None:
        """Decision logger should be importable."""
        from agents.governance_agent.decision_log import DecisionLogger

        logger = DecisionLogger()
        assert logger is not None

    def test_dify_bridge_importable(self) -> None:
        """Dify bridge should be importable."""
        from agents.dify_bridge.bridge import DifyBridge

        bridge = DifyBridge()
        assert bridge is not None

    def test_desktop_sdk_importable(self) -> None:
        """Desktop SDK should be importable."""
        from agents.client_agent.auth import DesktopAuthManager

        mgr = DesktopAuthManager()
        assert mgr is not None


# ══════════════════════════════════════════════════════════════════
# E2E: Decision Chain Logging
# ══════════════════════════════════════════════════════════════════


class TestDecisionChainLogging:
    @pytest.mark.asyncio
    async def test_full_log_cycle(self) -> None:
        """Plan -> Worker -> Final log cycle should complete."""
        from sqlalchemy import select
        from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

        from agents.governance_agent.database.models import DecisionChainLog
        from agents.governance_agent.decision_log import DecisionLogger

        engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)

        from agents.governance_agent.database import Base

        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        async with factory() as session:
            dlog = DecisionLogger()
            import uuid

            sid = str(uuid.uuid4())
            dlog.start_session(sid)

            await dlog.log_plan(
                session=session,
                session_id=sid,
                user_id=str(uuid.uuid4()),
                query="E2E test query",
                plan={"steps": [], "complexity": "simple"},
            )
            await dlog.log_worker_result(
                session=session,
                session_id=sid,
                user_id=str(uuid.uuid4()),
                worker_name="rag",
                result={"count": 3},
            )
            await dlog.log_final(
                session=session,
                session_id=sid,
                user_id=str(uuid.uuid4()),
                response="E2E response",
            )

            result = await session.execute(
                select(DecisionChainLog).where(DecisionChainLog.session_id == sid)
            )
            entries = result.scalars().all()
            assert len(entries) == 3

        await engine.dispose()


# ══════════════════════════════════════════════════════════════════
# E2E: Error Recovery
# ══════════════════════════════════════════════════════════════════


class TestErrorRecovery:
    def test_graph_handles_empty_input(self) -> None:
        """Graph should not crash on empty messages."""
        graph = _build_full_graph()
        result = graph.invoke(OrchestratorState())
        assert result is not None
        assert result.get("final_response", "") != ""

    def test_graph_safety_iteration_limit(self) -> None:
        """Graph should respect max_iterations safety limit."""
        from agents.orchestrator.langgraph.graph import build_orchestrator_graph

        graph = build_orchestrator_graph(max_iterations=2)
        result = graph.invoke(
            OrchestratorState(messages=[HumanMessage(content="compute endlessly")])
        )
        assert result.get("iteration", 0) <= 2

    def test_conflict_pipeline_no_crash_on_single_worker(self) -> None:
        """Conflict pipeline should handle single worker gracefully."""
        graph = _build_full_graph()
        result = graph.invoke(OrchestratorState(messages=[HumanMessage(content="你好")]))
        assert result.get("final_response", "") != ""
        # No conflicts should be detected with single/simple query
        assert len(result.get("conflicts", [])) == 0

    def test_worker_error_caught_not_crashed(self) -> None:
        """If a worker raises an error, the graph should catch it and continue."""
        graph = _build_full_graph()
        # "发送消息" triggers IM worker which requires target_id
        result = graph.invoke(
            OrchestratorState(messages=[HumanMessage(content="发送消息给所有用户")])
        )
        # Graph should complete
        assert result.get("final_response", "") != ""
        # IM worker output should exist (may contain error dict)
        outputs = result.get("worker_outputs", {})
        assert "im" in outputs


# ══════════════════════════════════════════════════════════════════
# E2E: M2 Architecture Compliance
# ══════════════════════════════════════════════════════════════════


class TestM2ArchitectureCompliance:
    """Verify all M2 modules are correctly wired and importable."""

    def test_all_m2_modules_importable(self) -> None:
        """Every M2 module should be importable without errors."""
        modules_to_import = [
            ("auth", "agents.governance_agent.auth.security"),
            ("permission filter", "agents.rag_agent.auth_filter"),
            ("decision log", "agents.governance_agent.decision_log"),
            ("compliance agent", "agents.compliance_agent"),
            ("business agent", "agents.business_agent"),
            ("conflict resolution", "agents.orchestrator.langgraph.conflict_resolution"),
            ("im agent", "agents.im_agent"),
            ("desktop sdk", "agents.client_agent"),
            ("dify bridge", "agents.dify_bridge"),
        ]
        for _name, module_path in modules_to_import:
            __import__(module_path)

    def test_graph_has_10_workers(self) -> None:
        """Graph should have 10 workers: 6 M1 + 4 M2 (compliance, business, im, map)."""
        from agents.orchestrator.langgraph.graph import build_orchestrator_graph
        from agents.orchestrator.langgraph.supervisor import WORKER_DESCRIPTIONS

        assert (
            len(WORKER_DESCRIPTIONS) == 10
        ), f"Expected 10 workers, got {len(WORKER_DESCRIPTIONS)}"
        graph = build_orchestrator_graph()
        assert graph is not None

    def test_no_dify_in_core_path(self) -> None:
        """Verify Dify is NOT in the core orchestration import chain."""
        import inspect

        from agents.orchestrator.langgraph.graph import build_orchestrator_graph

        source = inspect.getsource(build_orchestrator_graph)
        assert "dify" not in source.lower()

    def test_worker_outputs_accumulate_across_steps(self) -> None:
        """Multi-step plans should accumulate worker outputs, not replace them."""
        graph = _build_full_graph()
        result = graph.invoke(
            OrchestratorState(messages=[HumanMessage(content="检索知识库，检查合规性")])
        )
        outputs = result.get("worker_outputs", {})
        # Both rag and compliance should be present (not just the last one)
        assert (
            len(outputs) >= 2
        ), f"Expected >=2 accumulated outputs, got {len(outputs)}: {list(outputs.keys())}"
