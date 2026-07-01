"""HR Agent — comprehensive test suite.

M3-T5-10: 30+ tests covering all HR modules:
- models: Pydantic model validation
- adapters: MockHRAdapter data access
- profiling: Employee profile generation
- matching: Person-job matching
- risk: Risk assessment
- redundancy: Redundancy analysis
- foolproof: Layoff simulation 5-step confirmation
- integration: Tool registration and dispatch
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from agents.hr_agent.adapters import (
    MockHRAdapter,
    get_hr_adapter,
    reset_hr_adapter,
)
from agents.hr_agent.foolproof import get_simulator
from agents.hr_agent.integration import register_hr_tools
from agents.hr_agent.matching import CompetencyModel, get_matcher
from agents.hr_agent.models import (
    Competency,
    Department,
    Employee,
    EmployeeCompetency,
    EmploymentStatus,
    LayoffPlanConfig,
    PerformanceRecord,
    Position,
    RiskLevel,
    RiskType,
)
from agents.hr_agent.profiling import get_profiler
from agents.hr_agent.redundancy import get_analyzer
from agents.hr_agent.risk_assessment import get_assessor
from agents.orchestrator.tools.registry import ToolRegistry

# ══════════════════════════════════════════════════════════════════
# Fixtures
# ══════════════════════════════════════════════════════════════════


def _run(coro: Any) -> Any:
    """Run an async coroutine synchronously, compatible with pytest-asyncio AUTO mode."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_closed():
            raise RuntimeError("loop closed")
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    return loop.run_until_complete(coro)


@pytest.fixture
def mock_adapter() -> MockHRAdapter:
    return MockHRAdapter()


@pytest.fixture
def sample_employees(mock_adapter: MockHRAdapter) -> list[Employee]:
    return _run(mock_adapter.get_employees())


@pytest.fixture
def sample_departments(mock_adapter: MockHRAdapter) -> list[Department]:
    return _run(mock_adapter.get_departments())


@pytest.fixture
def sample_positions(mock_adapter: MockHRAdapter) -> list[Position]:
    return _run(mock_adapter.get_positions())


@pytest.fixture(autouse=True)
def reset_adapter():
    """Reset adapter singleton after each test."""
    yield
    reset_hr_adapter()


# ══════════════════════════════════════════════════════════════════
# Test: Models
# ══════════════════════════════════════════════════════════════════


class TestModels:
    """Test Pydantic model validation and computed properties."""

    def test_employee_default_status(self):
        emp = Employee(employee_id="T1", name="Test")
        assert emp.employment_status == EmploymentStatus.ACTIVE
        assert emp.competencies == []
        assert emp.performance_history == []

    def test_employee_latest_performance(self):
        emp = Employee(
            employee_id="T2",
            name="Test",
            performance_history=[
                PerformanceRecord(period="2024-Q2", score=80),
                PerformanceRecord(period="2024-Q4", score=90),
            ],
        )
        latest = emp.latest_performance
        assert latest is not None
        assert latest.period == "2024-Q4"

    def test_employee_avg_performance(self):
        emp = Employee(
            employee_id="T3",
            name="Test",
            performance_history=[
                PerformanceRecord(period="2024-Q2", score=80),
                PerformanceRecord(period="2024-Q4", score=90),
            ],
        )
        assert emp.avg_performance_score == 85.0

    def test_employee_competency_summary(self):
        emp = Employee(
            employee_id="T4",
            name="Test",
            competencies=[
                EmployeeCompetency(competency_id="c1", level=4),
                EmployeeCompetency(competency_id="c2", level=2),
            ],
        )
        summary = emp.competency_summary
        assert summary == {"c1": 4, "c2": 2}

    def test_risk_level_enum(self):
        assert RiskLevel.LOW.value == "low"
        assert RiskLevel.CRITICAL.value == "critical"

    def test_employment_status_enum(self):
        assert EmploymentStatus.PROBATION.value == "probation"


# ══════════════════════════════════════════════════════════════════
# Test: Adapters
# ══════════════════════════════════════════════════════════════════


