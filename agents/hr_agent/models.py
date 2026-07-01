"""HR Agent — Pydantic data models for the HR intelligent decision engine.

Defines the data contracts for employee profiling, competency modeling,
person-job matching, risk assessment, redundancy analysis, and layoff simulation.

M3-T5: HR 智能决策层
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

# ══════════════════════════════════════════════════════════════════
# Enums
# ══════════════════════════════════════════════════════════════════


class EmploymentStatus(StrEnum):
    """Employee employment status."""

    ACTIVE = "active"
    PROBATION = "probation"
    LEAVE = "leave"
    RESIGNED = "resigned"
    TERMINATED = "terminated"


class RiskLevel(StrEnum):
    """Risk severity level."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class RiskType(StrEnum):
    """Types of HR risks."""

    TURNOVER = "turnover"  # 离职风险
    COMPLIANCE = "compliance"  # 合规风险
    PERFORMANCE = "performance"  # 绩效风险
    COMPETENCY_GAP = "competency_gap"  # 能力缺口


class CompetencyLevel(StrEnum):
    """Competency proficiency level (1-5 scale)."""

    NOVICE = "novice"  # 1 — 初学者
    ADVANCED_BEGINNER = "advanced_beginner"  # 2 — 进阶初学者
    COMPETENT = "competent"  # 3 — 胜任
    PROFICIENT = "proficient"  # 4 — 熟练
    EXPERT = "expert"  # 5 — 专家


# ══════════════════════════════════════════════════════════════════
# Core Domain Models
# ══════════════════════════════════════════════════════════════════


class Department(BaseModel):
    """Organizational department."""

    dept_id: str = Field(description="Unique department identifier")
    name: str = Field(description="Department name")
    parent_dept_id: str | None = Field(default=None, description="Parent department ID")
    head_count: int = Field(default=0, ge=0, description="Total headcount")
    budget: float = Field(default=0.0, ge=0.0, description="Annual budget (CNY)")
    cost_center: str = Field(default="", description="Cost center code")


class Competency(BaseModel):
    """A single competency dimension (skill/ability)."""

    competency_id: str = Field(description="Unique competency identifier")
    name: str = Field(description="Competency name (e.g., 'Python', 'Leadership')")
    category: str = Field(
        default="technical",
        description="technical, soft_skill, leadership, domain",
    )
    weight: float = Field(
        default=1.0,
        ge=0.0,
        le=10.0,
        description="Importance weight for this competency",
    )


class EmployeeCompetency(BaseModel):
    """An employee's assessed level for a specific competency."""

    competency_id: str
    competency_name: str = Field(default="")
    level: int = Field(
        ge=1,
        le=5,
        description="Proficiency level 1-5 (novice to expert)",
    )
    assessed_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    assessed_by: str = Field(default="system")
    evidence: str = Field(default="", description="Supporting evidence / notes")


class PerformanceRecord(BaseModel):
    """A single performance evaluation record."""

    period: str = Field(description="Evaluation period (e.g., '2025-Q4')")
    score: float = Field(
        ge=0.0,
        le=100.0,
        description="Performance score (0-100)",
    )
    rating: str = Field(
        default="",
        description="Letter rating: A/B/C/D/E or 'excellent'/'meets'/'below'",
    )
    reviewer_id: str = Field(default="")
    comments: str = Field(default="")
    goals_met: bool = Field(default=True)


class Employee(BaseModel):
    """A full employee record for HR analysis.

    Contains identity, role, compensation, competency matrix, performance
    history, and employment metadata.
    """

    employee_id: str = Field(description="Unique employee identifier")
    name: str = Field(description="Employee full name")
    email: str = Field(default="")
    phone: str = Field(default="")

    # Organizational data
    department_id: str = Field(default="", description="Department ID")
    department_name: str = Field(default="", description="Department name")
    title: str = Field(default="", description="Job title")
    level: str = Field(default="", description="Job level (e.g., P5, M2)")
    manager_id: str = Field(default="", description="Direct manager ID")
    employment_status: EmploymentStatus = Field(default=EmploymentStatus.ACTIVE)

    # Tenure
    hire_date: datetime = Field(default_factory=lambda: datetime.now(UTC))
    years_of_service: float = Field(default=0.0, ge=0.0)

    # Compensation
    annual_salary: float = Field(default=0.0, ge=0.0, description="Annual salary (CNY)")
    bonus_percentage: float = Field(
        default=0.0,
        ge=0.0,
        description="Target bonus as % of salary",
    )

    # Competency & Performance
    competencies: list[EmployeeCompetency] = Field(default_factory=list)
    performance_history: list[PerformanceRecord] = Field(default_factory=list)

    # Metadata
    tags: list[str] = Field(default_factory=list, description="Custom tags")
    metadata: dict[str, Any] = Field(default_factory=dict)

    @property
    def latest_performance(self) -> PerformanceRecord | None:
        """Get the most recent performance record."""
        if not self.performance_history:
            return None
        return max(self.performance_history, key=lambda p: p.period)

    @property
    def avg_performance_score(self) -> float:
        """Average performance score across all records."""
        if not self.performance_history:
            return 0.0
        scores = [p.score for p in self.performance_history]
        return sum(scores) / len(scores)

    @property
    def competency_summary(self) -> dict[str, int]:
        """Map competency_id → level for quick lookup."""
        return {c.competency_id: c.level for c in self.competencies}


