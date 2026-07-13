"""Customs → GEO campaign router (P1-C, C-12 backend).

Exposes the full customs-driven GEO campaign pipeline over REST:

* ``GET  /api/customs-campaign/segments``  — build & list audience segments
* ``GET  /api/customs-campaign/overview``  — compliance / reach summary
* ``POST /api/customs-campaign/content``   — generate segment-targeted GEO copy
* ``POST /api/customs-campaign/push``      — deliver a segment via enterprise channel
* ``POST /api/customs-campaign/roi``       — attribute ROI across segments

The pipeline reuses C-8 (audience connector), C-9 (content), C-10 (push +
compliance), C-11 (ROI). The customs store is injectable (``set_store``) so the
endpoint can be tested against an in-memory database without touching disk.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from agents.data_agent.customs_store import CustomsStore, get_customs_store
from agents.data_agent.report_models import PushChannel
from agents.marketing_agent.customs_audience_connector import (
    CustomsAudienceConnector,
    FrequencyTier,
    GrowthTier,
)
from agents.marketing_agent.customs_campaign_content import CustomsCampaignContent
from agents.marketing_agent.customs_campaign_pusher import (
    CustomsCampaignPusher,
    SegmentPushRequest,
)
from agents.marketing_agent.customs_campaign_roi import CustomsCampaignROI

logger = logging.getLogger("fde.marketing.campaign")

router = APIRouter(prefix="/api/customs-campaign", tags=["customs-campaign"])

# Injectable store (overridden in tests).
_store_override: CustomsStore | None = None


def set_store(store: CustomsStore | None) -> None:
    """Override the customs store used by this router (test hook)."""
    global _store_override
    _store_override = store


async def _get_store() -> CustomsStore:
    return _store_override or await get_customs_store()


# ══════════════════════════════════════════════════════════════════
# Request models
# ══════════════════════════════════════════════════════════════════


class SegmentFilter(BaseModel):
    category: str | None = None
    port: str | None = None
    frequency_tier: FrequencyTier | None = None
    growth_tier: GrowthTier | None = None
    min_value_usd: float = 0.0
    min_import_count: int = 0
    limit: int = 200
    country: str | None = None


class CampaignContentRequest(BaseModel):
    segment_id: str = Field(description="Target segment id")
    brand: str = Field(description="Promoting brand name")
    brand_id: str | None = None
    target_langs: list[str] | None = None
    filters: SegmentFilter | None = None


class CampaignPushRequest(BaseModel):
    segment_id: str
    channel: str = Field(description="email | webhook | im | portal")
    address: str
    brand: str = "FDE 平台"
    email: str | None = None
    consent: bool | None = None
    unsubscribe_url: str | None = None
    subject: str | None = None
    filters: SegmentFilter | None = None


class CampaignROIRequest(BaseModel):
    filters: SegmentFilter | None = None
    total_budget: float | None = None
    cost_per_contact: float = 50.0
    conversion_rate: float = 0.08
    deal_value: float = 25_000.0


# ══════════════════════════════════════════════════════════════════
# Helpers
# ══════════════════════════════════════════════════════════════════


def _filter_kwargs(f: SegmentFilter | None) -> dict[str, Any]:
    if not f:
        return {}
    return {
        "category": f.category,
        "port": f.port,
        "frequency_tier": f.frequency_tier,
        "growth_tier": f.growth_tier,
        "min_value_usd": f.min_value_usd,
        "min_import_count": f.min_import_count,
        "limit": f.limit,
        "country": f.country,
    }


async def _find_segment(segment_id: str, f: SegmentFilter | None):
    store = await _get_store()
    connector = CustomsAudienceConnector(store)
    # try with filters first, then fall back to unfiltered
    for fw in (_filter_kwargs(f), {}):
        segs = await connector.build_segments(**fw)
        for s in segs:
            if s.segment_id == segment_id:
                return s
    return None


def _map_channel(channel: str) -> PushChannel:
    ch = channel.strip().lower()
    if ch == "portal":
        return PushChannel.WEBHOOK  # portal delivery routed as webhook to portal URL
    return PushChannel(ch)


# ══════════════════════════════════════════════════════════════════
# Endpoints
# ══════════════════════════════════════════════════════════════════


@router.get("/segments", response_model=list[dict[str, Any]])
async def list_segments(f: SegmentFilter | None = None) -> list[dict[str, Any]]:
    """Build and list customs audience segments (C-8)."""
    store = await _get_store()
    segments = await CustomsAudienceConnector(store).build_segments(**_filter_kwargs(f))
    return [s.model_dump() for s in segments]


@router.get("/overview", response_model=dict[str, Any])
async def overview(f: SegmentFilter | None = None) -> dict[str, Any]:
    """Compliance / reach summary across segments."""
    store = await _get_store()
    segments = await CustomsAudienceConnector(store).build_segments(**_filter_kwargs(f))
    ready = [s for s in segments if s.outreach_ready]
    blocked = [s for s in segments if s.compliance_status.value == "blocked"]
    partial = [s for s in segments if s.compliance_status.value == "partial"]
    return {
        "total_segments": len(segments),
        "outreach_ready": len(ready),
        "blocked_segments": len(blocked),
        "partial_segments": len(partial),
        "total_deliverable_buyers": sum(s.deliverable_count for s in segments),
        "total_blocked_buyers": sum(s.blocked_count for s in segments),
        "total_deliverable_value_usd": round(sum(s.total_value_usd for s in segments), 2),
    }


@router.post("/content", response_model=dict[str, Any])
async def content(req: CampaignContentRequest) -> dict[str, Any]:
    """Generate segment-targeted GEO content (C-9)."""
    seg = await _find_segment(req.segment_id, req.filters)
    if seg is None:
        raise HTTPException(status_code=404, detail=f"分群不存在: {req.segment_id}")
    pkg = CustomsCampaignContent(
        brand=req.brand, brand_id=req.brand_id, target_langs=req.target_langs
    ).generate(seg)
    return pkg.model_dump()


@router.post("/push", response_model=dict[str, Any])
async def push(req: CampaignPushRequest) -> dict[str, Any]:
    """Deliver a segment campaign via an enterprise channel (C-10)."""
    seg = await _find_segment(req.segment_id, req.filters)
    if seg is None:
        raise HTTPException(status_code=404, detail=f"分群不存在: {req.segment_id}")
    try:
        channel = _map_channel(req.channel)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"不支持的渠道: {req.channel}")
    content_pkg = CustomsCampaignContent(brand=req.brand).generate(seg)
    pusher = CustomsCampaignPusher()
    resp = await pusher.push_segment(
        seg,
        content_pkg,
        SegmentPushRequest(
            channel=channel,
            address=req.address,
            email=req.email,
            consent=req.consent,
            unsubscribe_url=req.unsubscribe_url,
            subject=req.subject,
        ),
    )
    return resp.model_dump()


@router.post("/roi", response_model=dict[str, Any])
async def roi(req: CampaignROIRequest) -> dict[str, Any]:
    """Attribute ROI across customs segments (C-11)."""
    store = await _get_store()
    segments = await CustomsAudienceConnector(store).build_segments(**_filter_kwargs(req.filters))
    roi_engine = CustomsCampaignROI(
        cost_per_contact=req.cost_per_contact,
        conversion_rate=req.conversion_rate,
        deal_value=req.deal_value,
    )
    return roi_engine.attribute(segments, total_budget=req.total_budget)


__all__ = ["router", "set_store"]
