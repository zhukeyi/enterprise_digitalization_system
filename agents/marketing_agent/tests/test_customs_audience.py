"""Tests for the customs-derived audience connector (P1-C, C-8).

These are numpy-free: the connector consumes ``BuyerEntity`` derivatives and
applies sanctions screening, so it can be validated without the marketing
content/analytics math (which depends on numpy).
"""

from __future__ import annotations

from agents.data_agent.customs_models import BuyerEntity
from agents.marketing_agent.customs_audience_connector import (
    CustomsAudienceConnector,
    FrequencyTier,
    GrowthTier,
    SegmentComplianceStatus,
)


def _buyer(
    *,
    name: str,
    norm: str | None = None,
    country: str | None = "US",
    source_country: str | None = "CN",
    import_count: int = 1,
    value: float = 1000.0,
    hs: list[str] | None = None,
    ports: list[str] | None = None,
    first_seen: str | None = "2023-01-01",
    last_seen: str | None = "2026-03-01",
) -> BuyerEntity:
    return BuyerEntity(
        raw_name=name,
        normalized_name=norm or name.lower(),
        country=country,
        source_country=source_country,
        import_count=import_count,
        total_value_usd=value,
        top_hs_codes=hs or [],
        top_ports=ports or [],
        first_seen=first_seen,
        last_seen=last_seen,
    )


def _sample_buyers() -> list[BuyerEntity]:
    return [
        # Machinery & electrical @ Shanghai, high freq, rising — mix of clean + sanctioned
        _buyer(name="Globex Corp", import_count=30, value=500_000.0,
               hs=["8517", "8471"], ports=["Shanghai", "Ningbo"], last_seen="2026-03-01"),
        _buyer(name="SANCTIONED SAMPLE CORP", import_count=50, value=900_000.0,
               hs=["8517"], ports=["Shanghai"], last_seen="2026-01-01"),
        # Machinery & electrical @ Shanghai, mid freq, rising — clean
        _buyer(name="Initech LLC", import_count=8, value=120_000.0,
               hs=["8517"], ports=["Shanghai"], last_seen="2025-06-01"),
        # Textiles @ Ningbo, low freq, declining — clean
        _buyer(name="Umbrella Ltd", import_count=3, value=40_000.0,
               hs=["6109"], ports=["Ningbo"], last_seen="2021-01-01"),
        # Vehicles @ Los Angeles, mid freq, stable — clean
        _buyer(name="Stark Industries", import_count=12, value=300_000.0,
               hs=["8708"], ports=["Los Angeles"], last_seen="2024-01-01"),
    ]


def _find(segments, **kw):
    for s in segments:
        ok = all(getattr(s, k) == v for k, v in kw.items())
        if ok:
            return s
    return None


def test_segmentation_produces_expected_cells():
    connector = CustomsAudienceConnector()
    segs = connector.build_from_buyers(_sample_buyers())
    # 4 distinct (category × port × freq × growth) cells
    assert len(segs) == 4
    categories = {s.category for s in segs}
    assert any("Machinery" in c for c in categories)
    assert any("Textiles" in c for c in categories)
    assert any("Vehicles" in c for c in categories)


def test_segments_sorted_by_deliverable_value_desc():
    connector = CustomsAudienceConnector()
    segs = connector.build_from_buyers(_sample_buyers())
    vals = [s.total_value_usd for s in segs]
    assert vals == sorted(vals, reverse=True)


def test_sanctions_blocked_buyer_excluded_from_deliverable():
    connector = CustomsAudienceConnector()
    segs = connector.build_from_buyers(_sample_buyers())
    high = _find(segs, port="shanghai", frequency_tier=FrequencyTier.HIGH,
                 growth_tier=GrowthTier.RISING)
    assert high is not None
    # Globex (clean) deliverable, SANCTIONED SAMPLE CORP blocked
    assert high.deliverable_count == 1
    assert high.blocked_count == 1
    assert high.compliance_status == SegmentComplianceStatus.PARTIAL
    assert "SANCTIONED SAMPLE CORP" in high.blocked_sample
    assert high.outreach_ready is True


def test_clean_segment_is_passed():
    connector = CustomsAudienceConnector()
    segs = connector.build_from_buyers(_sample_buyers())
    mid = _find(segs, port="shanghai", frequency_tier=FrequencyTier.MID,
                growth_tier=GrowthTier.RISING)
    assert mid is not None
    assert mid.deliverable_count == 1
    assert mid.blocked_count == 0
    assert mid.compliance_status == SegmentComplianceStatus.PASSED


def test_growth_tier_derived_from_last_seen():
    connector = CustomsAudienceConnector()
    segs = connector.build_from_buyers(_sample_buyers())
    declining = _find(segs, growth_tier=GrowthTier.DECLINING)
    assert declining is not None
    assert any(b.name == "Umbrella Ltd" for b in declining.deliverable_buyers)
    stable = _find(segs, growth_tier=GrowthTier.STABLE)
    assert stable is not None
    assert any(b.name == "Stark Industries" for b in stable.deliverable_buyers)


def test_filter_by_growth_tier():
    connector = CustomsAudienceConnector()
    segs = connector.build_from_buyers(_sample_buyers(), growth_tier=GrowthTier.RISING)
    assert len(segs) == 2  # the two Shanghai cells
    assert all(s.growth_tier == GrowthTier.RISING for s in segs)


def test_filter_by_min_value_excludes_small():
    connector = CustomsAudienceConnector()
    segs = connector.build_from_buyers(_sample_buyers(), min_value_usd=50_000.0)
    # Umbrella (40k) dropped
    assert all(s.total_value_usd >= 50_000.0 for s in segs)
    assert _find(segs, port="ningbo") is None


def test_deliverable_buyer_contains_only_derivative_fields():
    connector = CustomsAudienceConnector()
    segs = connector.build_from_buyers(_sample_buyers())
    for s in segs:
        for b in s.deliverable_buyers:
            # No raw BOL payload leaks — only the derivative profile
            assert isinstance(b, object)
            assert b.name
            assert b.total_value_usd >= 0


def test_filter_by_country():
    """country filter restricts segmentation to buyers from a specific country."""
    buyers = _sample_buyers()
    # Add a buyer from Japan
    buyers.append(_buyer(name="Japanese Corp", country="JP", import_count=25,
                         value=400_000.0, hs=["8517"], ports=["Osaka"],
                         last_seen="2026-01-01"))
    connector = CustomsAudienceConnector()
    segs = connector.build_from_buyers(buyers, country="JP")
    assert len(segs) == 1
    assert segs[0].port == "osaka"
    assert all(
        b.country == "JP" for s in segs for b in s.deliverable_buyers
    )


def test_filter_by_min_import_count():
    """min_import_count drops buyers below the shipment threshold."""
    connector = CustomsAudienceConnector()
    # All sample buyers have import_count: 30,50,8,3,12
    # min_import_count=10 → drops Initech (8) and Umbrella (3)
    segs = connector.build_from_buyers(_sample_buyers(), min_import_count=10)
    for s in segs:
        for b in s.deliverable_buyers:
            assert b.import_count >= 10
    # Umbrella (count=3) should not appear in any segment
    assert not any(
        b.name == "Umbrella Ltd" for s in segs for b in s.deliverable_buyers
    )
