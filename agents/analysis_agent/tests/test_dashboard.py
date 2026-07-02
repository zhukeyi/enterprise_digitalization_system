"""Tests for M3-T4: Dashboard + drill-down + correlation + aggregation.

Covers:
- Dashboard models: Widget, DashboardConfig, DashboardFilter, DrillDownLevel, CorrelationResult
- DrillDownEngine: top-level, drill-down with path filters, edge cases
- CorrelationEngine: Pearson, Spearman, auto-detect join column, edge cases
- AggregationService: groupby, pivot, timeseries
"""

from __future__ import annotations

from agents.analysis_agent.aggregation import (
    AggregationService,
    get_aggregation_service,
)
from agents.analysis_agent.correlation import CorrelationEngine, get_correlation_engine
from agents.analysis_agent.dashboard_models import (
    CorrelationResult,
    DashboardConfig,
    DashboardFilter,
    DrillDownLevel,
    DrillDownResult,
    FilterOperator,
    Widget,
    WidgetType,
)
from agents.analysis_agent.drill_down import DrillDownEngine, get_drill_down_engine

# ══════════════════════════════════════════════════════════════════
# Dashboard Model Tests
# ══════════════════════════════════════════════════════════════════


class TestDashboardModels:
    """Tests for dashboard Pydantic models."""

    def test_widget_defaults(self) -> None:
        w = Widget(title="Test Widget", data_source="sales")
        assert w.title == "Test Widget"
        assert w.widget_type == WidgetType.TABLE
        assert w.width == 6
        assert w.height == 4
        assert w.filters == []
        assert w.config == {}
        assert w.id  # auto-generated

    def test_widget_type_enum(self) -> None:
        w = Widget(title="Chart", data_source="sales", widget_type=WidgetType.BAR_CHART)
        assert w.widget_type == "bar_chart"

    def test_dashboard_filter(self) -> None:
        f = DashboardFilter(column="region", operator=FilterOperator.EQ, value="East")
        assert f.column == "region"
        assert f.operator == FilterOperator.EQ
        assert f.value == "East"

    def test_filter_operator_values(self) -> None:
        assert FilterOperator.EQ == "eq"
        assert FilterOperator.GT == "gt"
        assert FilterOperator.IN == "in"
        assert FilterOperator.LIKE == "like"
        assert FilterOperator.BETWEEN == "between"

    def test_dashboard_config_defaults(self) -> None:
        dc = DashboardConfig(name="Sales Dashboard")
        assert dc.name == "Sales Dashboard"
        assert dc.widgets == []
        assert dc.global_filters == []
        assert dc.refresh_interval == 0
        assert dc.id  # auto-generated

    def test_dashboard_config_with_widgets(self) -> None:
        dc = DashboardConfig(
            name="Dashboard",
            widgets=[
                Widget(title="W1", data_source="sales", x=0, y=0, width=6),
                Widget(title="W2", data_source="sales", x=6, y=0, width=6),
            ],
        )
        assert len(dc.widgets) == 2
        assert dc.widgets[0].title == "W1"

    def test_drill_down_level(self) -> None:
        level = DrillDownLevel(level=0, dimension="region", value="East")
        assert level.level == 0
        assert level.dimension == "region"
        assert level.value == "East"

    def test_drill_down_result_defaults(self) -> None:
        r = DrillDownResult()
        assert r.current_level == 0
        assert r.rows == []
        assert r.columns == []
        assert r.next_dimensions == []
        assert r.total_count == 0

    def test_correlation_result_defaults(self) -> None:
        r = CorrelationResult(table_a="t1", table_b="t2")
        assert r.table_a == "t1"
        assert r.table_b == "t2"
        assert r.coefficient == 0.0
        assert r.correlation_type == "statistical"

    def test_widget_type_all_values(self) -> None:
        types = [wt.value for wt in WidgetType]
        assert "table" in types
        assert "bar_chart" in types
        assert "line_chart" in types
        assert "pie_chart" in types
        assert "scatter_plot" in types
        assert "heatmap" in types
        assert "metric_card" in types
        assert "text" in types


# ══════════════════════════════════════════════════════════════════
# DrillDownEngine Tests
# ══════════════════════════════════════════════════════════════════


