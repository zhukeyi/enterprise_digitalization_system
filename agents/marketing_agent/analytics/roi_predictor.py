"""ROI Predictor — fits a spend→revenue relationship on historical campaign
data with ordinary least squares (numpy only) and predicts revenue / ROAS /
profit for a proposed spend. Includes an intercept so it also captures a
baseline (brand/organic) revenue component.
"""

from __future__ import annotations

import numpy as np

from agents.marketing_agent.models import PlatformPerformance, ROIPrediction


class ROIPredictor:
    """OLS spend→revenue model with prediction + confidence."""

    def predict(self, platforms: list[PlatformPerformance], spend: float) -> ROIPrediction:
        if len(platforms) < 2:
            raise ValueError("ROI 预测至少需要 2 个历史渠道数据点")
        x = np.array([p.spend for p in platforms], dtype=float)
        y = np.array([p.revenue for p in platforms], dtype=float)

        # OLS: revenue = a + b*spend  (design matrix with intercept)
        design = np.vstack([np.ones_like(x), x]).T
        coeffs, *_ = np.linalg.lstsq(design, y, rcond=None)
        a, b = float(coeffs[0]), float(coeffs[1])

        # R^2
        y_hat = a + b * x
        ss_res = float(np.sum((y - y_hat) ** 2))
        ss_tot = float(np.sum((y - y.mean()) ** 2))
        r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else 0.0

        # residual std → prediction interval width (1 sigma)
        n = len(x)
        sigma = np.sqrt(ss_res / max(1, n - 2)) if n > 2 else 0.0
        pred = a + b * spend
        # simple variance of prediction (ignore x-mean leverage for demo)
        pred_var = sigma**2 * (1.0 + 1.0 / n) if n > 2 else 0.0
        conf = float(np.clip(1.0 - min(1.0, np.sqrt(pred_var) / max(1.0, abs(pred))), 0.3, 0.97))

        profit = pred - spend
        roas = pred / spend if spend > 0 else 0.0
        return ROIPrediction(
            spend=round(spend, 2),
            predicted_revenue=round(pred, 2),
            predicted_roas=round(roas, 2),
            predicted_profit=round(profit, 2),
            payback_ratio=round(roas, 2),
            confidence=round(conf, 2),
            slope=round(b, 4),
            fit_r_squared=round(float(r2), 3),
        )


__all__ = ["ROIPredictor"]
