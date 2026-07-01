"""HR Agent — ToolRegistry integration.

Registers 6 HR tools to the orchestrator ToolRegistry and provides
async handlers for each tool.

M3-T5-9: 工具注册 + Worker 集成

Tools registered:
- hr_employee_profile: Generate employee profile
- hr_person_job_match: Person-job matching score
- hr_risk_assessment: Risk assessment for an employee
- hr_redundancy_analysis: Department redundancy analysis
- hr_layoff_simulation: Layoff simulation (with foolproof)
- hr_org_health: Organizational health report
"""

from __future__ import annotations

import logging
from typing import Any

from agents.hr_agent.adapters import get_hr_adapter
from agents.hr_agent.foolproof import get_simulator
from agents.hr_agent.matching import get_matcher
from agents.hr_agent.models import (
    Employee,
    LayoffPlanConfig,
    OrgHealthReport,
    RiskLevel,
)
from agents.hr_agent.profiling import get_profiler
from agents.hr_agent.redundancy import get_analyzer
from agents.hr_agent.risk_assessment import get_assessor
from agents.orchestrator.tools.registry import ToolDefinition, ToolRegistry

logger = logging.getLogger("fde.hr.integration")


# ══════════════════════════════════════════════════════════════════
# Tool Handlers (async)
# ══════════════════════════════════════════════════════════════════


async def _hr_employee_profile_handler(
    employee_id: str = "",
) -> dict[str, Any]:
    """Generate a comprehensive employee profile.

    Args:
        employee_id: The employee to profile.

    Returns:
        Employee profile data as a dict.
    """
    if not employee_id:
        return {"error": "employee_id is required"}

    adapter = get_hr_adapter()
    employee = await adapter.get_employee(employee_id)

    if employee is None:
        return {"error": f"Employee not found: {employee_id}"}

    profiler = get_profiler()
    profile = profiler.profile(employee)

    return profile.model_dump()


async def _hr_person_job_match_handler(
    employee_id: str = "",
    position_id: str = "",
) -> dict[str, Any]:
    """Match an employee against a job position.

    Args:
        employee_id: The candidate employee.
        position_id: The target position.

    Returns:
        Match result with overall score, gaps, and recommendation.
    """
    if not employee_id or not position_id:
        return {"error": "employee_id and position_id are required"}

    adapter = get_hr_adapter()
    employee = await adapter.get_employee(employee_id)
    positions = await adapter.get_positions()

    if employee is None:
        return {"error": f"Employee not found: {employee_id}"}

    position = next(
        (p for p in positions if p.position_id == position_id),
        None,
    )
    if position is None:
        return {"error": f"Position not found: {position_id}"}

    matcher = get_matcher()
    result = matcher.match(employee, position)

    return result.model_dump()


async def _hr_risk_assessment_handler(
    employee_id: str = "",
    risk_types: list[str] | None = None,
) -> dict[str, Any]:
    """Run comprehensive risk assessment for an employee.

    Args:
        employee_id: The employee to assess.
        risk_types: Optional list of risk types to include (default: all).

    Returns:
        Risk assessment with per-dimension scores and recommendations.
    """
    if not employee_id:
        return {"error": "employee_id is required"}

    adapter = get_hr_adapter()
    employee = await adapter.get_employee(employee_id)

    if employee is None:
        return {"error": f"Employee not found: {employee_id}"}

    assessor = get_assessor()
    assessment = assessor.assess(employee)

    return assessment.model_dump()


async def _hr_redundancy_analysis_handler(
    department_id: str = "",
) -> dict[str, Any]:
    """Analyze department redundancy and role overlap.

    Args:
        department_id: The department to analyze.

    Returns:
        Redundancy report with role overlaps, cost impact, and recommendations.
    """
    if not department_id:
        return {"error": "department_id is required"}

    adapter = get_hr_adapter()
    departments = await adapter.get_departments()
    employees = await adapter.get_department_employees(department_id)

    department = next(
        (d for d in departments if d.dept_id == department_id),
        None,
    )
    if department is None:
        return {"error": f"Department not found: {department_id}"}

    analyzer = get_analyzer()
    report = analyzer.analyze(department, employees)

    return report.model_dump()


