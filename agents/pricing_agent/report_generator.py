"""Report Generator — human-readable pricing recommendation reports."""

from __future__ import annotations

import logging
from typing import Any

from agents.pricing_agent.models import (
    CompetitorSnapshot,
    ElasticityResult,
    PricingRecommendation,
    Product,
)

logger = logging.getLogger("fde.pricing.report")


class ReportGenerator:
    """Render a markdown pricing report from analysis artifacts."""

    def render(
        self,
        product: Product,
        elasticity: ElasticityResult,
        snapshot: CompetitorSnapshot,
        recommendation: PricingRecommendation,
    ) -> str:
        margin_now = (product.current_price - product.cost) / product.current_price
        margin_rec = (recommendation.recommended_price - product.cost) / recommendation.recommended_price
        direction = "上调" if recommendation.recommended_price > product.current_price else "下调"
        delta = abs(recommendation.recommended_price - product.current_price)

        lines = [
            f"# 定价建议报告 · {product.name}",
            "",
            f"> 商品编号：**{product.product_id}** ｜ 品类：**{product.category}** ｜ 成本：¥{product.cost:.2f}",
            "",
            "## 一、当前状态",
            "",
            f"- 当前售价：¥{product.current_price:.2f}（毛利率 {margin_now:.1%}）",
            f"- 竞品均价：¥{snapshot.avg_competitor:.2f}（{snapshot.position}）",
            f"- 价格弹性 β = {elasticity.elasticity:.2f}（{elasticity.interpretation.split('：')[0]}）",
            "",
            "## 二、弹性洞察",
            "",
            elasticity.interpretation,
            "",
            "## 三、竞品定位",
            "",
            f"- 最低竞品：¥{snapshot.min_competitor:.2f} ｜ 最高竞品：¥{snapshot.max_competitor:.2f}",
            f"- 本商品相对竞品均价处于 **{snapshot.position}** 区间。",
            "",
            "## 四、AI 定价建议",
            "",
            f"- 建议{direction}至 **¥{recommendation.recommended_price:.2f}**（变动 ¥{delta:.2f}）",
            f"- 预计收入变化：**{recommendation.expected_delta_revenue_pct:+.1f}%**",
            f"- 预计利润变化：**{recommendation.expected_delta_profit_pct:+.1f}%**",
            f"- 预计销量变化：**{recommendation.expected_delta_volume_pct:+.1f}%**",
            f"- 策略：{recommendation.strategy}",
            f"- 置信度：{recommendation.confidence:.0%}",
            "",
            "## 五、策略依据",
            "",
            recommendation.rationale,
            "",
            f"> 建议毛利率将由 {margin_now:.1%} 调整为 {margin_rec:.1%}。",
            "",
            "---",
            "_本报告由 FDE 动态定价引擎自动生成，供定价决策参考，最终价格需业务负责人确认。_",
        ]
        return "\n".join(lines)


def build_report_payload(product: Product, recommendation: PricingRecommendation, elasticity: ElasticityResult, snapshot: CompetitorSnapshot) -> dict[str, Any]:
    """Convenience: assemble a JSON-serializable report payload."""
    gen = ReportGenerator()
    return {
        "product_id": product.product_id,
        "markdown": gen.render(product, elasticity, snapshot, recommendation),
        "summary": {
            "recommended_price": recommendation.recommended_price,
            "current_price": product.current_price,
            "delta_profit_pct": recommendation.expected_delta_profit_pct,
            "strategy": recommendation.strategy,
        },
    }


__all__ = ["ReportGenerator", "build_report_payload"]