class Position(BaseModel):
    """A job position with competency requirements."""

    position_id: str = Field(description="Unique position identifier")
    title: str = Field(description="Position title")
    department_id: str = Field(default="")
    level: str = Field(default="", description="Required job level")
    description: str = Field(default="")

    # Required competencies with minimum levels
    required_competencies: list[CompetencyRequirement] = Field(default_factory=list)

    # Compensation range
    salary_min: float = Field(default=0.0, ge=0.0)
    salary_max: float = Field(default=0.0, ge=0.0)

    # Headcount
    headcount: int = Field(default=1, ge=1, description="Open positions")


class CompetencyRequirement(BaseModel):
    """A competency requirement for a position."""

    competency_id: str
    competency_name: str = Field(default="")
    min_level: int = Field(
        default=3,
        ge=1,
        le=5,
        description="Minimum required proficiency level",
    )
    weight: float = Field(
        default=1.0,
        ge=0.0,
        le=10.0,
        description="Importance weight for this requirement",
    )


# ══════════════════════════════════════════════════════════════════
# Analysis Result Models
# ══════════════════════════════════════════════════════════════════


class EmployeeProfile(BaseModel):
    """Generated employee profile — comprehensive analysis output.

    Aggregates competency matrix, performance trends, stability score,
    and risk indicators into a single view.
    """

    employee_id: str
    employee_name: str = Field(default="")
    department: str = Field(default="")
    title: str = Field(default="")

    # Competency matrix
    competency_count: int = Field(default=0)
    avg_competency_level: float = Field(default=0.0, ge=0.0, le=5.0)
    top_competencies: list[EmployeeCompetency] = Field(default_factory=list)
    competency_gaps: list[str] = Field(
        default_factory=list,
        description="Competency IDs below required level",
    )

    # Performance trends
    performance_trend: str = Field(
        default="stable",
        description="improving, stable, declining, volatile",
    )
    avg_performance_score: float = Field(default=0.0, ge=0.0, le=100.0)
    latest_rating: str = Field(default="")

    # Stability
    tenure_years: float = Field(default=0.0, ge=0.0)
    stability_score: float = Field(
        default=0.0,
        ge=0.0,
        le=100.0,
        description="Stability score (higher = more stable)",
    )

    # Risk indicators
    risk_flags: list[str] = Field(default_factory=list)

    # Summary
    summary: str = Field(default="")


class MatchResult(BaseModel):
    """Person-job matching result for a single employee-position pair."""

    employee_id: str
    employee_name: str = Field(default="")
    position_id: str
    position_title: str = Field(default="")

    overall_score: float = Field(
        ge=0.0,
        le=100.0,
        description="Overall match score (0-100)",
    )
    competency_scores: list[CompetencyMatchScore] = Field(default_factory=list)
    gap_count: int = Field(default=0, description="Number of unmet requirements")
    gaps: list[str] = Field(default_factory=list, description="Competency gap descriptions")
    recommendation: str = Field(
        default="",
        description="strong_match, match, partial_match, no_match",
    )
    notes: str = Field(default="")


class CompetencyMatchScore(BaseModel):
    """Score for a single competency in a person-job match."""

    competency_id: str
    competency_name: str = Field(default="")
    required_level: int = Field(ge=1, le=5)
    actual_level: int = Field(ge=0, le=5, description="0 = competency not assessed")
    meets_requirement: bool = True
    gap: int = Field(default=0, ge=0, description="Level gap (required - actual)")
    weighted_score: float = Field(default=0.0, ge=0.0)


class RiskAssessment(BaseModel):
    """Comprehensive risk assessment for an employee."""

    employee_id: str
    employee_name: str = Field(default="")
    overall_risk_level: RiskLevel = Field(default=RiskLevel.LOW)
    overall_risk_score: float = Field(
        default=0.0,
        ge=0.0,
        le=100.0,
        description="Composite risk score (higher = more risky)",
    )

    # Individual risk dimensions
    turnover_risk: RiskDimension | None = Field(default=None)
    compliance_risk: RiskDimension | None = Field(default=None)
    performance_risk: RiskDimension | None = Field(default=None)
    competency_gap_risk: RiskDimension | None = Field(default=None)

    # Mitigation
    recommended_actions: list[str] = Field(default_factory=list)
    assessment_date: datetime = Field(default_factory=lambda: datetime.now(UTC))
    summary: str = Field(default="")


class RiskDimension(BaseModel):
    """A single risk dimension within a risk assessment."""

    risk_type: RiskType
    level: RiskLevel
    score: float = Field(ge=0.0, le=100.0)
    factors: list[str] = Field(default_factory=list, description="Contributing factors")
    description: str = Field(default="")


