"""Report Generator — builds a concise executive summary for the marketing
module by composing the outputs of the visibility tracker, keyword strategy,
content optimizer and performance tracker.
"""

from __future__ import annotations

from typing import Any

from agents.marketing_agent.analytics.performance_tracker import PerformanceTracker
from agents.marketing_agent.data_connector import get_connector
from agents.marketing_agent.geo.keyword_strategy import KeywordStrategy
from agents.marketing_agent.geo.visibility_tracker import VisibilityTracker


class ReportGenerator:
    """Composes a marketing/GEO executive summary for a brand."""

    def summary(self, brand_id: str) -> dict[str, Any]:
        connector = get_connector()
        brand = connector.get_brand(brand_id)
        if brand is None:
            raise ValueError(f"品牌不存在: {brand_id}")

        vis = VisibilityTracker().track(brand_id)
        plan = KeywordStrategy().plan(brand_id, top_n=3)
        perf = PerformanceTracker().aggregate(connector.get_platforms(brand_id))
        contents = connector.get_content(brand_id)
        avg_eeat = round(sum(c.eeat_score for c in contents) / len(contents), 1) if contents else 0.0

        bullets: list[str] = []
        bullets.append(f"GEO 可见度指数 {vis.geo_index}/100，近 30 天变化 {vis.trend_30d:+} 分。")
        best_engine = max(vis.engines, key=lambda e: e.score)
        bullets.append(f"在 {best_engine.engine} 上表现最佳（{best_engine.score}/100）。")
        if plan:
            bullets.append(f"最高机会关键词：{plan[0]['term']}（机会分 {plan[0]['opportunity_score']}）。")
        bullets.append(f"跨平台综合 ROAS {perf['blended_roas']}，内容平均 E-E-A-T {avg_eeat}/100。")

        return {
            "brand": brand.name,
            "geo_index": vis.geo_index,
            "blended_roas": perf["blended_roas"],
            "avg_eeat": avg_eeat,
            "top_keywords": plan,
            "engine_scores": [e.score for e in vis.engines],
            "bullets": bullets,
        }


__all__ = ["ReportGenerator"]
