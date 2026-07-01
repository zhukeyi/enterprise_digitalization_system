"""Tests for Conflict Detection, Resolution, and Response Generation (M2-T6)."""

from __future__ import annotations

from langchain_core.messages import HumanMessage

from agents.orchestrator.langgraph.conflict_resolution import (
    ConflictDetector,
    ConflictResolver,
    ResponseGenerator,
)
from agents.orchestrator.langgraph.state import OrchestratorState

# ══════════════════════════════════════════════════════════════════
# Helpers
# ══════════════════════════════════════════════════════════════════


def _make_state(worker_outputs: dict, messages: list | None = None) -> OrchestratorState:
    """Create a minimal state with given worker outputs."""
    return OrchestratorState(
        messages=messages or [HumanMessage(content="test query")],
        worker_outputs=worker_outputs,
    )


# ══════════════════════════════════════════════════════════════════
# ConflictDetector Tests
# ══════════════════════════════════════════════════════════════════


class TestConflictDetector:
    def test_no_conflicts_single_worker(self) -> None:
        """Single worker should produce no conflicts."""
        detector = ConflictDetector()
        state = _make_state({"rag": {"total_results": 5, "results": []}})
        result = detector(state)
        assert result["conflicts"] == []

    def test_no_conflicts_harmonious_outputs(self) -> None:
        """Workers with non-conflicting outputs should pass clean."""
        detector = ConflictDetector()
        state = _make_state(
            {
                "rag": {"total_results": 10, "note": "mock"},
                "analysis": {"confidence": 0.9, "note": "mock"},
            }
        )
        result = detector(state)
        assert result["conflicts"] == []

    def test_status_conflict_detected(self) -> None:
        """Different status values should trigger status conflict."""
        detector = ConflictDetector()
        state = _make_state(
            {
                "compliance": {"overall_status": "compliant"},
                "business_system": {"overall_status": "degraded"},
            }
        )
        result = detector(state)
        assert len(result["conflicts"]) >= 1
        conflict = result["conflicts"][0]
        assert conflict.severity == "medium"
        assert "status" in conflict.field

    def test_numeric_conflict_large_discrepancy(self) -> None:
        """Large numeric difference should trigger conflict."""
        detector = ConflictDetector()
        state = _make_state(
            {
                "data": {"count": 100},
                "rag": {"count": 10},  # 10x difference
            }
        )
        result = detector(state)
        # 50% threshold: (100-10)/100 = 0.9 > 0.5 → conflict
        assert len(result["conflicts"]) >= 1
        assert result["conflicts"][0].field == "count"

    def test_numeric_close_values_no_conflict(self) -> None:
        """Small numeric differences should not trigger conflict."""
        detector = ConflictDetector()
        state = _make_state(
            {
                "data": {"count": 100},
                "rag": {"count": 90},  # only 10% diff
            }
        )
        result = detector(state)
        assert result["conflicts"] == []

    def test_coverage_conflict(self) -> None:
        """One worker finding results and another finding none."""
        detector = ConflictDetector()
        state = _make_state(
            {
                "rag": {"total_results": 5},
                "business_system": {"count": 0},
            }
        )
        result = detector(state)
        assert len(result["conflicts"]) >= 1
        assert "Coverage conflict" in result["conflicts"][0].description

    def test_risk_conflict(self) -> None:
        """Different risk assessments should trigger conflict."""
        detector = ConflictDetector()
        state = _make_state(
            {
                "compliance": {"risk_level": "low", "checks": {}},
                "hr": {"risk_level": "high", "checks": {}},
            }
        )
        result = detector(state)
        assert len(result["conflicts"]) >= 1
        assert "Risk level conflict" in result["conflicts"][0].description

    def test_empty_worker_outputs(self) -> None:
        """Empty outputs should not crash."""
        detector = ConflictDetector()
        state = _make_state({})
        result = detector(state)
        assert result["conflicts"] == []

    def test_string_worker_outputs(self) -> None:
        """String outputs (non-dict) should not crash."""
        detector = ConflictDetector()
        state = _make_state(
            {
                "router": "Simple response",
                "rag": {"total_results": 3},
            }
        )
        result = detector(state)
        # router's string output shouldn't trigger false conflicts
        assert len(result["conflicts"]) == 0


# ══════════════════════════════════════════════════════════════════
# ConflictResolver Tests
# ══════════════════════════════════════════════════════════════════


