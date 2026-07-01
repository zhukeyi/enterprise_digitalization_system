"""HR Agent — intelligent HR decision engine.

M3-T5: HR 系统对接 + 员工画像 + 人岗匹配 + 飞险评估 + 冗余分析

Modules:
- models: Pydantic data models (Employee, Position, RiskAssessment, etc.)
- adapters: HR system data source adapters (Mock + Workday stub)
- profiling: Employee profiling engine (competency, performance, stability)
- matching: Competency model + person-job matching engine
- risk_assessment: Multi-dimension risk assessment (turnover, compliance, etc.)
- redundancy: Department redundancy analysis and optimization
- foolproof: Layoff simulation with 5-step foolproof confirmation
- integration: ToolRegistry registration (6 tools)
"""

from agents.hr_agent.adapters import (
    BaseHRAdapter,
    MockHRAdapter,
    WorkdayAdapter,
    get_hr_adapter,
    reset_hr_adapter,
    set_hr_adapter,
)
from agents.hr_agent.foolproof import LayoffSimulator, get_simulator
from agents.hr_agent.matching import CompetencyModel, PersonJobMatcher, get_matcher
from agents.hr_agent.models import (
    Competency,
    CompetencyMatchScore,
    CompetencyRequirement,
    Department,
    Employee,
    EmployeeCompetency,
    EmployeeProfile,
    EmploymentStatus,
    LayoffCandidate,
    LayoffPlanConfig,
    LayoffSimulationResult,
    MatchResult,
    OrgHealthReport,
    PerformanceRecord,
    Position,
    RedundancyReport,
    RiskAssessment,
    RiskDimension,
    RiskLevel,
    RiskType,
    RoleOverlap,
)
from agents.hr_agent.profiling import EmployeeProfiler, get_profiler
from agents.hr_agent.redundancy import RedundancyAnalyzer, get_analyzer
from agents.hr_agent.risk_assessment import RiskAssessor, get_assessor

__all__ = [
    # Adapters
    "BaseHRAdapter",
    # Models
    "Competency",
    "CompetencyMatchScore",
    # Matching
    "CompetencyModel",
    "CompetencyRequirement",
    "Department",
    "Employee",
    "EmployeeCompetency",
    "EmployeeProfile",
    # Profiling
    "EmployeeProfiler",
    "EmploymentStatus",
    "LayoffCandidate",
    "LayoffPlanConfig",
    "LayoffSimulationResult",
    # Foolproof
    "LayoffSimulator",
    "MatchResult",
    "MockHRAdapter",
    "OrgHealthReport",
    "PerformanceRecord",
    "PersonJobMatcher",
    "Position",
    # Redundancy
    "RedundancyAnalyzer",
    "RedundancyReport",
    "RiskAssessment",
    # Risk
    "RiskAssessor",
    "RiskDimension",
    "RiskLevel",
    "RiskType",
    "RoleOverlap",
    "WorkdayAdapter",
    "get_analyzer",
    "get_assessor",
    "get_hr_adapter",
    "get_matcher",
    "get_profiler",
    "get_simulator",
    "reset_hr_adapter",
    "set_hr_adapter",
]