class RedundancyReport(BaseModel):
    """Department-level redundancy analysis report."""

    department_id: str
    department_name: str = Field(default="")

    # Headcount
    total_headcount: int = Field(default=0, ge=0)
    redundant_count: int = Field(default=0, ge=0)
    redundancy_rate: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Redundant / total",
    )

    # Role overlap
    role_overlaps: list[RoleOverlap] = Field(default_factory=list)

    # Cost impact
    estimated_savings: float = Field(
        default=0.0,
        ge=0.0,
        description="Estimated annual savings if redundancy addressed (CNY)",
    )

    # Recommendations
    recommendations: list[str] = Field(default_factory=list)
    summary: str = Field(default="")


class RoleOverlap(BaseModel):
    """Detected role overlap within a department."""

    role_title: str = Field(description="Overlapping job title")
    employee_ids: list[str] = Field(default_factory=list)
    employee_count: int = Field(default=0, ge=0)
    overlap_score: float = Field(
        ge=0.0,
        le=1.0,
        description="0 = no overlap, 1 = complete overlap",
    )
    suggested_action: str = Field(
        default="",
        description="merge, reassign, retain, train",
    )


# ══════════════════════════════════════════════════════════════════
# Layoff Simulation Models (with foolproof)
# ══════════════════════════════════════════════════════════════════


class LayoffPlanConfig(BaseModel):
    """Configuration for a layoff simulation plan."""

    department_id: str = Field(description="Target department")
    target_reduction: int = Field(
        ge=1,
        description="Number of positions to reduce",
    )
    criteria: list[str] = Field(
        default_factory=list,
        description="Selection criteria: performance, tenure, competency, cost",
    )
    exclude_probation: bool = Field(
        default=True,
        description="Exclude employees on probation (legally protected)",
    )
    min_severance_budget: float = Field(
        default=0.0,
        ge=0.0,
        description="Minimum severance budget available (CNY)",
    )


class LayoffCandidate(BaseModel):
    """A candidate for layoff selection."""

    employee_id: str
    employee_name: str = Field(default="")
    department: str = Field(default="")
    title: str = Field(default="")
    annual_salary: float = Field(default=0.0, ge=0.0)
    years_of_service: float = Field(default=0.0, ge=0.0)
    performance_score: float = Field(default=0.0, ge=0.0, le=100.0)
    risk_level: RiskLevel = Field(default=RiskLevel.LOW)
    selection_reason: str = Field(default="")
    severance_cost: float = Field(default=0.0, ge=0.0)
    is_reversible: bool = Field(
        default=True,
        description="Whether this layoff can be reversed",
    )
    legal_risk: str = Field(default="low", description="low, medium, high")


class LayoffSimulationResult(BaseModel):
    """Result of a layoff simulation.

    This is a PREVIEW only — no actual changes are made.
    The foolproof mechanism requires explicit confirmation before
    any action is taken.
    """

    plan_config: LayoffPlanConfig
    candidates: list[LayoffCandidate] = Field(default_factory=list)
    total_affected: int = Field(default=0, ge=0)
    total_severance_cost: float = Field(default=0.0, ge=0.0)
    estimated_annual_savings: float = Field(default=0.0, ge=0.0)
    net_first_year_savings: float = Field(default=0.0, ge=0.0)

    # Risk assessment
    legal_risk_summary: str = Field(default="")
    morale_impact: str = Field(default="medium", description="low, medium, high")
    key_personnel_risk: list[str] = Field(
        default_factory=list,
        description="IDs of high-impact employees in candidate list",
    )

    # Foolproof status
    foolproof_step: int = Field(
        default=1,
        ge=1,
        le=5,
        description="Current step in 5-step foolproof process",
    )
    foolproof_completed: bool = Field(default=False)
    confirmed: bool = Field(default=False, description="User has explicitly confirmed")

    # Snapshot reference
    snapshot_id: str = Field(default="", description="Org snapshot ID for rollback")

    # Plain-language explanation
    plain_explanation: str = Field(default="")

    summary: str = Field(default="")


# ══════════════════════════════════════════════════════════════════
# Org Health Report
# ══════════════════════════════════════════════════════════════════


class OrgHealthReport(BaseModel):
    """Organizational health report for a department."""

    department_id: str
    department_name: str = Field(default="")

    # Headcount metrics
    total_employees: int = Field(default=0, ge=0)
    avg_tenure: float = Field(default=0.0, ge=0.0)
    avg_performance: float = Field(default=0.0, ge=0.0, le=100.0)
    avg_salary: float = Field(default=0.0, ge=0.0)

    # Risk distribution
    high_risk_count: int = Field(default=0, ge=0)
    medium_risk_count: int = Field(default=0, ge=0)
    low_risk_count: int = Field(default=0, ge=0)

    # Competency
    avg_competency_level: float = Field(default=0.0, ge=0.0, le=5.0)
    critical_gaps: list[str] = Field(default_factory=list)

    # Health score
    health_score: float = Field(
        default=0.0,
        ge=0.0,
        le=100.0,
        description="Overall department health (higher = healthier)",
    )
    health_grade: str = Field(default="B", description="A/B/C/D/E")

    # Insights
    strengths: list[str] = Field(default_factory=list)
    concerns: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)

    summary: str = Field(default="")