class TestConflictResolver:
    def test_no_conflicts_noop(self) -> None:
        """No conflicts should produce no resolutions."""
        resolver = ConflictResolver()
        state = _make_state({"rag": {"ok": True}})
        state.conflicts = []
        result = resolver(state)
        assert result["conflict_resolutions"] == []
        assert result["conflict_resolved"] is True

    def test_resolve_by_source_priority(self) -> None:
        """Status conflict should use source priority (compliance wins)."""
        from agents.orchestrator.langgraph.state import ConflictReport

        resolver = ConflictResolver()
        state = _make_state(
            {
                "rag": {"status": "ok"},
                "compliance": {"status": "warning"},
            }
        )
        state.conflicts = [
            ConflictReport(
                conflict_id="c-001",
                source_workers=["rag", "compliance"],
                description="Status conflict",
                severity="medium",
                field="status",
                resolution_strategy="source_priority",
            )
        ]

        result = resolver(state)
        assert len(result["conflict_resolutions"]) == 1
        resolution = result["conflict_resolutions"][0]
        assert resolution.resolved is True
        # compliance has higher priority than rag (10 > 8)
        assert resolution.chosen_worker == "compliance"
        assert "priority" in resolution.reasoning

    def test_resolve_by_highest_confidence(self) -> None:
        """Numeric conflict should pick highest confidence worker."""
        from agents.orchestrator.langgraph.state import ConflictReport

        resolver = ConflictResolver()
        state = _make_state(
            {
                "data": {"count": 100, "confidence": 0.6},
                "analysis": {"count": 50, "confidence": 0.95},
            }
        )
        state.conflicts = [
            ConflictReport(
                conflict_id="c-002",
                source_workers=["data", "analysis"],
                description="Numeric conflict in count",
                severity="medium",
                field="count",
                resolution_strategy="highest_confidence",
            )
        ]

        result = resolver(state)
        resolution = result["conflict_resolutions"][0]
        assert resolution.chosen_worker == "analysis"
        assert resolution.chosen_value == 50

    def test_resolve_by_merge(self) -> None:
        """Coverage conflict should merge results."""
        from agents.orchestrator.langgraph.state import ConflictReport

        resolver = ConflictResolver()
        state = _make_state(
            {
                "rag": {
                    "total_results": 2,
                    "results": [
                        {"title": "doc1", "content": "a"},
                        {"title": "doc2", "content": "b"},
                    ],
                },
                "business_system": {
                    "count": 0,
                    "sample": [],
                },
            }
        )
        state.conflicts = [
            ConflictReport(
                conflict_id="c-003",
                source_workers=["rag", "business_system"],
                description="Coverage conflict",
                severity="low",
                field="total_results",
                resolution_strategy="merge",
            )
        ]

        result = resolver(state)
        resolution = result["conflict_resolutions"][0]
        assert resolution.resolved is True
        assert isinstance(resolution.chosen_value, dict)
        assert "merged" in resolution.reasoning.lower()

    def test_all_resolved_flag(self) -> None:
        """Multiple conflicts should all be resolved."""
        from agents.orchestrator.langgraph.state import ConflictReport

        resolver = ConflictResolver()
        state = _make_state(
            {
                "compliance": {"status": "ok"},
                "business_system": {"status": "degraded"},
            }
        )
        state.conflicts = [
            ConflictReport(
                conflict_id=f"c-{i}",
                source_workers=["compliance", "business_system"],
                description=f"Conflict {i}",
                severity="medium",
                field="status",
                resolution_strategy="source_priority",
            )
            for i in range(3)
        ]

        result = resolver(state)
        assert len(result["conflict_resolutions"]) == 3
        assert result["conflict_resolved"] is True


# ══════════════════════════════════════════════════════════════════
# ResponseGenerator Tests
# ══════════════════════════════════════════════════════════════════


