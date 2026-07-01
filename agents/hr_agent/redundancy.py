"""HR Agent — redundancy analysis and organizational optimization.

Analyzes department-level role overlaps, headcount efficiency,
and generates optimization recommendations.

M3-T5-7: 冗余分析 + 组织优化建议
"""

from __future__ import annotations

import logging
from collections import Counter

from agents.hr_agent.models import (
    Department,
    Employee,
    EmploymentStatus,
    RedundancyReport,
    RoleOverlap,
)

logger = logging.getLogger("fde.hr.redundancy")


# ══════════════════════════════════════════════════════════════════
# Redundancy Analyzer
# ══════════════════════════════════════════════════════════════════


class RedundancyAnalyzer:
    """Analyzes department-level redundancy and role overlap.

    Detects:
    - Role overlap: multiple employees with same title and similar competencies
    - Overstaffing: headcount exceeds reasonable span of control
    - Cost inefficiency: high-cost roles with low performance

    Generates actionable recommendations for organizational optimization.
    """

    # Thresholds
    OVERLAP_TITLE_THRESHOLD = 2  # 2+ employees with same title = potential overlap
    OVERLAP_COMPETENCY_THRESHOLD = 0.7  # 70% competency similarity = overlap
    SPAN_OF_CONTROL_MAX = 8  # Max direct reports per manager
    LOW_PERFORMANCE_THRESHOLD = 70.0

    def analyze(
        self,
        department: Department,
        employees: list[Employee],
    ) -> RedundancyReport:
        """Analyze redundancy for a department.

        Args:
            department: The department to analyze.
            employees: All employees in the department.

        Returns:
            RedundancyReport with role overlaps, cost impact, and recommendations.
        """
        logger.info("Analyzing redundancy for department: %s", department.name)

        # Filter to active employees only
        active = [
            e
            for e in employees
            if e.employment_status in (EmploymentStatus.ACTIVE, EmploymentStatus.PROBATION)
        ]

        # Detect role overlaps
        role_overlaps = self._detect_role_overlaps(active)

        # Count redundant positions
        redundant_count = sum(
            ro.employee_count - 1
            for ro in role_overlaps
            if ro.overlap_score >= self.OVERLAP_COMPETENCY_THRESHOLD
        )

        # Estimate savings
        estimated_savings = self._estimate_savings(active, role_overlaps)

        # Recommendations
        recommendations = self._generate_recommendations(
            department,
            active,
            role_overlaps,
            redundant_count,
        )

        redundancy_rate = redundant_count / len(active) if active else 0.0

        summary = self._generate_summary(
            department,
            len(active),
            redundant_count,
            redundancy_rate,
            estimated_savings,
            role_overlaps,
        )

        return RedundancyReport(
            department_id=department.dept_id,
            department_name=department.name,
            total_headcount=len(active),
            redundant_count=redundant_count,
            redundancy_rate=round(redundancy_rate, 3),
            role_overlaps=role_overlaps,
            estimated_savings=round(estimated_savings, 2),
            recommendations=recommendations,
            summary=summary,
        )

    # ── Role Overlap Detection ───────────────────────────────────

    def _detect_role_overlaps(self, employees: list[Employee]) -> list[RoleOverlap]:
        """Detect role overlaps within a group of employees.

        Groups employees by title, then checks competency similarity
        within each group.
        """
        overlaps: list[RoleOverlap] = []

        # Group by title
        title_groups: dict[str, list[Employee]] = {}
        for emp in employees:
            title = emp.title or "Unknown"
            title_groups.setdefault(title, []).append(emp)

        for title, group in title_groups.items():
            if len(group) < self.OVERLAP_TITLE_THRESHOLD:
                continue

            # Calculate pairwise competency overlap
            overlap_score = self._group_competency_overlap(group)

            # Determine suggested action
            action = self._suggest_action(overlap_score, group)

            overlaps.append(
                RoleOverlap(
                    role_title=title,
                    employee_ids=[e.employee_id for e in group],
                    employee_count=len(group),
                    overlap_score=round(overlap_score, 2),
                    suggested_action=action,
                ),
            )

        # Sort by overlap score (highest first)
        overlaps.sort(key=lambda ro: ro.overlap_score, reverse=True)

        return overlaps

    def _group_competency_overlap(self, group: list[Employee]) -> float:
        """Calculate average competency overlap within a group.

        Uses Jaccard similarity on competency ID sets, averaged
        across all pairs.
        """
        if len(group) < 2:
            return 0.0

        # Get competency ID sets
        comp_sets = [{c.competency_id for c in emp.competencies} for emp in group]

        # Average pairwise Jaccard similarity
        total_sim = 0.0
        pair_count = 0

        for i in range(len(comp_sets)):
            for j in range(i + 1, len(comp_sets)):
                set_a = comp_sets[i]
                set_b = comp_sets[j]
                if set_a or set_b:
                    intersection = len(set_a & set_b)
                    union = len(set_a | set_b)
                    sim = intersection / union if union > 0 else 0.0
                else:
                    sim = 0.0
                total_sim += sim
                pair_count += 1

        return total_sim / pair_count if pair_count > 0 else 0.0

    def _suggest_action(self, overlap_score: float, group: list[Employee]) -> str:
        """Suggest an action for a role overlap."""
        if overlap_score >= 0.8:
            return "merge"  # High overlap → merge roles / reduce headcount
        if overlap_score >= 0.5:
            # Check if there are performance differences
            perf_scores = [e.avg_performance_score for e in group]
            if max(perf_scores) - min(perf_scores) > 20:
                return "reassign"  # Reassign low performer
            return "train"  # Similar performance → differentiate via training
        return "retain"  # Low overlap → keep all

    # ── Cost Estimation ─────────────────────────────────────────

    def _estimate_savings(
        self,
        employees: list[Employee],
        role_overlaps: list[RoleOverlap],
    ) -> float:
        """Estimate potential annual savings from addressing redundancy.

        For each overlapping role with high overlap score, estimate
        savings from removing the lowest-performing employee.
        """
        savings = 0.0

        emp_map = {e.employee_id: e for e in employees}

        for ro in role_overlaps:
            if ro.overlap_score < self.OVERLAP_COMPETENCY_THRESHOLD:
                continue

            # Find the lowest performer in the overlap group
            group_emps = [emp_map[eid] for eid in ro.employee_ids if eid in emp_map]
            if len(group_emps) < 2:
                continue

            # Sort by performance (ascending) and take the lowest
            group_emps.sort(key=lambda e: e.avg_performance_score)
            lowest = group_emps[0]

            # Savings = salary + bonus + overhead (20%)
            annual_cost = lowest.annual_salary * (1 + lowest.bonus_percentage / 100)
            annual_cost *= 1.2  # Add 20% overhead
            savings += annual_cost

        return savings

    # ── Recommendations ─────────────────────────────────────────

    def _generate_recommendations(
        self,
        department: Department,
        employees: list[Employee],
        role_overlaps: list[RoleOverlap],
        redundant_count: int,
    ) -> list[str]:
        """Generate actionable optimization recommendations."""
        recs: list[str] = []

        if redundant_count == 0:
            recs.append("当前部门人员配置合理，无明显冗余。")
            return recs

        recs.append(f"检测到 {redundant_count} 个潜在冗余岗位，建议优化。")

        for ro in role_overlaps:
            if ro.overlap_score >= 0.8:
                recs.append(
                    f"「{ro.role_title}」岗位重叠度极高（{ro.overlap_score:.0%}），"
                    f"建议合并职责，保留最优表现者。"
                )
            elif ro.overlap_score >= 0.5:
                recs.append(
                    f"「{ro.role_title}」岗位存在一定重叠（{ro.overlap_score:.0%}），"
                    f"建议通过差异化培训或岗位轮换提升效率。"
                )

        # Check for underperformers
        underperformers = [
            e
            for e in employees
            if e.avg_performance_score < self.LOW_PERFORMANCE_THRESHOLD
            and e.avg_performance_score > 0
        ]
        if underperformers:
            recs.append(
                f"部门内有 {len(underperformers)} 名员工绩效低于"
                f"{self.LOW_PERFORMANCE_THRESHOLD:.0f}分，建议启动绩效改进计划。"
            )

        # Check span of control
        manager_ids = [e.manager_id for e in employees if e.manager_id]
        for mgr_id, report_count in Counter(manager_ids).items():
            if report_count > self.SPAN_OF_CONTROL_MAX:
                recs.append(
                    f"管理者 {mgr_id} 的直接下属为 {report_count} 人，"
                    f"超出合理管理幅度（{self.SPAN_OF_CONTROL_MAX}人），建议拆分团队。"
                )

        return recs

    def _generate_summary(
        self,
        department: Department,
        headcount: int,
        redundant: int,
        rate: float,
        savings: float,
        overlaps: list[RoleOverlap],
    ) -> str:
        """Generate a natural-language summary."""
        parts = [
            f"{department.name}部门共 {headcount} 人，",
            f"检测到 {redundant} 个潜在冗余岗位（冗余率 {rate:.1%}）。",
        ]

        if savings > 0:
            parts.append(f"预计优化后可节省约 {savings:.0f} 元/年。")

        if overlaps:
            high_overlap = [ro for ro in overlaps if ro.overlap_score >= 0.7]
            if high_overlap:
                titles = "、".join(ro.role_title for ro in high_overlap)
                parts.append(f"高重叠岗位：{titles}。")

        return " ".join(parts)


# ── Module-level singleton ─────────────────────────────────────────

_analyzer: RedundancyAnalyzer | None = None


def get_analyzer() -> RedundancyAnalyzer:
    """Get or create the redundancy analyzer singleton."""
    global _analyzer
    if _analyzer is None:
        _analyzer = RedundancyAnalyzer()
    return _analyzer
