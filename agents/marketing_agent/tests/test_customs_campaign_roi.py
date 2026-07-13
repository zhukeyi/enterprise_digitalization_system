"""Tests for customs-segment ROI attribution (P1-C, C-11)."""

from __future__ import annotations

from agents.data_agent.customs_models import BuyerEntity
from agents.marketing_agent.customs_audience_connector import CustomsAudienceConnector
from agents.marketing_agent.customs_campaign_roi import CustomsCampaignROI


def _segments():
    buyers = [
        BuyerEntity(
            raw_name="Globex Corp", normalized_name="globex corp",
            import_count=30, total_value_usd=500_000.0,
            top_hs_codes=["8517"], top_ports=["Shanghai"],
            last_seen="2026-03-01",
        ),
        BuyerEntity(
            raw_name="Initech LLC", normalized_name="initech llc",
            import_count=8, total_value_usd=120_000.0,
            top_hs_codes=["8517"], top_ports=["Shanghai"],
            last_seen="2025-06-01",
        ),
        BuyerEntity(
            raw_name="Stark Industries", normalized_name="stark industries",
            import_count=12, total_value_usd=300_000.0,
            top_hs_codes=["8708"], top_ports=["Los Angeles"],
            last_seen="2024-01-01",
        ),
    ]
    return CustomsAudienceConnector().build_from_buyers(buyers)


def test_attribute_produces_blended_roas():
    roi = CustomsCampaignROI()
    out = roi.attribute(_segments())
    assert out["segments"]
    assert out["blended_roas"] > 0
    # revenue should exceed spend (positive ROAS) under default assumptions
    assert out["total_revenue"] > out["total_spend"]
    # ranking sorted desc by roas
    roas = [r["roas"] for r in out["ranking"]]
    assert roas == sorted(roas, reverse=True)


def test_per_segment_buyer_count_carried():
    roi = CustomsCampaignROI()
    out = roi.attribute(_segments())
    total_buyers = sum(s["deliverable_buyers"] for s in out["segments"])
    assert total_buyers >= 3  # 3 clean buyers across segments


def test_roi_prediction_requires_two_segments():
    roi = CustomsCampaignROI()
    # only one deliverable segment
    buyers = [
        BuyerEntity(
            raw_name="Solo Corp", normalized_name="solo corp",
            import_count=20, total_value_usd=200_000.0,
            top_hs_codes=["8517"], top_ports=["Shanghai"],
            last_seen="2026-02-01",
        )
    ]
    segs = CustomsAudienceConnector().build_from_buyers(buyers)
    out = roi.attribute(segs, total_budget=50_000.0)
    # single segment → no OLS prediction (predictor needs ≥2 points)
    assert out["roi_prediction"] is None


def test_roi_prediction_fires_with_budget():
    roi = CustomsCampaignROI()
    out = roi.attribute(_segments(), total_budget=80_000.0)
    assert out["roi_prediction"] is not None
    pred = out["roi_prediction"]
    assert pred["spend"] == 80_000.0
    assert 0 <= pred["fit_r_squared"] <= 1
    # predicted revenue scales with budget
    assert pred["predicted_revenue"] > 0
    assert pred["predicted_roas"] >= 0


def test_empty_segments_safe():
    roi = CustomsCampaignROI()
    out = roi.attribute([])
    assert out["blended_roas"] == 0.0
    assert out["segments"] == []


def test_roas_differs_across_segments():
    """F3 regression: segments with different growth tiers and aggregate values
    must produce *different* ROAS — not a constant.

    Without differentiation, all segments share the same roas = deal*conv/cpl,
    and OLS regression degenerates. This test guards against that.
    """
    buyers = [
        # Rising + high value → highest ROAS
        BuyerEntity(
            raw_name="Alpha Corp", normalized_name="alpha corp",
            import_count=30, total_value_usd=600_000.0,
            top_hs_codes=["8517"], top_ports=["Shanghai"],
            last_seen="2026-03-01",
        ),
        # Declining + low value → lowest ROAS
        BuyerEntity(
            raw_name="Beta Corp", normalized_name="beta corp",
            import_count=12, total_value_usd=30_000.0,
            top_hs_codes=["8708"], top_ports=["Los Angeles"],
            last_seen="2021-01-01",
        ),
    ]
    segs = CustomsAudienceConnector().build_from_buyers(buyers)
    assert len(segs) == 2
    roi = CustomsCampaignROI()
    out = roi.attribute(segs)
    roas_values = [s["roas"] for s in out["segments"]]
    assert len(roas_values) == 2
    # The two segments must have *different* ROAS
    assert roas_values[0] != roas_values[1]
    # Rising+high-value segment should have higher ROAS than declining+low-value
    rising_idx = next(
        i for i, s in enumerate(out["segments"])
        if "Machinery" in s["channel"]
    )
    declining_idx = 1 - rising_idx
    assert roas_values[rising_idx] > roas_values[declining_idx]
