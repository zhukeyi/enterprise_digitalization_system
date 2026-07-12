"""Pricing Agent — HTTP router for Pricing Portal (V5-⑦).

Exposes the dynamic-pricing engine via REST API:

* ``GET  /api/pricing/overview``         — 定价总览看板
* ``GET  /api/pricing/products``         — 商品列表
* ``GET  /api/pricing/products/{id}``    — 商品详情 + 销售历史 + 竞品
* ``POST /api/pricing/forecast/{id}``    — 需求预测
* ``GET  /api/pricing/elasticity/{id}``  — 价格弹性
* ``GET  /api/pricing/competitors/{id}`` — 竞品价格监控
* ``POST /api/pricing/optimize/{id}``    — 定价优化（规则 / RL）
* ``POST /api/pricing/simulate``         — What-if 模拟
* ``GET  /api/pricing/strategies``       — 策略预设
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException

from agents.pricing_agent.competitor_tracker import CompetitorTracker
from agents.pricing_agent.data_connector import get_connector
from agents.pricing_agent.demand_forecaster import DemandForecaster
from agents.pricing_agent.elasticity_estimator import ElasticityEstimator
from agents.pricing_agent.models import (
    DemandForecast,
    ElasticityResult,
    PricingOverview,
    PricingRecommendation,
    PricingStrategy,
    Product,
    RLTrainingLog,
    SalesPoint,
    SimulatorRequest,
    SimulatorResult,
)
from agents.pricing_agent.pricing_optimizer import PPOPricingOptimizer, RuleBasedOptimizer

logger = logging.getLogger("fde.pricing.router")

router = APIRouter(prefix="/api/pricing", tags=["pricing"])


# ══════════════════════════════════════════════════════════════════
# Helpers
# ══════════════════════════════════════════════════════════════════


def _require_product(product_id: str) -> Product:
    connector = get_connector()
    product = connector.get_product(product_id)
    if product is None:
        raise HTTPException(status_code=404, detail=f"商品不存在: {product_id}")
    return product


def _history(product_id: str) -> list[SalesPoint]:
    return get_connector().get_sales_history(product_id)


def _base_demand(history: list[SalesPoint]) -> float:
    if not history:
        return 0.0
    return sum(p.quantity for p in history) / len(history)


def _elasticity_value(history: list[SalesPoint]) -> ElasticityResult:
    est = ElasticityEstimator()
    return est.estimate("tmp", history)


def _project(
    product: Product,
    elasticity: float,
    base_demand: float,
    from_price: float,
    to_price: float,
) -> dict[str, float]:
    """Project quantity/revenue/profit moving from from_price to to_price."""
    e = elasticity
    q_from = base_demand * (from_price / product.current_price) ** e if product.current_price else base_demand
    q_to = base_demand * (to_price / product.current_price) ** e if product.current_price else base_demand
    rev_from = from_price * q_from
    rev_to = to_price * q_to
    prof_from = (from_price - product.cost) * q_from
    prof_to = (to_price - product.cost) * q_to
    return {
        "q_from": q_from,
        "q_to": q_to,
        "rev_from": rev_from,
        "rev_to": rev_to,
        "prof_from": prof_from,
        "prof_to": prof_to,
    }


def _analytic_optimum(product: Product, elasticity: ElasticityResult) -> float:
    """Closed-form profit-max price for constant-elasticity demand."""
    floor = product.cost * 1.05
    if elasticity.is_elastic:
        e_abs = abs(elasticity.elasticity)
        p_star = product.cost * e_abs / (e_abs - 1.0)
    else:
        p_star = product.cost * 1.6
    return float(max(floor, p_star))


# ══════════════════════════════════════════════════════════════════
# Endpoints
# ══════════════════════════════════════════════════════════════════


@router.get("/overview", response_model=PricingOverview)
async def overview() -> PricingOverview:
    """定价总览看板。"""
    connector = get_connector()
    products = connector.get_products()

    total_products = len(products)
    margins = []
    total_est_revenue = 0.0
    cat_map: dict[str, int] = {}
    opportunities: list[dict[str, Any]] = []

    for p in products:
        hist = connector.get_sales_history(p.product_id)
        bd = _base_demand(hist)
        try:
            el = _elasticity_value(hist)
        except ValueError:
            el = ElasticityResult(
                product_id=p.product_id, elasticity=-1.5, r_squared=0.0,
                interpretation="", sample_points=0, price_range=[p.cost, p.current_price], is_elastic=True,
            )
        margin = (p.current_price - p.cost) / p.current_price
        margins.append(margin)
        total_est_revenue += p.current_price * bd

        opt = _analytic_optimum(p, el)
        proj = _project(p, el.elasticity, bd, p.current_price, opt)
        delta_profit = (proj["prof_to"] - proj["prof_from"]) / proj["prof_from"] * 100 if proj["prof_from"] else 0.0
        delta_rev = (proj["rev_to"] - proj["rev_from"]) / proj["rev_from"] * 100 if proj["rev_from"] else 0.0
        delta_vol = (proj["q_to"] - proj["q_from"]) / proj["q_from"] * 100 if proj["q_from"] else 0.0

        cat_map[p.category] = cat_map.get(p.category, 0) + 1

        if abs(opt - p.current_price) / p.current_price > 0.03:
            opportunities.append({
                "product_id": p.product_id,
                "name": p.name,
                "category": p.category,
                "current_price": p.current_price,
                "recommended_price": round(opt, 2),
                "expected_delta_profit_pct": round(delta_profit, 1),
                "expected_delta_revenue_pct": round(delta_rev, 1),
                "expected_delta_volume_pct": round(delta_vol, 1),
            })

    opportunities.sort(key=lambda x: abs(x["expected_delta_profit_pct"]), reverse=True)

    return PricingOverview(
        total_products=total_products,
        avg_margin_pct=round(sum(margins) / len(margins) * 100, 1) if margins else 0.0,
        total_est_revenue=round(total_est_revenue, 2),
        opportunity_count=len(opportunities),
        category_distribution=[{"category": k, "count": v} for k, v in sorted(cat_map.items())],
        top_opportunities=opportunities[:5],
    )


@router.get("/products", response_model=list[dict[str, Any]])
async def list_products() -> list[dict[str, Any]]:
    """商品列表。"""
    connector = get_connector()
    result = []
    for p in connector.get_products():
        margin = (p.current_price - p.cost) / p.current_price
        result.append({
            "product_id": p.product_id,
            "name": p.name,
            "category": p.category,
            "cost": p.cost,
            "current_price": p.current_price,
            "margin_pct": round(margin * 100, 1),
        })
    return result


@router.get("/products/{product_id}", response_model=dict[str, Any])
async def get_product_detail(product_id: str) -> dict[str, Any]:
    """商品详情 + 销售历史 + 竞品快照。"""
    product = _require_product(product_id)
    hist = _history(product_id)
    tracker = CompetitorTracker()
    snapshot = tracker.snapshot(product_id)
    recent = [
        {"date": p.date.strftime("%Y-%m-%d"), "price": p.price, "quantity": p.quantity}
        for p in hist[-30:]
    ]
    return {
        "product": product.model_dump(),
        "sales_history": recent,
        "competitors": snapshot.model_dump(),
    }


@router.post("/forecast/{product_id}", response_model=DemandForecast)
async def forecast(product_id: str, periods: int = 14) -> DemandForecast:
    """需求预测（季节+趋势）。"""
    _require_product(product_id)
    hist = _history(product_id)
    if len(hist) < 4:
        raise HTTPException(status_code=400, detail="历史数据不足，无法预测")

    from agents.pricing_agent.models import DemandPoint

    points = [DemandPoint(t=i, quantity=hist[i].quantity) for i in range(len(hist))]
    fc = DemandForecaster(seasonal_period=7).forecast(points, periods=periods)
    fc.product_id = product_id
    return fc


@router.get("/elasticity/{product_id}", response_model=ElasticityResult)
async def elasticity(product_id: str) -> ElasticityResult:
    """价格弹性估计。"""
    _require_product(product_id)
    hist = _history(product_id)
    if len(hist) < 3:
        raise HTTPException(status_code=400, detail="历史数据不足，无法估计弹性")
    est = ElasticityEstimator()
    return est.estimate(product_id, hist)


@router.get("/competitors/{product_id}", response_model=dict[str, Any])
async def competitors(product_id: str) -> dict[str, Any]:
    """竞品价格监控快照。"""
    _require_product(product_id)
    tracker = CompetitorTracker()
    return tracker.snapshot(product_id).model_dump()


@router.post("/optimize/{product_id}", response_model=dict[str, Any])
async def optimize(product_id: str, strategy: str = "rl_optimal") -> dict[str, Any]:
    """定价优化。strategy ∈ {rl_optimal, cost_plus, competitor_follow, psychological, tiered}。"""
    product = _require_product(product_id)
    hist = _history(product_id)
    bd = _base_demand(hist)
    try:
        el = _elasticity_value(hist)
    except ValueError:
        el = ElasticityResult(
            product_id=product_id, elasticity=-1.5, r_squared=0.0,
            interpretation="", sample_points=0, price_range=[product.cost, product.current_price], is_elastic=True,
        )

    tracker = CompetitorTracker()
    snapshot = tracker.snapshot(product_id)

    rl_log: RLTrainingLog | None = None
    rationale = ""
    recommended = product.current_price

    try:
        strat = PricingStrategy(strategy)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"未知策略: {strategy}")

    if strat == PricingStrategy.RL_OPTIMAL:
        opt = PPOPricingOptimizer(episodes=400, seed=7)
        recommended, rl_log = opt.optimize(product, el.elasticity, bd)
        analytic = _analytic_optimum(product, el)
        rationale = (
            f"强化学习定价：经 {rl_log.iterations} 轮策略梯度训练，最优价收敛至 ¥{recommended:.2f}"
            f"（解析最优 ¥{analytic:.2f}，误差 {abs(recommended-analytic)/analytic*100:.1f}%）。"
        )
    else:
        rule_opt = RuleBasedOptimizer()
        recommended, rationale = rule_opt.optimize(product, snapshot, strat, el.elasticity, bd)

    # Business guardrail: never move price more than ±30% in one recommendation.
    guard_lo = product.current_price * 0.7
    guard_hi = product.current_price * 1.3
    recommended = round(max(guard_lo, min(guard_hi, recommended)), 2)

    proj = _project(product, el.elasticity, bd, product.current_price, recommended)
    delta_rev = (proj["rev_to"] - proj["rev_from"]) / proj["rev_from"] * 100 if proj["rev_from"] else 0.0
    delta_prof = (proj["prof_to"] - proj["prof_from"]) / proj["prof_from"] * 100 if proj["prof_from"] else 0.0
    delta_vol = (proj["q_to"] - proj["q_from"]) / proj["q_from"] * 100 if proj["q_from"] else 0.0

    # confidence from elasticity fit quality
    confidence = max(0.3, min(0.95, el.r_squared))

    rec = PricingRecommendation(
        product_id=product_id,
        current_price=product.current_price,
        recommended_price=recommended,
        expected_delta_revenue_pct=round(delta_rev, 1),
        expected_delta_profit_pct=round(delta_prof, 1),
        expected_delta_volume_pct=round(delta_vol, 1),
        strategy=strategy,
        rationale=rationale,
        confidence=round(confidence, 2),
    )

    payload: dict[str, Any] = rec.model_dump()
    if rl_log is not None:
        payload["rl_log"] = rl_log.model_dump()
    payload["elasticity"] = el.model_dump()
    payload["competitors"] = snapshot.model_dump()
    return payload


@router.post("/simulate", response_model=SimulatorResult)
async def simulate(req: SimulatorRequest) -> SimulatorResult:
    """What-if 定价模拟。"""
    product = _require_product(req.product_id)
    hist = _history(req.product_id)
    bd = _base_demand(hist)
    try:
        el = _elasticity_value(hist)
    except ValueError:
        el = ElasticityResult(
            product_id=req.product_id, elasticity=-1.5, r_squared=0.0,
            interpretation="", sample_points=0, price_range=[product.cost, product.current_price], is_elastic=True,
        )

    e = el.elasticity
    current_q = bd
    proj_q = bd * (req.new_price / product.current_price) ** e if product.current_price else bd

    cur_rev = product.current_price * current_q
    new_rev = req.new_price * proj_q
    cur_prof = (product.current_price - product.cost) * current_q
    new_prof = (req.new_price - product.cost) * proj_q

    return SimulatorResult(
        product_id=req.product_id,
        current_price=product.current_price,
        new_price=req.new_price,
        current_volume=round(current_q, 1),
        projected_volume=round(proj_q, 1),
        current_revenue=round(cur_rev, 2),
        projected_revenue=round(new_rev, 2),
        current_profit=round(cur_prof, 2),
        projected_profit=round(new_prof, 2),
        delta_revenue_pct=round((new_rev - cur_rev) / cur_rev * 100, 1) if cur_rev else 0.0,
        delta_profit_pct=round((new_prof - cur_prof) / cur_prof * 100, 1) if cur_prof else 0.0,
        delta_volume_pct=round((proj_q - current_q) / current_q * 100, 1) if current_q else 0.0,
        elasticity_used=e,
    )


@router.get("/strategies", response_model=list[dict[str, Any]])
async def strategies() -> list[dict[str, Any]]:
    """定价策略预设列表。"""
    return [
        {"key": "rl_optimal", "name": "强化学习最优价", "desc": "PPO 风格策略梯度，最大化利润"},
        {"key": "cost_plus", "name": "成本加成", "desc": "成本 × (1+加成率)，稳健可审计"},
        {"key": "competitor_follow", "name": "竞品跟随", "desc": "略低于竞品均价以争取流量"},
        {"key": "psychological", "name": "心理定价", "desc": "尾数 charm 价（.99/.95）提升转化"},
        {"key": "tiered", "name": "阶梯定价", "desc": "按销量高低采用不同加成"},
    ]


__all__ = ["router"]
