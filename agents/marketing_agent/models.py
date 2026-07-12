"""Marketing Agent — data models for the GEO / ads / content / analytics layers.

Lightweight Pydantic models shared across the marketing engine. All numeric
fields are plain floats/ints so the demo connectors and the (future) real
ad-platform adapters can fill them identically.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

# ── Brand / keyword ────────────────────────────────────────────────────


class Brand(BaseModel):
    brand_id: str
    name: str
    domain: str
    category: str
    strength: float = Field(ge=0, le=100, description="品牌整体声量强度 0-100")


class Keyword(BaseModel):
    term: str
    intent: str = Field(description="informational/navigational/transactional/commercial")
    monthly_volume: int = Field(ge=0)
    difficulty: float = Field(ge=0, le=100, description="SEO/GEO 排名难度 0-100")
    current_position: float = Field(ge=0, description="当前在 AI 答案中的平均位次")
    opportunity_score: float = Field(default=0.0, description="机会分 0-100")


# ── GEO visibility ─────────────────────────────────────────────────────


class EngineVisibility(BaseModel):
    engine: str
    score: float = Field(ge=0, le=100, description="该引擎对该品牌的可见度 0-100")
    cited: bool = Field(description="监控关键词中是否被引用")
    avg_position: float = Field(ge=0)
    sampled_keywords: int


class BrandVisibility(BaseModel):
    brand_id: str
    brand_name: str
    geo_index: float = Field(ge=0, le=100, description="综合 GEO 可见度指数 0-100")
    engines: list[EngineVisibility]
    cited_keywords: int
    total_keywords: int
    trend_30d: float = Field(description="近 30 天可见度变化 (百分点)")


# ── Content / GEO writing ──────────────────────────────────────────────


class ContentScore(BaseModel):
    eeat_score: float = Field(ge=0, le=100, description="E-E-A-T 总分")
    experience: float = Field(ge=0, le=100)
    expertise: float = Field(ge=0, le=100)
    authoritativeness: float = Field(ge=0, le=100)
    trustworthiness: float = Field(ge=0, le=100)
    citation_score: float = Field(ge=0, le=100, description="被 AI 引擎引用的友好度")
    suggestions: list[str] = Field(default_factory=list)


class ContentPiece(BaseModel):
    title: str
    body: str
    topic: str = ""
    eeat_score: float = Field(default=0.0, ge=0, le=100)
    citation_score: float = Field(default=0.0, ge=0, le=100)
    geo_optimized: bool = False
    created_at: datetime | None = None


class MultilingualContent(BaseModel):
    brand: str
    topic: str
    source_lang: str = "zh"
    target_langs: list[str] = []
    pieces: dict[str, ContentPiece] = Field(default_factory=dict)
    generated_at: datetime | None = None


# ── Ads ────────────────────────────────────────────────────────────────


class AdVariant(BaseModel):
    variant_id: str
    headline: str
    body: str
    cta: str
    quality_score: float = Field(ge=0, le=100)
    predicted_ctr: float = Field(ge=0, description="预测点击率 (小数, e.g. 0.032)")
    angle: str = ""


class ABTestResult(BaseModel):
    variant_a: str
    variant_b: str
    impressions_a: int
    impressions_b: int
    clicks_a: int
    clicks_b: int
    ctr_a: float
    ctr_b: float
    lift_pct: float
    z_score: float
    p_value: float
    confidence: float = Field(ge=0, le=100)
    winner: str | None
    significant: bool


class PlatformBudget(BaseModel):
    platform: str
    current_spend: float
    current_roas: float = Field(description="当前广告支出回报倍数")
    allocated_budget: float
    projected_revenue: float
    projected_roas: float


# ── Analytics / ROI ────────────────────────────────────────────────────


class PlatformPerformance(BaseModel):
    platform: str
    spend: float
    revenue: float
    impressions: int
    clicks: int
    conversions: int
    roas: float = Field(description="revenue / spend")
    ctr: float
    cpc: float
    conv_rate: float
    trend_30d: float = Field(default=0.0, description="近 30 天 ROAS 变化")


class ROIPrediction(BaseModel):
    spend: float
    predicted_revenue: float
    predicted_roas: float
    predicted_profit: float
    payback_ratio: float = Field(description="revenue/spend 即 ROAS 同义")
    confidence: float = Field(ge=0, le=1)
    slope: float = Field(description="每元投入的边际收入 (回归系数)")
    fit_r_squared: float


# ── Strategy enums ─────────────────────────────────────────────────────


class ContentType(str, Enum):  # noqa: UP042
    GEO = "geo"
    SEO = "seo"
    AD = "ad"
    SOCIAL = "social"


class MarketingOverview(BaseModel):
    total_brands: int
    avg_geo_index: float
    total_keywords: int
    tracked_engines: int
    total_ad_spend: float
    blended_roas: float
    total_content: int
    avg_eeat: float
    top_opportunities: list[dict[str, Any]] = Field(default_factory=list)
    engine_breakdown: list[dict[str, Any]] = Field(default_factory=list)
