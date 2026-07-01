"""Query Executor — SQL execution engine.

M3-T3: Read-only SQL execution with Mock and real database support.

Two implementations:
- MockExecutor: In-memory data store for testing (no real DB needed)
- QueryExecutor: Real execution using governance_agent's async DB session

Both enforce read-only mode via SQL safety validation before execution.
"""

from __future__ import annotations

import logging
import time
from abc import ABC, abstractmethod
from typing import Any

from agents.analysis_agent.models import SQLResult
from agents.analysis_agent.sql_safety import validate_sql

logger = logging.getLogger("fde.analysis.executor")


# ══════════════════════════════════════════════════════════════════
# Abstract Base
# ══════════════════════════════════════════════════════════════════


class BaseExecutor(ABC):
    """Abstract base for SQL query execution."""

    @abstractmethod
    async def execute(
        self,
        sql: str,
        params: dict[str, Any] | None = None,
        max_results: int = 100,
    ) -> SQLResult:
        """Execute a read-only SQL query.

        Args:
            sql: The SQL statement to execute (must pass safety validation).
            params: Optional parameter dict for parameterized queries.
            max_results: Maximum number of rows to return.

        Returns:
            SQLResult with query results and metadata.
        """
        ...


# ══════════════════════════════════════════════════════════════════
# Mock Executor (in-memory, for testing)
# ══════════════════════════════════════════════════════════════════


def _build_mock_data() -> dict[str, list[dict[str, Any]]]:
    """Build mock data for the in-memory executor."""
    return {
        "employees": [
            {
                "id": 1,
                "name": "Zhang Wei",
                "department": "eng",
                "salary": 250000,
                "hire_date": "2019-03-15",
                "status": "active",
            },
            {
                "id": 2,
                "name": "Li Na",
                "department": "eng",
                "salary": 180000,
                "hire_date": "2020-07-01",
                "status": "active",
            },
            {
                "id": 3,
                "name": "Wang Fang",
                "department": "eng",
                "salary": 120000,
                "hire_date": "2024-01-15",
                "status": "probation",
            },
            {
                "id": 4,
                "name": "Chen Jie",
                "department": "sales",
                "salary": 200000,
                "hire_date": "2018-11-20",
                "status": "active",
            },
            {
                "id": 5,
                "name": "Liu Yang",
                "department": "sales",
                "salary": 300000,
                "hire_date": "2016-05-10",
                "status": "active",
            },
            {
                "id": 6,
                "name": "Zhao Min",
                "department": "sales",
                "salary": 150000,
                "hire_date": "2022-09-01",
                "status": "active",
            },
            {
                "id": 7,
                "name": "Sun Lei",
                "department": "eng",
                "salary": 90000,
                "hire_date": "2024-03-01",
                "status": "active",
            },
            {
                "id": 8,
                "name": "Zhou Yu",
                "department": "hr",
                "salary": 160000,
                "hire_date": "2019-08-15",
                "status": "active",
            },
            {
                "id": 9,
                "name": "Wu Xin",
                "department": "hr",
                "salary": 140000,
                "hire_date": "2021-02-01",
                "status": "active",
            },
            {
                "id": 10,
                "name": "Zheng He",
                "department": "hr",
                "salary": 500000,
                "hire_date": "2015-01-01",
                "status": "active",
            },
        ],
        "departments": [
            {"id": 1, "name": "Engineering", "budget": 2000000, "manager_id": 1},
            {"id": 2, "name": "Sales", "budget": 3000000, "manager_id": 5},
            {"id": 3, "name": "HR", "budget": 1000000, "manager_id": 10},
        ],
        "sales": [
            {
                "id": 1,
                "employee_id": 4,
                "amount": 50000,
                "sale_date": "2024-01-15",
                "product": "Widget A",
                "region": "north",
            },
            {
                "id": 2,
                "employee_id": 4,
                "amount": 75000,
                "sale_date": "2024-02-20",
                "product": "Widget B",
                "region": "north",
            },
            {
                "id": 3,
                "employee_id": 5,
                "amount": 1200000,
                "sale_date": "2024-03-10",
                "product": "Gadget X",
                "region": "south",
            },
            {
                "id": 4,
                "employee_id": 5,
                "amount": 800000,
                "sale_date": "2024-04-05",
                "product": "Gadget Y",
                "region": "south",
            },
            {
                "id": 5,
                "employee_id": 6,
                "amount": 300000,
                "sale_date": "2024-05-15",
                "product": "Widget A",
                "region": "east",
            },
            {
                "id": 6,
                "employee_id": 6,
                "amount": 450000,
                "sale_date": "2024-06-20",
                "product": "Widget B",
                "region": "east",
            },
        ],
        "products": [
            {"id": 1, "name": "Widget A", "category": "widgets", "price": 50.00, "stock": 1000},
            {"id": 2, "name": "Widget B", "category": "widgets", "price": 75.00, "stock": 500},
            {"id": 3, "name": "Gadget X", "category": "gadgets", "price": 1200.00, "stock": 200},
            {"id": 4, "name": "Gadget Y", "category": "gadgets", "price": 800.00, "stock": 150},
        ],
    }


