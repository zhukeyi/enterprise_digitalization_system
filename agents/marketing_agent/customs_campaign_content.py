"""Segment-targeted GEO content generation for customs audiences (P1-C, C-9).

Turns a ``CustomsAudienceSegment`` (from C-8) into ready-to-publish GEO assets
for the *promoting* brand:

* a GEO-optimised content draft whose facts are seeded with the segment's
  category / port / frequency / growth context;
* localised multilingual variants (reuses ``MultilingualWriter``);
* a derived keyword-opportunity list (reuses ``Keyword`` + ``KeywordStrategy``
  when a ``brand_id`` is supplied, otherwise a self-contained customs scorer).

No raw BOL data is rendered into copy — only the derivative segment profile
(category, port, tier labels, aggregate counts) is used as the targeting hook.
"""

from __future__ import annotations

from datetime import UTC, datetime

from pydantic import BaseModel, Field

from agents.marketing_agent.content.geo_writer import GEOWriter
from agents.marketing_agent.content.multilingual import MultilingualWriter
from agents.marketing_agent.customs_audience_connector import CustomsAudienceSegment
from agents.marketing_agent.geo.keyword_strategy import KeywordStrategy
from agents.marketing_agent.models import ContentPiece, Keyword, MultilingualContent

__all__ = ["CustomsCampaignContent", "CustomsSegmentContent"]


class CustomsSegmentContent(BaseModel):
    """The GEO content package produced for one customs audience segment."""

    segment_id: str = Field(description="Source segment id")
    topic: str = Field(description="GEO topic = segment category (HS section)")
    geo_piece: ContentPiece = Field(description="Source-language GEO draft")
    multilingual: MultilingualContent = Field(description="Localised variants")
    keywords: list[Keyword] = Field(default_factory=list, description="Derived keyword opportunities")
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class CustomsCampaignContent:
    """Generates GEO content packages targeted at customs audience segments."""

    def __init__(
        self,
        brand: str,
        *,
        brand_id: str | None = None,
        target_langs: list[str] | None = None,
    ) -> None:
        """Initialize.

        Args:
            brand: The promoting brand name (rendered into the copy).
            brand_id: Optional marketing-connector brand id; when provided, the
                brand's own ``KeywordStrategy`` plan is fused into the derived
                keyword list (reuse).
            target_langs: Target languages for multilingual localisation.
        """
        self._brand = brand
        self._brand_id = brand_id
        self._target_langs = target_langs

    def generate(self, segment: CustomsAudienceSegment) -> CustomsSegmentContent:
        """Produce a full GEO content package for ``segment``."""
        topic = segment.category
        facts = self._segment_facts(segment)
        geo_piece = GEOWriter().write(self._brand, topic, facts=facts)
        multilingual = MultilingualWriter().write(
            self._brand, topic, self._target_langs
        )
        keywords = self._derive_keywords(segment)
        return CustomsSegmentContent(
            segment_id=segment.segment_id,
            topic=topic,
            geo_piece=geo_piece,
            multilingual=multilingual,
            keywords=keywords,
        )

    # ── helpers ───────────────────────────────────────────────────

    def _segment_facts(self, segment: CustomsAudienceSegment) -> list[str]:
        port_label = segment.port if segment.port != "unknown" else "主要口岸"
        avg_batches = (
            round(segment.deliverable_count and sum(b.import_count for b in segment.deliverable_buyers) / segment.deliverable_count, 1)
            if segment.deliverable_count
            else 0.0
        )
        facts = [
            f"目标受众：{port_label} 口岸的 {segment.category} 进口商"
            f"（{segment.frequency_tier.value}频次、{segment.growth_tier.value}增长信号）",
            f"可触达买家 {segment.deliverable_count} 家，合计进口额约 "
            f"${segment.total_value_usd:,.0f}",
            f"该群体单家平均年进口批次约 {avg_batches} 批，需求持续且高频",
        ]
        if segment.hs_codes:
            facts.append(f"核心 HS 编码：{'、'.join(segment.hs_codes[:3])}")
        facts.append(
            f"{self._brand} 面向该群体的供应方案已在生产环境验证，可提供可引用基准数据"
        )
        return facts

    def _derive_keywords(self, segment: CustomsAudienceSegment) -> list[Keyword]:
        # Seed commercial-intent terms from the segment's derivative profile.
        seeds: list[str] = [f"{segment.category} 供应商"]
        if segment.port and segment.port != "unknown":
            seeds.append(f"{segment.port} {segment.category} 进口")
        for hs in segment.hs_codes[:3]:
            seeds.append(f"{hs} 采购商推荐")

        out: list[Keyword] = []
        for term in seeds:
            # Volume proxy: more deliverable buyers → higher proxy search interest.
            vol = int(min(25000, 800 + segment.deliverable_count * 400 + int(segment.total_value_usd // 1000)))
            # Long-tail (has port / HS) terms are easier to rank than generic ones.
            is_generic = "供应商" in term and (not segment.port or segment.port == "unknown")
            difficulty = 72.0 if is_generic else 44.0
            position = 8.0  # assume not yet in the AI citation zone
            opp = round(
                100.0
                * (0.45 * (vol / 25000.0) + 0.30 * (1.0 - difficulty / 100.0) + 0.25 * ((10.0 - position) / 9.0)),
                1,
            )
            out.append(
                Keyword(
                    term=term,
                    intent="commercial",
                    monthly_volume=vol,
                    difficulty=difficulty,
                    current_position=position,
                    opportunity_score=opp,
                )
            )

        # Optional enrichment: fuse the brand's own keyword plan (reuse KeywordStrategy).
        if self._brand_id:
            try:
                for k in KeywordStrategy().plan(self._brand_id, top_n=5):
                    out.append(
                        Keyword(
                            term=k["term"],
                            intent=k["intent"],
                            monthly_volume=k["monthly_volume"],
                            difficulty=k["difficulty"],
                            current_position=k["current_position"],
                            opportunity_score=k["opportunity_score"],
                        )
                    )
            except Exception:
                pass

        out.sort(key=lambda x: x.opportunity_score, reverse=True)
        return out
