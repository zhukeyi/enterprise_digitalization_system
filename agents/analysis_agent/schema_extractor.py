"""Schema Extractor — database metadata extraction.

M3-T3: Extract table and column metadata for NL2SQL rule engine.

Two implementations:
- MockSchemaExtractor: In-memory mock with pre-defined tables for testing
- SchemaExtractor: Real implementation reading information_schema via async session
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Any

from agents.analysis_agent.models import ColumnSchema, DatabaseSchema, TableSchema

logger = logging.getLogger("fde.analysis.schema")


# ══════════════════════════════════════════════════════════════════
# Abstract Base
# ══════════════════════════════════════════════════════════════════


class BaseSchemaExtractor(ABC):
    """Abstract base for schema extraction strategies."""

    @abstractmethod
    async def extract(self, schema_id: str = "default") -> DatabaseSchema:
        """Extract the full database schema.

        Args:
            schema_id: The database schema identifier.

        Returns:
            DatabaseSchema with all tables and columns.
        """
        ...

    @abstractmethod
    async def get_table(self, table_name: str, schema_id: str = "default") -> TableSchema | None:
        """Get a single table's schema by name.

        Args:
            table_name: The table name to look up.
            schema_id: The database schema identifier.

        Returns:
            TableSchema if found, None otherwise.
        """
        ...

    @abstractmethod
    async def list_tables(self, schema_id: str = "default") -> list[str]:
        """List all table names in the schema.

        Args:
            schema_id: The database schema identifier.

        Returns:
            List of table names.
        """
        ...


# ══════════════════════════════════════════════════════════════════
# Mock Schema Extractor (in-memory, for testing)
# ══════════════════════════════════════════════════════════════════


def _build_mock_schema() -> DatabaseSchema:
    """Build the default mock database schema for testing."""
    tables: list[TableSchema] = [
        TableSchema(
            table_name="employees",
            description="Employee master records",
            row_count=1000,
            columns=[
                ColumnSchema(
                    name="id", data_type="integer", nullable=False, description="Primary key"
                ),
                ColumnSchema(
                    name="name",
                    data_type="varchar(100)",
                    nullable=False,
                    description="Employee name",
                ),
                ColumnSchema(
                    name="department",
                    data_type="varchar(50)",
                    nullable=True,
                    description="Department code",
                ),
                ColumnSchema(
                    name="salary",
                    data_type="numeric(12,2)",
                    nullable=True,
                    description="Annual salary",
                ),
                ColumnSchema(
                    name="hire_date", data_type="date", nullable=False, description="Hire date"
                ),
                ColumnSchema(
                    name="status",
                    data_type="varchar(20)",
                    nullable=False,
                    description="Employment status",
                ),
            ],
        ),
        TableSchema(
            table_name="departments",
            description="Department master records",
            row_count=50,
            columns=[
                ColumnSchema(
                    name="id", data_type="integer", nullable=False, description="Primary key"
                ),
                ColumnSchema(
                    name="name",
                    data_type="varchar(100)",
                    nullable=False,
                    description="Department name",
                ),
                ColumnSchema(
                    name="budget",
                    data_type="numeric(15,2)",
                    nullable=True,
                    description="Annual budget",
                ),
                ColumnSchema(
                    name="manager_id",
                    data_type="integer",
                    nullable=True,
                    description="Manager employee ID",
                ),
            ],
        ),
        TableSchema(
            table_name="sales",
            description="Sales transaction records",
            row_count=50000,
            columns=[
                ColumnSchema(
                    name="id", data_type="integer", nullable=False, description="Primary key"
                ),
                ColumnSchema(
                    name="employee_id",
                    data_type="integer",
                    nullable=False,
                    description="Salesperson ID",
                ),
                ColumnSchema(
                    name="amount",
                    data_type="numeric(12,2)",
                    nullable=False,
                    description="Sale amount",
                ),
                ColumnSchema(
                    name="sale_date",
                    data_type="timestamp",
                    nullable=False,
                    description="Transaction date",
                ),
                ColumnSchema(
                    name="product",
                    data_type="varchar(100)",
                    nullable=True,
                    description="Product name",
                ),
                ColumnSchema(
                    name="region",
                    data_type="varchar(50)",
                    nullable=True,
                    description="Sales region",
                ),
            ],
        ),
        TableSchema(
            table_name="products",
            description="Product catalog",
            row_count=500,
            columns=[
                ColumnSchema(
                    name="id", data_type="integer", nullable=False, description="Primary key"
                ),
                ColumnSchema(
                    name="name",
                    data_type="varchar(200)",
                    nullable=False,
                    description="Product name",
                ),
                ColumnSchema(
                    name="category",
                    data_type="varchar(50)",
                    nullable=True,
                    description="Product category",
                ),
                ColumnSchema(
                    name="price",
                    data_type="numeric(10,2)",
                    nullable=False,
                    description="Unit price",
                ),
                ColumnSchema(
                    name="stock", data_type="integer", nullable=False, description="Stock quantity"
                ),
            ],
        ),
    ]
    return DatabaseSchema(schema_id="default", tables=tables)


class MockSchemaExtractor(BaseSchemaExtractor):
    """In-memory schema extractor with pre-defined tables.

    Provides a realistic mock schema for testing NL2SQL without a real database.
    The mock schema includes employees, departments, sales, and products tables.
    """

    def __init__(self) -> None:
        self._schema = _build_mock_schema()

    async def extract(self, schema_id: str = "default") -> DatabaseSchema:
        """Return the full mock schema."""
        logger.debug("MockSchemaExtractor: extract() called (schema_id=%s)", schema_id)
        return self._schema

    async def get_table(self, table_name: str, schema_id: str = "default") -> TableSchema | None:
        """Look up a single table by name (case-insensitive)."""
        for table in self._schema.tables:
            if table.table_name.lower() == table_name.lower():
                return table
        return None

    async def list_tables(self, schema_id: str = "default") -> list[str]:
        """Return all table names."""
        return [t.table_name for t in self._schema.tables]


# ══════════════════════════════════════════════════════════════════
# Real Schema Extractor (information_schema via async session)
# ══════════════════════════════════════════════════════════════════


class SchemaExtractor(BaseSchemaExtractor):
    """Real schema extractor reading information_schema from the database.

    Uses an async session factory (compatible with governance_agent's
    database session) to query table and column metadata.

    Args:
        session_factory: A callable that returns an async context manager
            yielding a session with an `execute(text(sql))` method.
    """

    def __init__(self, session_factory: Any | None = None) -> None:
        self._session_factory = session_factory

    async def extract(self, schema_id: str = "default") -> DatabaseSchema:
        """Extract full schema from information_schema."""
        if self._session_factory is None:
            raise RuntimeError("No session factory configured for SchemaExtractor")

        sql = """
            SELECT
                t.table_name,
                t.table_type,
                c.column_name,
                c.data_type,
                c.is_nullable,
                pgd.description AS column_description
            FROM information_schema.tables t
            JOIN information_schema.columns c
                ON t.table_name = c.table_name
            LEFT JOIN pg_catalog.pg_statio_all_tables psat
                ON psat.relname = t.table_name
            LEFT JOIN pg_catalog.pg_description pgd
                ON pgd.objoid = psat.relid
                AND pgd.objsubid = c.ordinal_position
            WHERE t.table_schema = 'public'
            ORDER BY t.table_name, c.ordinal_position
        """

        rows = await self._execute_query(sql)
        tables_map: dict[str, list[ColumnSchema]] = {}

        for row in rows:
            table_name = row["table_name"]
            column = ColumnSchema(
                name=row["column_name"],
                data_type=row["data_type"],
                nullable=row["is_nullable"] == "YES",
                description=row.get("column_description") or "",
            )
            if table_name not in tables_map:
                tables_map[table_name] = []
            tables_map[table_name].append(column)

        tables = [TableSchema(table_name=name, columns=cols) for name, cols in tables_map.items()]
        return DatabaseSchema(schema_id=schema_id, tables=tables)

    async def get_table(self, table_name: str, schema_id: str = "default") -> TableSchema | None:
        """Get a single table schema by name from the database."""
        schema = await self.extract(schema_id)
        for table in schema.tables:
            if table.table_name.lower() == table_name.lower():
                return table
        return None

    async def list_tables(self, schema_id: str = "default") -> list[str]:
        """List all table names from the database."""
        schema = await self.extract(schema_id)
        return [t.table_name for t in schema.tables]

    async def _execute_query(self, sql: str) -> list[dict[str, Any]]:
        """Execute a read-only query using the session factory."""
        from sqlalchemy import (  # type: ignore[import-not-found]
            text,
        )

        assert self._session_factory is not None
        async with self._session_factory() as session:
            result = await session.execute(text(sql))
            rows = result.fetchall()
            return [dict(row._mapping) for row in rows]


# ══════════════════════════════════════════════════════════════════
# Module-level singleton (mock by default)
# ══════════════════════════════════════════════════════════════════

_extractor: BaseSchemaExtractor | None = None


def get_extractor() -> BaseSchemaExtractor:
    """Get the singleton schema extractor (MockSchemaExtractor by default)."""
    global _extractor
    if _extractor is None:
        _extractor = MockSchemaExtractor()
    return _extractor


def set_extractor(extractor: BaseSchemaExtractor) -> None:
    """Override the singleton extractor (e.g., for real DB mode)."""
    global _extractor
    _extractor = extractor


def reset_extractor() -> None:
    """Reset to default mock extractor."""
    global _extractor
    _extractor = None