class TestAdapters:
    """Test MockHRAdapter data access."""

    def test_get_all_employees(self, sample_employees: list[Employee]):
        assert len(sample_employees) == 10
        assert all(isinstance(e, Employee) for e in sample_employees)

    def test_get_employee_by_id(self, mock_adapter: MockHRAdapter):
        emp = _run(
            mock_adapter.get_employee("EMP-001"),
        )
        assert emp is not None
        assert emp.name == "Zhang Wei"
        assert emp.department_id == "dept-eng"

    def test_get_employee_not_found(self, mock_adapter: MockHRAdapter):
        emp = _run(
            mock_adapter.get_employee("NONEXISTENT"),
        )
        assert emp is None

    def test_get_departments(self, sample_departments: list[Department]):
        assert len(sample_departments) == 3
        dept_ids = {d.dept_id for d in sample_departments}
        assert "dept-eng" in dept_ids
        assert "dept-sales" in dept_ids
        assert "dept-hr" in dept_ids

    def test_get_positions(self, sample_positions: list[Position]):
        assert len(sample_positions) == 3
        assert all(p.required_competencies for p in sample_positions)

    def test_filter_employees_by_department(self, mock_adapter: MockHRAdapter):
        eng_emps = _run(
            mock_adapter.get_employees(department_id="dept-eng"),
        )
        assert len(eng_emps) == 4
        assert all(e.department_id == "dept-eng" for e in eng_emps)

    def test_get_hr_adapter_singleton(self):
        adapter1 = get_hr_adapter()
        adapter2 = get_hr_adapter()
        assert adapter1 is adapter2


# ══════════════════════════════════════════════════════════════════
# Test: Profiling
# ══════════════════════════════════════════════════════════════════


class TestProfiling:
    """Test employee profile generation."""

    def test_profile_high_performer(self, sample_employees: list[Employee]):
        emp = next(e for e in sample_employees if e.employee_id == "EMP-001")
        profiler = get_profiler()
        profile = profiler.profile(emp)

        assert profile.employee_id == "EMP-001"
        assert profile.employee_name == "Zhang Wei"
        assert profile.avg_competency_level > 3.0
        assert profile.avg_performance_score > 85
        assert profile.stability_score > 50
        assert len(profile.summary) > 0

    def test_profile_low_performer(self, sample_employees: list[Employee]):
        emp = next(e for e in sample_employees if e.employee_id == "EMP-007")
        profiler = get_profiler()
        profile = profiler.profile(emp)

        assert "low_performance" in profile.risk_flags
        assert profile.avg_performance_score < 65

    def test_profile_probation_employee(self, sample_employees: list[Employee]):
        emp = next(e for e in sample_employees if e.employee_id == "EMP-003")
        profiler = get_profiler()
        profile = profiler.profile(emp)

        assert "on_probation" in profile.risk_flags
        assert profile.tenure_years < 1.0

    def test_performance_trend_improving(self):
        emp = Employee(
            employee_id="T5",
            name="Trend Test",
            performance_history=[
                PerformanceRecord(period="2024-Q1", score=70),
                PerformanceRecord(period="2024-Q2", score=75),
                PerformanceRecord(period="2024-Q3", score=82),
                PerformanceRecord(period="2024-Q4", score=90),
            ],
        )
        profiler = get_profiler()
        profile = profiler.profile(emp)
        assert profile.performance_trend == "improving"

    def test_performance_trend_declining(self):
        emp = Employee(
            employee_id="T6",
            name="Trend Test",
            performance_history=[
                PerformanceRecord(period="2024-Q1", score=90),
                PerformanceRecord(period="2024-Q2", score=85),
                PerformanceRecord(period="2024-Q3", score=78),
                PerformanceRecord(period="2024-Q4", score=70),
            ],
        )
        profiler = get_profiler()
        profile = profiler.profile(emp)
        assert profile.performance_trend == "declining"

    def test_stability_score_range(self, sample_employees: list[Employee]):
        profiler = get_profiler()
        for emp in sample_employees:
            profile = profiler.profile(emp)
            assert 0.0 <= profile.stability_score <= 100.0


# ══════════════════════════════════════════════════════════════════
# Test: Matching
# ══════════════════════════════════════════════════════════════════


