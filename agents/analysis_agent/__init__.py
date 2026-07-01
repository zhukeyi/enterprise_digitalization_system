"""Analysis Agent — NL2SQL engine and data query gateway.

M3-T3: Natural language to SQL conversion, safety validation, and read-only execution.

Modules:
- models: Pydantic data models (NL2SQLRequest, SQLResult, ChartData, etc.)
- sql_safety: SQL safety validator (blocks DML/DDL, detects injection)
- schema_extractor: Database schema metadata extraction (Mock + real)
- nl2sql: Rule-based NL→SQL engine with LLM fallback
- executor: Read-only query execution (Mock in-memory + real DB session)
- integration: ToolRegistry registration (4 tools)
"""

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
    "BaseExecutor",
    "BaseSchemaExtractor",
    "ChartData",
    "ChartDataset",
    "ColumnSchema",
    "DatabaseSchema",
    "MockExecutor",
    "MockSchemaExtractor",
    "NL2SQLEngine",
    "NL2SQLRequest",
    "NL2SQLResult",
    "QueryExecutor",
    "SQLResult",
    "SQLSafetyValidator",
    "SafetyCheckResult",
    "SchemaExtractor",
    "TableSchema",
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
