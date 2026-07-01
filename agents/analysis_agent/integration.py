"""Analysis Agent — ToolRegistry integration.

M3-T3: Register 4 analysis tools to the orchestrator ToolRegistry.

Tools registered:
- nl2sql: Natural language to SQL conversion and execution
- sql_execute: Execute a pre-validated SQL statement (read-only)
- schema_list: List database tables and columns
- query_chart_data: Query data and return chart-formatted results
"""

from __future__ import annotations

import logging
from typing import Any

from agents.analysis_agent.executor import get_executor
from agents.analysis_agent.models import (
    ChartData,
    ChartDataset,
    NL2SQLRequest,
    NL2SQLResult,
    SQLResult,
)
from agents.analysis_agent.nl2sql import get_engine
from agents.analysis_agent.schema_extractor import get_extractor
from agents.analysis_agent.sql_safety import validate_sql
from agents.orchestrator.tools.registry import ToolDefinition, ToolRegistry

logger = logging.getLogger("fde.analysis.integration")


# ══════════════════════════════════════════════════════════════════
# Tool Handlers (async)
# ══════════════════════════════════════════════════════════════════


async def _nl2sql_handler(
    query: str = "",
    db_schema_id: str = "default",
    max_results: int = 100,
) -> dict[str, Any]:
    """Convert natural language to SQL and execute.

    Args:
        query: Natural language query (Chinese or English).
        db_schema_id: Database schema identifier.
        max_results: Maximum rows to return.

    Returns:
        NL2SQLResult as dict with SQL, results, and safety status.
    """
    if not query.strip():
        return NL2SQLResult(
            success=False,
            error="query is required",
            safety_check_passed=False,
        ).model_dump()

    request = NL2SQLRequest(
        query=query,
        db_schema_id=db_schema_id,
        max_results=max_results,
    )

    # Step 1: Convert NL → SQL
    engine = get_engine()
    conversion = await engine.convert(request)

    if not conversion.matched:
        # LLM fallback — Mock mode returns prompt
        prompt = engine.build_llm_prompt(request)
        return NL2SQLResult(
            success=False,
            sql="",
            source="llm_fallback",
            error=f"Rule engine could not match query. LLM prompt: {prompt}",
            safety_check_passed=True,
        ).model_dump()

    # Step 2: Safety validation
    safety = validate_sql(conversion.sql)
    if not safety.is_safe:
        return NL2SQLResult(
            success=False,
            sql=conversion.sql,
            source=conversion.source,
            error=f"SQL safety check failed: {'; '.join(safety.violations)}",
            safety_check_passed=False,
        ).model_dump()

    # Step 3: Execute
    executor = get_executor()
    result = await executor.execute(
        conversion.sql,
        max_results=max_results,
    )

    return NL2SQLResult(
        success=True,
        sql=conversion.sql,
        source=conversion.source,
        result=result,
        safety_check_passed=True,
    ).model_dump()


async def _sql_execute_handler(
    sql: str = "",
    params: dict[str, Any] | None = None,
    max_results: int = 100,
) -> dict[str, Any]:
    """Execute a pre-validated SQL statement (read-only enforced).

    Args:
        sql: The SQL statement to execute.
        params: Optional parameters for parameterized queries.
        max_results: Maximum rows to return.

    Returns:
        SQLResult as dict with rows, columns, and execution metadata.
    """
    if not sql.strip():
        return SQLResult(
            sql="",
            rows=[],
            row_count=0,
            columns=[],
            execution_time_ms=0.0,
            source="rule_engine",
        ).model_dump()

    # Safety validation
    safety = validate_sql(sql)
    if not safety.is_safe:
        return SQLResult(
            sql=sql,
            rows=[],
            row_count=0,
            columns=[],
            execution_time_ms=0.0,
            source="rule_engine",
        ).model_dump()

    executor = get_executor()
    result = await executor.execute(sql, params, max_results)
    return result.model_dump()


async def _schema_list_handler(
    db_schema_id: str = "default",
) -> dict[str, Any]:
    """List database tables and their columns.

    Args:
        db_schema_id: Database schema identifier.

    Returns:
        DatabaseSchema as dict with table and column metadata.
    """
    extractor = get_extractor()
    schema = await extractor.extract(db_schema_id)
    return schema.model_dump()


