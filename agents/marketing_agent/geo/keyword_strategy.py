"""Keyword Strategy — ranks monitored keywords by GEO opportunity.

Opportunity blends search volume, ranking difficulty and the gap between the
brand's current position and the citation zone (top ~3). Higher volume, lower
difficulty and a position closer to the top all raise the score.
"""

from __future__ import annotations

from typing import Any

import numpy as np

from agents.marketing_agent.data_connector import get_connector
from agents.marketing_agent.models import Keyword


class KeywordStrategy:
    """Computes opportunity scores and a ranked keyword plan for a brand."""

    def score_keywords(self, brand_id: str) -> list[Keyword]:
        connector = get_connector()
        keywords = connector.get_keywords(brand_id)
        scored: list[Keyword] = []
        for kw in keywords:
            opp = self._opportunity(kw)
            k = kw.model_copy()
            k.opportunity_score = round(opp, 1)
            scored.append(k)
        scored.sort(key=lambda x: x.opportunity_score, reverse=True)
        return scored

    def _opportunity(self, kw: Keyword) -> float:
        vol = np.log1p(kw.monthly_volume) / np.log1p(25000)  # normalise 0-1
        diff = 1.0 - kw.difficulty / 100.0
        # position gap: top-3 is the citation zone
        pos_gap = max(0.0, (10.0 - kw.current_position) / 9.0)
        raw = 100.0 * (0.45 * vol + 0.30 * diff + 0.25 * pos_gap)
        return float(np.clip(raw, 0.0, 100.0))

    def plan(self, brand_id: str, top_n: int = 5) -> list[dict[str, Any]]:
        scored = self.score_keywords(brand_id)
        return [
            {
                "term": k.term,
                "intent": k.intent,
                "monthly_volume": k.monthly_volume,
                "difficulty": k.difficulty,
                "current_position": k.current_position,
                "opportunity_score": k.opportunity_score,
            }
            for k in scored[:top_n]
        ]


__all__ = ["KeywordStrategy"]
