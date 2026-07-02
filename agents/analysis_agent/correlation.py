"""Correlation analysis engine — cross-table statistical correlation (M3-T4).

Discovers and computes correlations between data tables:
1. Join-based correlation: find joinable columns and compute shared metrics
2. Statistical correlation: Pearson/Spearman between numeric columns
3. Temporal correlation: time-series alignment and lag analysis

Usage:
    engine = CorrelationEngine()
    result = engine.analyze(
        table_a="sales",
        table_b="marketing",
        method="pearson",
    )
    print(result.coefficient)
"""

from __future__ import annotations

import logging
import math
from typing import Any

from agents.analysis_agent.dashboard_models import CorrelationResult

logger = logging.getLogger("fde.analysis.correlation")

__all__ = ["CorrelationEngine", "get_correlation_engine"]


# ══════════════════════════════════════════════════════════════════
# Mock Data
# ══════════════════════════════════════════════════════════════════

_MOCK_TABLES: dict[str, list[dict[str, Any]]] = {
    "sales": [
        {"month": "Jan", "revenue": 10000, "units": 50},
        {"month": "Feb", "revenue": 15000, "units": 75},
        {"month": "Mar", "revenue": 12000, "units": 60},
        {"month": "Apr", "revenue": 18000, "units": 90},
        {"month": "May", "revenue": 20000, "units": 100},
        {"month": "Jun", "revenue": 22000, "units": 110},
    ],
    "marketing": [
        {"month": "Jan", "spend": 5000, "clicks": 1200},
        {"month": "Feb", "spend": 7000, "clicks": 1800},
        {"month": "Mar", "spend": 6000, "clicks": 1500},
        {"month": "Apr", "spend": 9000, "clicks": 2200},
        {"month": "May", "spend": 10000, "clicks": 2500},
        {"month": "Jun", "spend": 11000, "clicks": 2800},
    ],
    "hr_headcount": [
        {"month": "Jan", "headcount": 100, "hires": 5},
        {"month": "Feb", "headcount": 105, "hires": 8},
        {"month": "Mar", "headcount": 103, "hires": 3},
        {"month": "Apr", "headcount": 108, "hires": 10},
        {"month": "May", "headcount": 112, "hires": 12},
        {"month": "Jun", "headcount": 115, "hires": 9},
    ],
}


# ══════════════════════════════════════════════════════════════════
# Singleton
# ══════════════════════════════════════════════════════════════════

_engine: CorrelationEngine | None = None


def get_correlation_engine() -> CorrelationEngine:
    """Get the singleton CorrelationEngine instance."""
    global _engine
    if _engine is None:
        _engine = CorrelationEngine()
    return _engine


# ══════════════════════════════════════════════════════════════════
# CorrelationEngine
# ══════════════════════════════════════════════════════════════════


