"""Rule-Based Pricing Optimizer.

Implements classic, explainable pricing rules:
  * cost_plus          — cost × (1 + markup)
  * competitor_follow  — competitor_avg × factor
  * psychological      — charm pricing (.99 / .95 endings)
  * tiered             — volume-aware markup (high-volume → lower markup)

All strategies are deterministic and auditable — suitable for conservative
enterprise deployments where a human must sign off on every price change.
"""

from __future__ import annotations

import logging

from agents.pricing_agent.models import CompetitorSnapshot, PricingStrategy, Product

logger = logging.getLogger("fde.pricing.rule_based")


class RuleBasedOptimizer:
    """Deterministic rule-based pricing."""

    def optimize(
        self,
        product: Product,
        snapshot: CompetitorSnapshot,
        strategy: PricingStrategy,
        elasticity: float = -1.5,
        base_demand: float = 100.0,
        markup: float | None = None,
    ) -> tuple[float, str]:
        """Return (recommended_price, rationale)."""
        cost = product.cost
        floor = cost * 1.05  # never price below cost

        if strategy == PricingStrategy.COST_PLUS:
            mk = markup if markup is not None else 0.5
            price = max(floor, cost * (1 + mk))
            rationale = f"成本加成法：单位成本 ¥{cost:.2f} × (1+{mk:.0%}) = ¥{price:.2f}，保障 {mk:.0%} 毛利。"

        elif strategy == PricingStrategy.COMPETITOR_FOLLOW:
            factor = 0.98
            price = max(floor, snapshot.avg_competitor * factor)
            rationale = (
                f"竞品跟随：竞品均价 ¥{snapshot.avg_competitor:.2f} × {factor} = ¥{price:.2f}，"
                f"略低于竞品以争取流量（当前定位：{snapshot.position}）。"
            )

        elif strategy == PricingStrategy.PSYCHOLOGICAL:
            base = snapshot.avg_competitor * 0.99
            base = max(floor, base)
            charm = round(base) - 0.01
            charm = max(floor, charm)
            price = charm
            rationale = f"心理定价：将候选价 ¥{base:.2f} 调整为尾数 charm 价 ¥{price:.2f}，提升转化直觉。"

        elif strategy == PricingStrategy.Tiered:
            mk = 0.35 if base_demand > 200 else 0.6
            price = max(floor, cost * (1 + mk))
            tier = "高销量" if base_demand > 200 else "低销量"
            rationale = f"阶梯定价：{tier}商品采用 {mk:.0%} 加成（高销量走量 / 低销量保供），建议 ¥{price:.2f}。"

        else:
            price = product.current_price
            rationale = "未知策略，沿用当前价。"

        return round(price, 2), rationale


__all__ = ["RuleBasedOptimizer"]
