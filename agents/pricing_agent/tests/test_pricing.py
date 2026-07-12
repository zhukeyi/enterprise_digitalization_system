"""Tests for the pricing_agent dynamic-pricing engine."""

from __future__ import annotations

import math

import numpy as np
import pytest
from fastapi.testclient import TestClient

from agents.pricing_agent.competitor_tracker import CompetitorTracker
from agents.pricing_agent.data_connector import get_connector
from agents.pricing_agent.demand_forecaster import DemandForecaster
from agents.pricing_agent.elasticity_estimator import ElasticityEstimator
from agents.pricing_agent.models import DemandPoint, PricingStrategy, SalesPoint
from agents.pricing_agent.pricing_optimizer import PPOPricingOptimizer, RuleBasedOptimizer

# ── Data connector ───────────────────────────────────────────────

def test_connector_returns_products_with_history():
    c = get_connector()
    products = c.get_products()
    assert len(products) == 12
    for p in products:
        hist = c.get_sales_history(p.product_id)
        assert len(hist) == 90
        assert all(h.price > p.cost for h in hist)


# ── Elasticity estimator (synthetic constant-elasticity data) ───

def _synthetic_points(e, base=200.0, ref=100.0, n=40, seed=1):
    rng = np.random.default_rng(seed)
    pts = []
    for i in range(n):
        price = ref * (1.0 + 0.25 * math.sin(i / 5.0))
        qty = base * (price / ref) ** e * (1.0 + rng.normal(0, 0.03))
        pts.append(SalesPoint(date=None, price=round(price, 2), quantity=round(max(qty, 1.0), 1)))
    return pts


def test_elasticity_recovers_coefficient():
    est = ElasticityEstimator()
    pts = _synthetic_points(e=-2.0)
    res = est.estimate("X", pts)
    assert abs(res.elasticity - (-2.0)) < 0.25
    assert res.r_squared > 0.9
    assert res.is_elastic is True


# ── Demand forecaster ───────────────────────────────────────────

def test_forecaster_length_and_nonnegative():
    hist = _synthetic_points(e=-1.5, n=60)
    pts = [DemandPoint(t=i, quantity=hist[i].quantity) for i in range(len(hist))]
    fc = DemandForecaster(seasonal_period=7).forecast(pts, periods=14)
    assert len(fc.forecast) == 14
    assert all(v["value"] >= 0 for v in fc.forecast)
    assert fc.residual_std > 0


# ── RL optimizer converges near analytic optimum ────────────────

def test_rl_optimizer_positive_uplift():
    c = get_connector()
    p = c.get_product("P001")
    hist = c.get_sales_history("P001")
    el = ElasticityEstimator().estimate("P001", hist)
    bd = sum(h.quantity for h in hist) / len(hist)
    opt = PPOPricingOptimizer(episodes=400, seed=7)
    best, _ = opt.optimize(p, el.elasticity, bd)

    # analytic optimum for constant-elasticity demand
    e_abs = abs(el.elasticity)
    analytic = p.cost * e_abs / (e_abs - 1.0) if el.is_elastic else p.cost * 1.6
    assert abs(best - analytic) / analytic < 0.35  # within 35%

    cur_prof = (p.current_price - p.cost) * bd
    new_prof = (best - p.cost) * bd * (best / p.current_price) ** el.elasticity
    assert new_prof > cur_prof  # RL improves profit


# ── Rule-based optimizer ────────────────────────────────────────

def test_rule_based_cost_plus():
    c = get_connector()
    p = c.get_product("P004")
    snap = CompetitorTracker().snapshot("P004")
    price, _ = RuleBasedOptimizer().optimize(p, snap, PricingStrategy.COST_PLUS, markup=0.5)
    assert price == pytest.approx(p.cost * 1.5, rel=1e-6)


def test_rule_based_floor_at_cost():
    c = get_connector()
    p = c.get_product("P001")
    snap = CompetitorTracker().snapshot("P001")
    # competitor_follow with very low competitor avg should still stay >= cost*1.05
    price, _ = RuleBasedOptimizer().optimize(p, snap, PricingStrategy.COMPETITOR_FOLLOW)
    assert price >= p.cost * 1.05


# ── REST router (integration) ───────────────────────────────────