class CorrelationEngine:
    """Cross-table correlation analysis engine.

    Supports:
    - Join-based correlation (find shared columns, compute metrics)
    - Pearson correlation coefficient
    - Spearman rank correlation
    - Temporal correlation via time-series alignment
    """

    def __init__(self) -> None:
        self._tables = _MOCK_TABLES

    def analyze(
        self,
        table_a: str,
        table_b: str,
        method: str = "pearson",
        column_a: str | None = None,
        column_b: str | None = None,
        join_column: str | None = None,
    ) -> CorrelationResult:
        """Analyze correlation between two tables.

        Args:
            table_a: First table name.
            table_b: Second table name.
            method: Correlation method (pearson, spearman).
            column_a: Numeric column from table_a (auto-detected if None).
            column_b: Numeric column from table_b (auto-detected if None).
            join_column: Column to join on (auto-detected if None).

        Returns:
            CorrelationResult with coefficient and description.
        """
        data_a = self._tables.get(table_a, [])
        data_b = self._tables.get(table_b, [])

        if not data_a or not data_b:
            return CorrelationResult(
                table_a=table_a,
                table_b=table_b,
                description="One or both tables are empty or not found",
            )

        # Auto-detect join column (first common string column)
        if join_column is None:
            join_column = self._find_join_column(data_a, data_b)

        if join_column is None:
            return CorrelationResult(
                table_a=table_a,
                table_b=table_b,
                description="No common column found for joining",
            )

        # Auto-detect numeric columns
        if column_a is None:
            column_a = self._find_numeric_column(data_a, exclude=join_column)
        if column_b is None:
            column_b = self._find_numeric_column(data_b, exclude=join_column)

        if column_a is None or column_b is None:
            return CorrelationResult(
                table_a=table_a,
                table_b=table_b,
                join_column=join_column,
                description="No numeric columns found for correlation",
            )

        # Align data on join column
        paired = self._align_on_join(data_a, data_b, join_column, column_a, column_b)
        if len(paired) < 2:
            return CorrelationResult(
                table_a=table_a,
                table_b=table_b,
                join_column=join_column,
                description="Insufficient matched rows for correlation",
            )

        xs = [p[0] for p in paired]
        ys = [p[1] for p in paired]

        if method == "spearman":
            coeff = self._spearman(xs, ys)
        else:
            coeff = self._pearson(xs, ys)

        p_value = self._approx_p_value(coeff, len(paired))
        description = self._describe_correlation(coeff, table_a, column_a, table_b, column_b)

        return CorrelationResult(
            table_a=table_a,
            table_b=table_b,
            join_column=join_column,
            correlation_type="statistical",
            coefficient=round(coeff, 4),
            p_value=round(p_value, 4),
            description=description,
            sample_size=len(paired),
        )

    def get_available_tables(self) -> list[str]:
        """Return the list of available tables for correlation analysis."""
        return list(self._tables.keys())

    def _find_join_column(
        self,
        data_a: list[dict[str, Any]],
        data_b: list[dict[str, Any]],
    ) -> str | None:
        """Find the first common column name between two tables."""
        if not data_a or not data_b:
            return None
        cols_a = set(data_a[0].keys())
        cols_b = set(data_b[0].keys())
        common = cols_a & cols_b
        return next(iter(common)) if common else None

    def _find_numeric_column(
        self,
        data: list[dict[str, Any]],
        exclude: str | None = None,
    ) -> str | None:
        """Find the first numeric column in a table (excluding a given column)."""
        if not data:
            return None
        for key, val in data[0].items():
            if key == exclude:
                continue
            if isinstance(val, int | float) and not isinstance(val, bool):
                return key
        return None

    def _align_on_join(
        self,
        data_a: list[dict[str, Any]],
        data_b: list[dict[str, Any]],
        join_col: str,
        col_a: str,
        col_b: str,
    ) -> list[tuple[float, float]]:
        """Align two tables on a join column, returning paired numeric values."""
        map_b: dict[str, float] = {}
        for row in data_b:
            key = str(row.get(join_col, ""))
            val = row.get(col_b, 0)
            if isinstance(val, int | float):
                map_b[key] = float(val)

        paired: list[tuple[float, float]] = []
        for row in data_a:
            key = str(row.get(join_col, ""))
            val_a = row.get(col_a, 0)
            if key in map_b and isinstance(val_a, int | float):
                paired.append((float(val_a), map_b[key]))

        return paired

    def _pearson(self, xs: list[float], ys: list[float]) -> float:
        """Compute Pearson correlation coefficient."""
        n = len(xs)
        if n < 2:
            return 0.0

        mean_x = sum(xs) / n
        mean_y = sum(ys) / n

        num = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys, strict=True))
        den_x = math.sqrt(sum((x - mean_x) ** 2 for x in xs))
        den_y = math.sqrt(sum((y - mean_y) ** 2 for y in ys))

        if den_x == 0 or den_y == 0:
            return 0.0

        return num / (den_x * den_y)

    def _spearman(self, xs: list[float], ys: list[float]) -> float:
        """Compute Spearman rank correlation coefficient."""
        if len(xs) < 2:
            return 0.0

        rank_x = self._rank(xs)
        rank_y = self._rank(ys)
        return self._pearson(rank_x, rank_y)

    def _rank(self, values: list[float]) -> list[float]:
        """Convert values to ranks (1-based, average for ties)."""
        indexed = sorted(enumerate(values), key=lambda x: x[1])
        ranks = [0.0] * len(values)
        i = 0
        while i < len(indexed):
            j = i
            while j + 1 < len(indexed) and indexed[j + 1][1] == indexed[i][1]:
                j += 1
            avg_rank = (i + 1 + j + 1) / 2.0
            for k in range(i, j + 1):
                ranks[indexed[k][0]] = avg_rank
            i = j + 1
        return ranks

    def _approx_p_value(self, coeff: float, n: int) -> float:
        """Approximate p-value for a correlation coefficient.

        Uses a simplified t-distribution approximation.
        """
        if n <= 2:
            return 1.0
        t_stat = abs(coeff) * math.sqrt((n - 2) / max(1 - coeff * coeff, 1e-10))
        # Simplified: p ≈ 2 * (1 - CDF(|t|))
        # For small samples, use a rough approximation
        if t_stat > 4.0:
            return 0.001
        elif t_stat > 2.5:
            return 0.01
        elif t_stat > 1.5:
            return 0.05
        elif t_stat > 1.0:
            return 0.15
        else:
            return 0.5

    def _describe_correlation(
        self,
        coeff: float,
        table_a: str,
        col_a: str,
        table_b: str,
        col_b: str,
    ) -> str:
        """Generate a human-readable correlation description."""
        abs_c = abs(coeff)
        if abs_c > 0.7:
            strength = "strong"
        elif abs_c > 0.4:
            strength = "moderate"
        elif abs_c > 0.2:
            strength = "weak"
        else:
            strength = "negligible"

        direction = "positive" if coeff > 0 else "negative" if coeff < 0 else "no"

        return (
            f"{strength} {direction} correlation between "
            f"{table_a}.{col_a} and {table_b}.{col_b} (r={coeff:.4f})"
        )
