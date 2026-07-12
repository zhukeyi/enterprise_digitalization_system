"""A/B Tester — statistically compares two ad variants using a two-proportion
z-test on click-through rates, reporting lift, significance and a winner.
"""

from __future__ import annotations

import math

from agents.marketing_agent.models import ABTestResult


class ABTester:
    """Compares variant A vs B on CTR with a z-test."""

    def compare(
        self,
        variant_a: str,
        variant_b: str,
        impressions_a: int,
        clicks_a: int,
        impressions_b: int,
        clicks_b: int,
    ) -> ABTestResult:
        if impressions_a <= 0 or impressions_b <= 0:
            raise ValueError("曝光量必须为正数")
        ctr_a = clicks_a / impressions_a
        ctr_b = clicks_b / impressions_b

        # pooled two-proportion z-test
        p_pool = (clicks_a + clicks_b) / (impressions_a + impressions_b)
        se = math.sqrt(p_pool * (1 - p_pool) * (1 / impressions_a + 1 / impressions_b))
        z = (ctr_b - ctr_a) / se if se > 0 else 0.0
        p_value = 2 * (1 - _norm_cdf(abs(z)))
        significant = p_value < 0.05
        winner = variant_b if (ctr_b > ctr_a and significant) else (variant_a if (ctr_a > ctr_b and significant) else None)
        lift = ((ctr_b - ctr_a) / ctr_a * 100) if ctr_a > 0 else 0.0

        return ABTestResult(
            variant_a=variant_a,
            variant_b=variant_b,
            impressions_a=impressions_a,
            impressions_b=impressions_b,
            clicks_a=clicks_a,
            clicks_b=clicks_b,
            ctr_a=round(ctr_a, 5),
            ctr_b=round(ctr_b, 5),
            lift_pct=round(lift, 2),
            z_score=round(z, 3),
            p_value=round(p_value, 4),
            confidence=round((1 - p_value) * 100, 1),
            winner=winner,
            significant=significant,
        )


def _norm_cdf(x: float) -> float:
    """Standard normal CDF via erf approximation."""
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


__all__ = ["ABTester"]
