"""Aggregation service — GroupBy, Pivot, TimeSeries (M3-T4).

Provides data aggregation operations for dashboard widgets:
1. GroupBy: Aggregate by one or more dimensions
2. Pivot: Cross-tabulation (rows x columns → values)
3. TimeSeries: Time-based aggregation with configurable granularity

Usage:
    service = AggregationService()
    result = service.groupby("sales", group_by=["region"], metrics=["revenue"])
    pivot = service.pivot("sales", rows=["region"], cols=["month"], values="revenue")
    ts = service.timeseries("sales", time_col="month", value_col="revenue")
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger("fde.analysis.aggregation")

__all__ = [
    "AggregationResult",
    "AggregationService",
    "PivotResult",
    "TimeSeriesPoint",
    "TimeSeriesResult",
    "get_aggregation_service",
]


# ══════════════════════════════════════════════════════════════════
# Mock Data (shared with drill_down and correlation)
# ══════════════════════════════════════════════════════════════════

_MOCK_DATA: dict[str, list[dict[str, Any]]] = {
    "sales": [
        {"region": "East", "month": "Jan", "revenue": 10000, "units": 50},
        {"region": "East", "month": "Feb", "revenue": 15000, "units": 75},
        {"region": "East", "month": "Mar", "revenue": 12000, "units": 60},
        {"region": "West", "month": "Jan", "revenue": 8000, "units": 40},
        {"region": "West", "month": "Feb", "revenue": 9000, "units": 45},
        {"region": "West", "month": "Mar", "revenue": 11000, "units": 55},
        {"region": "North", "month": "Jan", "revenue": 20000, "units": 100},
        {"region": "North", "month": "Feb", "revenue": 22000, "units": 110},
        {"region": "North", "month": "Mar", "revenue": 25000, "units": 125},
    ],
}


# ══════════════════════════════════════════════════════════════════
# Result Models
# ══════════════════════════════════════════════════════════════════


class AggregationResult:
    """Result of a groupby aggregation."""

    def __init__(
        self,
        group_keys: list[str],
        rows: list[dict[str, Any]],
    ) -> None:
        self.group_keys = group_keys
        self.rows = rows

    def to_dict(self) -> dict[str, Any]:
        return {"group_keys": self.group_keys, "rows": self.rows}


class PivotResult:
    """Result of a pivot operation."""

    def __init__(
        self,
        row_labels: list[str],
        col_labels: list[str],
        matrix: list[list[Any]],
    ) -> None:
        self.row_labels = row_labels
        self.col_labels = col_labels
        self.matrix = matrix

    def to_dict(self) -> dict[str, Any]:
        return {
            "row_labels": self.row_labels,
            "col_labels": self.col_labels,
            "matrix": self.matrix,
        }


class TimeSeriesPoint:
    """A single point in a time series."""

    def __init__(self, timestamp: str, value: float) -> None:
        self.timestamp = timestamp
        self.value = value

    def to_dict(self) -> dict[str, str | float]:
        return {"timestamp": self.timestamp, "value": self.value}


class TimeSeriesResult:
    """Result of a time series aggregation."""

    def __init__(
        self,
        points: list[TimeSeriesPoint],
        granularity: str = "month",
    ) -> None:
        self.points = points
        self.granularity = granularity

    def to_dict(self) -> dict[str, Any]:
        return {
            "granularity": self.granularity,
            "points": [p.to_dict() for p in self.points],
        }


# ══════════════════════════════════════════════════════════════════
# Singleton
# ══════════════════════════════════════════════════════════════════

_service: AggregationService | None = None


def get_aggregation_service() -> AggregationService:
    """Get the singleton AggregationService instance."""
    global _service
    if _service is None:
        _service = AggregationService()
    return _service


# ══════════════════════════════════════════════════════════════════
# AggregationService
# ══════════════════════════════════════════════════════════════════


class AggregationService:
    """Data aggregation service for dashboard widgets.

    Provides:
    - groupby: Group by dimensions and aggregate metrics (sum/avg/count/min/max)
    - pivot: Cross-tabulation with rows x columns → aggregated values
    - timeseries: Time-based aggregation with configurable granularity
    """

    def __init__(self) -> None:
        self._tables = _MOCK_DATA

    def groupby(
        self,
        table: str,
        group_by: list[str],
        metrics: list[str] | None = None,
        agg_func: str = "sum",
    ) -> AggregationResult:
        """Group data by one or more dimensions and aggregate metrics.

        Args:
            table: Source table name.
            group_by: List of dimension columns to group by.
            metrics: Metric columns to aggregate (default: all numeric).
            agg_func: Aggregation function (sum, avg, count, min, max).

        Returns:
            AggregationResult with group keys and aggregated rows.
        """
        data = self._tables.get(table, [])
        if not data:
            return AggregationResult(group_keys=group_by, rows=[])

        metrics = metrics or self._get_numeric_columns(data, exclude=set(group_by))
        groups: dict[tuple[str, ...], dict[str, Any]] = {}

        for data_row in data:
            key = tuple(str(data_row.get(g, "")) for g in group_by)
            if key not in groups:
                groups[key] = dict(zip(group_by, key, strict=True))
                for m in metrics:
                    groups[key][m] = []

            for m in metrics:
                val = data_row.get(m, 0)
                if isinstance(val, int | float):
                    groups[key][m].append(val)

        rows: list[dict[str, Any]] = []
        for group_data in groups.values():
            out_row: dict[str, Any] = {}
            for g in group_by:
                out_row[g] = group_data[g]
            for m in metrics:
                values: list[float] = group_data.get(m, [])
                out_row[m] = self._aggregate_values(values, agg_func)
            rows.append(out_row)

        return AggregationResult(group_keys=group_by, rows=rows)

    def pivot(
        self,
        table: str,
        rows: str,
        cols: str,
        values: str,
        agg_func: str = "sum",
    ) -> PivotResult:
        """Create a pivot table (cross-tabulation).

        Args:
            table: Source table name.
            rows: Dimension for pivot rows.
            cols: Dimension for pivot columns.
            values: Value column to aggregate.
            agg_func: Aggregation function (sum, avg, count, min, max).

        Returns:
            PivotResult with row labels, column labels, and value matrix.
        """
        data = self._tables.get(table, [])
        if not data:
            return PivotResult(row_labels=[], col_labels=[], matrix=[])

        row_labels: list[str] = []
        col_labels: list[str] = []
        cell_values: dict[tuple[str, str], list[float]] = {}

        for row in data:
            r = str(row.get(rows, ""))
            c = str(row.get(cols, ""))
            v = row.get(values, 0)

            if r not in row_labels:
                row_labels.append(r)
            if c not in col_labels:
                col_labels.append(c)

            if isinstance(v, int | float):
                key = (r, c)
                if key not in cell_values:
                    cell_values[key] = []
                cell_values[key].append(float(v))

        matrix: list[list[Any]] = []
        for rl in row_labels:
            matrix_row: list[Any] = []
            for cl in col_labels:
                vals = cell_values.get((rl, cl), [])
                matrix_row.append(self._aggregate_values(vals, agg_func) if vals else 0)
            matrix.append(matrix_row)

        return PivotResult(row_labels=row_labels, col_labels=col_labels, matrix=matrix)

    def timeseries(
        self,
        table: str,
        time_col: str,
        value_col: str,
        granularity: str = "month",
        agg_func: str = "sum",
    ) -> TimeSeriesResult:
        """Aggregate data as a time series.

        Args:
            table: Source table name.
            time_col: Time column name.
            value_col: Value column to aggregate.
            granularity: Time granularity (month, day, hour).
            agg_func: Aggregation function (sum, avg, count, min, max).

        Returns:
            TimeSeriesResult with ordered time series points.
        """
        data = self._tables.get(table, [])
        if not data:
            return TimeSeriesResult(points=[], granularity=granularity)

        grouped: dict[str, list[float]] = {}
        for row in data:
            ts = str(row.get(time_col, ""))
            val = row.get(value_col, 0)
            if isinstance(val, int | float):
                (
                    grouped[ts].append(float(val))
                    if ts in grouped
                    else grouped.update({ts: [float(val)]})
                )

        sorted_ts = sorted(grouped.keys())
        points = [
            TimeSeriesPoint(
                timestamp=ts,
                value=self._aggregate_values(grouped[ts], agg_func),
            )
            for ts in sorted_ts
        ]

        return TimeSeriesResult(points=points, granularity=granularity)

    def get_available_tables(self) -> list[str]:
        """Return the list of available tables."""
        return list(self._tables.keys())

    def _get_numeric_columns(
        self,
        data: list[dict[str, Any]],
        exclude: set[str] | None = None,
    ) -> list[str]:
        """Identify numeric columns in the data."""
        if not data:
            return []
        exclude = exclude or set()
        return [
            key
            for key, val in data[0].items()
            if key not in exclude and isinstance(val, int | float) and not isinstance(val, bool)
        ]

    def _aggregate_values(self, values: list[float], agg_func: str) -> float:
        """Aggregate a list of values using the specified function."""
        if not values:
            return 0.0

        if agg_func == "sum":
            return sum(values)
        elif agg_func == "avg":
            return sum(values) / len(values)
        elif agg_func == "count":
            return float(len(values))
        elif agg_func == "min":
            return min(values)
        elif agg_func == "max":
            return max(values)
        else:
            return sum(values)
