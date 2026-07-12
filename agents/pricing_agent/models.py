"""Pricing Agent — data models (Pydantic).

Defines the domain types used across the dynamic-pricing engine:
products, sales history points, forecasts, elasticity results,
competitor tracking, optimization recommendations and what-if sims.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class PricingStrategy(str, Enum):  # noqa: UP042
    """规则引擎支持的定价策略。"""

    COST_PLUS = "cost_plus"          # 成本加成
    COMPETITOR_FOLLOW = "competitor_follow"  # 竞品跟随
    PSYCHOLOGICAL = "psychological"  # 心理定价（.99 尾数）
    Tiered = "tiered"                # 阶梯定价
    RL_OPTIMAL = "rl_optimal"        # 强化学习最优价


class Product(BaseModel):
    """一个可被定价的商品 / SKU。"""

    product_id: str
    name: str
    category: str
    cost: float = Field(..., description="单位成本（元）")
    current_price: float = Field(..., description="当前售价（元）")
    currency: str = "CNY"


class SalesPoint(BaseModel):
    """单日销售观测（价格 + 销量）。"""

    date: datetime | None = None
    price: float
    quantity: float


class DemandPoint(BaseModel):
    """通用需求量点（用于预测，仅含时序索引与数量）。"""

    t: int                         # 时序索引（0,1,2,...）
    quantity: float


class DemandForecast(BaseModel):
    """需求预测结果。"""

    product_id: str
    history: list[dict[str, Any]]          # 历史拟合 [{t, actual, fitted}]
    forecast: list[dict[str, Any]]         # 预测 [{t, value, lower, upper}]
    seasonal_period: int
    trend_slope: float
    residual_std: float
    method: str = "additive-seasonal-ols"


class ElasticityResult(BaseModel):
    """价格弹性估计结果。"""

    product_id: str
    elasticity: float                     # 弹性系数（通常为负）
    r_squared: float
    interpretation: str
    sample_points: int
    price_range: list[float]              # [min, max]
    is_elastic: bool                      # |elasticity| > 1


class CompetitorPrice(BaseModel):
    """单个竞品价格观测。"""

    competitor: str
    price: float
    observed_at: datetime | None = None


class CompetitorSnapshot(BaseModel):
    """某商品的竞品价格快照 + 自身定位。"""

    product_id: str
    own_price: float
    competitors: list[CompetitorPrice]
    avg_competitor: float
    min_competitor: float
    max_competitor: float
    position: str                         # cheaper / parity / premium


class PricingRecommendation(BaseModel):
    """定价优化建议。"""

    product_id: str
    current_price: float
    recommended_price: float
    expected_delta_revenue_pct: float
    expected_delta_profit_pct: float
    expected_delta_volume_pct: float
    strategy: str
    rationale: str
    confidence: float = Field(..., description="0-1 置信度")


class SimulatorRequest(BaseModel):
    """What-if 模拟请求。"""

    product_id: str
    new_price: float
    competitor_price: float | None = None


class SimulatorResult(BaseModel):
    """What-if 模拟结果。"""

    product_id: str
    current_price: float
    new_price: float
    current_volume: float
    projected_volume: float
    current_revenue: float
    projected_revenue: float
    current_profit: float
    projected_profit: float
    delta_revenue_pct: float
    delta_profit_pct: float
    delta_volume_pct: float
    elasticity_used: float


class RLTrainingLog(BaseModel):
    """RL 优化器的训练轨迹。"""

    episodes: list[float]                 # 每轮回报（profit）
    prices: list[float]                   # 每轮尝试的价格
    best_price: float
    best_profit: float
    final_policy_mean: float
    iterations: int


class PricingOverview(BaseModel):
    """定价总览看板。"""

    total_products: int
    avg_margin_pct: float
    total_est_revenue: float
    opportunity_count: int                # 存在提价/降价空间的产品数
    category_distribution: list[dict[str, Any]]
    top_opportunities: list[dict[str, Any]]


__all__ = [
    "CompetitorPrice",
    "CompetitorSnapshot",
    "DemandForecast",
    "DemandPoint",
    "ElasticityResult",
    "PricingOverview",
    "PricingRecommendation",
    "PricingStrategy",
    "Product",
    "RLTrainingLog",
    "SalesPoint",
    "SimulatorRequest",
    "SimulatorResult",
]
