"""Price Elasticity Estimator — log-log OLS regression.

Estimates the constant-elasticity demand coefficient:

    ln(Q) = α + β · ln(P)   →   β = price elasticity of demand

A negative β means demand falls when price rises. |β| > 1 → elastic.
Dependency-free (numpy only).
"""

from __future__ import annotations

import logging
from collections.abc import Sequence

import numpy as np

from agents.pricing_agent.models import ElasticityResult, SalesPoint

logger = logging.getLogger("fde.pricing.elasticity")


class ElasticityEstimator:
    """Estimate price elasticity from historical (price, quantity) pairs."""

    def estimate(self, product_id: str, points: Sequence[SalesPoint]) -> ElasticityResult:
        if len(points) < 3:
            raise ValueError("至少需要 3 个价格-销量观测点")

        prices = np.array([max(p.price, 1e-6) for p in points], dtype=float)
        qtys = np.array([max(p.quantity, 1e-6) for p in points], dtype=float)

        log_p = np.log(prices)
        log_q = np.log(qtys)

        # OLS: log_q = a + b*log_p
        design = np.vstack([np.ones_like(log_p), log_p]).T
        coeffs, _, _, _ = np.linalg.lstsq(design, log_q, rcond=None)
        a, b = float(coeffs[0]), float(coeffs[1])

        # R^2
        pred = a + b * log_p
        ss_res = float(np.sum((log_q - pred) ** 2))
        ss_tot = float(np.sum((log_q - log_q.mean()) ** 2))
        r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else 0.0

        elasticity = b
        is_elastic = abs(elasticity) > 1.0

        if is_elastic:
            interp = f"需求富有弹性（|β|={abs(elasticity):.2f}>1）：价格每上涨1%，销量约下降{abs(elasticity):.2f}%，小幅提价可能损及总收入，需谨慎。"
        else:
            interp = f"需求缺乏弹性（|β|={abs(elasticity):.2f}≤1）：价格每上涨1%，销量仅下降{abs(elasticity):.2f}%，存在温和提价空间。"

        return ElasticityResult(
            product_id=product_id,
            elasticity=round(elasticity, 4),
            r_squared=round(max(0.0, min(1.0, r2)), 4),
            interpretation=interp,
            sample_points=len(points),
            price_range=[float(prices.min()), float(prices.max())],
            is_elastic=is_elastic,
        )


__all__ = ["ElasticityEstimator"]
