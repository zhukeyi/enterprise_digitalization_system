"""HR Agent — layoff simulation with 5-step foolproof mechanism.

Implements the mandatory foolproof process for any layoff/restructuring
action:
1. Reversibility check — can the action be undone?
2. Impact assessment — who/what is affected?
3. Plain-language explanation — human-readable summary
4. Explicit confirmation — requires typing "CONFIRM_LAYOFF"
5. Snapshot — organizational snapshot for rollback reference

M3-T5-8: 裁员防呆机制
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from agents.hr_agent.models import (
    Employee,
    EmploymentStatus,
    LayoffCandidate,
    LayoffPlanConfig,
    LayoffSimulationResult,
    RiskLevel,
)

logger = logging.getLogger("fde.hr.foolproof")


# ══════════════════════════════════════════════════════════════════
# Layoff Simulator (with foolproof)
# ══════════════════════════════════════════════════════════════════


CONFIRMATION_KEYWORD = "CONFIRM_LAYOFF"

# Severance pay multipliers by tenure (Chinese labor law approximation)
SEVERANCE_PER_YEAR = 1.0  # 1 month salary per year of service
SEVERANCE_MIN_MONTHS = 1  # Minimum 1 month regardless of tenure


class LayoffSimulator:
    """Simulates layoff scenarios with mandatory foolproof checks.

    This class NEVER performs actual layoffs. It only generates
    preview simulations and enforces the 5-step confirmation process.

    Usage:
        simulator = LayoffSimulator()
        result = simulator.simulate(config, employees)
        # result is a PREVIEW — no changes made

        # Step 1: Check reversibility (already in result)
        # Step 2: Review impact (already in result)
        # Step 3: Read plain_explanation
        # Step 4: Confirm
        confirmed = simulator.confirm(result, keyword="CONFIRM_LAYOFF")
        # Step 5: Snapshot is auto-generated
    """

    def simulate(
        self,
        config: LayoffPlanConfig,
        employees: list[Employee],
    ) -> LayoffSimulationResult:
        """Generate a layoff simulation preview.

        Args:
            config: Layoff plan configuration.
            employees: All employees in the target department.

        Returns:
            LayoffSimulationResult with candidates, costs, and foolproof status.
            The result is a PREVIEW only — no changes are made.
        """
        logger.info(
            "Simulating layoff: dept=%s, reduction=%d",
            config.department_id,
            config.target_reduction,
        )

        # Filter eligible employees
        eligible = self._filter_eligible(config, employees)

        # Rank by criteria
        ranked = self._rank_candidates(eligible, config.criteria)

        # Select top N
        selected = ranked[: config.target_reduction]

        # Build candidate details
        candidates = [self._build_candidate(emp, config) for emp in selected]

        # Calculate costs
        total_severance = sum(c.severance_cost for c in candidates)
        annual_savings = sum(
            c.annual_salary * (1 + 0.2) for c in candidates  # salary + 20% overhead
        )
        net_savings = annual_savings - total_severance

        # Assess morale and legal risk
        morale_impact = self._assess_morale(len(candidates), len(eligible))
        legal_summary = self._legal_risk_summary(candidates)
        key_personnel = [c.employee_id for c in candidates if "key_personnel" in c.legal_risk]

        # Generate plain-language explanation
        plain = self._plain_explanation(
            config,
            len(candidates),
            total_severance,
            annual_savings,
            net_savings,
        )

        # Generate snapshot
        snapshot_id = str(uuid.uuid4())

        return LayoffSimulationResult(
            plan_config=config,
            candidates=candidates,
            total_affected=len(candidates),
            total_severance_cost=round(total_severance, 2),
            estimated_annual_savings=round(annual_savings, 2),
            net_first_year_savings=round(net_savings, 2),
            legal_risk_summary=legal_summary,
            morale_impact=morale_impact,
            key_personnel_risk=key_personnel,
            foolproof_step=1,
            foolproof_completed=False,
            confirmed=False,
            snapshot_id=snapshot_id,
            plain_explanation=plain,
            summary=self._generate_summary(config, candidates, total_severance, annual_savings),
        )

    def check_reversibility(self, result: LayoffSimulationResult) -> dict[str, Any]:
        """Step 1: Check if each layoff can be reversed.

        Returns a dict with reversibility details for each candidate.
        """
        reversibility: list[dict[str, Any]] = []
        for c in result.candidates:
            reversible = c.is_reversible and c.legal_risk != "high"
            reversibility.append(
                {
                    "employee_id": c.employee_id,
                    "employee_name": c.employee_name,
                    "is_reversible": reversible,
                    "reason": self._reversibility_reason(c),
                }
            )

        all_reversible = all(r["is_reversible"] for r in reversibility)

        # Advance to step 2
        result.foolproof_step = max(result.foolproof_step, 2)

        return {
            "step": 1,
            "step_name": "可逆性检查",
            "all_reversible": all_reversible,
            "details": reversibility,
            "warning": (
                "部分裁员操作不可逆，请仔细评估。"
                if not all_reversible
                else "所有裁员操作在法律程序完成前可撤销。"
            ),
        }

    def check_impact(self, result: LayoffSimulationResult) -> dict[str, Any]:
        """Step 2: Assess impact of the layoff plan.

        Returns impact details including affected people, cost, and morale.
        """
        result.foolproof_step = max(result.foolproof_step, 3)

        return {
            "step": 2,
            "step_name": "影响范围评估",
            "total_affected": result.total_affected,
            "total_severance_cost": result.total_severance_cost,
            "estimated_annual_savings": result.estimated_annual_savings,
            "net_first_year_savings": result.net_first_year_savings,
            "morale_impact": result.morale_impact,
            "key_personnel_at_risk": len(result.key_personnel_risk),
            "departments_affected": list({c.department for c in result.candidates}),
        }

    def get_explanation(self, result: LayoffSimulationResult) -> dict[str, Any]:
        """Step 3: Get plain-language explanation of the plan."""
        result.foolproof_step = max(result.foolproof_step, 4)

        return {
            "step": 3,
            "step_name": "通俗解释",
            "explanation": result.plain_explanation,
            "confirmation_required": f'请输入 "{CONFIRMATION_KEYWORD}" 以确认执行',
        }

    def confirm(
        self,
        result: LayoffSimulationResult,
        keyword: str,
    ) -> dict[str, Any]:
        """Step 4: Explicit confirmation.

        The user must type the exact confirmation keyword.
        """
        if keyword != CONFIRMATION_KEYWORD:
            return {
                "step": 4,
                "step_name": "二次确认",
                "confirmed": False,
                "error": f'确认关键词不匹配，请输入 "{CONFIRMATION_KEYWORD}"',
            }

        result.confirmed = True
        result.foolproof_step = max(result.foolproof_step, 5)

        return {
            "step": 4,
            "step_name": "二次确认",
            "confirmed": True,
            "message": "已确认，正在生成组织架构快照...",
        }

    def create_snapshot(self, result: LayoffSimulationResult) -> dict[str, Any]:
        """Step 5: Create organizational snapshot for rollback reference.

        In production, this would serialize the current org structure
        to persistent storage. Here it returns a snapshot descriptor.
        """
        if not result.confirmed:
            return {
                "step": 5,
                "step_name": "快照",
                "error": "未确认，无法创建快照",
            }

        result.foolproof_completed = True

        return {
            "step": 5,
            "step_name": "快照",
            "snapshot_id": result.snapshot_id,
            "created_at": datetime.now(UTC).isoformat(),
            "message": f"组织架构快照已创建（ID: {result.snapshot_id}），可在需要时回滚。",
            "completed": True,
        }

    def run_full_foolproof(
        self,
        result: LayoffSimulationResult,
        confirm_keyword: str,
    ) -> dict[str, Any]:
        """Run all 5 foolproof steps in sequence.

        Convenience method for automated testing. In production,
        each step should be reviewed by a human.
        """
        step1 = self.check_reversibility(result)
        step2 = self.check_impact(result)
        step3 = self.get_explanation(result)
        step4 = self.confirm(result, confirm_keyword)
        if not step4["confirmed"]:
            return {"error": "Confirmation failed", "step4": step4}
        step5 = self.create_snapshot(result)

        return {
            "step1": step1,
            "step2": step2,
            "step3": step3,
            "step4": step4,
            "step5": step5,
            "completed": result.foolproof_completed,
        }

    # ── Private: Eligibility & Ranking ──────────────────────────

    def _filter_eligible(
        self,
        config: LayoffPlanConfig,
        employees: list[Employee],
    ) -> list[Employee]:
        """Filter employees eligible for layoff consideration."""
        eligible = [
            e
            for e in employees
            if e.department_id == config.department_id
            and e.employment_status in (EmploymentStatus.ACTIVE, EmploymentStatus.PROBATION)
        ]

        if config.exclude_probation:
            eligible = [e for e in eligible if e.employment_status != EmploymentStatus.PROBATION]

        return eligible

    def _rank_candidates(
        self,
        employees: list[Employee],
        criteria: list[str],
    ) -> list[Employee]:
        """Rank employees by criteria (lowest performers first)."""

        def score(emp: Employee) -> float:
            s = 0.0
            # Lower performance → higher layoff priority
            s += (100.0 - emp.avg_performance_score) * 2.0

            # Shorter tenure → higher priority (lower severance cost)
            if "tenure" in criteria:
                s += (10.0 - min(emp.years_of_service, 10.0)) * 3.0

            # Lower competency → higher priority
            if "competency" in criteria:
                avg_comp = (
                    sum(c.level for c in emp.competencies) / len(emp.competencies)
                    if emp.competencies
                    else 1.0
                )
                s += (5.0 - avg_comp) * 5.0

            # Higher cost → higher priority
            if "cost" in criteria:
                s += min(emp.annual_salary / 100_000, 10.0)

            # Key personnel penalty (lower priority)
            if "key_personnel" in emp.tags:
                s -= 50.0

            return s

        return sorted(employees, key=score, reverse=True)

    def _build_candidate(
        self,
        emp: Employee,
        config: LayoffPlanConfig,
    ) -> LayoffCandidate:
        """Build a LayoffCandidate from an Employee."""
        severance = self._calculate_severance(emp)

        # Legal risk assessment
        if emp.years_of_service >= 5.0:
            legal_risk = "high"
        elif emp.employment_status == EmploymentStatus.PROBATION:
            legal_risk = "low"
        elif "key_personnel" in emp.tags:
            legal_risk = "high"
        else:
            legal_risk = "medium"

        # Reversibility
        is_reversible = (
            emp.employment_status == EmploymentStatus.PROBATION or emp.years_of_service < 3.0
        )

        reason_parts: list[str] = []
        if emp.avg_performance_score < 70:
            reason_parts.append(f"绩效偏低（{emp.avg_performance_score:.0f}分）")
        if emp.years_of_service < 2:
            reason_parts.append("司龄较短")
        if emp.competencies and (
            sum(c.level for c in emp.competencies) / len(emp.competencies) < 3
        ):
            reason_parts.append("能力水平偏低")

        return LayoffCandidate(
            employee_id=emp.employee_id,
            employee_name=emp.name,
            department=emp.department_name,
            title=emp.title,
            annual_salary=emp.annual_salary,
            years_of_service=emp.years_of_service,
            performance_score=round(emp.avg_performance_score, 1),
            risk_level=RiskLevel.MEDIUM,
            selection_reason="；".join(reason_parts) if reason_parts else "综合评分最低",
            severance_cost=round(severance, 2),
            is_reversible=is_reversible,
            legal_risk=legal_risk,
        )

    def _calculate_severance(self, emp: Employee) -> float:
        """Calculate estimated severance cost.

        Based on Chinese labor law: N months of salary for N years of service
        (minimum 1 month), where N = years of service.
        """
        months = max(int(emp.years_of_service), SEVERANCE_MIN_MONTHS)
        monthly_salary = emp.annual_salary / 12.0
        return months * monthly_salary

    # ── Private: Assessments ────────────────────────────────────

    def _assess_morale(self, affected: int, total: int) -> str:
        """Assess morale impact of the layoff."""
        if total == 0:
            return "unknown"
        rate = affected / total
        if rate > 0.3:
            return "high"
        if rate > 0.15:
            return "medium"
        return "low"

    def _legal_risk_summary(self, candidates: list[LayoffCandidate]) -> str:
        """Generate a legal risk summary."""
        high_risk = sum(1 for c in candidates if c.legal_risk == "high")
        medium_risk = sum(1 for c in candidates if c.legal_risk == "medium")
        low_risk = sum(1 for c in candidates if c.legal_risk == "low")

        parts = [
            f"法律风险评估：高风险 {high_risk} 人，中风险 {medium_risk} 人，低风险 {low_risk} 人。",
        ]
        if high_risk > 0:
            parts.append("高风险人员（工龄5年以上或关键岗位）需法务部门专项审核。")
        return " ".join(parts)

    def _reversibility_reason(self, candidate: LayoffCandidate) -> str:
        """Explain why a candidate's layoff is/isn't reversible."""
        if candidate.is_reversible:
            if candidate.years_of_service < 1.0:
                return "试用期/短工龄，法律程序简单，可撤销"
            return "工龄较短，协商解除后可重新聘用"
        if candidate.years_of_service >= 5.0:
            return "工龄5年以上，解除合同后难以恢复原岗位"
        if candidate.legal_risk == "high":
            return "法律风险高，操作不可逆"
        return "操作完成后难以撤销"

    def _plain_explanation(
        self,
        config: LayoffPlanConfig,
        affected: int,
        severance: float,
        savings: float,
        net: float,
    ) -> str:
        """Generate a plain-language explanation of the layoff plan."""
        return (
            f"本方案计划在目标部门裁减 {affected} 个岗位。"
            f"预计需要支付经济补偿金约 {severance:,.0f} 元，"
            f"每年可节省人力成本约 {savings:,.0f} 元，"
            f"首年净节省约 {net:,.0f} 元。"
            f"请注意：裁员将对团队士气产生影响，"
            f"建议同步制定留任员工的心理疏导和沟通方案。"
        )

    def _generate_summary(
        self,
        config: LayoffPlanConfig,
        candidates: list[LayoffCandidate],
        severance: float,
        savings: float,
    ) -> str:
        """Generate a brief summary of the simulation."""
        names = "、".join(c.employee_name for c in candidates[:3])
        if len(candidates) > 3:
            names += f" 等{len(candidates)}人"
        return (
            f"裁员模拟方案：拟裁减 {len(candidates)} 人（{names}），"
            f"经济补偿 {severance:,.0f} 元，年节省 {savings:,.0f} 元。"
            f"此为预览方案，需通过5步防呆确认后方可执行。"
        )


# ── Module-level singleton ─────────────────────────────────────────

_simulator: LayoffSimulator | None = None


def get_simulator() -> LayoffSimulator:
    """Get or create the layoff simulator singleton."""
    global _simulator
    if _simulator is None:
        _simulator = LayoffSimulator()
    return _simulator
