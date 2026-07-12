"""GEO Visibility Tracker — measures how often a brand is surfaced/cited by
AI search engines (ChatGPT, Claude, Gemini, Perplexity, Bing Copilot) for its
monitored keywords.

The synthetic probe models each engine's per-brand visibility as a function of
brand strength, keyword coverage and a deterministic engine bias, so the demo
produces stable, explainable numbers (mirrors GEOVisibilityTool's probe idea
without live API calls). Swap ``probe`` for real LLM-engine queries in prod.
"""

from __future__ import annotations

from typing import Any

import numpy as np

from agents.marketing_agent.data_connector import get_connector
from agents.marketing_agent.models import BrandVisibility, EngineVisibility

# engine bias: which engines lean toward which brand archetypes (demo)
_ENGINE_BIAS: dict[str, float] = {
    "ChatGPT": 0.94,
    "Claude": 0.88,
    "Gemini": 0.90,
    "Perplexity": 1.06,  # citation-heavy → rewards authoritative sources
    "Bing Copilot": 0.98,
}


class VisibilityTracker:
    """Computes GEO visibility index and per-engine breakdown for a brand."""

    def track(self, brand_id: str) -> BrandVisibility:
        connector = get_connector()
        brand = connector.get_brand(brand_id)
        if brand is None:
            raise ValueError(f"品牌不存在: {brand_id}")
        keywords = connector.get_keywords(brand_id)
        engines = connector.get_engines()

        total = len(keywords) or 1
        engine_rows: list[EngineVisibility] = []
        # per-keyword: is it cited in ANY engine?
        cited_in_any = [False] * total

        for eng in engines:
            bias = _ENGINE_BIAS.get(eng, 1.0)
            # probability a monitored keyword cites this brand in this engine
            coverages = []
            for i, kw in enumerate(keywords):
                # higher strength + lower difficulty + better position → cited
                cite_p = (
                    0.55 * (brand.strength / 100)
                    + 0.25 * (1 - kw.difficulty / 100)
                    + 0.20 * max(0.0, (11 - kw.current_position) / 10)
                )
                cite_p = float(np.clip(cite_p * bias, 0.02, 0.98))
                coverages.append(cite_p)
                if cite_p > 0.5:
                    cited_in_any[i] = True
            coverages_arr = np.array(coverages)
            cited = int(np.sum(coverages_arr > 0.5))
            score = float(np.clip(coverages_arr.mean() * 100 * bias, 0.0, 100.0))
            avg_pos = float(np.mean([kw.current_position for kw in keywords])) if keywords else 0.0
            engine_rows.append(
                EngineVisibility(
                    engine=eng,
                    score=round(score, 1),
                    cited=cited > total * 0.4,
                    avg_position=round(avg_pos, 1),
                    sampled_keywords=total,
                )
            )

        cited_total = sum(cited_in_any)

        geo_index = round(float(np.mean([e.score for e in engine_rows])), 1)
        trend = round(float(np.mean([e.score for e in engine_rows])) - 62.0, 1)  # vs 30d-ago baseline 62

        return BrandVisibility(
            brand_id=brand_id,
            brand_name=brand.name,
            geo_index=geo_index,
            engines=engine_rows,
            cited_keywords=cited_total,
            total_keywords=total,
            trend_30d=trend,
        )

    def aggregate(self) -> dict[str, Any]:
        """Cross-brand engine breakdown for the overview dashboard."""
        connector = get_connector()
        engines = connector.get_engines()
        per_engine: dict[str, list[float]] = {e: [] for e in engines}
        for b in connector.get_brands():
            bv = self.track(b.brand_id)
            for er in bv.engines:
                per_engine[er.engine].append(er.score)
        return {
            e: {
                "avg_score": round(float(np.mean(v)), 1) if v else 0.0,
                "brands_cited": sum(1 for x in v if x >= 50),
                "total_brands": len(v),
            }
            for e, v in per_engine.items()
        }


__all__ = ["VisibilityTracker"]