class TestResponseGenerator:
    def test_generate_basic_response(self) -> None:
        """Should generate a response from single worker output."""
        gen = ResponseGenerator()
        state = _make_state(
            {"rag": {"total_results": 5, "results": [], "note": "mock"}},
            [HumanMessage(content="search for docs")],
        )

        result = gen(state)
        assert result["final_response"] != ""
        assert "rag" in result["final_response"]
        assert len(result["messages"]) == 1

    def test_generate_with_multiple_workers(self) -> None:
        """Should aggregate outputs from multiple workers."""
        gen = ResponseGenerator()
        state = _make_state(
            {
                "rag": {"total_results": 3, "note": "mock"},
                "compliance": {
                    "overall_status": "compliant",
                    "domains": {"access_control": {"status": "compliant"}},
                },
            },
            [HumanMessage(content="search and check")],
        )

        result = gen(state)
        response = result["final_response"]
        assert "rag" in response
        assert "compliance" in response

    def test_generate_with_conflicts(self) -> None:
        """Should include conflict resolution info in response."""
        from agents.orchestrator.langgraph.state import ConflictReport, ConflictResolution

        gen = ResponseGenerator()
        state = _make_state(
            {
                "compliance": {"status": "compliant"},
                "business_system": {"status": "degraded"},
            },
        )
        state.conflicts = [
            ConflictReport(
                conflict_id="c-1",
                source_workers=["compliance", "business_system"],
                description="Status mismatch",
                severity="medium",
                field="status",
                resolution_strategy="source_priority",
            )
        ]
        state.conflict_resolutions = [
            ConflictResolution(
                conflict_id="c-1",
                resolved=True,
                chosen_worker="compliance",
                chosen_value="compliant",
                reasoning="Priority: compliance (10) > business_system (4)",
            )
        ]

        result = gen(state)
        response = result["final_response"]
        assert "冲突" in response  # Chinese text
        assert "compliance" in response

    def test_generate_empty_outputs(self) -> None:
        """Empty outputs should produce a fallback message."""
        gen = ResponseGenerator()
        state = _make_state({})
        result = gen(state)
        assert result["final_response"] != ""
        assert "未能获取" in result["final_response"]

    def test_response_with_healthy_statuses(self) -> None:
        """All healthy statuses should produce positive verdict."""
        gen = ResponseGenerator()
        state = _make_state(
            {
                "compliance": {"overall_status": "compliant"},
                "business_system": {"overall_status": "healthy"},
            },
        )
        result = gen(state)
        assert "正常" in result["final_response"]

    def test_response_with_degraded_status(self) -> None:
        """Degraded status should produce warning verdict."""
        gen = ResponseGenerator()
        state = _make_state(
            {
                "business_system": {"overall_status": "degraded"},
            },
        )
        result = gen(state)
        assert "告警" in result["final_response"]


# ══════════════════════════════════════════════════════════════════
# State Model Tests (M2-T6 fields)
# ══════════════════════════════════════════════════════════════════


class TestM2T6State:
    def test_state_has_conflict_fields(self) -> None:
        """OrchestratorState should have M2-T6 conflict fields."""
        state = OrchestratorState(
            messages=[HumanMessage(content="test")],
        )
        assert hasattr(state, "conflicts")
        assert hasattr(state, "conflict_resolved")
        assert hasattr(state, "conflict_resolutions")
        assert hasattr(state, "final_response")
        assert state.conflicts == []
        assert state.conflict_resolved is False
        assert state.final_response == ""

    def test_conflict_report_creation(self) -> None:
        """ConflictReport model should be instantiable."""
        from agents.orchestrator.langgraph.state import ConflictReport

        report = ConflictReport(
            conflict_id="c-123",
            source_workers=["rag", "analysis"],
            description="Test conflict",
            severity="high",
            field="count",
            resolution_strategy="highest_confidence",
        )
        assert report.conflict_id == "c-123"
        assert report.severity == "high"
        assert len(report.source_workers) == 2

    def test_conflict_resolution_creation(self) -> None:
        """ConflictResolution model should be instantiable."""
        from agents.orchestrator.langgraph.state import ConflictResolution

        resolution = ConflictResolution(
            conflict_id="c-123",
            resolved=True,
            chosen_worker="rag",
            chosen_value=42,
            reasoning="rag had highest confidence score of 0.95",
        )
        assert resolution.conflict_id == "c-123"
        assert resolution.resolved is True
        assert resolution.chosen_value == 42


# ══════════════════════════════════════════════════════════════════
# P0 Bug-Regression Tests (added during M2-T6 Review)
# ══════════════════════════════════════════════════════════════════


