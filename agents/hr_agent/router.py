"""HR Agent — HTTP router for HR Portal (V5-⑥).

Exposes hr_agent capabilities via REST API:

* ``GET  /api/hr/employees``         — 员工列表
* ``GET  /api/hr/employees/{id}``    — 员工详情 + 画像
* ``GET  /api/hr/departments``       — 部门列表
* ``POST /api/hr/risk/{id}``         — 风险评估
* ``POST /api/hr/match``             — 人岗匹配
* ``POST /api/hr/redundancy/{dept}`` — 冗余分析
* ``GET  /api/hr/overview``          — HR 总览看板
* ``GET  /api/hr/positions``         — 岗位列表
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from agents.hr_agent.adapters import get_hr_adapter
from agents.hr_agent.matching import get_matcher
from agents.hr_agent.models import EmploymentStatus
from agents.hr_agent.profiling import get_profiler
from agents.hr_agent.redundancy import get_analyzer
from agents.hr_agent.risk_assessment import get_assessor

logger = logging.getLogger("fde.hr.router")

router = APIRouter(prefix="/api/hr", tags=["hr"])


# ══════════════════════════════════════════════════════════════════
# Response Models
# ══════════════════════════════════════════════════════════════════


class EmployeeSummary(BaseModel):
    employee_id: str
    name: str
    department: str
    position: str
    status: str
    risk_level: str = "low"


class HROverview(BaseModel):
    total_employees: int
    active_count: int
    departments: list[dict[str, Any]]
    risk_distribution: dict[str, int]
    recent_hires: list[dict[str, Any]]


class MatchRequest(BaseModel):
    employee_id: str
    position_id: str


# ══════════════════════════════════════════════════════════════════
# Endpoints
# ══════════════════════════════════════════════════════════════════


@router.get("/overview", response_model=HROverview)
async def overview() -> HROverview:
    """HR 总览看板数据。"""
    adapter = get_hr_adapter()
    employees = await adapter.get_employees()

    active_count = sum(1 for e in employees if e.employment_status == EmploymentStatus.ACTIVE)

    dept_map: dict[str, int] = {}
    for e in employees:
        dept_name = e.department_name or "未分配"
        dept_map[dept_name] = dept_map.get(dept_name, 0) + 1
    dept_list = [{"name": k, "count": v} for k, v in sorted(dept_map.items(), key=lambda x: -x[1])]

    risk_dist = {"low": 0, "medium": 0, "high": 0, "critical": 0}
    assessor = get_assessor()
    sample_size = min(20, len(employees))
    for e in employees[:sample_size]:
        try:
            assessment = assessor.assess(e)
            level = assessment.overall_risk_level.value
            if level in risk_dist:
                risk_dist[level] += 1
            else:
                risk_dist["low"] += 1
        except Exception:
            risk_dist["low"] += 1

    remaining = len(employees) - sample_size
    risk_dist["low"] += remaining

    sorted_emp = sorted(employees, key=lambda e: e.hire_date, reverse=True)[:5]
    recent = [
        {
            "id": e.employee_id,
            "name": e.name,
            "department": e.department_name or "-",
            "position": e.title or "-",
            "hire_date": e.hire_date.isoformat() if e.hire_date else "-",
        }
        for e in sorted_emp
    ]

    return HROverview(
        total_employees=len(employees),
        active_count=active_count,
        departments=dept_list,
        risk_distribution=risk_dist,
        recent_hires=recent,
    )


@router.get("/employees", response_model=list[EmployeeSummary])
async def list_employees(department: str | None = None) -> list[EmployeeSummary]:
    """员工列表，可按部门过滤。"""
    adapter = get_hr_adapter()
    employees = await adapter.get_employees(department_id=department)

    results: list[EmployeeSummary] = []
    for e in employees:
        results.append(EmployeeSummary(
            employee_id=e.employee_id,
            name=e.name,
            department=e.department_name or "-",
            position=e.title or "-",
            status=e.employment_status.value,
        ))
    return results


@router.get("/employees/{employee_id}", response_model=dict[str, Any])
async def get_employee_detail(employee_id: str) -> dict[str, Any]:
    """员工详情 + AI 画像分析。"""
    adapter = get_hr_adapter()
    employee = await adapter.get_employee(employee_id)
    if employee is None:
        raise HTTPException(status_code=404, detail=f"员工不存在: {employee_id}")

    profiler = get_profiler()
    profile = profiler.profile(employee)

    return {
        "employee": employee.model_dump(),
        "profile": profile.model_dump(),
    }


@router.post("/risk/{employee_id}", response_model=dict[str, Any])
async def risk_assessment(employee_id: str) -> dict[str, Any]:
    """员工风险评估。"""
    adapter = get_hr_adapter()
    employee = await adapter.get_employee(employee_id)
    if employee is None:
        raise HTTPException(status_code=404, detail=f"员工不存在: {employee_id}")

    assessor = get_assessor()
    assessment = assessor.assess(employee)
    return assessment.model_dump()


@router.post("/match", response_model=dict[str, Any])
async def person_job_match(req: MatchRequest) -> dict[str, Any]:
    """人岗匹配分析。"""
    adapter = get_hr_adapter()
    employee = await adapter.get_employee(req.employee_id)
    if employee is None:
        raise HTTPException(status_code=404, detail=f"员工不存在: {req.employee_id}")

    positions = await adapter.get_positions()
    position = next((p for p in positions if p.position_id == req.position_id), None)
    if position is None:
        raise HTTPException(status_code=404, detail=f"岗位不存在: {req.position_id}")

    matcher = get_matcher()
    result = matcher.match(employee, position)
    return result.model_dump()


@router.post("/redundancy/{department_id}", response_model=dict[str, Any])
async def redundancy_analysis(department_id: str) -> dict[str, Any]:
    """部门冗余分析。"""
    adapter = get_hr_adapter()
    departments = await adapter.get_departments()
    dept = next((d for d in departments if d.dept_id == department_id), None)
    if dept is None:
        raise HTTPException(status_code=404, detail=f"部门不存在: {department_id}")

    employees = await adapter.get_department_employees(department_id)
    if not employees:
        raise HTTPException(status_code=404, detail=f"部门无员工: {department_id}")

    analyzer = get_analyzer()
    report = analyzer.analyze(dept, employees)
    return report.model_dump()


@router.get("/positions", response_model=list[dict[str, Any]])
async def list_positions(department: str | None = None) -> list[dict[str, Any]]:
    """岗位列表。"""
    adapter = get_hr_adapter()
    positions = await adapter.get_positions(department_id=department)
    return [
        {
            "position_id": p.position_id,
            "title": p.title,
            "department": getattr(p, "department", "-"),
            "level": getattr(p, "level", "-"),
        }
        for p in positions
    ]


@router.get("/departments", response_model=list[dict[str, Any]])
async def list_departments() -> list[dict[str, Any]]:
    """部门列表。"""
    adapter = get_hr_adapter()
    departments = await adapter.get_departments()
    return [
        {
            "dept_id": d.dept_id,
            "name": d.name,
            "head_count": d.head_count,
            "budget": d.budget,
        }
        for d in departments
    ]


__all__ = ["router"]
