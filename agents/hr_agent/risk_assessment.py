"""HR Agent — risk assessment engine.

Evaluates multiple risk dimensions for employees: turnover risk,
compliance risk, performance risk, and competency gap risk.

M3-T5-6: 风险评估引擎
"""

from __future__ import annotations

import logging

from agents.hr_agent.models import (
    Employee,
    EmploymentStatus,
    RiskAssessment,
    RiskDimension,
    RiskLevel,
    RiskType,
)

logger = logging.getLogger("fde.hr.risk")


# ══════════════════════════════════════════════════════════════════
# Risk Assessor
# ══════════════════════════════════════════════════════════════════


class RiskAssessor:
    """Comprehensive risk assessment engine for employees.

    Evaluates four risk dimensions:
    1. Turnover risk — likelihood of employee leaving
    2. Compliance risk — legal/regulatory exposure
    3. Performance risk — sustained low performance
    4. Competency gap risk — skills below role requirements

    Each dimension produces a score (0-100) and risk level.
    The overall risk is a weighted composite.
    """

    # Dimension weights for overall score
    TURNOVER_WEIGHT = 0.35
    COMPLIANCE_WEIGHT = 0.20
    PERFORMANCE_WEIGHT = 0.25
    COMPETENCY_GAP_WEIGHT = 0.20

    # Score → Level thresholds
    CRITICAL_THRESHOLD = 80.0
    HIGH_THRESHOLD = 60.0
    MEDIUM_THRESHOLD = 40.0

    def assess(self, employee: Employee) -> RiskAssessment:
        """Run comprehensive risk assessment for an employee.

        Args:
            employee: Full employee record.

        Returns:
            RiskAssessment with all four dimensions and overall rating.
        """
        logger.info("Assessing risk for employee: %s (%s)", employee.name, employee.employee_id)

        turnover = self._assess_turnover(employee)
        compliance = self._assess_compliance(employee)
        performance = self._assess_performance(employee)
        competency_gap = self._assess_competency_gap(employee)

        # Overall score (weighted composite)
        overall_score = (
            self.TURNOVER_WEIGHT * turnover.score
            + self.COMPLIANCE_WEIGHT * compliance.score
            + self.PERFORMANCE_WEIGHT * performance.score
            + self.COMPETENCY_GAP_WEIGHT * competency_gap.score
        )
        overall_score = round(min(overall_score, 100.0), 1)
        overall_level = self._score_to_level(overall_score)

        # Recommended actions
        actions = self._recommend_actions(
            turnover,
            compliance,
            performance,
            competency_gap,
        )

        summary = self._generate_summary(
            employee,
            overall_level,
            overall_score,
            turnover,
            compliance,
            performance,
            competency_gap,
        )

        return RiskAssessment(
            employee_id=employee.employee_id,
            employee_name=employee.name,
            overall_risk_level=overall_level,
            overall_risk_score=overall_score,
            turnover_risk=turnover,
            compliance_risk=compliance,
            performance_risk=performance,
            competency_gap_risk=competency_gap,
            recommended_actions=actions,
            summary=summary,
        )

    # ── Turnover Risk ────────────────────────────────────────────

    def _assess_turnover(self, employee: Employee) -> RiskDimension:
        """Assess turnover risk based on tenure, performance trend, and status."""
        score = 0.0
        factors: list[str] = []

        # Short tenure increases risk
        if employee.years_of_service < 1.0:
            score += 30.0
            factors.append("入职不足1年")
        elif employee.years_of_service < 2.0:
            score += 15.0
            factors.append("入职不足2年")

        # Declining performance trend may indicate disengagement
        if employee.performance_history:
            scores = [p.score for p in sorted(employee.performance_history, key=lambda p: p.period)]
            if len(scores) >= 2:
                recent_avg = sum(scores[-2:]) / 2
                older_avg = (
                    sum(scores[:-2]) / max(len(scores) - 2, 1) if len(scores) > 2 else scores[0]
                )
                if recent_avg < older_avg - 5:
                    score += 25.0
                    factors.append("绩效呈下降趋势")

        # Low performance score
        if employee.avg_performance_score < 65.0:
            score += 20.0
            factors.append("绩效偏低")

        # Tags indicating turnover risk
        if "turnover_risk" in employee.tags:
            score += 15.0
            factors.append("已被标记为离职风险")

        # Probation status
        if employee.employment_status == EmploymentStatus.PROBATION:
            score += 10.0
            factors.append("试用期员工")

        # Goals not met
        latest = employee.latest_performance
        if latest and not latest.goals_met:
            score += 10.0
            factors.append("最近一期目标未达成")

        score = min(score, 100.0)
        level = self._score_to_level(score)

        return RiskDimension(
            risk_type=RiskType.TURNOVER,
            level=level,
            score=round(score, 1),
            factors=factors,
            description=f"离职风险评分 {score:.0f}/100，风险等级：{level.value}",
        )

    # ── Compliance Risk ──────────────────────────────────────────

    def _assess_compliance(self, employee: Employee) -> RiskDimension:
        """Assess compliance risk (legal/regulatory exposure)."""
        score = 0.0
        factors: list[str] = []

        # Probation employees have weaker legal protection
        if employee.employment_status == EmploymentStatus.PROBATION:
            score += 20.0
            factors.append("试用期员工，解雇法律风险较低但需合规操作")

        # High salary + low performance = potential dispute risk
        if employee.annual_salary > 500_000 and employee.avg_performance_score < 70:
            score += 25.0
            factors.append("高薪低绩效，裁员争议风险高")

        # Long tenure employees have stronger legal protection
        if employee.years_of_service >= 5.0:
            score += 15.0
            factors.append("工龄5年以上，解除合同法律要求严格")

        # Key personnel
        if "key_personnel" in employee.tags:
            score += 20.0
            factors.append("关键岗位人员，离职/调岗需特殊合规处理")

        score = min(score, 100.0)
        level = self._score_to_level(score)

        return RiskDimension(
            risk_type=RiskType.COMPLIANCE,
            level=level,
            score=round(score, 1),
            factors=factors,
            description=f"合规风险评分 {score:.0f}/100，风险等级：{level.value}",
        )

    # ── Performance Risk ─────────────────────────────────────────

    def _assess_performance(self, employee: Employee) -> RiskDimension:
        """Assess performance risk based on history and trends."""
        score = 0.0
        factors: list[str] = []

        avg_perf = employee.avg_performance_score

        if avg_perf == 0.0:
            score += 20.0
            factors.append("无绩效记录")
        elif avg_perf < 60.0:
            score += 60.0
            factors.append(f"平均绩效极低（{avg_perf:.0f}分）")
        elif avg_perf < 70.0:
            score += 40.0
            factors.append(f"平均绩效偏低（{avg_perf:.0f}分）")
        elif avg_perf < 80.0:
            score += 20.0
            factors.append(f"平均绩效中等（{avg_perf:.0f}分）")

        # Performance trend
        if len(employee.performance_history) >= 2:
            sorted_hist = sorted(employee.performance_history, key=lambda p: p.period)
            scores = [p.score for p in sorted_hist]
            if scores[-1] < scores[0] - 10:
                score += 20.0
                factors.append("绩效持续下降")
            elif scores[-1] < scores[-2] - 5:
                score += 10.0
                factors.append("最近绩效下滑")

        # Goals not met
        unmet_count = sum(1 for p in employee.performance_history if not p.goals_met)
        if unmet_count >= 2:
            score += 15.0
            factors.append(f"{unmet_count}次目标未达成")

        score = min(score, 100.0)
        level = self._score_to_level(score)

        return RiskDimension(
            risk_type=RiskType.PERFORMANCE,
            level=level,
            score=round(score, 1),
            factors=factors,
            description=f"绩效风险评分 {score:.0f}/100，风险等级：{level.value}",
        )

    # ── Competency Gap Risk ──────────────────────────────────────

    def _assess_competency_gap(self, employee: Employee) -> RiskDimension:
        """Assess competency gap risk."""
        score = 0.0
        factors: list[str] = []

        if not employee.competencies:
            score += 50.0
            factors.append("无胜任力评估记录")
        else:
            # Count competencies below level 3
            low_count = sum(1 for c in employee.competencies if c.level < 3)
            total_count = len(employee.competencies)
            low_ratio = low_count / total_count if total_count > 0 else 0

            if low_ratio > 0.5:
                score += 50.0
                factors.append(f"超过半数胜任力低于3级（{low_count}/{total_count}）")
            elif low_ratio > 0.3:
                score += 30.0
                factors.append(f"较多胜任力低于3级（{low_count}/{total_count}）")
            elif low_count > 0:
                score += 15.0
                factors.append(f"{low_count}项胜任力低于3级")

            # Average level
            avg_level = sum(c.level for c in employee.competencies) / total_count
            if avg_level < 2.0:
                score += 20.0
                factors.append(f"平均胜任力水平极低（{avg_level:.1f}/5.0）")
            elif avg_level < 3.0:
                score += 10.0
                factors.append(f"平均胜任力水平偏低（{avg_level:.1f}/5.0）")

        score = min(score, 100.0)
        level = self._score_to_level(score)

        return RiskDimension(
            risk_type=RiskType.COMPETENCY_GAP,
            level=level,
            score=round(score, 1),
            factors=factors,
            description=f"能力缺口风险评分 {score:.0f}/100，风险等级：{level.value}",
        )

    # ── Utility ──────────────────────────────────────────────────

    def _score_to_level(self, score: float) -> RiskLevel:
        """Convert a risk score to a risk level."""
        if score >= self.CRITICAL_THRESHOLD:
            return RiskLevel.CRITICAL
        if score >= self.HIGH_THRESHOLD:
            return RiskLevel.HIGH
        if score >= self.MEDIUM_THRESHOLD:
            return RiskLevel.MEDIUM
        return RiskLevel.LOW

    def _recommend_actions(
        self,
        turnover: RiskDimension,
        compliance: RiskDimension,
        performance: RiskDimension,
        competency_gap: RiskDimension,
    ) -> list[str]:
        """Generate recommended actions based on risk dimensions."""
        actions: list[str] = []

        if turnover.level in (RiskLevel.HIGH, RiskLevel.CRITICAL):
            actions.append("安排一对一沟通，了解员工想法和需求")
            actions.append("评估薪酬竞争力，必要时调整薪资或福利")

        if performance.level in (RiskLevel.HIGH, RiskLevel.CRITICAL):
            actions.append("制定绩效改进计划（PIP），设定明确目标和时间线")
            actions.append("安排导师辅导，提供具体改进支持")

        if competency_gap.level in (RiskLevel.HIGH, RiskLevel.CRITICAL):
            actions.append("制定针对性培训计划，补齐能力缺口")
            actions.append("考虑岗位调整，匹配当前能力水平")

        if compliance.level in (RiskLevel.HIGH, RiskLevel.CRITICAL):
            actions.append("任何人事变动前需法务部门审核")
            actions.append("准备完整的绩效记录和沟通记录作为证据")

        if not actions:
            actions.append("保持定期关注，无需特别干预")

        return actions

    def _generate_summary(
        self,
        employee: Employee,
        overall_level: RiskLevel,
        overall_score: float,
        turnover: RiskDimension,
        compliance: RiskDimension,
        performance: RiskDimension,
        competency_gap: RiskDimension,
    ) -> str:
        """Generate a natural-language risk summary."""
        level_cn = {
            RiskLevel.LOW: "低",
            RiskLevel.MEDIUM: "中",
            RiskLevel.HIGH: "高",
            RiskLevel.CRITICAL: "极高",
        }

        parts = [
            f"{employee.name}的综合风险等级为{level_cn[overall_level]}（{overall_score}分）。",
            f"离职风险：{level_cn[turnover.level]}（{turnover.score:.0f}分）。",
            f"合规风险：{level_cn[compliance.level]}（{compliance.score:.0f}分）。",
            f"绩效风险：{level_cn[performance.level]}（{performance.score:.0f}分）。",
            f"能力缺口风险：{level_cn[competency_gap.level]}（{competency_gap.score:.0f}分）。",
        ]

        return " ".join(parts)


# ── Module-level singleton ─────────────────────────────────────────

_assessor: RiskAssessor | None = None


def get_assessor() -> RiskAssessor:
    """Get or create the risk assessor singleton."""
    global _assessor
    if _assessor is None:
        _assessor = RiskAssessor()
    return _assessor