class TestDrillDownEngine:
    """Tests for the DrillDownEngine."""

    DIMS = ["region", "province", "city"]

    def test_top_level_aggregation(self) -> None:
        engine = DrillDownEngine()
        result = engine.drill_down(
            table="sales",
            dimensions=self.DIMS,
            level=0,
        )
        assert result.current_level == 0
        assert result.total_count > 0
        assert "region" in result.columns
        assert "amount" in result.columns or "count" in result.columns
        # Should have regions: East, West, North, South
        regions = [row["region"] for row in result.rows]
        assert "East" in regions
        assert "West" in regions

    def test_drill_down_level1(self) -> None:
        engine = DrillDownEngine()
        result = engine.drill_down(
            table="sales",
            dimensions=self.DIMS,
            level=1,
            path=[DrillDownLevel(level=0, dimension="region", value="East")],
        )
        assert result.current_level == 1
        # Should show provinces within East: Jiangsu, Shanghai, Zhejiang
        provinces = [row["province"] for row in result.rows]
        assert "Jiangsu" in provinces
        assert "Shanghai" in provinces
        assert "Zhejiang" in provinces

    def test_drill_down_level2(self) -> None:
        engine = DrillDownEngine()
        result = engine.drill_down(
            table="sales",
            dimensions=self.DIMS,
            level=2,
            path=[
                DrillDownLevel(level=0, dimension="region", value="East"),
                DrillDownLevel(level=1, dimension="province", value="Jiangsu"),
            ],
        )
        assert result.current_level == 2
        cities = [row["city"] for row in result.rows]
        assert "Nanjing" in cities
        assert "Suzhou" in cities

    def test_drill_down_next_dimensions(self) -> None:
        engine = DrillDownEngine()
        result = engine.drill_down(table="sales", dimensions=self.DIMS, level=0)
        assert "province" in result.next_dimensions
        assert "city" in result.next_dimensions

    def test_drill_down_last_level_no_next(self) -> None:
        engine = DrillDownEngine()
        result = engine.drill_down(
            table="sales",
            dimensions=self.DIMS,
            level=2,
            path=[
                DrillDownLevel(level=0, dimension="region", value="East"),
                DrillDownLevel(level=1, dimension="province", value="Jiangsu"),
            ],
        )
        assert result.next_dimensions == []

    def test_drill_down_invalid_level(self) -> None:
        engine = DrillDownEngine()
        result = engine.drill_down(table="sales", dimensions=self.DIMS, level=99)
        assert result.rows == []
        assert result.total_count == 0

    def test_drill_down_nonexistent_table(self) -> None:
        engine = DrillDownEngine()
        result = engine.drill_down(table="nonexistent", dimensions=self.DIMS, level=0)
        assert result.rows == []
        assert result.total_count == 0

    def test_drill_down_path_filter_isolates_data(self) -> None:
        engine = DrillDownEngine()
        # West has: Sichuan, Shaanxi
        result = engine.drill_down(
            table="sales",
            dimensions=self.DIMS,
            level=1,
            path=[DrillDownLevel(level=0, dimension="region", value="West")],
        )
        provinces = [row["province"] for row in result.rows]
        assert "Sichuan" in provinces
        assert "Shaanxi" in provinces
        # Should NOT have East provinces
        assert "Jiangsu" not in provinces

    def test_get_available_tables(self) -> None:
        engine = DrillDownEngine()
        tables = engine.get_available_tables()
        assert "sales" in tables

    def test_get_drill_down_engine_singleton(self) -> None:
        e1 = get_drill_down_engine()
        e2 = get_drill_down_engine()
        assert e1 is e2


# ══════════════════════════════════════════════════════════════════
# CorrelationEngine Tests
# ══════════════════════════════════════════════════════════════════


class TestCorrelationEngine:
    """Tests for the CorrelationEngine."""

    def test_pearson_correlation(self) -> None:
        engine = CorrelationEngine()
        result = engine.analyze(
            table_a="sales",
            table_b="marketing",
            method="pearson",
        )
        assert result.table_a == "sales"
        assert result.table_b == "marketing"
        assert -1.0 <= result.coefficient <= 1.0
        assert result.sample_size > 0
        # Revenue and marketing spend should be positively correlated
        assert result.coefficient > 0

    def test_spearman_correlation(self) -> None:
        engine = CorrelationEngine()
        result = engine.analyze(
            table_a="sales",
            table_b="marketing",
            method="spearman",
        )
        assert -1.0 <= result.coefficient <= 1.0
        assert result.sample_size > 0

    def test_auto_detect_join_column(self) -> None:
        engine = CorrelationEngine()
        result = engine.analyze(table_a="sales", table_b="marketing")
        # "month" is the common column
        assert result.join_column == "month"

    def test_correlation_description(self) -> None:
        engine = CorrelationEngine()
        result = engine.analyze(table_a="sales", table_b="marketing")
        assert "correlation" in result.description.lower()
        assert "sales" in result.description
        assert "marketing" in result.description

    def test_correlation_nonexistent_table(self) -> None:
        engine = CorrelationEngine()
        result = engine.analyze(table_a="nonexistent", table_b="marketing")
        assert result.coefficient == 0.0
        assert "empty" in result.description.lower() or "not found" in result.description.lower()

    def test_correlation_p_value_range(self) -> None:
        engine = CorrelationEngine()
        result = engine.analyze(table_a="sales", table_b="marketing")
        assert 0.0 <= result.p_value <= 1.0

    def test_correlation_hr_headcount(self) -> None:
        engine = CorrelationEngine()
        result = engine.analyze(
            table_a="sales",
            table_b="hr_headcount",
            method="pearson",
        )
        assert result.sample_size > 0
        # Both growing over time — should be positive
        assert result.coefficient > 0

    def test_get_available_tables(self) -> None:
        engine = CorrelationEngine()
        tables = engine.get_available_tables()
        assert "sales" in tables
        assert "marketing" in tables
        assert "hr_headcount" in tables

    def test_get_correlation_engine_singleton(self) -> None:
        e1 = get_correlation_engine()
        e2 = get_correlation_engine()
        assert e1 is e2


