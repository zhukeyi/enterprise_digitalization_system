"""HR Agent — competency model and person-job matching engine.

Provides competency assessment, weighted scoring, cosine similarity
matching, and gap analysis between employees and positions.

M3-T5-4: 岗位胜任力模型
M3-T5-5: 人岗匹配引擎
"""

from __future__ import annotations

import logging
import math

from agents.hr_agent.models import (
    Competency,
    CompetencyMatchScore,
    Employee,
    MatchResult,
    Position,
)

logger = logging.getLogger("fde.hr.matching")


# ══════════════════════════════════════════════════════════════════
# Competency Model
# ══════════════════════════════════════════════════════════════════


class CompetencyModel:
    """Manages competency definitions and scoring.

    A competency model defines:
    - The set of competencies relevant to the organization
    - Proficiency levels (1-5 scale)
    - Category-based weighting
    """

    # Level labels (1-5)
    LEVEL_LABELS = {
        1: "Novice",
        2: "Advanced Beginner",
        3: "Competent",
        4: "Proficient",
        5: "Expert",
    }

    # Category default weights
    CATEGORY_WEIGHTS: dict[str, float] = {
        "technical": 1.0,
        "soft_skill": 0.8,
        "leadership": 1.2,
        "domain": 0.9,
    }

    def __init__(self) -> None:
        self._competencies: dict[str, Competency] = {}

    def register(self, competency: Competency) -> None:
        """Register a competency definition."""
        self._competencies[competency.competency_id] = competency

    def get(self, competency_id: str) -> Competency | None:
        """Get a competency by ID."""
        return self._competencies.get(competency_id)

    def list_all(self) -> list[Competency]:
        """List all registered competencies."""
        return list(self._competencies.values())

    def category_weight(self, category: str) -> float:
        """Get the default weight for a competency category."""
        return self.CATEGORY_WEIGHTS.get(category, 1.0)

    @staticmethod
    def level_label(level: int) -> str:
        """Get the human-readable label for a proficiency level."""
        return CompetencyModel.LEVEL_LABELS.get(level, f"Level {level}")


# ══════════════════════════════════════════════════════════════════
# Person-Job Matcher
# ══════════════════════════════════════════════════════════════════