async def _hr_layoff_simulation_handler(
    department_id: str = "",
    target_reduction: int = 1,
    criteria: list[str] | None = None,
    exclude_probation: bool = True,
    min_severance_budget: float = 0.0,
) -> dict[str, Any]:
    """Simulate a layoff plan (PREVIEW ONLY — no changes made).

    This tool requires 5-step foolproof confirmation before any action.

    Args:
        department_id: Target department.
        target_reduction: Number of positions to reduce.
        criteria: Selection criteria (performance, tenure, competency, cost).
        exclude_probation: Exclude probation employees.
        min_severance_budget: Minimum severance budget available.

    Returns:
        Layoff simulation preview with candidates and foolproof status.
    """
    if not department_id:
        return {"error": "department_id is required"}

    config = LayoffPlanConfig(
        department_id=department_id,
        target_reduction=max(target_reduction, 1),
        criteria=criteria or ["performance", "tenure"],
        exclude_probation=exclude_probation,
        min_severance_budget=min_severance_budget,
    )

    adapter = get_hr_adapter()
    employees = await adapter.get_department_employees(department_id)

    if not employees:
        return {"error": f"No employees found in department: {department_id}"}

    simulator = get_simulator()
    result = simulator.simulate(config, employees)

    return result.model_dump()


async def _hr_org_health_handler(
    department_id: str = "",
) -> dict[str, Any]:
    """Generate an organizational health report for a department.

    Args:
        department_id: The department to report on.

    Returns:
        Org health report with metrics, risk distribution, and recommendations.
    """
    if not department_id:
        return {"error": "department_id is required"}

    adapter = get_hr_adapter()
    departments = await adapter.get_departments()
    employees = await adapter.get_department_employees(department_id)

    department = next(
        (d for d in departments if d.dept_id == department_id),
        None,
    )
    if department is None:
        return {"error": f"Department not found: {department_id}"}

    report = _generate_org_health(department, employees)
    return report.model_dump()


# ══════════════════════════════════════════════════════════════════
# Org Health Report Generator
# ══════════════════════════════════════════════════════════════════


def _generate_org_health(
    department: Any,
    employees: list[Employee],
) -> OrgHealthReport:
    """Generate an organizational health report."""

    if not employees:
        return OrgHealthReport(
            department_id=department.dept_id if hasattr(department, "dept_id") else "",
            department_name=department.name if hasattr(department, "name") else "",
            summary="部门无员工数据。",
        )

    total = len(employees)
    avg_tenure = sum(e.years_of_service for e in employees) / total
    avg_perf = sum(e.avg_performance_score for e in employees) / total
    avg_salary = sum(e.annual_salary for e in employees) / total

    # Competency
    all_comps = [c.level for e in employees for c in e.competencies]
    avg_comp = sum(all_comps) / len(all_comps) if all_comps else 0.0

    # Risk distribution
    assessor = get_assessor()
    high_risk = 0
    medium_risk = 0
    low_risk = 0
    critical_gaps: list[str] = []

    for emp in employees:
        assessment = assessor.assess(emp)
        if assessment.overall_risk_level in (RiskLevel.HIGH, RiskLevel.CRITICAL):
            high_risk += 1
        elif assessment.overall_risk_level == RiskLevel.MEDIUM:
            medium_risk += 1
        else:
            low_risk += 1

        # Collect competency gaps
        for comp in emp.competencies:
            if comp.level < 3 and comp.competency_name not in critical_gaps:
                critical_gaps.append(comp.competency_name)

    # Health score (composite)
    health_score = _calculate_health_score(
        avg_perf,
        avg_comp,
        high_risk,
        total,
        avg_tenure,
    )
    health_grade = _score_to_grade(health_score)

    # Strengths and concerns
    strengths: list[str] = []
    concerns: list[str] = []

    if avg_perf >= 85:
        strengths.append(f"整体绩效优秀（均分{avg_perf:.0f}）")
    if avg_tenure >= 3.0:
        strengths.append(f"团队稳定性好（平均司龄{avg_tenure:.1f}年）")
    if avg_comp >= 3.5:
        strengths.append(f"综合能力水平高（{avg_comp:.1f}/5.0）")

    if high_risk > total * 0.3:
        concerns.append(f"高风险员工比例较高（{high_risk}/{total}）")
    if avg_perf < 70:
        concerns.append(f"整体绩效偏低（均分{avg_perf:.0f}）")
    if avg_tenure < 1.5:
        concerns.append("团队司龄偏短，知识传承风险")
    if len(critical_gaps) > 3:
        concerns.append(f"存在{len(critical_gaps)}项能力缺口")

    # Recommendations
    recommendations: list[str] = []
    if concerns:
        recommendations.append("建议针对薄弱环节制定改进计划")
    if high_risk > 0:
        recommendations.append(f"关注{high_risk}名高风险员工的留任和发展")
    if critical_gaps:
        recommendations.append(f"针对能力缺口（{'、'.join(critical_gaps[:3])}）组织专项培训")
    if not recommendations:
        recommendations.append("部门健康状况良好，保持当前管理策略")

    summary = (
        f"{department.name}部门共{total}人，健康评分{health_score:.0f}（{health_grade}级）。"
        f"平均绩效{avg_perf:.0f}分，平均司龄{avg_tenure:.1f}年。"
        f"高风险{high_risk}人，中风险{medium_risk}人，低风险{low_risk}人。"
    )

    return OrgHealthReport(
        department_id=department.dept_id,
        department_name=department.name,
        total_employees=total,
        avg_tenure=round(avg_tenure, 1),
        avg_performance=round(avg_perf, 1),
        avg_salary=round(avg_salary, 2),
        high_risk_count=high_risk,
        medium_risk_count=medium_risk,
        low_risk_count=low_risk,
        avg_competency_level=round(avg_comp, 2),
        critical_gaps=critical_gaps[:5],
        health_score=round(health_score, 1),
        health_grade=health_grade,
        strengths=strengths,
        concerns=concerns,
        recommendations=recommendations,
        summary=summary,
    )


