"""HR Agent — data source adapters.

Abstract base for HR system integration, with MockHRAdapter providing
complete demo data and WorkdayAdapter as a production stub.

M3-T5-2: HR 系统数据源适配器
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from datetime import UTC, datetime, timedelta

from agents.hr_agent.models import (
    CompetencyRequirement,
    Department,
    Employee,
    EmployeeCompetency,
    EmploymentStatus,
    PerformanceRecord,
    Position,
)

logger = logging.getLogger("fde.hr.adapters")


# ══════════════════════════════════════════════════════════════════
# Base Adapter
# ══════════════════════════════════════════════════════════════════


class BaseHRAdapter(ABC):
    """Abstract base for HR system data adapters.

    Concrete implementations connect to real HR systems (Workday, SAP SuccessFactors,
    BambooHR, etc.) and return standardized Pydantic models.
    """

    @abstractmethod
    async def get_employees(
        self,
        department_id: str | None = None,
    ) -> list[Employee]:
        """Fetch all employees, optionally filtered by department."""
        ...

    @abstractmethod
    async def get_employee(self, employee_id: str) -> Employee | None:
        """Fetch a single employee by ID."""
        ...

    @abstractmethod
    async def get_departments(self) -> list[Department]:
        """Fetch all departments."""
        ...

    @abstractmethod
    async def get_positions(self, department_id: str | None = None) -> list[Position]:
        """Fetch job positions, optionally filtered by department."""
        ...

    @abstractmethod
    async def get_department_employees(self, department_id: str) -> list[Employee]:
        """Fetch all employees in a specific department."""
        ...


# ══════════════════════════════════════════════════════════════════
# Mock Adapter — complete demo data for development & testing
# ══════════════════════════════════════════════════════════════════


class MockHRAdapter(BaseHRAdapter):
    """Mock HR adapter with realistic demo data.

    Provides a complete set of departments, employees, positions, and
    competency data for development and testing without a real HR system.
    """

    def __init__(self) -> None:
        self._departments: list[Department] = self._build_departments()
        self._employees: list[Employee] = self._build_employees()
        self._positions: list[Position] = self._build_positions()

    # ── Public API ───────────────────────────────────────────────

    async def get_employees(
        self,
        department_id: str | None = None,
    ) -> list[Employee]:
        if department_id is None:
            return list(self._employees)
        return [e for e in self._employees if e.department_id == department_id]

    async def get_employee(self, employee_id: str) -> Employee | None:
        return next(
            (e for e in self._employees if e.employee_id == employee_id),
            None,
        )

    async def get_departments(self) -> list[Department]:
        return list(self._departments)

    async def get_positions(
        self,
        department_id: str | None = None,
    ) -> list[Position]:
        if department_id is None:
            return list(self._positions)
        return [p for p in self._positions if p.department_id == department_id]

    async def get_department_employees(self, department_id: str) -> list[Employee]:
        return [e for e in self._employees if e.department_id == department_id]

    # ── Data Builders ────────────────────────────────────────────

    def _build_departments(self) -> list[Department]:
        return [
            Department(
                dept_id="dept-eng",
                name="Engineering",
                head_count=8,
                budget=15_000_000,
                cost_center="CC-001",
            ),
            Department(
                dept_id="dept-sales",
                name="Sales",
                parent_dept_id=None,
                head_count=5,
                budget=8_000_000,
                cost_center="CC-002",
            ),
            Department(
                dept_id="dept-hr",
                name="Human Resources",
                head_count=3,
                budget=2_500_000,
                cost_center="CC-003",
            ),
        ]

    def _build_employees(self) -> list[Employee]:
        now = datetime.now(UTC)

        # ── Engineering Department ──
        emp1 = Employee(
            employee_id="EMP-001",
            name="Zhang Wei",
            email="zhang.wei@company.com",
            department_id="dept-eng",
            department_name="Engineering",
            title="Senior Software Engineer",
            level="P6",
            manager_id="EMP-004",
            employment_status=EmploymentStatus.ACTIVE,
            hire_date=now - timedelta(days=365 * 4 + 100),
            years_of_service=4.3,
            annual_salary=480_000,
            bonus_percentage=20.0,
            competencies=[
                EmployeeCompetency(
                    competency_id="comp-python",
                    competency_name="Python",
                    level=5,
                    evidence="10+ years, core contributor",
                ),
                EmployeeCompetency(
                    competency_id="comp-arch",
                    competency_name="System Architecture",
                    level=4,
                    evidence="Designed 3 microservice systems",
                ),
                EmployeeCompetency(
                    competency_id="comp-lead",
                    competency_name="Technical Leadership",
                    level=3,
                    evidence="Leads team of 4",
                ),
                EmployeeCompetency(
                    competency_id="comp-ml",
                    competency_name="Machine Learning",
                    level=3,
                    evidence="Built 2 ML pipelines",
                ),
            ],
            performance_history=[
                PerformanceRecord(period="2024-Q4", score=92, rating="A", goals_met=True),
                PerformanceRecord(period="2024-Q2", score=88, rating="A-", goals_met=True),
                PerformanceRecord(period="2023-Q4", score=90, rating="A", goals_met=True),
                PerformanceRecord(period="2023-Q2", score=85, rating="B+", goals_met=True),
            ],
            tags=["high_potential", "tech_lead"],
        )

        emp2 = Employee(
            employee_id="EMP-002",
            name="Li Na",
            email="li.na@company.com",
            department_id="dept-eng",
            department_name="Engineering",
            title="Software Engineer",
            level="P5",
            manager_id="EMP-004",
            employment_status=EmploymentStatus.ACTIVE,
            hire_date=now - timedelta(days=365 * 2 + 50),
            years_of_service=2.1,
            annual_salary=320_000,
            bonus_percentage=15.0,
            competencies=[
                EmployeeCompetency(
                    competency_id="comp-python",
                    competency_name="Python",
                    level=4,
                ),
                EmployeeCompetency(
                    competency_id="comp-react",
                    competency_name="React/Vue Frontend",
                    level=3,
                ),
                EmployeeCompetency(
                    competency_id="comp-arch",
                    competency_name="System Architecture",
                    level=2,
                ),
                EmployeeCompetency(
                    competency_id="comp-ml",
                    competency_name="Machine Learning",
                    level=2,
                ),
            ],
            performance_history=[
                PerformanceRecord(period="2024-Q4", score=78, rating="B+", goals_met=True),
                PerformanceRecord(period="2024-Q2", score=75, rating="B", goals_met=True),
                PerformanceRecord(period="2023-Q4", score=72, rating="B", goals_met=False),
            ],
            tags=["stable"],
        )

        emp3 = Employee(
            employee_id="EMP-003",
            name="Wang Fang",
            email="wang.fang@company.com",
            department_id="dept-eng",
            department_name="Engineering",
            title="Junior Software Engineer",
            level="P4",
            manager_id="EMP-004",
            employment_status=EmploymentStatus.PROBATION,
            hire_date=now - timedelta(days=90),
            years_of_service=0.25,
            annual_salary=220_000,
            bonus_percentage=10.0,
            competencies=[
                EmployeeCompetency(
                    competency_id="comp-python",
                    competency_name="Python",
                    level=2,
                ),
                EmployeeCompetency(
                    competency_id="comp-react",
                    competency_name="React/Vue Frontend",
                    level=2,
                ),
                EmployeeCompetency(
                    competency_id="comp-arch",
                    competency_name="System Architecture",
                    level=1,
                ),
            ],
            performance_history=[
                PerformanceRecord(period="2025-Q1", score=65, rating="C+", goals_met=False),
            ],
            tags=["probation", "needs_mentoring"],
        )

        emp4 = Employee(
            employee_id="EMP-004",
            name="Chen Ming",
            email="chen.ming@company.com",
            department_id="dept-eng",
            department_name="Engineering",
            title="Engineering Manager",
            level="M2",
            manager_id="EMP-010",
            employment_status=EmploymentStatus.ACTIVE,
            hire_date=now - timedelta(days=365 * 7),
            years_of_service=7.0,
            annual_salary=650_000,
            bonus_percentage=30.0,
            competencies=[
                EmployeeCompetency(
                    competency_id="comp-python",
                    competency_name="Python",
                    level=4,
                ),
                EmployeeCompetency(
                    competency_id="comp-arch",
                    competency_name="System Architecture",
                    level=5,
                ),
                EmployeeCompetency(
                    competency_id="comp-lead",
                    competency_name="Technical Leadership",
                    level=5,
                    evidence="Manages 8-person team",
                ),
                EmployeeCompetency(
                    competency_id="comp-strategy",
                    competency_name="Strategic Planning",
                    level=4,
                ),
            ],
            performance_history=[
                PerformanceRecord(period="2024-Q4", score=95, rating="A+", goals_met=True),
                PerformanceRecord(period="2024-Q2", score=93, rating="A+", goals_met=True),
                PerformanceRecord(period="2023-Q4", score=91, rating="A", goals_met=True),
                PerformanceRecord(period="2023-Q2", score=89, rating="A-", goals_met=True),
            ],
            tags=["key_personnel", "high_potential"],
        )

        # ── Sales Department ──
        emp5 = Employee(
            employee_id="EMP-005",
            name="Liu Yang",
            email="liu.yang@company.com",
            department_id="dept-sales",
            department_name="Sales",
            title="Sales Director",
            level="M3",
            manager_id="EMP-010",
            employment_status=EmploymentStatus.ACTIVE,
            hire_date=now - timedelta(days=365 * 5 + 200),
            years_of_service=5.5,
            annual_salary=580_000,
            bonus_percentage=40.0,
            competencies=[
                EmployeeCompetency(
                    competency_id="comp-sales",
                    competency_name="Sales Strategy",
                    level=5,
                ),
                EmployeeCompetency(
                    competency_id="comp-negotiation",
                    competency_name="Negotiation",
                    level=5,
                ),
                EmployeeCompetency(
                    competency_id="comp-lead",
                    competency_name="Technical Leadership",
                    level=4,
                ),
            ],
            performance_history=[
                PerformanceRecord(period="2024-Q4", score=97, rating="A+", goals_met=True),
                PerformanceRecord(period="2024-Q2", score=94, rating="A+", goals_met=True),
                PerformanceRecord(period="2023-Q4", score=96, rating="A+", goals_met=True),
            ],
            tags=["key_personnel", "top_performer"],
        )

        emp6 = Employee(
            employee_id="EMP-006",
            name="Zhao Jing",
            email="zhao.jing@company.com",
            department_id="dept-sales",
            department_name="Sales",
            title="Account Manager",
            level="P5",
            manager_id="EMP-005",
            employment_status=EmploymentStatus.ACTIVE,
            hire_date=now - timedelta(days=365 * 3),
            years_of_service=3.0,
            annual_salary=280_000,
            bonus_percentage=25.0,
            competencies=[
                EmployeeCompetency(
                    competency_id="comp-sales",
                    competency_name="Sales Strategy",
                    level=3,
                ),
                EmployeeCompetency(
                    competency_id="comp-negotiation",
                    competency_name="Negotiation",
                    level=3,
                ),
                EmployeeCompetency(
                    competency_id="comp-crm",
                    competency_name="CRM Management",
                    level=4,
                ),
            ],
            performance_history=[
                PerformanceRecord(period="2024-Q4", score=82, rating="B+", goals_met=True),
                PerformanceRecord(period="2024-Q2", score=80, rating="B+", goals_met=True),
                PerformanceRecord(period="2023-Q4", score=76, rating="B", goals_met=True),
                PerformanceRecord(period="2023-Q2", score=70, rating="B-", goals_met=False),
            ],
            tags=["improving"],
        )

        emp7 = Employee(
            employee_id="EMP-007",
            name="Sun Lei",
            email="sun.lei@company.com",
            department_id="dept-sales",
            department_name="Sales",
            title="Sales Representative",
            level="P4",
            manager_id="EMP-005",
            employment_status=EmploymentStatus.ACTIVE,
            hire_date=now - timedelta(days=365 + 60),
            years_of_service=1.2,
            annual_salary=180_000,
            bonus_percentage=15.0,
            competencies=[
                EmployeeCompetency(
                    competency_id="comp-sales",
                    competency_name="Sales Strategy",
                    level=2,
                ),
                EmployeeCompetency(
                    competency_id="comp-negotiation",
                    competency_name="Negotiation",
                    level=2,
                ),
                EmployeeCompetency(
                    competency_id="comp-crm",
                    competency_name="CRM Management",
                    level=2,
                ),
            ],
            performance_history=[
                PerformanceRecord(period="2024-Q4", score=58, rating="C", goals_met=False),
                PerformanceRecord(period="2024-Q2", score=62, rating="C+", goals_met=False),
            ],
            tags=["underperforming", "turnover_risk"],
        )

        # ── HR Department ──
        emp8 = Employee(
            employee_id="EMP-008",
            name="Huang Mei",
            email="huang.mei@company.com",
            department_id="dept-hr",
            department_name="Human Resources",
            title="HR Director",
            level="M3",
            manager_id="EMP-010",
            employment_status=EmploymentStatus.ACTIVE,
            hire_date=now - timedelta(days=365 * 6),
            years_of_service=6.0,
            annual_salary=520_000,
            bonus_percentage=25.0,
            competencies=[
                EmployeeCompetency(
                    competency_id="comp-hr",
                    competency_name="HR Management",
                    level=5,
                ),
                EmployeeCompetency(
                    competency_id="comp-legal",
                    competency_name="Employment Law",
                    level=4,
                ),
                EmployeeCompetency(
                    competency_id="comp-lead",
                    competency_name="Technical Leadership",
                    level=4,
                ),
            ],
            performance_history=[
                PerformanceRecord(period="2024-Q4", score=90, rating="A", goals_met=True),
                PerformanceRecord(period="2024-Q2", score=88, rating="A-", goals_met=True),
                PerformanceRecord(period="2023-Q4", score=92, rating="A", goals_met=True),
            ],
            tags=["key_personnel"],
        )

        emp9 = Employee(
            employee_id="EMP-009",
            name="Xu Tao",
            email="xu.tao@company.com",
            department_id="dept-hr",
            department_name="Human Resources",
            title="HR Specialist",
            level="P5",
            manager_id="EMP-008",
            employment_status=EmploymentStatus.ACTIVE,
            hire_date=now - timedelta(days=365 * 2 + 200),
            years_of_service=2.5,
            annual_salary=240_000,
            bonus_percentage=12.0,
            competencies=[
                EmployeeCompetency(
                    competency_id="comp-hr",
                    competency_name="HR Management",
                    level=3,
                ),
                EmployeeCompetency(
                    competency_id="comp-legal",
                    competency_name="Employment Law",
                    level=3,
                ),
            ],
            performance_history=[
                PerformanceRecord(period="2024-Q4", score=75, rating="B", goals_met=True),
                PerformanceRecord(period="2024-Q2", score=72, rating="B", goals_met=True),
            ],
            tags=["stable"],
        )

        emp10 = Employee(
            employee_id="EMP-010",
            name="CEO Office",
            email="ceo@company.com",
            department_id="dept-hr",
            department_name="Executive",
            title="CEO",
            level="M4",
            manager_id="",
            employment_status=EmploymentStatus.ACTIVE,
            hire_date=now - timedelta(days=365 * 10),
            years_of_service=10.0,
            annual_salary=1_200_000,
            bonus_percentage=50.0,
            competencies=[
                EmployeeCompetency(
                    competency_id="comp-strategy",
                    competency_name="Strategic Planning",
                    level=5,
                ),
                EmployeeCompetency(
                    competency_id="comp-lead",
                    competency_name="Technical Leadership",
                    level=5,
                ),
            ],
            performance_history=[
                PerformanceRecord(period="2024-Q4", score=98, rating="A+", goals_met=True),
            ],
            tags=["key_personnel", "executive"],
        )

        return [emp1, emp2, emp3, emp4, emp5, emp6, emp7, emp8, emp9, emp10]

    def _build_positions(self) -> list[Position]:
        return [
            Position(
                position_id="POS-SSE-01",
                title="Senior Software Engineer",
                department_id="dept-eng",
                level="P6",
                description="Lead technical design and implementation",
                required_competencies=[
                    CompetencyRequirement(
                        competency_id="comp-python",
                        competency_name="Python",
                        min_level=4,
                        weight=3.0,
                    ),
                    CompetencyRequirement(
                        competency_id="comp-arch",
                        competency_name="System Architecture",
                        min_level=4,
                        weight=2.5,
                    ),
                    CompetencyRequirement(
                        competency_id="comp-lead",
                        competency_name="Technical Leadership",
                        min_level=3,
                        weight=2.0,
                    ),
                    CompetencyRequirement(
                        competency_id="comp-ml",
                        competency_name="Machine Learning",
                        min_level=3,
                        weight=1.5,
                    ),
                ],
                salary_min=400_000,
                salary_max=600_000,
                headcount=1,
            ),
            Position(
                position_id="POS-EM-01",
                title="Engineering Manager",
                department_id="dept-eng",
                level="M2",
                description="Manage engineering team and technical roadmap",
                required_competencies=[
                    CompetencyRequirement(
                        competency_id="comp-arch",
                        competency_name="System Architecture",
                        min_level=4,
                        weight=2.0,
                    ),
                    CompetencyRequirement(
                        competency_id="comp-lead",
                        competency_name="Technical Leadership",
                        min_level=4,
                        weight=3.0,
                    ),
                    CompetencyRequirement(
                        competency_id="comp-strategy",
                        competency_name="Strategic Planning",
                        min_level=3,
                        weight=2.0,
                    ),
                ],
                salary_min=550_000,
                salary_max=800_000,
                headcount=1,
            ),
            Position(
                position_id="POS-SD-01",
                title="Sales Director",
                department_id="dept-sales",
                level="M3",
                description="Lead sales strategy and team",
                required_competencies=[
                    CompetencyRequirement(
                        competency_id="comp-sales",
                        competency_name="Sales Strategy",
                        min_level=4,
                        weight=3.0,
                    ),
                    CompetencyRequirement(
                        competency_id="comp-negotiation",
                        competency_name="Negotiation",
                        min_level=4,
                        weight=2.5,
                    ),
                    CompetencyRequirement(
                        competency_id="comp-lead",
                        competency_name="Technical Leadership",
                        min_level=3,
                        weight=2.0,
                    ),
                ],
                salary_min=500_000,
                salary_max=700_000,
                headcount=1,
            ),
        ]


# ══════════════════════════════════════════════════════════════════
# Workday Adapter Stub — production placeholder
# ══════════════════════════════════════════════════════════════════


class WorkdayAdapter(BaseHRAdapter):
    """Workday HR system adapter (stub).

    Production implementation would connect to Workday REST API:
    - Base URL: https://{tenant}.workday.com/ccx/api/{tenant}/v1
    - Auth: OAuth2 Bearer token
    - Endpoints: /workers, /organizations, /positions

    Currently raises NotImplementedError for all methods.
    """

    def __init__(self, base_url: str, api_key: str) -> None:
        self.base_url = base_url
        self.api_key = api_key
        logger.warning("WorkdayAdapter is a stub — not connected to real API")

    async def get_employees(
        self,
        department_id: str | None = None,
    ) -> list[Employee]:
        raise NotImplementedError("WorkdayAdapter not implemented — use MockHRAdapter")

    async def get_employee(self, employee_id: str) -> Employee | None:
        raise NotImplementedError("WorkdayAdapter not implemented — use MockHRAdapter")

    async def get_departments(self) -> list[Department]:
        raise NotImplementedError("WorkdayAdapter not implemented — use MockHRAdapter")

    async def get_positions(
        self,
        department_id: str | None = None,
    ) -> list[Position]:
        raise NotImplementedError("WorkdayAdapter not implemented — use MockHRAdapter")

    async def get_department_employees(self, department_id: str) -> list[Employee]:
        raise NotImplementedError("WorkdayAdapter not implemented — use MockHRAdapter")


# ══════════════════════════════════════════════════════════════════
# Adapter Registry
# ══════════════════════════════════════════════════════════════════


_adapter: BaseHRAdapter | None = None


def get_hr_adapter() -> BaseHRAdapter:
    """Get the default HR adapter singleton.

    Returns MockHRAdapter by default. Production code should call
    set_hr_adapter(WorkdayAdapter(...)) during startup.
    """
    global _adapter
    if _adapter is None:
        _adapter = MockHRAdapter()
    return _adapter


def set_hr_adapter(adapter: BaseHRAdapter) -> None:
    """Override the default HR adapter (for testing or production)."""
    global _adapter
    _adapter = adapter


def reset_hr_adapter() -> None:
    """Reset to default MockHRAdapter (for testing)."""
    global _adapter
    _adapter = None