class MockExecutor(BaseExecutor):
    """In-memory query executor for testing without a real database.

    Simulates basic SELECT queries against pre-loaded mock data.
    Supports: column selection, WHERE conditions (>, <, =, !=, >=, <=),
    ORDER BY, LIMIT, and COUNT(*) aggregation.
    """

    def __init__(self) -> None:
        self._data = _build_mock_data()

    async def execute(
        self,
        sql: str,
        params: dict[str, Any] | None = None,
        max_results: int = 100,
    ) -> SQLResult:
        """Execute a mock SELECT query against in-memory data."""
        start_time = time.monotonic()

        # Safety validation first
        safety = validate_sql(sql)
        if not safety.is_safe:
            return SQLResult(
                sql=sql,
                rows=[],
                row_count=0,
                columns=[],
                execution_time_ms=0.0,
                source="rule_engine",
            )

        sql_upper = sql.strip().upper()
        rows: list[dict[str, Any]] = []
        columns: list[str] = []

        try:
            # Parse and execute the query
            rows, columns = self._execute_select(sql, sql_upper, max_results)
        except Exception as e:
            logger.error("MockExecutor error: %s", e)
            rows = []
            columns = []

        elapsed_ms = (time.monotonic() - start_time) * 1000

        truncated = len(rows) > max_results
        if truncated:
            rows = rows[:max_results]

        return SQLResult(
            sql=sql,
            rows=rows,
            row_count=len(rows),
            columns=columns,
            execution_time_ms=round(elapsed_ms, 2),
            source="rule_engine",
            truncated=truncated,
        )

    def _execute_select(
        self,
        sql: str,
        sql_upper: str,
        max_results: int,
    ) -> tuple[list[dict[str, Any]], list[str]]:
        """Parse and execute a SELECT against mock data."""
        import re

        # Detect table
        table_name = ""
        for tname in self._data:
            if tname.upper() in sql_upper:
                table_name = tname
                break

        if not table_name:
            return [], []

        table_data = self._data[table_name]
        if not table_data:
            return [], []

        # All available columns from the first row
        all_columns = list(table_data[0].keys())

        # COUNT(*) aggregation
        if "COUNT(*)" in sql_upper or "COUNT (" in sql_upper:
            count = len(table_data)
            return ([{"count": count}], ["count"])

        # Detect selected columns
        # Pattern: SELECT col1, col2 FROM ... or SELECT * FROM ...
        select_match = re.match(
            r"SELECT\s+(.+?)\s+FROM",
            sql,
            re.IGNORECASE,
        )
        if select_match:
            select_part = select_match.group(1).strip()
            if select_part == "*":
                selected_columns = all_columns
            else:
                selected_columns = [
                    c.strip()
                    for c in select_part.split(",")
                    if c.strip() and c.strip() in all_columns
                ]
                if not selected_columns:
                    selected_columns = all_columns
        else:
            selected_columns = all_columns

        # Parse WHERE clause
        where_match = re.search(r"WHERE\s+(.+?)(?:\s+ORDER BY|\s+LIMIT|$)", sql, re.IGNORECASE)
        filtered_data = table_data
        if where_match:
            where_clause = where_match.group(1).strip()
            filtered_data = self._apply_where(table_data, where_clause)

        # Parse ORDER BY
        order_match = re.search(r"ORDER\s+BY\s+(\w+)\s*(ASC|DESC)?", sql, re.IGNORECASE)
        if order_match:
            order_col = order_match.group(1)
            direction = (order_match.group(2) or "ASC").upper()
            if order_col in all_columns:
                filtered_data = sorted(
                    filtered_data,
                    key=lambda r: r.get(order_col, 0),
                    reverse=(direction == "DESC"),
                )

        # Parse LIMIT (only from SQL clause, not from max_results)
        limit_match = re.search(r"LIMIT\s+(\d+)", sql, re.IGNORECASE)
        sql_limit = int(limit_match.group(1)) if limit_match else len(filtered_data)

        # Project columns
        result_rows = [
            {col: row.get(col) for col in selected_columns} for row in filtered_data[:sql_limit]
        ]

        return result_rows, selected_columns

    def _apply_where(
        self,
        data: list[dict[str, Any]],
        where_clause: str,
    ) -> list[dict[str, Any]]:
        """Apply WHERE conditions to filter data."""
        import re

        # Split by AND
        conditions = re.split(r"\s+AND\s+", where_clause, flags=re.IGNORECASE)
        result = data

        for cond in conditions:
            cond = cond.strip()
            # Pattern: column OP value
            match = re.match(r"(\w+)\s*(>=|<=|!=|=|>|<)\s*(.+)", cond)
            if not match:
                continue

            col = match.group(1)
            op = match.group(2)
            val_str = match.group(3).strip().rstrip(";")

            # Parse value
            if val_str.startswith("'") and val_str.endswith("'"):
                val: Any = val_str[1:-1]
            else:
                try:
                    val = int(val_str)
                except ValueError:
                    try:
                        val = float(val_str)
                    except ValueError:
                        val = val_str

            result = [row for row in result if col in row and self._compare(row[col], op, val)]

        return result

    @staticmethod
    def _compare(actual: Any, op: str, expected: Any) -> bool:
        """Compare two values with the given operator."""
        try:
            if op == ">":
                return bool(actual > expected)
            if op == "<":
                return bool(actual < expected)
            if op == "=":
                return bool(actual == expected)
            if op == "!=":
                return bool(actual != expected)
            if op == ">=":
                return bool(actual >= expected)
            if op == "<=":
                return bool(actual <= expected)
        except TypeError:
            return False
        return False