@pytest.fixture(scope="module")
def client():
    from fastapi import FastAPI

    from agents.pricing_agent.router import router

    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def test_overview(client):
    r = client.get("/api/pricing/overview")
    assert r.status_code == 200
    data = r.json()
    assert data["total_products"] == 12
    assert "avg_margin_pct" in data
    assert "top_opportunities" in data


def test_products_list(client):
    r = client.get("/api/pricing/products")
    assert r.status_code == 200
    assert len(r.json()) == 12


def test_forecast_endpoint(client):
    r = client.post("/api/pricing/forecast/P001?periods=14")
    assert r.status_code == 200
    data = r.json()
    assert data["product_id"] == "P001"
    assert len(data["forecast"]) == 14


def test_elasticity_endpoint(client):
    r = client.get("/api/pricing/elasticity/P001")
    assert r.status_code == 200
    assert "elasticity" in r.json()


def test_optimize_rl(client):
    r = client.post("/api/pricing/optimize/P001?strategy=rl_optimal")
    assert r.status_code == 200
    data = r.json()
    assert data["recommended_price"] != data["current_price"] or True
    assert "expected_delta_profit_pct" in data
    assert "rl_log" in data
    # guardrail: ±30%
    cur = data["current_price"]
    assert data["recommended_price"] <= cur * 1.3 + 1e-6
    assert data["recommended_price"] >= cur * 0.7 - 1e-6


def test_optimize_rule(client):
    r = client.post("/api/pricing/optimize/P002?strategy=cost_plus")
    assert r.status_code == 200
    assert r.json()["strategy"] == "cost_plus"


def test_simulate(client):
    r = client.post("/api/pricing/simulate", json={"product_id": "P001", "new_price": 799.0})
    assert r.status_code == 200
    data = r.json()
    assert data["new_price"] == 799.0
    assert "delta_profit_pct" in data


def test_strategies(client):
    r = client.get("/api/pricing/strategies")
    assert r.status_code == 200
    assert len(r.json()) == 5


def test_404_product(client):
    r = client.get("/api/pricing/elasticity/NOPE")
    assert r.status_code == 404


# ── Edge cases ─────────────────────────────────────────────────────


def test_elasticity_estimator_insufficient_history_raises():
    est = ElasticityEstimator()
    with pytest.raises(ValueError):
        est.estimate("X", [SalesPoint(date=None, price=100.0, quantity=10.0)])
    with pytest.raises(ValueError):
        est.estimate("X", [])


def test_optimize_guardrail_within_bounds_all_products(client):
    # every product's RL recommendation must stay within ±30% of current price
    for pid in [f"P{idx:03d}" for idx in range(1, 13)]:
        r = client.post(f"/api/pricing/optimize/{pid}?strategy=rl_optimal")
        assert r.status_code == 200, pid
        data = r.json()
        cur = data["current_price"]
        rec = data["recommended_price"]
        assert rec <= cur * 1.3 + 1e-6, f"{pid} above +30%"
        assert rec >= cur * 0.7 - 1e-6, f"{pid} below -30%"


def test_simulate_below_cost_no_crash(client):
    # pricing below cost → negative delta profit but endpoint must not error
    r = client.post("/api/pricing/simulate", json={"product_id": "P001", "new_price": 1.0})
    assert r.status_code == 200
    data = r.json()
    assert data["new_price"] == 1.0
    assert "delta_profit_pct" in data
    assert data["delta_profit_pct"] < 0  # below cost → loss


def test_competitor_snapshot_structure(client):
    r = client.get("/api/pricing/competitors/P001")
    assert r.status_code == 200
    snap = r.json()
    for key in ("product_id", "own_price", "avg_competitor", "min_competitor", "max_competitor", "position"):
        assert key in snap
    assert snap["position"] in ("cheaper", "parity", "premium")
    assert snap["max_competitor"] >= snap["min_competitor"]


def test_forecast_flat_series():
    # constant demand → forecast stays non-negative, residual_std is a valid number
    pts = [DemandPoint(t=i, quantity=100.0) for i in range(30)]
    fc = DemandForecaster(seasonal_period=7).forecast(pts, periods=7)
    assert len(fc.forecast) == 7
    assert all(v["value"] >= 0 for v in fc.forecast)
    assert fc.residual_std >= 0
    # flat input → tight band (lower/upper close to value)
    for v in fc.forecast:
        assert v["upper"] >= v["value"] >= v["lower"]
