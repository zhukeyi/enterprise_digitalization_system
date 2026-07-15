"""HR Agent — employee profiling engine.

Generates comprehensive employee profiles including competency matrix,
performance trends, stability scores, and risk indicators.

M3-T5-3: 员工画像引擎
"""

from __future__ import annotations

import logging

from agents.hr_agent.models import (
    Employee,
    EmployeeCompetency,
    EmployeeProfile,
    PerformanceRecord,
)

logger = logging.getLogger("fde.hr.profiling")


# ══════════════════════════════════════════════════════════════════
# Employee Profiler
# ══════════════════════════════════════════════════════════════════


class EmployeeProfiler:
    """Generates comprehensive employee profiles.

    Analyzes competency matrix, performance history, tenure, and other
    signals to produce an EmployeeProfile with actionable insights.
    """

    # Stability score weights
    TENURE_WEIGHT = 0.4
    PERFORMANCE_STABILITY_WEIGHT = 0.35
    STATUS_WEIGHT = 0.25

    # Performance trend thresholds
    TREND_THRESHOLD = 5.0  # Points of change to qualify as trend

    def profile(self, employee: Employee) -> EmployeeProfile:
        """Generate a comprehensive profile for an employee.

        Args:
            employee: Full employee record with competencies and performance history.

        Returns:
            EmployeeProfile with competency summary, performance trends,
            stability score, and risk flags.
        """
        logger.info("Profiling employee: %s (%s)", employee.name, employee.employee_id)

        # Competency analysis
        top_comps = self._get_top_competencies(employee.competencies, top_n=5)
        avg_comp = self._avg_competency_level(employee.competencies)

        # Performance trend
        perf_trend = self._analyze_performance_trend(employee.performance_history)
        latest_perf = employee.latest_performance
        latest_rating = latest_perf.rating if latest_perf else ""
        avg_perf = employee.avg_performance_score

        # Stability score
        stability = self._calculate_stability(employee)

        # Risk flags
        risk_flags = self._identify_risk_flags(employee, perf_trend, stability)

        # Summary
        summary = self._generate_summary(
            employee,
            avg_comp,
            avg_perf,
            perf_trend,
            stability,
            risk_flags,
        )

        return EmployeeProfile(
            employee_id=employee.employee_id,
            employee_name=employee.name,
            department=employee.department_name,
            title=employee.title,
            competency_count=len(employee.competencies),
            avg_competency_level=round(avg_comp, 2),
            top_competencies=top_comps,
            competency_gaps=self._identify_competency_gaps(employee),
            performance_trend=perf_trend,
            avg_performance_score=round(avg_perf, 1),
            latest_rating=latest_rating,
            tenure_years=employee.years_of_service,
            stability_score=round(stability, 1),
            risk_flags=risk_flags,
            summary=summary,
        )

    # ── Competency Analysis ──────────────────────────────────────

    def _get_top_competencies(
        self,
        competencies: list[EmployeeCompetency],
        top_n: int = 5,
    ) -> list[EmployeeCompetency]:
        """Get top N competencies by level."""
        sorted_comps = sorted(competencies, key=lambda c: c.level, reverse=True)
        return sorted_comps[:top_n]

    def _avg_competency_level(self, competencies: list[EmployeeCompetency]) -> float:
        """Calculate average competency level."""
        if not competencies:
            return 0.0
        return sum(c.level for c in competencies) / len(competencies)

    def _identify_competency_gaps(self, employee: Employee) -> list[str]:
        """Identify competencies below level 3 (basic competency threshold)."""
        return [c.competency_id for c in employee.competencies if c.level < 3]

    # ── Performance Trend Analysis ───────────────────────────────

    def _analyze_performance_trend(
        self,
        history: list[PerformanceRecord],
    ) -> str:
        """Analyze performance trend over time.

        Returns one of: 'improving', 'stable', 'declining', 'volatile', 'insufficient_data'
        """
        if len(history) < 2:
            return "insufficient_data"

        # Sort by period (ascending)
        sorted_hist = sorted(history, key=lambda p: p.period)
        scores = [p.score for p in sorted_hist]

        # Linear regression slope
        n = len(scores)
        x_mean = (n - 1) / 2
        y_mean = sum(scores) / n
        numerator = sum((i - x_mean) * (s - y_mean) for i, s in enumerate(scores))
        denominator = sum((i - x_mean) ** 2 for i in range(n))
        slope = numerator / denominator if denominator != 0 else 0.0

        # Volatility (standard deviation)
        variance = sum((s - y_mean) ** 2 for s in scores) / n
        std_dev = variance**0.5

        if std_dev > 10.0:
            return "volatile"
        if slope > self.TREND_THRESHOLD / n:
            return "improving"
        if slope < -self.TREND_THRESHOLD / n:
            return "declining"
        return "stable"

    # ── Stability Score ──────────────────────────────────────────

    def _calculate_stability(self, employee: Employee) -> float:
        """Calculate a stability score (0-100, higher = more stable).

        Factors:
        - Tenure: longer tenure → higher stability
        - Performance consistency: lower volatility → higher stability
        - Employment status: active > probation > leave
        """
        # Tenure score (cap at 10 years = 100)
        tenure_score = min(employee.years_of_service / 10.0, 1.0) * 100

        # Performance stability (inverse of std dev)
        if len(employee.performance_history) >= 2:
            scores = [p.score for p in employee.performance_history]
            mean_score = sum(scores) / len(scores)
            variance = sum((s - mean_score) ** 2 for s in scores) / len(scores)
            std_dev = variance**0.5
            perf_stability = max(0.0, 100.0 - std_dev * 5.0)
        else:
            perf_stability = 50.0  # Neutral if insufficient data

        # Status score
        status_scores = {
            "active": 100.0,
            "probation": 30.0,
            "leave": 50.0,
            "resigned": 0.0,
            "terminated": 0.0,
        }
        status_score = status_scores.get(employee.employment_status.value, 50.0)

        # Weighted combination
        total = (
            self.TENURE_WEIGHT * tenure_score
            + self.PERFORMANCE_STABILITY_WEIGHT * perf_stability
            + self.STATUS_WEIGHT * status_score
        )

        return float(min(total, 100.0))

    # ── Risk Flags ───────────────────────────────────────────────

    def _identify_risk_flags(
        self,
        employee: Employee,
        perf_trend: str,
        stability: float,
    ) -> list[str]:
        """Identify risk indicators for an employee."""
        flags: list[str] = []

        # Low performance
        if employee.avg_performance_score < 65.0:
            flags.append("low_performance")

        # Declining trend
        if perf_trend == "declining":
            flags.append("performance_declining")
        elif perf_trend == "volatile":
            flags.append("performance_volatile")

        # Low stability
        if stability < 40.0:
            flags.append("low_stability")

        # Probation
        if employee.employment_status.value == "probation":
            flags.append("on_probation")

        # Short tenure + low performance
        if employee.years_of_service < 1.0 and employee.avg_performance_score < 70.0:
            flags.append("new_hire_underperforming")

        # Goals not met in latest period
        latest = employee.latest_performance
        if latest and not latest.goals_met:
            flags.append("goals_not_met")

        return flags

    # ── Summary Generation ───────────────────────────────────────

    def _generate_summary(
        self,
        employee: Employee,
        avg_comp: float,
        avg_perf: float,
        perf_trend: str,
        stability: float,
        risk_flags: list[str],
    ) -> str:
        """Generate a natural-language summary of the employee profile."""
        parts: list[str] = []

        parts.append(
            f"{employee.name}（{employee.title}，{employee.department_name}），"
            f"司龄 {employee.years_of_service:.1f} 年。"
        )

        # Competency
        if avg_comp >= 4.0:
            parts.append(f"综合能力水平优秀（{avg_comp:.1f}/5.0）。")
        elif avg_comp >= 3.0:
            parts.append(f"综合能力水平良好（{avg_comp:.1f}/5.0）。")
        else:
            parts.append(f"综合能力水平待提升（{avg_comp:.1f}/5.0）。")

        # Performance
        if avg_perf >= 90:
            parts.append(f"绩效表现卓越（均分 {avg_perf:.0f}），趋势{self._trend_cn(perf_trend)}。")
        elif avg_perf >= 75:
            parts.append(f"绩效表现稳定（均分 {avg_perf:.0f}），趋势{self._trend_cn(perf_trend)}。")
        elif avg_perf > 0:
            parts.append(f"绩效表现偏弱（均分 {avg_perf:.0f}），趋势{self._trend_cn(perf_trend)}。")

        # Stability
        if stability >= 70:
            parts.append("稳定性高。")
        elif stability >= 40:
            parts.append("稳定性中等。")
        else:
            parts.append("稳定性偏低，需关注。")

        # Risk
        if risk_flags:
            risk_cn = ", ".join(self._flag_cn(f) for f in risk_flags)
            parts.append(f"风险提示：{risk_cn}。")

        return " ".join(parts)

    @staticmethod
    def _trend_cn(trend: str) -> str:
        return {
            "improving": "上升",
            "stable": "平稳",
            "declining": "下降",
            "volatile": "波动较大",
            "insufficient_data": "数据不足",
        }.get(trend, "未知")

    @staticmethod
    def _flag_cn(flag: str) -> str:
        return {
            "low_performance": "绩效偏低",
            "performance_declining": "绩效下滑",
            "performance_volatile": "绩效波动",
            "low_stability": "稳定性不足",
            "on_probation": "试用期",
            "new_hire_underperforming": "新人表现不佳",
            "goals_not_met": "目标未达成",
        }.get(flag, flag)


# ── Module-level singleton ──────────────────────────────────────────

_profiler: EmployeeProfiler | None = None


def get_profiler() -> EmployeeProfiler:
    """Get or create the profiler singleton."""
    global _profiler
    if _profiler is None:
        _profiler = EmployeeProfiler()
    return _profiler