class TestP0RegressionFixes:
    """Tests that verify fixes for P0 bugs found in code review."""

    def test_falsy_status_not_missed(self) -> None:
        """P0: empty string '' as status should NOT be treated as missing.

        Bug: `output.get("status") or output.get("overall_status")`
        treated "" as falsy, skipping status conflict detection.
        """
        detector = ConflictDetector()
        state = _make_state(
            {
                "worker_a": {"status": ""},
                "worker_b": {"status": "healthy"},
            }
        )
        result = detector(state)
        # Two workers with different statuses ("" vs "healthy") should conflict
        assert len(result["conflicts"]) >= 1

    def test_zero_values_no_division_by_zero(self) -> None:
        """P0: numeric conflict with all-zero values should not crash."""
        detector = ConflictDetector()
        state = _make_state(
            {
                "a": {"count": 0},
                "b": {"count": 0},
            }
        )
        result = detector(state)
        # Zero values with ratio 0/0 should not trigger conflict
        assert len(result["conflicts"]) == 0

    def test_merge_does_not_mutate_original(self) -> None:
        """P0: merge should deep-copy entries, not mutate in-place.

        Bug: `entry["_source_worker"] = worker` modified the original
        dict in `state.worker_outputs`.
        """
        from agents.orchestrator.langgraph.state import ConflictReport

        original_result = [
            {"title": "doc1", "content": "a"},
            {"title": "doc2", "content": "b"},
        ]

        resolver = ConflictResolver()
        state = _make_state(
            {
                "rag": {
                    "results": list(original_result),  # copy for comparison
                    "total_results": 2,
                },
            }
        )
        state.conflicts = [
            ConflictReport(
                conflict_id="c-p0",
                source_workers=["rag"],
                description="Test",
                severity="low",
                field="total_results",
                resolution_strategy="merge",
            )
        ]

        result = resolver(state)
        resolution = result["conflict_resolutions"][0]

        # Original data should NOT be mutated
        assert "_source_worker" not in original_result[0]
        assert "_source_worker" not in original_result[1]

        # Resolved value should have source tags
        assert resolution.chosen_value["total_merged"] == 2

    def test_response_messages_are_ai_message(self) -> None:
        """P0: messages should be AIMessage objects, not raw strings.

        Bug: `"messages": [final_response]` put raw strings in the list,
        incompatible with LangGraph's add_messages reducer.
        """
        from langchain_core.messages import AIMessage

        gen = ResponseGenerator()
        state = _make_state({"rag": {"total_results": 1}})
        result = gen(state)

        msgs = result["messages"]
        assert len(msgs) == 1
        assert isinstance(msgs[0], AIMessage)
        assert msgs[0].content == result["final_response"]


class TestP1RobustnessFixes:
    """Tests that verify P1 robustness improvements from code review."""

    def test_confidence_fallback_when_no_scores(self) -> None:
        """P1: when no worker has confidence/score, fall back to first worker."""
        from agents.orchestrator.langgraph.state import ConflictReport

        resolver = ConflictResolver()
        state = _make_state(
            {
                "a": {"count": 100},  # no confidence field
                "b": {"count": 150},  # no confidence field
            }
        )
        state.conflicts = [
            ConflictReport(
                conflict_id="c-p1",
                source_workers=["a", "b"],
                description="No confidence scores",
                severity="medium",
                field="count",
                resolution_strategy="highest_confidence",
            )
        ]

        result = resolver(state)
        resolution = result["conflict_resolutions"][0]
        assert resolution.resolved is True
        assert "fallback" in resolution.reasoning

    def test_empty_workers_in_resolver(self) -> None:
        """P1: empty source_workers in ConflictReport should not crash."""
        from agents.orchestrator.langgraph.state import ConflictReport

        resolver = ConflictResolver()
        state = _make_state({"a": {"ok": True}})
        state.conflicts = [
            ConflictReport(
                conflict_id="c-empty",
                source_workers=[],  # empty list
                description="Test",
                severity="low",
                field="x",
                resolution_strategy="source_priority",
            )
        ]

        result = resolver(state)
        resolution = result["conflict_resolutions"][0]
        assert resolution.resolved is True
        assert resolution.chosen_worker == ""

    def test_unknown_status_falls_to_default(self) -> None:
        """P1: unknown status value should not trigger wrong verdict."""
        gen = ResponseGenerator()
        state = _make_state({"worker": {"overall_status": "running"}})  # not in old list
        result = gen(state)
        assert "正常" in result["final_response"]

    def test_verdict_with_mixed_unknown_statuses(self) -> None:
        """Multiple unknown statuses should use default verdict."""
        gen = ResponseGenerator()
        state = _make_state(
            {
                "a": {"overall_status": "initializing"},
                "b": {"overall_status": "pending"},
            }
        )
        result = gen(state)
        # Should not crash and should produce a response
        assert len(result["final_response"]) > 0
        assert "正常" not in result["final_response"]
        assert "告警" not in result["final_response"]
        assert "严重" not in result["final_response"]
