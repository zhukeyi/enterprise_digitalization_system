"""Analysis Agent — Pydantic data models.

M3-T3: NL2SQL engine data models.

Models:
- NL2SQLRequest: Natural language query input
- ColumnSchema / TableSchema / DatabaseSchema: Schema metadata
- SQLResult: Query execution result
- ChartDataset / ChartData: Chart-formatted data
- NL2SQLResult: Full NL2SQL pipeline result
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

# ══════════════════════════════════════════════════════════════════
# Request Models
# ══════════════════════════════════════════════════════════════════


class NL2SQLRequest(BaseModel):
    """Natural language to SQL conversion request."""

    query: str = Field(..., description="Natural language query")
    db_schema_id: str = Field(default="default", description="Database schema identifier")
    max_results: int = Field(default=100, ge=1, le=10000, description="Maximum rows to return")


# ══════════════════════════════════════════════════════════════════
# Schema Metadata Models
# ══════════════════════════════════════════════════════════════════


class ColumnSchema(BaseModel):
    """Database column metadata."""

    name: str
    data_type: str
    nullable: bool = True
    description: str = ""


class TableSchema(BaseModel):
    """Database table metadata."""

    table_name: str
    columns: list[ColumnSchema]
    row_count: int | None = None
    description: str = ""


class DatabaseSchema(BaseModel):
    """Full database schema with all tables."""

    schema_id: str
    tables: list[TableSchema]


# ══════════════════════════════════════════════════════════════════
# Query Result Models
# ══════════════════════════════════════════════════════════════════


class SQLResult(BaseModel):
    """SQL query execution result."""

    sql: str = Field(..., description="The SQL statement that was executed")
    rows: list[dict[str, Any]] = Field(default_factory=list, description="Query result rows")
    row_count: int = Field(default=0, description="Number of rows returned")
    columns: list[str] = Field(default_factory=list, description="Column names")
    execution_time_ms: float = Field(default=0.0, description="Execution time in milliseconds")
    source: str = Field(
        default="rule_engine",
        description="SQL generation source: 'rule_engine' or 'llm_fallback'",
    )
    truncated: bool = Field(default=False, description="Whether results were truncated")


class ChartDataset(BaseModel):
    """A single dataset within a chart."""

    label: str
    data: list[float | int | None]
    color: str | None = None


class ChartData(BaseModel):
    """Chart-formatted query result data."""

    chart_type: str = Field(..., description="Chart type: 'line', 'bar', 'pie', or 'scatter'")
    labels: list[str] = Field(default_factory=list, description="X-axis labels")
    datasets: list[ChartDataset] = Field(default_factory=list, description="Data series")
    title: str = ""


# ══════════════════════════════════════════════════════════════════
# NL2SQL Pipeline Result
# ══════════════════════════════════════════════════════════════════


class NL2SQLResult(BaseModel):
    """Complete NL2SQL conversion and execution result."""

    success: bool
    sql: str = ""
    source: str = Field(
        default="rule_engine",
        description="SQL generation source: 'rule_engine' or 'llm_fallback'",
    )
    result: SQLResult | None = None
    error: str | None = None
    safety_check_passed: bool = True