def _calculate_health_score(
    avg_perf: float,
    avg_comp: float,
    high_risk: int,
    total: int,
    avg_tenure: float,
) -> float:
    """Calculate a composite health score (0-100)."""
    # Performance component (40%)
    perf_component = (avg_perf / 100.0) * 40.0

    # Competency component (25%)
    comp_component = (avg_comp / 5.0) * 25.0

    # Risk component (20%) — inverse of high risk ratio
    risk_ratio = high_risk / total if total > 0 else 0
    risk_component = (1.0 - risk_ratio) * 20.0

    # Tenure component (15%)
    tenure_component = min(avg_tenure / 5.0, 1.0) * 15.0

    return perf_component + comp_component + risk_component + tenure_component


def _score_to_grade(score: float) -> str:
    """Convert health score to letter grade."""
    if score >= 90:
        return "A"
    if score >= 80:
        return "B"
    if score >= 70:
        return "C"
    if score >= 60:
        return "D"
    return "E"


# ══════════════════════════════════════════════════════════════════
# Registration Function
# ══════════════════════════════════════════════════════════════════


def register_hr_tools(registry: ToolRegistry) -> None:
    """Register all HR tools to the ToolRegistry.

    Args:
        registry: The orchestrator's ToolRegistry instance.
    """
    tools = [
        ToolDefinition(
            name="hr_employee_profile",
            description="Generate a comprehensive employee profile with competency, performance, and risk analysis",
            worker="hr",
            handler=_hr_employee_profile_handler,
            parameters={
                "employee_id": {"type": "string", "required": True, "description": "Employee ID"},
            },
            is_dangerous=False,
            category="hr_analysis",
        ),
        ToolDefinition(
            name="hr_person_job_match",
            description="Match an employee against a job position with competency gap analysis",
            worker="hr",
            handler=_hr_person_job_match_handler,
            parameters={
                "employee_id": {"type": "string", "required": True},
                "position_id": {"type": "string", "required": True},
            },
            is_dangerous=False,
            category="hr_analysis",
        ),
        ToolDefinition(
            name="hr_risk_assessment",
            description="Run comprehensive risk assessment (turnover, compliance, performance, competency gap)",
            worker="hr",
            handler=_hr_risk_assessment_handler,
            parameters={
                "employee_id": {"type": "string", "required": True},
                "risk_types": {"type": "array", "required": False},
            },
            is_dangerous=False,
            category="hr_analysis",
        ),
        ToolDefinition(
            name="hr_redundancy_analysis",
            description="Analyze department redundancy, role overlap, and estimate optimization savings",
            worker="hr",
            handler=_hr_redundancy_analysis_handler,
            parameters={
                "department_id": {"type": "string", "required": True},
            },
            is_dangerous=False,
            category="hr_analysis",
        ),
        ToolDefinition(
            name="hr_layoff_simulation",
            description="Simulate a layoff plan with 5-step foolproof confirmation (PREVIEW ONLY)",
            worker="hr",
            handler=_hr_layoff_simulation_handler,
            parameters={
                "department_id": {"type": "string", "required": True},
                "target_reduction": {"type": "integer", "required": False, "default": 1},
                "criteria": {"type": "array", "required": False},
                "exclude_probation": {"type": "boolean", "required": False, "default": True},
                "min_severance_budget": {"type": "number", "required": False, "default": 0},
            },
            is_dangerous=True,
            category="hr_action",
        ),
        ToolDefinition(
            name="hr_org_health",
            description="Generate organizational health report for a department",
            worker="hr",
            handler=_hr_org_health_handler,
            parameters={
                "department_id": {"type": "string", "required": True},
            },
            is_dangerous=False,
            category="hr_analysis",
        ),
    ]

    for tool in tools:
        registry.register(tool)

    logger.info("Registered %d HR tools", len(tools))