class TestMatching:
    """Test person-job matching engine."""

    def test_strong_match(
        self,
        sample_employees: list[Employee],
        sample_positions: list[Position],
    ):
        # EMP-001 (Zhang Wei, P6, Python 5, Arch 4, Lead 3, ML 3)
        # vs POS-SSE-01 (requires Python 4, Arch 4, Lead 3, ML 3)
        emp = next(e for e in sample_employees if e.employee_id == "EMP-001")
        pos = next(p for p in sample_positions if p.position_id == "POS-SSE-01")

        matcher = get_matcher()
        result = matcher.match(emp, pos)

        assert result.overall_score >= 70.0
        assert result.gap_count == 0
        assert result.recommendation in ("strong_match", "match")

    def test_partial_match(
        self,
        sample_employees: list[Employee],
        sample_positions: list[Position],
    ):
        # EMP-003 (Wang Fang, junior, Python 2, React 2, Arch 1)
        # vs POS-SSE-01 (requires Python 4, Arch 4, Lead 3, ML 3)
        emp = next(e for e in sample_employees if e.employee_id == "EMP-003")
        pos = next(p for p in sample_positions if p.position_id == "POS-SSE-01")

        matcher = get_matcher()
        result = matcher.match(emp, pos)

        assert result.overall_score < 70.0
        assert result.gap_count > 0
        assert result.recommendation in ("partial_match", "no_match")

    def test_match_batch_sorted(
        self,
        sample_employees: list[Employee],
        sample_positions: list[Position],
    ):
        pos = next(p for p in sample_positions if p.position_id == "POS-SSE-01")
        matcher = get_matcher()
        results = matcher.match_batch(sample_employees, pos)

        # Verify sorted by score descending
        scores = [r.overall_score for r in results]
        assert scores == sorted(scores, reverse=True)

    def test_match_employee_to_positions(
        self,
        sample_employees: list[Employee],
        sample_positions: list[Position],
    ):
        emp = next(e for e in sample_employees if e.employee_id == "EMP-004")
        matcher = get_matcher()
        results = matcher.match_employee_to_positions(emp, sample_positions)

        assert len(results) == len(sample_positions)
        scores = [r.overall_score for r in results]
        assert scores == sorted(scores, reverse=True)

    def test_competency_model_registration(self):
        model = CompetencyModel()
        comp = Competency(
            competency_id="test-comp",
            name="Test Competency",
            category="technical",
            weight=2.0,
        )
        model.register(comp)
        assert model.get("test-comp") is not None
        assert model.get("nonexistent") is None


# ══════════════════════════════════════════════════════════════════
# Test: Risk Assessment
# ══════════════════════════════════════════════════════════════════


class TestRiskAssessment:
    """Test risk assessment engine."""

    def test_low_risk_employee(self, sample_employees: list[Employee]):
        # EMP-005 (Liu Yang, Sales Director, top performer, 5.5 years)
        emp = next(e for e in sample_employees if e.employee_id == "EMP-005")
        assessor = get_assessor()
        assessment = assessor.assess(emp)

        assert assessment.overall_risk_level in (RiskLevel.LOW, RiskLevel.MEDIUM)
        assert assessment.turnover_risk is not None
        assert assessment.compliance_risk is not None

    def test_high_risk_employee(self, sample_employees: list[Employee]):
        # EMP-007 (Sun Lei, low performance, short tenure, turnover_risk tag)
        emp = next(e for e in sample_employees if e.employee_id == "EMP-007")
        assessor = get_assessor()
        assessment = assessor.assess(emp)

        assert assessment.overall_risk_level in (RiskLevel.HIGH, RiskLevel.MEDIUM)
        assert assessment.overall_risk_score > 40.0

    def test_risk_dimensions_all_present(self, sample_employees: list[Employee]):
        emp = sample_employees[0]
        assessor = get_assessor()
        assessment = assessor.assess(emp)

        assert assessment.turnover_risk is not None
        assert assessment.turnover_risk.risk_type == RiskType.TURNOVER
        assert assessment.compliance_risk is not None
        assert assessment.compliance_risk.risk_type == RiskType.COMPLIANCE
        assert assessment.performance_risk is not None
        assert assessment.performance_risk.risk_type == RiskType.PERFORMANCE
        assert assessment.competency_gap_risk is not None
        assert assessment.competency_gap_risk.risk_type == RiskType.COMPETENCY_GAP

    def test_recommended_actions(self, sample_employees: list[Employee]):
        emp = next(e for e in sample_employees if e.employee_id == "EMP-007")
        assessor = get_assessor()
        assessment = assessor.assess(emp)

        assert len(assessment.recommended_actions) > 0

    def test_risk_score_range(self, sample_employees: list[Employee]):
        assessor = get_assessor()
        for emp in sample_employees:
            assessment = assessor.assess(emp)
            assert 0.0 <= assessment.overall_risk_score <= 100.0


# ══════════════════════════════════════════════════════════════════
# Test: Redundancy
# ══════════════════════════════════════════════════════════════════