# ══════════════════════════════════════════════════════════════════
# AggregationService Tests
# ══════════════════════════════════════════════════════════════════


class TestAggregationService:
    """Tests for the AggregationService."""

    def test_groupby_single_dimension(self) -> None:
        svc = AggregationService()
        result = svc.groupby("sales", group_by=["region"], metrics=["revenue"])
        assert "region" in result.group_keys
        assert len(result.rows) > 0
        regions = [row["region"] for row in result.rows]
        assert "East" in regions
        assert "West" in regions

    def test_groupby_sum(self) -> None:
        svc = AggregationService()
        result = svc.groupby("sales", group_by=["region"], metrics=["revenue"], agg_func="sum")
        for row in result.rows:
            assert row["revenue"] > 0

    def test_groupby_avg(self) -> None:
        svc = AggregationService()
        result = svc.groupby("sales", group_by=["region"], metrics=["revenue"], agg_func="avg")
        for row in result.rows:
            assert row["revenue"] > 0

    def test_groupby_count(self) -> None:
        svc = AggregationService()
        result = svc.groupby("sales", group_by=["region"], metrics=["revenue"], agg_func="count")
        for row in result.rows:
            assert row["revenue"] >= 1

    def test_groupby_multiple_dimensions(self) -> None:
        svc = AggregationService()
        result = svc.groupby("sales", group_by=["region", "month"], metrics=["revenue"])
        assert len(result.rows) > 0
        # Each row should have both region and month
        for row in result.rows:
            assert "region" in row
            assert "month" in row

    def test_groupby_nonexistent_table(self) -> None:
        svc = AggregationService()
        result = svc.groupby("nonexistent", group_by=["x"], metrics=["y"])
        assert result.rows == []

    def test_pivot_basic(self) -> None:
        svc = AggregationService()
        result = svc.pivot("sales", rows="region", cols="month", values="revenue")
        assert len(result.row_labels) > 0
        assert len(result.col_labels) > 0
        assert len(result.matrix) == len(result.row_labels)
        assert all(len(r) == len(result.col_labels) for r in result.matrix)
        assert "East" in result.row_labels
        assert "Jan" in result.col_labels

    def test_pivot_values_populated(self) -> None:
        svc = AggregationService()
        result = svc.pivot("sales", rows="region", cols="month", values="revenue")
        # Find East row, Jan column
        east_idx = result.row_labels.index("East")
        jan_idx = result.col_labels.index("Jan")
        assert result.matrix[east_idx][jan_idx] == 10000

    def test_pivot_missing_combination(self) -> None:
        svc = AggregationService()
        result = svc.pivot("sales", rows="region", cols="month", values="revenue")
        # All combinations in mock data exist, but missing should be 0
        for row in result.matrix:
            for val in row:
                assert val >= 0

    def test_timeseries_basic(self) -> None:
        svc = AggregationService()
        result = svc.timeseries("sales", time_col="month", value_col="revenue")
        assert len(result.points) > 0
        assert result.granularity == "month"
        # Points should be sorted by timestamp
        timestamps = [p.timestamp for p in result.points]
        assert timestamps == sorted(timestamps)

    def test_timeseries_sum(self) -> None:
        svc = AggregationService()
        result = svc.timeseries("sales", time_col="month", value_col="revenue", agg_func="sum")
        for point in result.points:
            assert point.value > 0

    def test_timeseries_avg(self) -> None:
        svc = AggregationService()
        result = svc.timeseries(
            "sales",
            time_col="month",
            value_col="revenue",
            agg_func="avg",
        )
        for point in result.points:
            assert point.value > 0

    def test_timeseries_nonexistent_table(self) -> None:
        svc = AggregationService()
        result = svc.timeseries("nonexistent", time_col="x", value_col="y")
        assert result.points == []

    def test_get_available_tables(self) -> None:
        svc = AggregationService()
        tables = svc.get_available_tables()
        assert "sales" in tables

    def test_get_aggregation_service_singleton(self) -> None:
        s1 = get_aggregation_service()
        s2 = get_aggregation_service()
        assert s1 is s2
