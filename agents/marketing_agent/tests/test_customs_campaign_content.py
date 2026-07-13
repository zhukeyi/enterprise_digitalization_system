"""Tests for segment-targeted GEO content generation (P1-C, C-9)."""

from __future__ import annotations

from agents.data_agent.customs_models import BuyerEntity
from agents.marketing_agent.customs_audience_connector import (
    CustomsAudienceConnector,
    FrequencyTier,
    GrowthTier,
)
from agents.marketing_agent.customs_campaign_content import CustomsCampaignContent


def _seg():
    buyers = [
        BuyerEntity(
            raw_name="Globex Corp", normalized_name="globex corp",
            country="US", source_country="CN",
            import_count=30, total_value_usd=500_000.0,
            top_hs_codes=["8517", "8471"], top_ports=["Shanghai"],
            first_seen="2023-01-01", last_seen="2026-03-01",
        )
    ]
    segs = CustomsAudienceConnector().build_from_buyers(buyers)
    assert segs and segs[0].frequency_tier == FrequencyTier.HIGH
    return segs[0]


def test_geo_piece_is_optimized_and_segment_aware():
    seg = _seg()
    content = CustomsCampaignContent(brand="云栖智能", brand_id="B001").generate(seg)
    assert content.geo_piece.geo_optimized is True
    # citation_score is topic-dependent; a citable, GEO-optimised draft is >= 50
    assert content.geo_piece.citation_score >= 50
    # segment context injected as facts
    assert "口岸" in content.geo_piece.body
    assert "Globex" in content.geo_piece.body or "Machinery" in content.geo_piece.body


def test_multilingual_variants_generated():
    seg = _seg()
    content = CustomsCampaignContent(
        brand="云栖智能", target_langs=["en", "ja", "ko"]
    ).generate(seg)
    assert "zh" in content.multilingual.pieces
    for lang in ["en", "ja", "ko"]:
        assert lang in content.multilingual.pieces
        assert content.multilingual.pieces[lang].geo_optimized is True


def test_keywords_derived_and_ranked():
    seg = _seg()
    content = CustomsCampaignContent(brand="云栖智能", brand_id="B001").generate(seg)
    assert content.keywords
    scores = [k.opportunity_score for k in content.keywords]
    assert scores == sorted(scores, reverse=True)
    # customs-derived seeds present
    assert any("供应商" in k.term or "进口" in k.term for k in content.keywords)
    # brand plan fused (brand_id given)
    assert any(k.intent for k in content.keywords)


def test_keywords_work_without_brand_id():
    seg = _seg()
    content = CustomsCampaignContent(brand="云栖智能").generate(seg)
    assert content.keywords
    assert all(0 <= k.opportunity_score <= 100 for k in content.keywords)