class TestRedundancy:
    """Test redundancy analysis."""

    def test_analyze_engineering(
        self,
        sample_departments: list[Department],
        sample_employees: list[Employee],
    ):
        dept = next(d for d in sample_departments if d.dept_id == "dept-eng")
        eng_emps = [e for e in sample_employees if e.department_id == "dept-eng"]

        analyzer = get_analyzer()
        report = analyzer.analyze(dept, eng_emps)

        assert report.department_id == "dept-eng"
        assert report.total_headcount == 4
        assert 0.0 <= report.redundancy_rate <= 1.0
        assert len(report.summary) > 0

    def test_analyze_no_redundancy(
        self,
        sample_departments: list[Department],
        sample_employees: list[Employee],
    ):
        dept = next(d for d in sample_departments if d.dept_id == "dept-hr")
        hr_emps = [e for e in sample_employees if e.department_id == "dept-hr"]

        analyzer = get_analyzer()
        report = analyzer.analyze(dept, hr_emps)

        # HR dept has 2 actual HR employees (EMP-008, EMP-009) + CEO (EMP-010)
        # Different titles, so low overlap
        assert report.total_headcount >= 2

    def test_role_overlap_detection(
        self,
        sample_departments: list[Department],
        sample_employees: list[Employee],
    ):
        dept = next(d for d in sample_departments if d.dept_id == "dept-eng")
        eng_emps = [e for e in sample_employees if e.department_id == "dept-eng"]

        analyzer = get_analyzer()
        report = analyzer.analyze(dept, eng_emps)

        # Engineering has 2 "Software Engineer" level employees
        # (EMP-001 Senior SE, EMP-002 SE) — different titles
        # Only exact title matches count
        for ro in report.role_overlaps:
            assert ro.employee_count >= 2
            assert 0.0 <= ro.overlap_score <= 1.0


# ══════════════════════════════════════════════════════════════════
# Test: Foolproof (Layoff Simulation)
# ══════════════════════════════════════════════════════════════════


class TestFoolproof:
    """Test layoff simulation with 5-step foolproof."""

    def test_simulate_preview(
        self,
        sample_employees: list[Employee],
    ):
        config = LayoffPlanConfig(
            department_id="dept-eng",
            target_reduction=1,
            criteria=["performance", "tenure"],
        )
        eng_emps = [e for e in sample_employees if e.department_id == "dept-eng"]

        simulator = get_simulator()
        result = simulator.simulate(config, eng_emps)

        # Preview only — no changes made
        assert result.confirmed is False
        assert result.foolproof_completed is False
        assert result.foolproof_step == 1
        assert len(result.candidates) == 1
        assert result.total_affected == 1
        assert result.snapshot_id != ""
        assert len(result.plain_explanation) > 0

    def test_exclude_probation(
        self,
        sample_employees: list[Employee],
    ):
        config = LayoffPlanConfig(
            department_id="dept-eng",
            target_reduction=1,
            exclude_probation=True,
        )
        eng_emps = [e for e in sample_employees if e.department_id == "dept-eng"]

        simulator = get_simulator()
        result = simulator.simulate(config, eng_emps)

        # No probation employee in candidates
        for c in result.candidates:
            assert c.employee_id != "EMP-003"  # Wang Fang is on probation

    def test_severance_calculation(
        self,
        sample_employees: list[Employee],
    ):
        config = LayoffPlanConfig(
            department_id="dept-sales",
            target_reduction=1,
        )
        sales_emps = [e for e in sample_employees if e.department_id == "dept-sales"]

        simulator = get_simulator()
        result = simulator.simulate(config, sales_emps)

        assert result.total_severance_cost > 0

    def test_5_step_foolproof_full(
        self,
        sample_employees: list[Employee],
    ):
        config = LayoffPlanConfig(
            department_id="dept-eng",
            target_reduction=1,
        )
        eng_emps = [e for e in sample_employees if e.department_id == "dept-eng"]

        simulator = get_simulator()
        result = simulator.simulate(config, eng_emps)

        # Step 1: Reversibility
        step1 = simulator.check_reversibility(result)
        assert step1["step"] == 1
        assert "all_reversible" in step1

        # Step 2: Impact
        step2 = simulator.check_impact(result)
        assert step2["step"] == 2
        assert step2["total_affected"] == 1

        # Step 3: Explanation
        step3 = simulator.get_explanation(result)
        assert step3["step"] == 3
        assert len(step3["explanation"]) > 0

        # Step 4: Confirm with wrong keyword
        step4_wrong = simulator.confirm(result, "WRONG")
        assert step4_wrong["confirmed"] is False

        # Step 4: Confirm with correct keyword
        step4 = simulator.confirm(result, "CONFIRM_LAYOFF")
        assert step4["confirmed"] is True
        assert result.confirmed is True

        # Step 5: Snapshot
        step5 = simulator.create_snapshot(result)
        assert step5["completed"] is True
        assert result.foolproof_completed is True

    def test_no_confirmation_no_snapshot(
        self,
        sample_employees: list[Employee],
    ):
        config = LayoffPlanConfig(
            department_id="dept-eng",
            target_reduction=1,
        )
        eng_emps = [e for e in sample_employees if e.department_id == "dept-eng"]

        simulator = get_simulator()
        result = simulator.simulate(config, eng_emps)

        # Try to create snapshot without confirmation
        step5 = simulator.create_snapshot(result)
        assert "error" in step5
        assert result.foolproof_completed is False