class PersonJobMatcher:
    """Matches employees to positions using weighted competency scoring.

    Algorithm:
    1. For each required competency, compare employee's level vs required level
    2. Calculate weighted score (requirement weight x ratio of actual/required)
    3. Aggregate into overall match score (0-100)
    4. Identify gaps where actual < required

    The cosine similarity component compares the employee's competency
    vector against the position's requirement vector for an overall
    directional alignment score.
    """

    # Score thresholds for recommendations
    STRONG_MATCH_THRESHOLD = 85.0
    MATCH_THRESHOLD = 70.0
    PARTIAL_MATCH_THRESHOLD = 50.0

    def __init__(self, competency_model: CompetencyModel | None = None) -> None:
        self.competency_model = competency_model or CompetencyModel()

    def match(self, employee: Employee, position: Position) -> MatchResult:
        """Match a single employee against a single position.

        Args:
            employee: The candidate employee.
            position: The target position with requirements.

        Returns:
            MatchResult with overall score, per-competency scores, gaps, and recommendation.
        """
        logger.info(
            "Matching employee %s against position %s",
            employee.employee_id,
            position.position_id,
        )

        emp_comp_map = employee.competency_summary
        comp_scores: list[CompetencyMatchScore] = []
        gaps: list[str] = []
        gap_count = 0

        total_weight = 0.0
        total_weighted_score = 0.0

        for req in position.required_competencies:
            actual_level = emp_comp_map.get(req.competency_id, 0)
            meets = actual_level >= req.min_level
            gap = max(0, req.min_level - actual_level)

            # Per-competency score: ratio of actual to required, capped at 1.0
            if req.min_level > 0:
                ratio = min(actual_level / req.min_level, 1.0)
            else:
                ratio = 1.0

            weighted_score = ratio * req.weight

            comp_scores.append(
                CompetencyMatchScore(
                    competency_id=req.competency_id,
                    competency_name=req.competency_name,
                    required_level=req.min_level,
                    actual_level=actual_level,
                    meets_requirement=meets,
                    gap=gap,
                    weighted_score=round(weighted_score, 2),
                ),
            )

            total_weight += req.weight
            total_weighted_score += weighted_score

            if not meets:
                gap_count += 1
                gaps.append(
                    f"{req.competency_name}: 需要{req.min_level}级，"
                    f"实际{actual_level}级（差距{gap}级）",
                )

        # Overall score: weighted average x 100
        if total_weight > 0:
            overall = (total_weighted_score / total_weight) * 100.0
        else:
            overall = 0.0

        overall = round(min(overall, 100.0), 1)

        # Cosine similarity component (directional alignment)
        cosine = self._cosine_similarity(employee, position)
        # Blend: 80% weighted score + 20% cosine
        blended = round(overall * 0.8 + cosine * 0.2, 1)

        recommendation = self._recommend(blended, gap_count)

        return MatchResult(
            employee_id=employee.employee_id,
            employee_name=employee.name,
            position_id=position.position_id,
            position_title=position.title,
            overall_score=blended,
            competency_scores=comp_scores,
            gap_count=gap_count,
            gaps=gaps,
            recommendation=recommendation,
            notes=self._generate_notes(blended, gap_count, gaps),
        )

    def match_batch(
        self,
        employees: list[Employee],
        position: Position,
    ) -> list[MatchResult]:
        """Match multiple employees against a single position, sorted by score."""
        results = [self.match(emp, position) for emp in employees]
        return sorted(results, key=lambda r: r.overall_score, reverse=True)

    def match_employee_to_positions(
        self,
        employee: Employee,
        positions: list[Position],
    ) -> list[MatchResult]:
        """Match a single employee against multiple positions, sorted by score."""
        results = [self.match(employee, pos) for pos in positions]
        return sorted(results, key=lambda r: r.overall_score, reverse=True)

    # ── Cosine Similarity ────────────────────────────────────────

    def _cosine_similarity(self, employee: Employee, position: Position) -> float:
        """Calculate cosine similarity between employee competency vector
        and position requirement vector.

        Returns a score from 0 to 100.
        """
        # Build aligned vectors from all competency IDs in requirements
        emp_map = employee.competency_summary

        # Vectors: employee levels and required levels
        emp_vec: list[float] = []
        req_vec: list[float] = []

        for req in position.required_competencies:
            emp_vec.append(float(emp_map.get(req.competency_id, 0)))
            req_vec.append(float(req.min_level))

        if not emp_vec or not req_vec:
            return 0.0

        # Cosine similarity = dot(a,b) / (||a|| * ||b||)
        dot = sum(a * b for a, b in zip(emp_vec, req_vec, strict=True))
        norm_a = math.sqrt(sum(a * a for a in emp_vec))
        norm_b = math.sqrt(sum(b * b for b in req_vec))

        if norm_a == 0 or norm_b == 0:
            return 0.0

        cosine = dot / (norm_a * norm_b)
        return round(cosine * 100.0, 1)

    # ── Recommendation Logic ─────────────────────────────────────

    def _recommend(self, score: float, gap_count: int) -> str:
        """Generate a recommendation based on score and gap count."""
        if score >= self.STRONG_MATCH_THRESHOLD and gap_count == 0:
            return "strong_match"
        if score >= self.MATCH_THRESHOLD and gap_count <= 1:
            return "match"
        if score >= self.PARTIAL_MATCH_THRESHOLD:
            return "partial_match"
        return "no_match"

    @staticmethod
    def _generate_notes(score: float, gap_count: int, gaps: list[str]) -> str:
        """Generate human-readable notes for the match result."""
        if gap_count == 0:
            return f"匹配度 {score}分，全部胜任力达标，无需额外培训。"
        if gap_count <= 2:
            gap_summary = "; ".join(gaps[:2])
            return f"匹配度 {score}分，存在 {gap_count} 项能力缺口：{gap_summary}。建议针对性培训。"
        return f"匹配度 {score}分，存在 {gap_count} 项能力缺口，差距较大，建议重新评估或加强培训。"


# ── Module-level singletons ────────────────────────────────────────

_matcher: PersonJobMatcher | None = None
_competency_model: CompetencyModel | None = None


def get_matcher() -> PersonJobMatcher:
    """Get or create the matcher singleton."""
    global _matcher
    if _matcher is None:
        _matcher = PersonJobMatcher()
    return _matcher


def get_competency_model() -> CompetencyModel:
    """Get or create the competency model singleton."""
    global _competency_model
    if _competency_model is None:
        _competency_model = CompetencyModel()
    return _competency_model
