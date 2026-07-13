"""ROI attribution for customs-segment GEO campaigns (P1-C, C-11).

Treats each customs audience ``segment`` as an ad "channel" and reuses the
existing ``PerformanceTracker`` (blended ROAS / ranking) and ``ROIPredictor``
(OLS spend→revenue) to attribute expected return.

The customs data base carries no spend/revenue, so a transparent, configurable
funnel model converts each segment's *deliverable buyer count* into a plausible
channel performance:

* ``spend``   = cost-per-contact × deliverable buyers
* ``revenue`` = deal value × conversion rate × deliverable buyers
* ``roas``    = revenue / spend

The same model is reused for the OLS prediction: ``ROIPredictor`` fits
revenue = a + b·spend across the segments and forecasts return for a proposed
total budget (requires ≥ 2 segments, matching the predictor's contract).
"""

from __future__ import annotations

from typing import Any

from agents.marketing_agent.analytics.performance_tracker import PerformanceTracker
from agents.marketing_agent.analytics.roi_predictor import ROIPredictor
from agents.marketing_agent.customs_audience_connector import CustomsAudienceSegment
from agents.marketing_agent.models import PlatformPerformance

__all__ = ["CustomsCampaignROI"]


class CustomsCampaignROI:
    """Attributes ROI across customs audience segments as channels."""

    def __init__(
        self,
        *,
        cost_per_contact: float = 50.0,
        conversion_rate: float = 0.08,
        deal_value: float = 25_000.0,
        impressions_per_contact: int = 3,
    ) -> None:
        """Initialize the funnel assumptions.

        Args:
            cost_per_contact: Expected cost to reach one deliverable buyer.
            conversion_rate: Fraction of reached buyers that convert to a deal.
            deal_value: Average revenue per converted buyer.
            impressions_per_contact: Impressions generated per contact (for CTR).
        """
        self._cpl = cost_per_contact
        self._conv = conversion_rate
        self._deal = deal_value
        self._impr = impressions_per_contact

    # ── public API ────────────────────────────────────────────────

    def attribute(
        self, segments: list[CustomsAudienceSegment], total_budget: float | None = None
    ) -> dict[str, Any]:
        """Attribute ROI across deliverable segments.

        Args:
            segments: Segments produced by the audience connector.
            total_budget: Proposed campaign budget for OLS ROI forecasting
                (only used when ≥ 2 deliverable segments are present).

        Returns:
            Dict with per-segment channel performance, blended ROAS, ranking,
            and (optionally) an ``roi_prediction`` key.
        """
        built = [(s, self._to_platform(s)) for s in segments if s.outreach_ready]
        platforms = [p for _, p in built]
        if not platforms:
            return {
                "segments": [],
                "blended_roas": 0.0,
                "total_spend": 0.0,
                "total_revenue": 0.0,
                "ranking": [],
                "roi_prediction": None,
            }

        agg = PerformanceTracker().aggregate(platforms)
        result: dict[str, Any] = {
            "segments": [
                self._channel_summary(seg, p) for seg, p in built
            ],
            "blended_roas": agg["blended_roas"],
            "total_spend": agg["total_spend"],
            "total_revenue": agg["total_revenue"],
            "ranking": agg["ranking"],
            "roi_prediction": None,
        }
        if total_budget is not None and len(platforms) >= 2:
            try:
                pred = ROIPredictor().predict(platforms, total_budget)
                result["roi_prediction"] = pred.model_dump()
            except ValueError:
                result["roi_prediction"] = None
        return result

    # ── internals ─────────────────────────────────────────────────

    def _to_platform(self, segment: CustomsAudienceSegment) -> PlatformPerformance:
        n = max(1, segment.deliverable_count)
        spend = round(self._cpl * n, 2)
        revenue = round(self._deal * self._conv * n, 2)
        impressions = n * self._impr
        clicks = max(1, int(impressions * 0.04))
        conversions = max(1, int(n * self._conv))
        roas = revenue / spend if spend else 0.0
        return PlatformPerformance(
            platform=f"{segment.category}@{segment.port}",
            spend=spend,
            revenue=revenue,
            impressions=impressions,
            clicks=clicks,
            conversions=conversions,
            roas=round(roas, 2),
            ctr=clicks / impressions if impressions else 0.0,
            cpc=spend / clicks if clicks else 0.0,
            conv_rate=conversions / clicks if clicks else 0.0,
            trend_30d=1.0 if segment.growth_tier.value in ("rising", "stable") else -0.2,
        )

    @staticmethod
    def _channel_summary(segment: CustomsAudienceSegment, p: PlatformPerformance) -> dict[str, Any]:
        return {
            "channel": p.platform,
            "deliverable_buyers": segment.deliverable_count,
            "spend": round(p.spend, 2),
            "revenue": round(p.revenue, 2),
            "roas": p.roas,
        }
