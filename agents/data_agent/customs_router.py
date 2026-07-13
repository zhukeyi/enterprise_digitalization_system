"""Customs data API router (P1-C, C-6 backend).

Exposes the customs data base to the Intelligence Portal (CustomsView):

* ``GET  /api/customs/overview``       — record/buyer counts + coverage
* ``GET  /api/customs/trade-records``  — search by HS / country / port (Tier-1)
* ``GET  /api/customs/buyers``         — top buyer entities (Tier-2 derivative)
* ``GET  /api/customs/trends``         — trade value trend for an HS code
* ``POST /api/customs/ingest``         — run a provider adapter → persist

Compliance: ingest never returns raw BOL rows; only aggregated ``BuyerEntity``
profiles are stored. Outbound marketing use must pass ``compliance_guard``.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from agents.data_agent.customs_models import DataSourceTier
from agents.data_agent.customs_store import get_customs_store
from agents.data_agent.models import SourceConfig, SourceType
from agents.data_agent.scrapers.customs_scraper import CustomsScraper

logger = logging.getLogger("fde.data.customs_router")

router = APIRouter(prefix="/api/customs", tags=["customs"])

# Default public UN Comtrade HS endpoint (Tier-1).
_UN_COMTRADE_URL = "https://comtradeapi.un.org/public/v1/get/HS"


# ══════════════════════════════════════════════════════════════════
# Request / response models
# ══════════════════════════════════════════════════════════════════


class IngestRequest(BaseModel):
    """Trigger a customs fetch + persist."""

    provider: str = Field(description="un_comtrade | importyeti | zauba")
    url: str = Field(default="", description="Provider endpoint (defaults for un_comtrade)")
    reporter: str = Field(default="842", description="Reporter country (ISO/Comtrade code)")
    partner: str = Field(default="all", description="Partner country")
    year: str = Field(default="2023", description="Reporting year")
    hs_code: str = Field(default="ALL", description="HS code or 'ALL'")
    max_items: int = Field(default=50, ge=1, le=500)


class IngestResponse(BaseModel):
    """Ingest result summary."""

    provider: str
    tier: str
    stored: int
    error: str | None = None


# ══════════════════════════════════════════════════════════════════
# Query endpoints
# ══════════════════════════════════════════════════════════════════


@router.get("/overview")
async def overview() -> dict[str, Any]:
    """High-level counts and coverage of the customs data base."""
    store = await get_customs_store()
    trade_count = await store.count_trade_records()
    buyer_count = await store.count_buyers()
    return {
        "trade_record_count": trade_count,
        "buyer_count": buyer_count,
        "tier1_available": trade_count > 0,
        "tier2_available": buyer_count > 0,
        "note": "Use /trade-records and /buyers for the full lists.",
    }


@router.get("/trade-records")
async def trade_records(
    hs_code: str | None = Query(default=None, description="HS code prefix, e.g. 85"),
    reporter_country: str | None = Query(default=None, description="Reporter country"),
    partner_country: str | None = Query(default=None, description="Partner country"),
    port: str | None = Query(default=None, description="Port name"),
    limit: int = Query(default=50, ge=1, le=500),
) -> list[dict[str, Any]]:
    """Search normalized Tier-1 trade records."""
    store = await get_customs_store()
    rows = await store.search(
        hs_code=hs_code,
        reporter_country=reporter_country,
        partner_country=partner_country,
        port=port,
        limit=limit,
    )
    return [r.model_dump(mode="json") for r in rows]


@router.get("/buyers")
async def buyers(
    country: str | None = Query(default=None, description="Buyer country filter"),
    limit: int = Query(default=50, ge=1, le=500),
) -> list[dict[str, Any]]:
    """Return top buyer entities (Tier-2 derivative profiles)."""
    store = await get_customs_store()
    rows = await store.top_buyers(country=country, limit=limit)
    return [b.model_dump(mode="json") for b in rows]


@router.get("/trends")
async def trends(
    hs_code: str = Query(description="HS code prefix, e.g. 8517"),
    group_by: str = Query(default="year", description="year | period"),
) -> list[dict[str, Any]]:
    """Aggregated trade value / quantity trend for an HS code prefix."""
    store = await get_customs_store()
    return await store.trend(hs_code=hs_code, group_by=group_by)


@router.post("/ingest", response_model=IngestResponse)
async def ingest(req: IngestRequest) -> IngestResponse:
    """Run a provider adapter and persist normalized results.

    Tier-1 → trade records; Tier-2 → aggregated buyer entities (never raw BOL).
    """
    url = req.url or (_UN_COMTRADE_URL if req.provider == "un_comtrade" else "")
    if not url:
        raise HTTPException(status_code=422, detail="url is required for this provider")

    config = SourceConfig(
        source_type=SourceType.CUSTOMS,
        url=url,
        max_items=req.max_items,
        metadata={
            "provider": req.provider,
            "reporter": req.reporter,
            "partner": req.partner,
            "year": req.year,
            "hsCode": req.hs_code,
        },
    )

    scraper = CustomsScraper()
    try:
        result = await scraper.fetch_records(config)
    except Exception as e:
        logger.error("Customs ingest failed: %s", e)
        return IngestResponse(provider=req.provider, tier="unknown", stored=0, error=str(e))

    store = await get_customs_store()
    if result.tier == DataSourceTier.TIER1:
        stored = await store.upsert_trade_records(result.trade_records)
    else:
        stored = await store.upsert_buyers(result.buyers)
    return IngestResponse(provider=req.provider, tier=result.tier.value, stored=stored)


__all__ = ["router"]
