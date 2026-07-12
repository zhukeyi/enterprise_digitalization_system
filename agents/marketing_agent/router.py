"""Marketing Agent — HTTP router for Marketing Portal (V5-⑤ GEO / ads).

Exposes the marketing engine via REST API:

* ``GET  /api/marketing/overview``        — 营销总览看板
* ``GET  /api/marketing/brands``          — 品牌列表
* ``GET  /api/marketing/visibility/{id}`` — GEO 可见度（分引擎）
* ``GET  /api/marketing/keywords/{id}``   — 关键词机会排序
* ``POST /api/marketing/content/optimize``— 内容 E-E-A-T / 引用友好度评分
* ``POST /api/marketing/content/geo``     — 生成 GEO 优化内容
* ``POST /api/marketing/content/seo``     — 生成 SEO 文章
* ``POST /api/marketing/ads/generate``    — 广告多变体生成
* ``POST /api/marketing/ads/abtest``      — A/B 显著性检验
* ``POST /api/marketing/ads/budget``      — 跨平台预算分配
* ``POST /api/marketing/roi/predict``     — ROI 预测
* ``GET  /api/marketing/performance/{id}``— 多平台效果聚合
* ``GET  /api/marketing/report/{id}``     — 执行摘要
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from agents.marketing_agent.ads import ABTester, BudgetAllocator, VariantGenerator
from agents.marketing_agent.analytics import PerformanceTracker, ROIPredictor
from agents.marketing_agent.content import GEOWriter, MultilingualWriter, SEOWriter
from agents.marketing_agent.data_connector import get_connector
from agents.marketing_agent.geo import ContentOptimizer, KeywordStrategy, VisibilityTracker
from agents.marketing_agent.models import (
    BrandVisibility,
    MarketingOverview,
    MultilingualContent,
)
from agents.marketing_agent.report_generator import ReportGenerator

logger = logging.getLogger("fde.marketing.router")

router = APIRouter(prefix="/api/marketing", tags=["marketing"])


# ══════════════════════════════════════════════════════════════════
# Request models
# ══════════════════════════════════════════════════════════════════


class OptimizeContentRequest(BaseModel):
    title: str
    body: str


class GenerateRequest(BaseModel):
    brand: str
    topic: str
    area: str | None = None
    n_variants: int = 5


class MultilingualRequest(BaseModel):
    brand: str
    topic: str
    target_langs: list[str] | None = None
    source_lang: str = "zh"


class ABTestRequest(BaseModel):
    variant_a: str = "A"
    variant_b: str = "B"
    impressions_a: int
    clicks_a: int
    impressions_b: int
    clicks_b: int


class BudgetRequest(BaseModel):
    brand_id: str
    total_budget: float


class ROIPredictRequest(BaseModel):
    brand_id: str
    spend: float


# ══════════════════════════════════════════════════════════════════
# Helpers
# ══════════════════════════════════════════════════════════════════


def _require_brand(brand_id: str) -> Any:
    connector = get_connector()
    brand = connector.get_brand(brand_id)
    if brand is None:
        raise HTTPException(status_code=404, detail=f"品牌不存在: {brand_id}")
    return brand


# ══════════════════════════════════════════════════════════════════
# Endpoints
# ══════════════════════════════════════════════════════════════════


@router.get("/overview", response_model=MarketingOverview)
async def overview() -> MarketingOverview:
    """营销总览看板。"""
    connector = get_connector()
    brands = connector.get_brands()
    tracker = VisibilityTracker()
    strat = KeywordStrategy()

    geo_idx: list[float] = []
    total_kw = 0
    total_spend = 0.0
    opportunities: list[dict[str, Any]] = []
    engine_acc: dict[str, list[float]] = {}

    for b in brands:
        bv = tracker.track(b.brand_id)
        geo_idx.append(bv.geo_index)
        total_kw += bv.total_keywords
        plan = strat.plan(b.brand_id, top_n=1)
        if plan:
            opportunities.append({
                "brand": b.name,
                "brand_id": b.brand_id,
                "keyword": plan[0]["term"],
                "opportunity_score": plan[0]["opportunity_score"],
                "monthly_volume": plan[0]["monthly_volume"],
                "difficulty": plan[0]["difficulty"],
            })
        for er in bv.engines:
            engine_acc.setdefault(er.engine, []).append(er.score)
        for plat in connector.get_platforms(b.brand_id):
            total_spend += plat.spend

    opportunities.sort(key=lambda x: x["opportunity_score"], reverse=True)

    all_content = [c for b in brands for c in connector.get_content(b.brand_id)]
    avg_eeat = round(sum(c.eeat_score for c in all_content) / len(all_content), 1) if all_content else 0.0

    # blended ROAS across all platforms
    all_plat = connector.get_all_platforms()
    blended = PerformanceTracker().aggregate(all_plat)["blended_roas"]

    engine_breakdown = [
        {"engine": e, "avg_score": round(sum(v) / len(v), 1), "brands_cited": sum(1 for x in v if x >= 50)}
        for e, v in engine_acc.items()
    ]

    return MarketingOverview(
        total_brands=len(brands),
        avg_geo_index=round(sum(geo_idx) / len(geo_idx), 1) if geo_idx else 0.0,
        total_keywords=total_kw,
        tracked_engines=len(connector.get_engines()),
        total_ad_spend=round(total_spend, 2),
        blended_roas=blended,
        total_content=len(all_content),
        avg_eeat=avg_eeat,
        top_opportunities=opportunities[:5],
        engine_breakdown=engine_breakdown,
    )


@router.get("/brands", response_model=list[dict[str, Any]])
async def list_brands() -> list[dict[str, Any]]:
    """品牌列表。"""
    connector = get_connector()
    return [b.model_dump() for b in connector.get_brands()]


@router.get("/visibility/{brand_id}", response_model=BrandVisibility)
async def visibility(brand_id: str) -> BrandVisibility:
    """GEO 可见度（分引擎）。"""
    _require_brand(brand_id)
    return VisibilityTracker().track(brand_id)


@router.get("/keywords/{brand_id}", response_model=list[dict[str, Any]])
async def keywords(brand_id: str) -> list[dict[str, Any]]:
    """关键词机会排序。"""
    _require_brand(brand_id)
    return KeywordStrategy().plan(brand_id, top_n=20)


@router.post("/content/optimize")
async def optimize_content(req: OptimizeContentRequest) -> dict[str, Any]:
    """内容 E-E-A-T / 引用友好度评分。"""
    return ContentOptimizer().score(req.title, req.body).model_dump()


@router.post("/content/geo")
async def geo_content(req: GenerateRequest) -> dict[str, Any]:
    """生成 GEO 优化内容。"""
    piece = GEOWriter().write(req.brand, req.topic)
    return piece.model_dump()


@router.post("/content/seo")
async def seo_content(req: GenerateRequest) -> dict[str, Any]:
    """生成 SEO 文章。"""
    piece = SEOWriter().write(req.topic, req.brand)
    return piece.model_dump()


@router.post("/content/multilingual")
async def multilingual_content(req: MultilingualRequest) -> dict[str, Any]:
    """生成多语言 GEO 文案（源语言 + 目标语言本地化）。"""
    result: MultilingualContent = MultilingualWriter().write(
        req.brand, req.topic, req.target_langs, req.source_lang
    )
    return result.model_dump()


@router.post("/ads/generate")
async def ads_generate(req: GenerateRequest) -> dict[str, Any]:
    """广告多变体生成 + 质量评分。"""
    area = req.area or req.topic
    variants = VariantGenerator().generate(req.brand, area, n=req.n_variants)
    return {
        "brand": req.brand,
        "area": area,
        "variants": [v.model_dump() for v in variants],
        "best_variant": variants[0].model_dump() if variants else None,
    }


@router.post("/ads/abtest")
async def ads_abtest(req: ABTestRequest) -> dict[str, Any]:
    """A/B 显著性检验。"""
    result = ABTester().compare(
        req.variant_a, req.variant_b,
        req.impressions_a, req.clicks_a,
        req.impressions_b, req.clicks_b,
    )
    return result.model_dump()


@router.post("/ads/budget")
async def ads_budget(req: BudgetRequest) -> dict[str, Any]:
    """跨平台预算分配（按 ROAS 加权）。"""
    _require_brand(req.brand_id)
    platforms = get_connector().get_platforms(req.brand_id)
    if req.total_budget <= 0:
        raise HTTPException(status_code=400, detail="预算必须为正数")
    return BudgetAllocator().allocate(platforms, req.total_budget)


@router.post("/roi/predict", response_model=dict[str, Any])
async def roi_predict(req: ROIPredictRequest) -> dict[str, Any]:
    """ROI 预测（OLS 回归）。"""
    _require_brand(req.brand_id)
    platforms = get_connector().get_platforms(req.brand_id)
    if req.spend <= 0:
        raise HTTPException(status_code=400, detail="投入必须为正数")
    pred = ROIPredictor().predict(platforms, req.spend)
    return pred.model_dump()


@router.get("/performance/{brand_id}", response_model=dict[str, Any])
async def performance(brand_id: str) -> dict[str, Any]:
    """多平台效果聚合。"""
    _require_brand(brand_id)
    platforms = get_connector().get_platforms(brand_id)
    return PerformanceTracker().aggregate(platforms)


@router.get("/report/{brand_id}", response_model=dict[str, Any])
async def report(brand_id: str) -> dict[str, Any]:
    """执行摘要。"""
    _require_brand(brand_id)
    return ReportGenerator().summary(brand_id)


__all__ = ["router"]
