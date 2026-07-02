"""Analysis Agent — NL2SQL engine, dashboard, drill-down, and correlation analysis.

M3-T3: Natural language to SQL conversion, safety validation, and read-only execution.
M3-T4: Dashboard configuration, drill-down analysis, cross-table correlation, aggregation.

Modules:
- models: Pydantic data models (NL2SQLRequest, SQLResult, ChartData, etc.)
- dashboard_models: Dashboard config, Widget, Filter, DrillDown, Correlation models
- sql_safety: SQL safety validator (blocks DML/DDL, detects injection)
- schema_extractor: Database schema metadata extraction (Mock + real)
- nl2sql: Rule-based NL->SQL engine with LLM fallback
- executor: Read-only query execution (Mock in-memory + real DB session)
- drill_down: Hierarchical drill-down analysis engine
- correlation: Cross-table statistical correlation (Pearson/Spearman)
- aggregation: GroupBy, Pivot, TimeSeries aggregation service
- integration: ToolRegistry registration (4 tools)
"""

from agents.analysis_agent.aggregation import (
    AggregationResult,
    AggregationService,
    PivotResult,
    TimeSeriesPoint,
    TimeSeriesResult,
    get_aggregation_service,
)
from agents.analysis_agent.correlation import (
    CorrelationEngine,
    get_correlation_engine,
)
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
from agents.analysis_agent.drill_down import (
    DrillDownEngine,
    get_drill_down_engine,
)
from agents.analysis_agent.executor import (
    BaseExecutor,
    MockExecutor,
    QueryExecutor,
    get_executor,
    reset_executor,
    set_executor,
)
from agents.analysis_agent.integration import register_analysis_tools
from agents.analysis_agent.models import (
    ChartData,
    ChartDataset,
    ColumnSchema,
    DatabaseSchema,
    NL2SQLRequest,
    NL2SQLResult,
    SQLResult,
    TableSchema,
)
from agents.analysis_agent.nl2sql import (
    NL2SQLEngine,
    get_engine,
    reset_engine,
)
from agents.analysis_agent.schema_extractor import (
    BaseSchemaExtractor,
    MockSchemaExtractor,
    SchemaExtractor,
    get_extractor,
    reset_extractor,
    set_extractor,
)
from agents.analysis_agent.sql_safety import (
    SafetyCheckResult,
    SQLSafetyValidator,
    get_validator,
    validate_sql,
)

__all__ = [
    "AggregationResult",
    "AggregationService",
    "BaseExecutor",
    "BaseSchemaExtractor",
    "ChartData",
    "ChartDataset",
    "ColumnSchema",
    "CorrelationEngine",
    "CorrelationResult",
    "DashboardConfig",
    "DashboardFilter",
    "DatabaseSchema",
    "DrillDownEngine",
    "DrillDownLevel",
    "DrillDownResult",
    "FilterOperator",
    "MockExecutor",
    "MockSchemaExtractor",
    "NL2SQLEngine",
    "NL2SQLRequest",
    "NL2SQLResult",
    "PivotResult",
    "QueryExecutor",
    "SQLResult",
    "SQLSafetyValidator",
    "SafetyCheckResult",
    "SchemaExtractor",
    "TableSchema",
    "TimeSeriesPoint",
    "TimeSeriesResult",
    "Widget",
    "WidgetType",
    "get_aggregation_service",
    "get_correlation_engine",
    "get_drill_down_engine",
    "get_engine",
    "get_executor",
    "get_extractor",
    "get_validator",
    "register_analysis_tools",
    "reset_engine",
    "reset_executor",
    "reset_extractor",
    "set_executor",
    "set_extractor",
    "validate_sql",
]
