"""Drill-down engine — hierarchical data exploration (M3-T4).

Provides DrillDownEngine for navigating data hierarchies:
1. Start at a top-level aggregation (e.g., by region)
2. Drill down to finer granularity (e.g., region → province → city)
3. Each level inherits filters from parent levels

Usage:
    engine = DrillDownEngine()
    result = engine.drill_down(
        table="sales",
        dimensions=["region", "province", "city"],
        level=0,
    )
    # User clicks "East" → drill to level 1
    result = engine.drill_down(
        table="sales",
        dimensions=["region", "province", "city"],
        level=1,
        path=[DrillDownLevel(level=0, dimension="region", value="East")],
    )
"""

from __future__ import annotations

import logging
from typing import Any

from agents.analysis_agent.dashboard_models import (
    DrillDownLevel,
    DrillDownResult,
)

logger = logging.getLogger("fde.analysis.drill_down")

__all__ = ["DrillDownEngine", "get_drill_down_engine"]


# ══════════════════════════════════════════════════════════════════
# Mock Data (in-memory, for development/testing)
# ══════════════════════════════════════════════════════════════════

_MOCK_SALES_DATA: list[dict[str, Any]] = [
    {"region": "East", "province": "Jiangsu", "city": "Nanjing", "amount": 12000, "count": 50},
    {"region": "East", "province": "Jiangsu", "city": "Suzhou", "amount": 18000, "count": 80},
    {"region": "East", "province": "Shanghai", "city": "Shanghai", "amount": 35000, "count": 120},
    {"region": "East", "province": "Zhejiang", "city": "Hangzhou", "amount": 22000, "count": 90},
    {"region": "West", "province": "Sichuan", "city": "Chengdu", "amount": 15000, "count": 60},
    {"region": "West", "province": "Shaanxi", "city": "Xi'an", "amount": 9000, "count": 35},
    {"region": "North", "province": "Beijing", "city": "Beijing", "amount": 40000, "count": 150},
    {"region": "North", "province": "Shandong", "city": "Qingdao", "amount": 11000, "count": 45},
    {
        "region": "South",
        "province": "Guangdong",
        "city": "Guangzhou",
        "amount": 28000,
        "count": 110,
    },
    {"region": "South", "province": "Guangdong", "city": "Shenzhen", "amount": 45000, "count": 180},
]


# ══════════════════════════════════════════════════════════════════
# Singleton
# ══════════════════════════════════════════════════════════════════

_engine: DrillDownEngine | None = None


def get_drill_down_engine() -> DrillDownEngine:
    """Get the singleton DrillDownEngine instance."""
    global _engine
    if _engine is None:
        _engine = DrillDownEngine()
    return _engine


# ══════════════════════════════════════════════════════════════════
# DrillDownEngine
# ══════════════════════════════════════════════════════════════════


class DrillDownEngine:
    """Hierarchical drill-down analysis engine.

    Navigates data through a predefined dimension hierarchy, aggregating
    metrics at each level and applying inherited filters from parent levels.
    """

    def __init__(self) -> None:
        self._mock_data: dict[str, list[dict[str, Any]]] = {
            "sales": _MOCK_SALES_DATA,
        }

    def drill_down(
        self,
        table: str,
        dimensions: list[str],
        level: int = 0,
        path: list[DrillDownLevel] | None = None,
        metrics: list[str] | None = None,
    ) -> DrillDownResult:
        """Execute a drill-down query at the specified level.

        Args:
            table: Data source table name.
            dimensions: Ordered list of drill-down dimensions (hierarchy).
            level: Target drill-down level (0 = top-level).
            path: Drill-down path from top to current (for filter inheritance).
            metrics: Metric columns to aggregate (default: all numeric columns).

        Returns:
            DrillDownResult with aggregated rows and available next dimensions.
        """
        path = path or []
        metrics = metrics or ["amount", "count"]

        if level < 0 or level >= len(dimensions):
            return DrillDownResult(
                current_level=level,
                path=path,
                rows=[],
                columns=[],
                next_dimensions=[],
                total_count=0,
            )

        data = self._get_data(table)
        filtered = self._apply_path_filters(data, path, dimensions)

        current_dim = dimensions[level]
        aggregated = self._aggregate(filtered, current_dim, metrics)

        columns = [current_dim, *metrics]
        next_dims = dimensions[level + 1 :] if level + 1 < len(dimensions) else []

        return DrillDownResult(
            current_level=level,
            path=path,
            rows=aggregated,
            columns=columns,
            next_dimensions=next_dims,
            total_count=len(aggregated),
        )

    def get_available_tables(self) -> list[str]:
        """Return the list of available data tables."""
        return list(self._mock_data.keys())

    def _get_data(self, table: str) -> list[dict[str, Any]]:
        """Get data for a table (from mock store)."""
        return self._mock_data.get(table, [])

    def _apply_path_filters(
        self,
        data: list[dict[str, Any]],
        path: list[DrillDownLevel],
        dimensions: list[str],
    ) -> list[dict[str, Any]]:
        """Filter data based on the drill-down path.

        Each DrillDownLevel in the path specifies a dimension and value
        that was selected. We filter the data to only include rows matching
        all selected path values.
        """
        if not path:
            return data

        result = data
        for level in path:
            dim = level.dimension
            val = level.value
            if val is None:
                continue
            result = [row for row in result if row.get(dim) == val]
        return result

    def _aggregate(
        self,
        data: list[dict[str, Any]],
        dimension: str,
        metrics: list[str],
    ) -> list[dict[str, Any]]:
        """Aggregate data by a dimension, summing numeric metrics.

        Args:
            data: Input data rows.
            dimension: The dimension to group by.
            metrics: Metric columns to sum.

        Returns:
            List of aggregated rows with dimension + summed metrics.
        """
        groups: dict[str, dict[str, Any]] = {}

        for row in data:
            key = str(row.get(dimension, ""))
            if key not in groups:
                groups[key] = {dimension: key}
                for m in metrics:
                    groups[key][m] = 0

            for m in metrics:
                val = row.get(m, 0)
                if isinstance(val, int | float):
                    groups[key][m] = groups[key].get(m, 0) + val

        return list(groups.values())
