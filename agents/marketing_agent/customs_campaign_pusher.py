"""Customs-segment push delivery for GEO campaigns (P1-C, C-10).

Delivers a ``CustomsAudienceSegment`` + its GEO content package as a
``ReportInstance`` over enterprise channels (portal / webhook / email), reusing
the existing ``PushService`` and the ``OutreachComplianceGate`` from the
compliance guard.

Compliance red lines enforced here (R2 — privacy / anti-spam):

* **Portal / webhook**: derivative-only, no buyer PII required → always allowed
  (``enterprise_outreach_allowed(None)`` is True).
* **Email**: requires a *corporate* (non-free) address, explicit consent, and a
  working unsubscribe URL; on pass, a CAN-SPAM/CASL/GDPR footer is force-appended.
* **Sanctions (R3)**: a segment that failed screening (``BLOCKED`` / no
  deliverable buyers) is refused before any send.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from agents.data_agent.compliance_guard import (
    OutreachComplianceGate,
    SanctionsGuard,
    append_unsubscribe_footer,
)
from agents.data_agent.push_service import PushService, get_push_service
from agents.data_agent.report_models import (
    PushChannel,
    PushResult,
    PushTarget,
    ReportFormat,
    ReportInstance,
)
from agents.marketing_agent.customs_audience_connector import CustomsAudienceSegment
from agents.marketing_agent.customs_campaign_content import CustomsSegmentContent

__all__ = ["CustomsCampaignPusher", "SegmentPushRequest", "SegmentPushResponse"]


class SegmentPushRequest(BaseModel):
    """A request to push a customs segment's campaign to one channel."""

    channel: PushChannel = Field(description="Delivery channel")
    address: str = Field(description="Target address (email / webhook URL / portal id)")
    email: str | None = Field(default=None, description="Corporate email (email channel)")
    consent: bool | None = Field(default=None, description="Explicit consent (email channel)")
    unsubscribe_url: str | None = Field(default=None, description="One-click unsubscribe URL")
    subject: str | None = Field(default=None, description="Email subject")
    metadata: dict[str, Any] = Field(default_factory=dict)


class SegmentPushResponse(BaseModel):
    """Outcome of a segment push attempt."""

    segment_id: str
    channel: PushChannel
    success: bool
    message: str
    delivered_at: datetime | None = None
    compliance_checked: bool = True


class CustomsCampaignPusher:
    """Builds and delivers customs-segment GEO campaign reports."""

    def __init__(
        self,
        push_service: PushService | None = None,
        gate: OutreachComplianceGate | None = None,
    ) -> None:
        self._push = push_service or get_push_service()
        self._gate = gate or OutreachComplianceGate(SanctionsGuard())

    # ── public API ────────────────────────────────────────────────

    def build_report(
        self, segment: CustomsAudienceSegment, content: CustomsSegmentContent
    ) -> ReportInstance:
        """Render the segment + content as a derivative-only markdown report."""
        langs = ", ".join(content.multilingual.pieces.keys())
        top_kw = content.keywords[0] if content.keywords else None
        kw_line = (
            f"- Top 关键词：`{top_kw.term}`（机会分 {top_kw.opportunity_score}）"
            if top_kw
            else "- Top 关键词：无"
        )
        lines = [
            "# 海关数据驱动的 GEO 定向触达报告",
            "",
            f"- 受众分群：{segment.name}",
            f"- 品类（HS 章节）：{segment.category}",
            f"- 口岸：{segment.port}",
            f"- 频次 / 增长：{segment.frequency_tier.value} / {segment.growth_tier.value}",
            f"- 可触达买家：{segment.deliverable_count} 家"
            f"（制裁拦截 {segment.blocked_count} 家，合规状态 {segment.compliance_status.value}）",
            f"- 合计进口额：${segment.total_value_usd:,.0f}",
            f"- GEO 内容主题：{content.topic}",
            f"- GEO 草稿标题：{content.geo_piece.title}",
            f"- 多语言版本：{langs}",
            kw_line,
            "",
            "> 本简报仅基于公开贸易数据的衍生画像（BuyerEntity），不含任何原始提单（BOL）记录。",
        ]
        return ReportInstance(
            template_id="customs-geo-segment",
            title=f"GEO 触达 · {segment.category} @ {segment.port}",
            format=ReportFormat.MARKDOWN,
            content="\n".join(lines),
            variables_used={"segment_id": segment.segment_id},
        )

    async def push_segment(
        self,
        segment: CustomsAudienceSegment,
        content: CustomsSegmentContent,
        req: SegmentPushRequest,
    ) -> SegmentPushResponse:
        """Validate compliance, render, and deliver a segment campaign."""
        # R3: refuse blocked / empty segments before any send.
        if not segment.outreach_ready:
            return SegmentPushResponse(
                segment_id=segment.segment_id,
                channel=req.channel,
                success=False,
                message=f"分群不可触达（合规状态 {segment.compliance_status.value}）",
                compliance_checked=True,
            )

        report = self.build_report(segment, content)
        target = PushTarget(
            channel=req.channel,
            address=req.address,
            metadata={"subject": req.subject or report.title, **req.metadata},
        )

        # R2: email requires enterprise channel + consent + unsubscribe footer.
        if req.channel == PushChannel.EMAIL:
            decision = self._gate.evaluate(
                buyer_name=segment.name,
                country=None,
                email=req.email,
                consent=req.consent,
                unsubscribe_url=req.unsubscribe_url,
            )
            if not decision.allowed:
                return SegmentPushResponse(
                    segment_id=segment.segment_id,
                    channel=req.channel,
                    success=False,
                    message="; ".join(decision.reasons),
                    compliance_checked=True,
                )
            if req.unsubscribe_url:
                report = report.model_copy(
                    update={"content": append_unsubscribe_footer(report.content, req.unsubscribe_url)}
                )

        result: PushResult = await self._push.push(report, target)
        return SegmentPushResponse(
            segment_id=segment.segment_id,
            channel=req.channel,
            success=result.success,
            message=result.message,
            delivered_at=result.delivered_at,
            compliance_checked=True,
        )
