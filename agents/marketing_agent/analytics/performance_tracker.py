"""Performance Tracker — aggregates multi-platform ad performance and derives
a blended ROAS, plus a ranking of platforms by efficiency. Used by the ROI
dashboard.
"""

from __future__ import annotations

from typing import Any

from agents.marketing_agent.models import PlatformPerformance


class PerformanceTracker:
    """Aggregates platform performance into blended metrics + ranking."""

    def aggregate(self, platforms: list[PlatformPerformance]) -> dict[str, Any]:
        if not platforms:
            return {"blended_roas": 0.0, "total_spend": 0.0, "total_revenue": 0.0, "ranking": []}
        total_spend = sum(p.spend for p in platforms)
        total_revenue = sum(p.revenue for p in platforms)
        total_clicks = sum(p.clicks for p in platforms)
        total_impr = sum(p.impressions for p in platforms)
        total_conv = sum(p.conversions for p in platforms)
        blended = total_revenue / total_spend if total_spend else 0.0

        ranking = sorted(
            platforms,
            key=lambda p: p.roas,
            reverse=True,
        )
        return {
            "blended_roas": round(blended, 2),
            "total_spend": round(total_spend, 2),
            "total_revenue": round(total_revenue, 2),
            "total_impressions": total_impr,
            "total_clicks": total_clicks,
            "total_conversions": total_conv,
            "blended_ctr": round(total_clicks / total_impr, 5) if total_impr else 0.0,
            "blended_conv_rate": round(total_conv / total_clicks, 5) if total_clicks else 0.0,
            "ranking": [
                {
                    "platform": p.platform,
                    "roas": p.roas,
                    "spend": round(p.spend, 2),
                    "revenue": round(p.revenue, 2),
                    "trend_30d": p.trend_30d,
                }
                for p in ranking
            ],
        }


__all__ = ["PerformanceTracker"]
