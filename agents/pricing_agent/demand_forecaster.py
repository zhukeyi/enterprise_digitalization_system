"""Demand Forecaster — additive seasonal + linear trend model.

Dependency-free (numpy only). Fits a linear trend via OLS, then estimates a
periodic seasonal component from detrended residuals, and produces a
point forecast with ±1.96·σ prediction bands.

This is a transparent, production-grade statistical forecaster; if XGBoost /
Prophet are available in the deployment they can replace the internals, but
the public API (``forecast``) stays the same.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence

import numpy as np

from agents.pricing_agent.models import DemandForecast, DemandPoint

logger = logging.getLogger("fde.pricing.forecaster")


class DemandForecaster:
    """Seasonal-trend demand forecasting."""

    def __init__(self, seasonal_period: int = 7) -> None:
        self.seasonal_period = max(2, int(seasonal_period))

    def forecast(
        self,
        points: Sequence[DemandPoint],
        periods: int = 14,
    ) -> DemandForecast:
        """Forecast ``periods`` steps ahead from historical ``points``.

        Args:
            points: historical demand points (ordered by ``t`` ascending).
            periods: number of future steps to forecast.

        Returns:
            A :class:`DemandForecast` with fitted history + forecast bands.
        """
        if len(points) < 4:
            raise ValueError("至少需要 4 个历史点才能预测")

        pts = sorted(points, key=lambda p: p.t)
        t = np.array([p.t for p in pts], dtype=float)
        y = np.array([p.quantity for p in pts], dtype=float)

        # ── 1. Linear trend via OLS (degree 1) ──
        # Solve least squares for y = a + b*t
        design = np.vstack([np.ones_like(t), t]).T
        coeffs, *_ = np.linalg.lstsq(design, y, rcond=None)
        a, b = float(coeffs[0]), float(coeffs[1])
        trend = a + b * t

        # ── 2. Seasonal component (detrended residual mean per phase) ──
        resid = y - trend
        seasonal = np.zeros(self.seasonal_period)
        counts = np.zeros(self.seasonal_period)
        for ti, ri in zip(t.astype(int), resid, strict=True):
            phase = ti % self.seasonal_period
            seasonal[phase] += ri
            counts[phase] += 1
        with np.errstate(divide="ignore", invalid="ignore"):
            seasonal = np.where(counts > 0, seasonal / np.maximum(counts, 1), 0.0)
        # center seasonal so it sums to ~0 over a period
        seasonal = seasonal - seasonal.mean()

        fitted = trend + seasonal[t.astype(int) % self.seasonal_period]
        residual_std = float(np.std(y - fitted)) or 1e-6

        # ── 3. Forecast future ──
        last_t = int(t[-1])
        fc_t = np.arange(last_t + 1, last_t + 1 + periods)
        fc_trend = a + b * fc_t
        fc_seasonal = seasonal[fc_t % self.seasonal_period]
        fc_value = fc_trend + fc_seasonal
        band = 1.96 * residual_std

        history = [
            {"t": int(pts[i].t), "actual": float(y[i]), "fitted": float(fitted[i])}
            for i in range(len(pts))
        ]
        forecast = [
            {
                "t": int(fc_t[i]),
                "value": float(max(fc_value[i], 0.0)),
                "lower": float(max(fc_value[i] - band, 0.0)),
                "upper": float(fc_value[i] + band),
            }
            for i in range(periods)
        ]

        return DemandForecast(
            product_id="",  # filled by caller
            history=history,
            forecast=forecast,
            seasonal_period=self.seasonal_period,
            trend_slope=b,
            residual_std=residual_std,
            method="additive-seasonal-ols",
        )


__all__ = ["DemandForecaster"]
