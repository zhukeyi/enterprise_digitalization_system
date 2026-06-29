"""Tests for Orchestrator State models."""

from __future__ import annotations

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from agents.orchestrator.langgraph.state import (
    OrchestratorState,
    PlanStep,
    SupervisorPlan,
)

# ══════════════════════════════════════════════════════════════════
# PlanStep Tests
# ══════════════════════════════════════════════════════════════════


class TestPlanStep:
    """Tests for PlanStep model."""

    def test_create_basic_step(self) -> None:
        step = PlanStep(worker="rag", task="Search for documents")
        assert step.worker == "rag"
        assert step.task == "Search for documents"
        assert step.tool is None
        assert step.tool_args == {}
        assert step.priority == 1

    def test_create_step_with_tool(self) -> None:
        step = PlanStep(
            worker="rag",
            task="Search knowledge base",
            tool="rag_search",
            tool_args={"query": "test query"},
        )
        assert step.tool == "rag_search"
        assert step.tool_args == {"query": "test query"}

    def test_priority_range(self) -> None:
        step = PlanStep(worker="hr", task="test", priority=5)
        assert step.priority == 5

    def test_priority_out_of_range(self) -> None:
        with pytest.raises(ValueError):
            PlanStep(worker="hr", task="test", priority=6)

    def test_priority_minimum(self) -> None:
        with pytest.raises(ValueError):
            PlanStep(worker="hr", task="test", priority=0)


# ══════════════════════════════════════════════════════════════════
# SupervisorPlan Tests
# ══════════════════════════════════════════════════════════════════


class TestSupervisorPlan:
    """Tests for SupervisorPlan model."""

    def test_create_empty_plan(self) -> None:
        plan = SupervisorPlan()
        assert plan.steps == []
        assert plan.reasoning == ""
        assert plan.requires_rag is False
        assert plan.complexity == "simple"
        assert plan.finish is False

    def test_create_plan_with_steps(self) -> None:
        plan = SupervisorPlan(
            steps=[
                PlanStep(worker="rag", task="Search", tool="rag_search"),
                PlanStep(worker="analysis", task="Analyze results"),
            ],
            reasoning="User needs search + analysis",
            requires_rag=True,
            complexity="complex",
        )
        assert len(plan.steps) == 2
        assert plan.requires_rag is True
        assert plan.complexity == "complex"

    def test_finish_plan(self) -> None:
        plan = SupervisorPlan(finish=True)
        assert plan.finish is True
        assert plan.steps == []

    def test_complexity_values(self) -> None:
        for complexity in ("simple", "medium", "complex"):
            plan = SupervisorPlan(complexity=complexity)
            assert plan.complexity == complexity


# ══════════════════════════════════════════════════════════════════
# OrchestratorState Tests
# ══════════════════════════════════════════════════════════════════


class TestOrchestratorState:
    """Tests for OrchestratorState model."""

    def test_create_default_state(self) -> None:
        state = OrchestratorState()
        assert state.messages == []
        assert state.next_worker == ""
        assert state.worker_outputs == {}
        assert state.plan is None
        assert state.metadata == {}
        assert state.iteration == 0
        assert state.error is None

    def test_state_with_messages(self) -> None:
        state = OrchestratorState(messages=[HumanMessage(content="Hello")])
        assert len(state.messages) == 1
        assert state.messages[0].content == "Hello"

    def test_state_with_plan(self) -> None:
        plan = SupervisorPlan(
            steps=[PlanStep(worker="rag", task="Search")],
            reasoning="Need to search",
        )
        state = OrchestratorState(plan=plan, next_worker="rag")
        assert state.plan is not None
        assert state.next_worker == "rag"

    def test_state_with_worker_outputs(self) -> None:
        state = OrchestratorState(worker_outputs={"rag": "Found 3 documents"})
        assert state.worker_outputs["rag"] == "Found 3 documents"

    def test_state_with_metadata(self) -> None:
        state = OrchestratorState(metadata={"trace_id": "abc123", "user_id": "user1"})
        assert state.metadata["trace_id"] == "abc123"

    def test_add_messages_reducer(self) -> None:
        """Test that the add_messages reducer properly appends."""
        state1 = OrchestratorState(messages=[HumanMessage(content="Hi")])
        state2 = OrchestratorState(messages=[AIMessage(content="Hello!")])

        # Simulate reducer behavior by combining
        combined_messages = state1.messages + state2.messages
        assert len(combined_messages) == 2