# ══════════════════════════════════════════════════════════════════
# Test: Integration (Tool Registration)
# ══════════════════════════════════════════════════════════════════


class TestIntegration:
    """Test ToolRegistry integration."""

    def test_register_hr_tools(self):
        registry = ToolRegistry()
        register_hr_tools(registry)

        hr_tools = registry.get_tools_for_worker("hr")
        assert len(hr_tools) == 6

        tool_names = {t.name for t in hr_tools}
        assert "hr_employee_profile" in tool_names
        assert "hr_person_job_match" in tool_names
        assert "hr_risk_assessment" in tool_names
        assert "hr_redundancy_analysis" in tool_names
        assert "hr_layoff_simulation" in tool_names
        assert "hr_org_health" in tool_names

    def test_layoff_tool_is_dangerous(self):
        registry = ToolRegistry()
        register_hr_tools(registry)

        hr_tools = registry.get_tools_for_worker("hr")
        layoff_tool = next(t for t in hr_tools if t.name == "hr_layoff_simulation")
        assert layoff_tool.is_dangerous is True

    def test_dispatch_employee_profile(self):
        registry = ToolRegistry()
        register_hr_tools(registry)

        result = _run(
            registry.dispatch("hr_employee_profile", employee_id="EMP-001"),
        )
        assert result is not None
        assert "employee_id" in result
        assert result["employee_id"] == "EMP-001"

    def test_dispatch_person_job_match(self):
        registry = ToolRegistry()
        register_hr_tools(registry)

        result = _run(
            registry.dispatch(
                "hr_person_job_match",
                employee_id="EMP-001",
                position_id="POS-SSE-01",
            ),
        )
        assert result is not None
        assert "overall_score" in result
        assert result["overall_score"] > 0

    def test_dispatch_risk_assessment(self):
        registry = ToolRegistry()
        register_hr_tools(registry)

        result = _run(
            registry.dispatch("hr_risk_assessment", employee_id="EMP-007"),
        )
        assert result is not None
        assert "overall_risk_level" in result

    def test_dispatch_redundancy_analysis(self):
        registry = ToolRegistry()
        register_hr_tools(registry)

        result = _run(
            registry.dispatch("hr_redundancy_analysis", department_id="dept-eng"),
        )
        assert result is not None
        assert "total_headcount" in result
        assert result["total_headcount"] == 4

    def test_dispatch_layoff_simulation(self):
        registry = ToolRegistry()
        register_hr_tools(registry)

        result = _run(
            registry.dispatch(
                "hr_layoff_simulation",
                department_id="dept-eng",
                target_reduction=1,
            ),
        )
        assert result is not None
        assert result["confirmed"] is False
        assert result["foolproof_step"] == 1

    def test_dispatch_org_health(self):
        registry = ToolRegistry()
        register_hr_tools(registry)

        result = _run(
            registry.dispatch("hr_org_health", department_id="dept-eng"),
        )
        assert result is not None
        assert "health_score" in result
        assert 0.0 <= result["health_score"] <= 100.0

    def test_dispatch_missing_param(self):
        registry = ToolRegistry()
        register_hr_tools(registry)

        result = _run(
            registry.dispatch("hr_employee_profile"),
        )
        assert "error" in result

    def test_dispatch_employee_not_found(self):
        registry = ToolRegistry()
        register_hr_tools(registry)

        result = _run(
            registry.dispatch("hr_employee_profile", employee_id="NONEXISTENT"),
        )
        assert "error" in result
