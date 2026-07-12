"""Data Connector — demo data generator + real-source interface.

For the V5 demo we synthesize realistic, *internally consistent* sales
histories: quantities are generated from a constant-elasticity demand curve
with weekly seasonality and noise, so that the elasticity estimator and
forecaster recover meaningful structure. In production, replace
``get_sales_history`` / ``get_competitor_prices`` with ERP / POS / e-commerce
API adapters — the public interface stays identical.
"""

from __future__ import annotations

import logging
import random
from datetime import datetime, timedelta
from typing import Any

from agents.pricing_agent.models import CompetitorPrice, Product, SalesPoint

logger = logging.getLogger("fde.pricing.connector")

_SEED = 20260712

# (name, category, cost, current_price, base_demand, elasticity)
_PRODUCT_SEED: list[tuple[str, str, float, float, float, float]] = [
    ("智能降噪耳机 Pro", "消费电子", 320.0, 899.0, 140.0, -2.3),
    ("便携蓝牙音箱 Mini", "消费电子", 95.0, 299.0, 210.0, -1.8),
    ("4K 投影仪 Lite", "消费电子", 1500.0, 3299.0, 60.0, -2.6),
    ("人体工学办公椅", "家居", 480.0, 1299.0, 90.0, -1.5),
    ("记忆棉床垫 Queen", "家居", 1100.0, 2599.0, 45.0, -2.1),
    ("北欧风餐桌套装", "家居", 760.0, 1899.0, 30.0, -1.4),
    ("纯棉基础款T恤", "服饰", 22.0, 79.0, 520.0, -1.3),
    ("轻量羽绒服", "服饰", 260.0, 699.0, 180.0, -2.0),
    ("有机冷萃咖啡 12 瓶", "食品", 36.0, 128.0, 300.0, -1.6),
    ("低糖坚果礼盒", "食品", 45.0, 159.0, 260.0, -1.9),
    ("企业版 SaaS 席位/月", "SaaS", 18.0, 68.0, 900.0, -1.2),
    ("AI 客服插件/月", "SaaS", 40.0, 199.0, 420.0, -2.4),
]

_COMPETITORS = ["竞品A·自营", "竞品B·电商", "竞品C·线下"]


class DataConnector:
    """Provides product catalog, sales history and competitor prices."""

    def __init__(self, days: int = 90) -> None:
        self.days = days
        self._rng = random.Random(_SEED)
        self._cache: dict[str, dict[str, Any]] = {}
        self._build()

    def _build(self) -> None:
        today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        for idx, (name, cat, cost, price, base, elast) in enumerate(_PRODUCT_SEED):
            pid = f"P{idx+1:03d}"
            # ── sales history with price variation (promos) ──
            history: list[SalesPoint] = []
            for d in range(self.days):
                day = today - timedelta(days=self.days - 1 - d)
                # weekly seasonality: weekend lift for consumer goods
                weekday = day.weekday()
                seasonal = 1.0 + (0.18 if weekday >= 5 else 0.0)
                if cat in ("SaaS",):
                    seasonal = 1.0  # SaaS no weekly season
                # price path: occasional promotions (deterministic seed)
                promo = self._rng.random() < 0.18
                day_price = price * (0.82 if promo else 1.0)
                # small daily price jitter
                day_price *= 1.0 + self._rng.uniform(-0.02, 0.02)
                # constant-elasticity demand + noise
                qty = base * (day_price / price) ** elast * seasonal
                qty *= 1.0 + self._rng.uniform(-0.08, 0.08)
                history.append(SalesPoint(date=day, price=round(day_price, 2), quantity=round(max(qty, 1.0), 1)))

            # competitor prices around current price
            comps = [
                CompetitorPrice(
                    competitor=c,
                    price=round(price * self._rng.uniform(0.9, 1.12), 2),
                )
                for c in _COMPETITORS
            ]

            self._cache[pid] = {
                "product": Product(
                    product_id=pid,
                    name=name,
                    category=cat,
                    cost=round(cost, 2),
                    current_price=round(price, 2),
                ),
                "history": history,
                "competitors": comps,
                "_elast": elast,
            }

    # ── public API ──

    def get_products(self) -> list[Product]:
        return [v["product"] for v in self._cache.values()]

    def get_product(self, product_id: str) -> Product | None:
        v = self._cache.get(product_id)
        return v["product"] if v else None

    def get_sales_history(self, product_id: str) -> list[SalesPoint]:
        v = self._cache.get(product_id)
        if not v:
            return []
        return list(v["history"])

    def get_competitor_prices(self, product_id: str) -> list[CompetitorPrice]:
        v = self._cache.get(product_id)
        if not v:
            return []
        return list(v["competitors"])

    def get_true_elasticity(self, product_id: str) -> float | None:
        """Ground-truth elasticity (demo only) for validation/debug."""
        v = self._cache.get(product_id)
        return v["_elast"] if v else None


# module-level singleton (deterministic)
_connector = DataConnector()


def get_connector() -> DataConnector:
    return _connector


__all__ = ["DataConnector", "get_connector"]