async def _query_chart_data_handler(
    query: str = "",
    chart_type: str = "bar",
    max_results: int = 100,
) -> dict[str, Any]:
    """Query data and return chart-formatted results.

    Args:
        query: Natural language query.
        chart_type: Chart type: 'line', 'bar', 'pie', or 'scatter'.
        max_results: Maximum rows to return.

    Returns:
        ChartData as dict with labels, datasets, and chart metadata.
    """
    if not query.strip():
        return ChartData(
            chart_type=chart_type,
            labels=[],
            datasets=[],
            title="No data — empty query",
        ).model_dump()

    valid_chart_types = {"line", "bar", "pie", "scatter"}
    if chart_type not in valid_chart_types:
        chart_type = "bar"

    # Use the NL2SQL pipeline to get data
    request = NL2SQLRequest(query=query, max_results=max_results)
    engine = get_engine()
    conversion = await engine.convert(request)

    if not conversion.matched:
        return ChartData(
            chart_type=chart_type,
            labels=[],
            datasets=[],
            title="No data — query could not be converted",
        ).model_dump()

    # Safety check
    safety = validate_sql(conversion.sql)
    if not safety.is_safe:
        return ChartData(
            chart_type=chart_type,
            labels=[],
            datasets=[],
            title="No data — SQL safety check failed",
        ).model_dump()

    # Execute
    executor = get_executor()
    result = await executor.execute(conversion.sql, max_results=max_results)

    # Convert to chart data
    chart = _rows_to_chart(result, chart_type, query)
    return chart.model_dump()


# ══════════════════════════════════════════════════════════════════
# Chart Data Formatter
# ══════════════════════════════════════════════════════════════════


def _rows_to_chart(result: SQLResult, chart_type: str, title: str) -> ChartData:
    """Convert SQLResult rows to ChartData format.

    Uses the first column as labels (X-axis) and remaining columns as datasets.
    """
    if not result.rows or not result.columns:
        return ChartData(
            chart_type=chart_type,
            labels=[],
            datasets=[],
            title=title,
        )

    # First column = labels, rest = data series
    label_col = result.columns[0]
    data_cols = result.columns[1:] if len(result.columns) > 1 else result.columns

    labels = [str(row.get(label_col, "")) for row in result.rows]

    datasets: list[ChartDataset] = []
    colors = ["#3498db", "#e74c3c", "#2ecc71", "#f39c12", "#9b59b6"]

    for i, col in enumerate(data_cols):
        data: list[float | int | None] = []
        for row in result.rows:
            val = row.get(col)
            if val is None:
                data.append(None)
            elif isinstance(val, int | float):
                data.append(val)
            else:
                try:
                    data.append(float(val))
                except (ValueError, TypeError):
                    data.append(None)

        datasets.append(
            ChartDataset(
                label=col,
                data=data,
                color=colors[i % len(colors)],
            )
        )

    return ChartData(
        chart_type=chart_type,
        labels=labels,
        datasets=datasets,
        title=title,
    )


# ══════════════════════════════════════════════════════════════════
# Registration Function
# ══════════════════════════════════════════════════════════════════


def register_analysis_tools(registry: ToolRegistry) -> None:
    """Register all analysis tools to the ToolRegistry.

    Args:
        registry: The orchestrator's ToolRegistry instance.
    """
    tools = [
        ToolDefinition(
            name="nl2sql",
            description="Convert natural language to SQL and execute a read-only query",
            worker="analysis",
            handler=_nl2sql_handler,
            parameters={
                "query": {
                    "type": "string",
                    "required": True,
                    "description": "Natural language query",
                },
                "db_schema_id": {"type": "string", "required": False, "default": "default"},
                "max_results": {"type": "integer", "required": False, "default": 100},
            },
            is_dangerous=False,
            category="data_query",
        ),
        ToolDefinition(
            name="sql_execute",
            description="Execute a pre-validated read-only SQL statement (safety checked)",
            worker="analysis",
            handler=_sql_execute_handler,
            parameters={
                "sql": {
                    "type": "string",
                    "required": True,
                    "description": "SQL statement to execute",
                },
                "params": {"type": "object", "required": False, "description": "Query parameters"},
                "max_results": {"type": "integer", "required": False, "default": 100},
            },
            is_dangerous=False,
            category="data_query",
        ),
        ToolDefinition(
            name="schema_list",
            description="List database tables and their column definitions",
            worker="analysis",
            handler=_schema_list_handler,
            parameters={
                "db_schema_id": {"type": "string", "required": False, "default": "default"},
            },
            is_dangerous=False,
            category="data_query",
        ),
        ToolDefinition(
            name="query_chart_data",
            description="Query data via NL2SQL and return chart-formatted results (line/bar/pie/scatter)",
            worker="analysis",
            handler=_query_chart_data_handler,
            parameters={
                "query": {
                    "type": "string",
                    "required": True,
                    "description": "Natural language query",
                },
                "chart_type": {"type": "string", "required": False, "default": "bar"},
                "max_results": {"type": "integer", "required": False, "default": 100},
            },
            is_dangerous=False,
            category="data_query",
        ),
    ]

    for tool in tools:
        registry.register(tool)

    logger.info("Registered %d analysis tools", len(tools))