# ══════════════════════════════════════════════════════════════════
# Real Query Executor (governance DB session, read-only)
# ══════════════════════════════════════════════════════════════════


class QueryExecutor(BaseExecutor):
    """Real SQL executor using governance_agent's async DB session.

    Enforces read-only mode by validating SQL through SQLSafetyValidator
    before execution. Uses parameterized queries to prevent injection.

    Args:
        session_factory: A callable that returns an async context manager
            yielding a session with an `execute(text(sql), params)` method.
    """

    def __init__(self, session_factory: Any | None = None) -> None:
        self._session_factory = session_factory

    async def execute(
        self,
        sql: str,
        params: dict[str, Any] | None = None,
        max_results: int = 100,
    ) -> SQLResult:
        """Execute a read-only SQL query against the real database."""
        start_time = time.monotonic()

        # Safety validation
        safety = validate_sql(sql)
        if not safety.is_safe:
            logger.warning("SQL safety check failed: %s", safety.violations)
            return SQLResult(
                sql=sql,
                rows=[],
                row_count=0,
                columns=[],
                execution_time_ms=0.0,
                source="rule_engine",
            )

        if self._session_factory is None:
            raise RuntimeError("No session factory configured for QueryExecutor")

        try:
            from sqlalchemy import text  # type: ignore[import-not-found]

            # Add LIMIT if not present (defense in depth)
            if "LIMIT" not in sql.upper():
                sql_with_limit = f"{sql.rstrip(';')} LIMIT {max_results}"
            else:
                sql_with_limit = sql

            async with self._session_factory() as session:
                result = await session.execute(text(sql_with_limit), params or {})
                rows_raw = result.fetchall()

                if rows_raw:
                    columns = list(rows_raw[0]._mapping.keys())
                    rows = [dict(row._mapping) for row in rows_raw]
                else:
                    columns = []
                    rows = []

        except Exception as e:
            logger.error("QueryExecutor error: %s", e)
            return SQLResult(
                sql=sql,
                rows=[],
                row_count=0,
                columns=[],
                execution_time_ms=0.0,
                source="rule_engine",
            )

        elapsed_ms = (time.monotonic() - start_time) * 1000
        truncated = len(rows) > max_results
        if truncated:
            rows = rows[:max_results]

        return SQLResult(
            sql=sql,
            rows=rows,
            row_count=len(rows),
            columns=columns,
            execution_time_ms=round(elapsed_ms, 2),
            source="rule_engine",
            truncated=truncated,
        )


# ══════════════════════════════════════════════════════════════════
# Module-level singleton (mock by default)
# ══════════════════════════════════════════════════════════════════

_executor: BaseExecutor | None = None


def get_executor() -> BaseExecutor:
    """Get the singleton executor (MockExecutor by default)."""
    global _executor
    if _executor is None:
        _executor = MockExecutor()
    return _executor


def set_executor(executor: BaseExecutor) -> None:
    """Override the singleton executor (e.g., for real DB mode)."""
    global _executor
    _executor = executor


def reset_executor() -> None:
    """Reset to default mock executor."""
    global _executor
    _executor = None
