"""Dashboard models — Pydantic data contracts for dashboard configuration (M3-T4).

Defines:
- WidgetType: Supported widget visualization types
- FilterOperator: Filter comparison operators
- DashboardFilter: A filter applied to dashboard data
- Widget: A single dashboard widget with data query and display config
- DashboardConfig: Complete dashboard layout with multiple widgets
- DrillDownLevel: A level in the drill-down hierarchy
- DrillDownResult: Result of a drill-down operation
- CorrelationResult: Result of a cross-table correlation analysis
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

from shared.utils.ids import new_uuid

__all__ = [
    "CorrelationResult",
    "DashboardConfig",
    "DashboardFilter",
    "DrillDownLevel",
    "DrillDownResult",
    "FilterOperator",
    "Widget",
    "WidgetType",
]


# ══════════════════════════════════════════════════════════════════
# Enums
# ══════════════════════════════════════════════════════════════════


class WidgetType(StrEnum):
    """Supported widget visualization types."""

    TABLE = "table"
    BAR_CHART = "bar_chart"
    LINE_CHART = "line_chart"
    PIE_CHART = "pie_chart"
    SCATTER_PLOT = "scatter_plot"
    HEATMAP = "heatmap"
    METRIC_CARD = "metric_card"
    TEXT = "text"


class FilterOperator(StrEnum):
    """Filter comparison operators for dashboard filters."""

    EQ = "eq"  # equals
    NE = "ne"  # not equals
    GT = "gt"  # greater than
    GTE = "gte"  # greater than or equal
    LT = "lt"  # less than
    LTE = "lte"  # less than or equal
    IN = "in"  # value in list
    NOT_IN = "not_in"  # value not in list
    LIKE = "like"  # pattern match
    BETWEEN = "between"  # range


# ══════════════════════════════════════════════════════════════════
# Filter Model
# ══════════════════════════════════════════════════════════════════


class DashboardFilter(BaseModel):
    """A filter applied to dashboard widget data.

    Attributes:
        column: The column/field name to filter on.
        operator: Comparison operator.
        value: The comparison value (or list for IN/BETWEEN).
        label: Human-readable filter description.
    """

    column: str = Field(description="Column name to filter on")
    operator: FilterOperator = Field(default=FilterOperator.EQ, description="Comparison operator")
    value: Any = Field(description="Comparison value")
    label: str = Field(default="", description="Human-readable filter description")


# ══════════════════════════════════════════════════════════════════
# Widget Model
# ══════════════════════════════════════════════════════════════════


class Widget(BaseModel):
    """A single dashboard widget.

    Attributes:
        id: Unique widget identifier.
        title: Widget display title.
        widget_type: Visualization type.
        data_source: SQL query or table name for data retrieval.
        x: Grid column position (0-based).
        y: Grid row position (0-based).
        width: Widget width in grid columns.
        height: Widget height in grid rows.
        filters: Filters applied to this widget's data.
        config: Widget-specific configuration (e.g., chart options).
    """

    id: str = Field(default_factory=new_uuid, description="Unique widget ID")
    title: str = Field(description="Widget display title")
    widget_type: WidgetType = Field(
        default=WidgetType.TABLE,
        description="Visualization type",
    )
    data_source: str = Field(description="SQL query or table name")
    x: int = Field(default=0, ge=0, description="Grid column position")
    y: int = Field(default=0, ge=0, description="Grid row position")
    width: int = Field(default=6, ge=1, le=12, description="Width in grid columns")
    height: int = Field(default=4, ge=1, le=12, description="Height in grid rows")
    filters: list[DashboardFilter] = Field(
        default_factory=list,
        description="Filters applied to this widget",
    )
    config: dict[str, Any] = Field(
        default_factory=dict,
        description="Widget-specific configuration",
    )


# ══════════════════════════════════════════════════════════════════
# Dashboard Config
# ══════════════════════════════════════════════════════════════════


class DashboardConfig(BaseModel):
    """Complete dashboard configuration with multiple widgets.

    Attributes:
        id: Unique dashboard identifier.
        name: Dashboard display name.
        description: Dashboard purpose description.
        widgets: Ordered list of widgets.
        global_filters: Filters applied to all widgets.
        refresh_interval: Auto-refresh interval in seconds (0 = disabled).
    """

    id: str = Field(default_factory=new_uuid, description="Unique dashboard ID")
    name: str = Field(description="Dashboard display name")
    description: str = Field(default="", description="Dashboard purpose")
    widgets: list[Widget] = Field(default_factory=list, description="Dashboard widgets")
    global_filters: list[DashboardFilter] = Field(
        default_factory=list,
        description="Filters applied to all widgets",
    )
    refresh_interval: int = Field(
        default=0,
        ge=0,
        description="Auto-refresh interval in seconds (0 = disabled)",
    )


# ══════════════════════════════════════════════════════════════════
# Drill-Down Models
# ══════════════════════════════════════════════════════════════════


class DrillDownLevel(BaseModel):
    """A single level in the drill-down hierarchy.

    Attributes:
        level: Level number (0 = top, 1 = first drill-down, etc.).
        dimension: The dimension/column being drilled into.
        value: The specific value selected at this level.
        label: Human-readable label for this level.
    """

    level: int = Field(default=0, ge=0, description="Level number (0 = top)")
    dimension: str = Field(description="Dimension/column being drilled")
    value: Any = Field(default=None, description="Selected value at this level")
    label: str = Field(default="", description="Human-readable label")


class DrillDownResult(BaseModel):
    """Result of a drill-down operation.

    Attributes:
        current_level: Current drill-down depth.
        path: The drill-down path (list of levels from top to current).
        rows: Data rows at the current drill-down level.
        columns: Column names in the result.
        next_dimensions: Available dimensions for further drill-down.
        total_count: Total rows at this level (before pagination).
    """

    current_level: int = Field(default=0, ge=0, description="Current drill-down depth")
    path: list[DrillDownLevel] = Field(
        default_factory=list,
        description="Drill-down path from top to current",
    )
    rows: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Data rows at current level",
    )
    columns: list[str] = Field(default_factory=list, description="Column names")
    next_dimensions: list[str] = Field(
        default_factory=list,
        description="Available dimensions for further drill-down",
    )
    total_count: int = Field(default=0, ge=0, description="Total rows before pagination")


# ══════════════════════════════════════════════════════════════════
# Correlation Models
# ══════════════════════════════════════════════════════════════════


class CorrelationResult(BaseModel):
    """Result of a cross-table correlation analysis.

    Attributes:
        table_a: First table name.
        table_b: Second table name.
        join_column: Column used for joining (if applicable).
        correlation_type: Type of correlation (join, statistical, temporal).
        coefficient: Correlation coefficient (-1.0 to 1.0).
        p_value: Statistical significance (0.0 to 1.0).
        description: Human-readable correlation description.
        sample_size: Number of data points analyzed.
    """

    table_a: str = Field(description="First table name")
    table_b: str = Field(description="Second table name")
    join_column: str = Field(default="", description="Join column (if applicable)")
    correlation_type: str = Field(
        default="statistical",
        description="Correlation type: join, statistical, temporal",
    )
    coefficient: float = Field(
        default=0.0,
        ge=-1.0,
        le=1.0,
        description="Correlation coefficient (-1.0 to 1.0)",
    )
    p_value: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Statistical significance",
    )
    description: str = Field(default="", description="Human-readable correlation description")
    sample_size: int = Field(default=0, ge=0, description="Number of data points analyzed")
