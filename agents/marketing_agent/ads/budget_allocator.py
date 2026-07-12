"""Budget Allocator — distributes a total ad budget across platforms in
proportion to their ROAS (return on ad spend), a simple but effective
multiplicative-weights rule that beats an even split when platforms differ.
Reports projected revenue / ROAS per platform and the blended improvement.
"""

from __future__ import annotations

from typing import Any

from agents.marketing_agent.models import PlatformBudget, PlatformPerformance


class BudgetAllocator:
    """Allocates budget proportionally to historical ROAS."""

    def allocate(
        self, platforms: list[PlatformPerformance], total_budget: float
    ) -> dict[str, Any]:
        if not platforms:
            return {"allocations": [], "blended_roas": 0.0, "projected_revenue": 0.0, "uplift_pct": 0.0}
        roas = [max(p.roas, 0.1) for p in platforms]
        weights = [r / sum(roas) for r in roas]

        allocations: list[PlatformBudget] = []
        proj_rev = 0.0
        even_rev = 0.0
        for p, w in zip(platforms, weights, strict=False):
            budget = total_budget * w
            # assume ROAS holds at the margin (first-order)
            rev = budget * p.roas
            proj_rev += rev
            even_rev += (total_budget / len(platforms)) * p.roas
            allocations.append(
                PlatformBudget(
                    platform=p.platform,
                    current_spend=p.spend,
                    current_roas=p.roas,
                    allocated_budget=round(budget, 2),
                    projected_revenue=round(rev, 2),
                    projected_roas=p.roas,
                )
            )

        blended_roas = proj_rev / total_budget if total_budget else 0.0
        even_roas = even_rev / total_budget if total_budget else 0.0
        uplift = ((blended_roas - even_roas) / even_roas * 100) if even_roas else 0.0

        return {
            "allocations": [a.model_dump() for a in allocations],
            "blended_roas": round(blended_roas, 2),
            "even_split_roas": round(even_roas, 2),
            "projected_revenue": round(proj_rev, 2),
            "uplift_pct": round(uplift, 1),
        }


__all__ = ["BudgetAllocator"]
