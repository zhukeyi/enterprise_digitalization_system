"""Analysis Agent — comprehensive test suite.

M3-T3: 35+ tests covering all modules:
- models: Pydantic model validation and defaults
- sql_safety: SQL injection prevention and read-only enforcement
- schema_extractor: Mock schema metadata extraction
- nl2sql: Rule engine keyword mapping and SQL generation
- executor: MockExecutor in-memory query execution
- integration: Tool registration and dispatch
"""

from __future__ import annotations

import asyncio
import os
from typing import Any
from unittest.mock import patch

import pytest

from agents.analysis_agent.executor import (
    MockExecutor,
    get_executor,
    reset_executor,
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
    ConversionResult,
    NL2SQLEngine,
    _extract_sql,
    get_engine,
    reset_engine,
)
from agents.analysis_agent.schema_extractor import (
    MockSchemaExtractor,
    get_extractor,
    reset_extractor,
)
from agents.analysis_agent.sql_safety import (
    SQLSafetyValidator,
    validate_sql,
)
from agents.analysis_agent.training_data import (
    EXAMPLE_QUERIES,
    build_ddl_context,
    build_example_context,
    get_schema_context,
)
from agents.orchestrator.tools.registry import ToolRegistry

# ══════════════════════════════════════════════════════════════════
# Helpers
# ══════════════════════════════════════════════════════════════════


def _run(coro: Any) -> Any:
    """Run an async coroutine synchronously, compatible with pytest-asyncio AUTO mode."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_closed():
            raise RuntimeError("loop closed")
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    return loop.run_until_complete(coro)


@pytest.fixture(autouse=True)
def reset_singletons():
    """Reset all module singletons after each test."""
    yield
    reset_engine()
    reset_executor()
    reset_extractor()


# ══════════════════════════════════════════════════════════════════
# Test: Models
# ══════════════════════════════════════════════════════════════════


class TestModels:
    """Test Pydantic model validation and defaults."""

    def test_nl2sql_request_defaults(self):
        req = NL2SQLRequest(query="查询所有员工")
        assert req.query == "查询所有员工"
        assert req.db_schema_id == "default"
        assert req.max_results == 100

    def test_nl2sql_request_max_results_bounds(self):
        req = NL2SQLRequest(query="test", max_results=5000)
        assert req.max_results == 5000

    def test_column_schema_defaults(self):
        col = ColumnSchema(name="id", data_type="integer")
        assert col.nullable is True
        assert col.description == ""

    def test_table_schema_defaults(self):
        table = TableSchema(table_name="users", columns=[])
        assert table.row_count is None
        assert table.description == ""

    def test_database_schema(self):
        schema = DatabaseSchema(
            schema_id="test",
            tables=[TableSchema(table_name="t1", columns=[])],
        )
        assert schema.schema_id == "test"
        assert len(schema.tables) == 1

    def test_sql_result_defaults(self):
        result = SQLResult(sql="SELECT 1")
        assert result.rows == []
        assert result.row_count == 0
        assert result.columns == []
        assert result.execution_time_ms == 0.0
        assert result.source == "rule_engine"
        assert result.truncated is False

    def test_chart_dataset(self):
        ds = ChartDataset(label="sales", data=[100, 200, None])
        assert ds.color is None
        assert len(ds.data) == 3

    def test_chart_data(self):
        chart = ChartData(
            chart_type="bar",
            labels=["Q1", "Q2"],
            datasets=[ChartDataset(label="revenue", data=[100, 200])],
            title="Quarterly Revenue",
        )
        assert chart.chart_type == "bar"
        assert len(chart.labels) == 2
        assert len(chart.datasets) == 1

    def test_nl2sql_result_defaults(self):
        result = NL2SQLResult(success=True, sql="SELECT 1")
        assert result.source == "rule_engine"
        assert result.result is None
        assert result.error is None
        assert result.safety_check_passed is True


# ══════════════════════════════════════════════════════════════════
# Test: SQL Safety
# ══════════════════════════════════════════════════════════════════


class TestSQLSafety:
    """Test SQL safety validator."""

    def test_safe_select(self):
        result = validate_sql("SELECT * FROM employees")
        assert result.is_safe is True
        assert len(result.violations) == 0

    def test_safe_select_with_where(self):
        result = validate_sql("SELECT name, salary FROM employees WHERE salary > 100000")
        assert result.is_safe is True

    def test_safe_with_cte(self):
        result = validate_sql(
            "WITH high_earners AS (SELECT * FROM employees WHERE salary > 200000) SELECT * FROM high_earners"
        )
        assert result.is_safe is True

    def test_block_delete(self):
        result = validate_sql("DELETE FROM employees WHERE id = 1")
        assert result.is_safe is False
        assert any("DELETE" in v for v in result.violations)

    def test_block_update(self):
        result = validate_sql("UPDATE employees SET salary = 0")
        assert result.is_safe is False
        assert any("UPDATE" in v for v in result.violations)

    def test_block_drop(self):
        result = validate_sql("DROP TABLE employees")
        assert result.is_safe is False
        assert any("DROP" in v for v in result.violations)

    def test_block_truncate(self):
        result = validate_sql("TRUNCATE TABLE employees")
        assert result.is_safe is False
        assert any("TRUNCATE" in v for v in result.violations)

    def test_block_insert(self):
        result = validate_sql("INSERT INTO employees VALUES (1, 'test')")
        assert result.is_safe is False
        assert any("INSERT" in v for v in result.violations)

    def test_block_alter(self):
        result = validate_sql("ALTER TABLE employees ADD COLUMN x int")
        assert result.is_safe is False
        assert any("ALTER" in v for v in result.violations)

    def test_block_create(self):
        result = validate_sql("CREATE TABLE hack (cmd text)")
        assert result.is_safe is False
        assert any("CREATE" in v for v in result.violations)

    def test_block_multiple_statements(self):
        result = validate_sql("SELECT * FROM employees; DROP TABLE employees")
        assert result.is_safe is False
        assert any(
            "semicolon" in v.lower() or "multi" in v.lower() or "DROP" in v
            for v in result.violations
        )

    def test_block_comment_injection(self):
        result = validate_sql("SELECT * FROM employees -- WHERE id = 1")
        assert result.is_safe is False
        assert any("comment" in v.lower() for v in result.violations)

    def test_block_block_comment_injection(self):
        result = validate_sql("SELECT * FROM employees /* comment */ WHERE 1=1")
        assert result.is_safe is False

    def test_block_pg_sleep(self):
        result = validate_sql("SELECT pg_sleep(100)")
        assert result.is_safe is False
        assert any("function" in v.lower() for v in result.violations)

    def test_column_name_with_keyword_not_blocked(self):
        # "updated_at" should not trigger "UPDATE" keyword detection
        result = validate_sql("SELECT updated_at FROM employees")
        assert result.is_safe is True

    def test_string_literal_with_keyword_not_blocked(self):
        # Keyword inside string literal should not trigger
        result = validate_sql("SELECT * FROM logs WHERE message = 'DELETE FROM users'")
        assert result.is_safe is True

    def test_empty_sql(self):
        result = validate_sql("")
        assert result.is_safe is False
        assert any("empty" in v.lower() for v in result.violations)

    def test_non_select_statement(self):
        result = validate_sql("EXPLAIN SELECT * FROM employees")
        assert result.is_safe is False

    def test_trailing_semicolon_allowed(self):
        result = validate_sql("SELECT * FROM employees;")
        assert result.is_safe is True

    def test_singleton_validator(self):
        v1 = SQLSafetyValidator()
        v2 = SQLSafetyValidator()
        # Both should behave identically (stateless)
        assert v1.validate("SELECT 1").is_safe == v2.validate("SELECT 1").is_safe


# ══════════════════════════════════════════════════════════════════
# Test: Schema Extractor
# ══════════════════════════════════════════════════════════════════


class TestSchemaExtractor:
    """Test MockSchemaExtractor."""

    def test_extract_returns_schema(self):
        extractor = MockSchemaExtractor()
        schema = _run(extractor.extract())
        assert isinstance(schema, DatabaseSchema)
        assert schema.schema_id == "default"
        assert len(schema.tables) == 4

    def test_list_tables(self):
        extractor = MockSchemaExtractor()
        tables = _run(extractor.list_tables())
        assert "employees" in tables
        assert "departments" in tables
        assert "sales" in tables
        assert "products" in tables

    def test_get_table_by_name(self):
        extractor = MockSchemaExtractor()
        table = _run(extractor.get_table("employees"))
        assert table is not None
        assert table.table_name == "employees"
        assert len(table.columns) == 6
        assert any(c.name == "salary" for c in table.columns)

    def test_get_table_case_insensitive(self):
        extractor = MockSchemaExtractor()
        table = _run(extractor.get_table("EMPLOYEES"))
        assert table is not None
        assert table.table_name == "employees"

    def test_get_table_not_found(self):
        extractor = MockSchemaExtractor()
        table = _run(extractor.get_table("nonexistent"))
        assert table is None

    def test_table_has_row_count(self):
        extractor = MockSchemaExtractor()
        table = _run(extractor.get_table("sales"))
        assert table is not None
        assert table.row_count == 50000

    def test_column_has_metadata(self):
        extractor = MockSchemaExtractor()
        table = _run(extractor.get_table("employees"))
        assert table is not None
        salary_col = next(c for c in table.columns if c.name == "salary")
        assert salary_col.data_type == "numeric(12,2)"
        assert "salary" in (salary_col.description.lower() if salary_col.description else "")

    def test_get_extractor_singleton(self):
        e1 = get_extractor()
        e2 = get_extractor()
        assert e1 is e2


# ══════════════════════════════════════════════════════════════════
# Test: NL2SQL Engine
# ══════════════════════════════════════════════════════════════════


class TestNL2SQLEngine:
    """Test the rule-based NL2SQL engine."""

    def test_convert_employee_query(self):
        engine = NL2SQLEngine()
        request = NL2SQLRequest(query="查询所有员工的姓名和薪资")
        result = _run(engine.convert(request))
        assert result.matched is True
        assert result.source == "rule_engine"
        assert "FROM employees" in result.sql
        assert "SELECT" in result.sql

    def test_convert_sales_query(self):
        engine = NL2SQLEngine()
        request = NL2SQLRequest(query="查询所有销售额大于100万的记录")
        result = _run(engine.convert(request))
        assert result.matched is True
        assert "FROM sales" in result.sql
        assert ">" in result.sql
        assert "1000000" in result.sql

    def test_convert_count_query(self):
        engine = NL2SQLEngine()
        request = NL2SQLRequest(query="统计员工总数")
        result = _run(engine.convert(request))
        assert result.matched is True
        assert "COUNT" in result.sql.upper()

    def test_convert_avg_query(self):
        engine = NL2SQLEngine()
        request = NL2SQLRequest(query="查询员工平均薪资")
        result = _run(engine.convert(request))
        assert result.matched is True
        assert "AVG" in result.sql.upper()
        assert "salary" in result.sql

    def test_convert_order_by(self):
        engine = NL2SQLEngine()
        request = NL2SQLRequest(query="查询员工薪资从高到低排序")
        result = _run(engine.convert(request))
        assert result.matched is True
        assert "ORDER BY" in result.sql.upper()
        assert "DESC" in result.sql.upper()

    def test_convert_limit(self):
        engine = NL2SQLEngine()
        request = NL2SQLRequest(query="查询前5条销售记录")
        result = _run(engine.convert(request))
        assert result.matched is True
        assert "LIMIT 5" in result.sql

    def test_convert_no_match_fallback(self):
        engine = NL2SQLEngine()
        request = NL2SQLRequest(query="今天天气怎么样")
        result = _run(engine.convert(request))
        assert result.matched is False
        assert result.source == "llm"

    def test_convert_empty_query(self):
        engine = NL2SQLEngine()
        request = NL2SQLRequest(query="")
        result = _run(engine.convert(request))
        assert result.matched is False

    def test_convert_department_query(self):
        engine = NL2SQLEngine()
        request = NL2SQLRequest(query="查询所有部门的预算")
        result = _run(engine.convert(request))
        assert result.matched is True
        assert "FROM departments" in result.sql
        assert "budget" in result.sql

    def test_convert_with_chinese_number_unit(self):
        engine = NL2SQLEngine()
        request = NL2SQLRequest(query="查询销售额大于50万的记录")
        result = _run(engine.convert(request))
        assert result.matched is True
        assert "500000" in result.sql

    def test_build_llm_prompt(self):
        engine = NL2SQLEngine()
        request = NL2SQLRequest(query="复杂分析查询")
        prompt = engine.build_llm_prompt(request)
        assert "复杂分析查询" in prompt
        assert "SELECT" in prompt

    def test_get_engine_singleton(self):
        e1 = get_engine()
        e2 = get_engine()
        assert e1 is e2


# ══════════════════════════════════════════════════════════════════
# Test: NL2SQL LLM Fallback (A-1)
# ══════════════════════════════════════════════════════════════════


class TestNL2SQLLLMFallback:
    """Test the LLM fallback channel (A-1) and SQL extraction helper."""

    def test_extract_sql_plain(self):
        assert _extract_sql("SELECT * FROM employees") == "SELECT * FROM employees"

    def test_extract_sql_code_fence(self):
        raw = "```sql\nSELECT * FROM employees\n```"
        assert _extract_sql(raw) == "SELECT * FROM employees"

    def test_extract_sql_code_fence_no_lang(self):
        raw = "```\nSELECT name FROM employees\n```"
        assert _extract_sql(raw) == "SELECT name FROM employees"

    def test_extract_sql_with_cte(self):
        raw = "WITH t AS (SELECT 1) SELECT * FROM t"
        assert _extract_sql(raw) == raw

    def test_extract_sql_empty(self):
        assert _extract_sql("") == ""
        assert _extract_sql("   ") == ""

    def test_extract_sql_non_sql(self):
        assert _extract_sql("I cannot answer that") == ""

    def test_convert_with_llm_not_configured(self):
        """When LLM env vars are unset, convert_with_llm returns matched=False."""
        engine = NL2SQLEngine()
        request = NL2SQLRequest(query="今天天气怎么样")
        result = _run(engine.convert_with_llm(request))
        assert result.matched is False
        assert result.source == "llm"
        assert "not configured" in result.reason.lower()

    def test_build_llm_prompt_with_schema_context(self):
        engine = NL2SQLEngine()
        request = NL2SQLRequest(query="复杂分析查询")
        prompt = engine.build_llm_prompt(request, schema_context="CREATE TABLE t (id INT)")
        assert "复杂分析查询" in prompt
        assert "CREATE TABLE t" in prompt
        assert "Database Schema" in prompt

    def test_conversion_result_has_llm_error_field(self):
        result = ConversionResult(source="llm", matched=False, llm_error="boom")
        assert result.llm_error == "boom"
        assert result.source == "llm"


# ══════════════════════════════════════════════════════════════════
# Test: Training Data / Schema Context (A-2)
# ══════════════════════════════════════════════════════════════════


class TestTrainingData:
    """Test DDL + example SQL context building (A-2)."""

    def test_build_ddl_context(self):
        ddl = build_ddl_context()
        assert "CREATE TABLE employees" in ddl
        assert "CREATE TABLE sales" in ddl
        assert "CREATE TABLE departments" in ddl
        assert "CREATE TABLE products" in ddl

    def test_build_example_context_relevance(self):
        # A query about salary should surface salary-related examples
        ctx = build_example_context("薪资大于50000的员工")
        assert "salary" in ctx.lower()

    def test_build_example_context_empty_query(self):
        ctx = build_example_context("")
        assert ctx  # non-empty default examples
        assert "SELECT" in ctx

    def test_build_example_context_max_examples(self):
        ctx = build_example_context("员工", max_examples=2)
        # Each example produces a "-- <nl>" comment line
        comment_lines = [ln for ln in ctx.splitlines() if ln.startswith("-- ")]
        assert len(comment_lines) <= 2

    def test_get_schema_context_full(self):
        ctx = _run(get_schema_context("统计员工总数"))
        assert "CREATE TABLE" in ctx
        assert "Example Queries" in ctx

    def test_example_queries_all_select(self):
        # All training examples must be read-only SELECT statements
        for ex in EXAMPLE_QUERIES:
            assert ex.sql.upper().lstrip().startswith(("SELECT", "WITH"))


class TestTrainingDataSemantic:
    """Qdrant semantic retrieval upgrade (A-2 continuation).

    Verifies opt-in gating, graceful fallback on failure, and that the
    semantic path is used when Qdrant + embedding are available.
    Heavy deps (sentence-transformers) are mocked so the suite runs in
    any environment.
    """

    def setup_method(self):
        import agents.analysis_agent.training_data as td

        self._td: Any = td
        self._prev_env = os.environ.pop("FDE_NL2SQL_USE_QDRANT", None)
        td._initialised = False
        td._qdrant_ready = False

    def teardown_method(self):
        self._td._initialised = False
        self._td._qdrant_ready = False
        if self._prev_env is not None:
            os.environ["FDE_NL2SQL_USE_QDRANT"] = self._prev_env
        else:
            os.environ.pop("FDE_NL2SQL_USE_QDRANT", None)

    def test_qdrant_disabled_by_default(self):
        assert self._td._qdrant_enabled() is False
        os.environ["FDE_NL2SQL_USE_QDRANT"] = "off"
        assert self._td._qdrant_enabled() is False

    @pytest.mark.parametrize("val", ["true", "1", "on", "yes", "auto"])
    def test_qdrant_enabled_variants(self, val):
        os.environ["FDE_NL2SQL_USE_QDRANT"] = val
        assert self._td._qdrant_enabled() is True

    def test_graceful_fallback_when_init_fails(self):
        os.environ["FDE_NL2SQL_USE_QDRANT"] = "true"

        def raiser(*_a, **_k):
            raise RuntimeError("embedding model unavailable")

        with patch("agents.ingestion_agent.store.get_embedding_model", side_effect=raiser):
            ctx = _run(get_schema_context("统计员工总数"))

        # Must still produce a valid keyword-based context
        assert "Example Queries" in ctx
        assert "SELECT" in ctx
        assert self._td._qdrant_ready is False

    def test_semantic_retrieval_used_when_ready(self):
        os.environ["FDE_NL2SQL_USE_QDRANT"] = "true"

        class _FakeResult:
            def __init__(self, vec):
                self.vector = vec

        class _FakeModel:
            async def embed(self, _text, **_kw):
                return _FakeResult([0.1, 0.2, 0.3, 0.4])

            async def embed_batch(self, texts, **_kw):
                return [_FakeResult([0.1 + 0.01 * i, 0.2, 0.3, 0.4]) for i in range(len(texts))]

        class _FakeStore:
            def __init__(self):
                self.created = []
                self.upserted: list[Any] = []
                self._exists = False
                self.hits: list[Any] = []

            def collection_exists(self, _name=None):
                return self._exists

            def create_collection(self, cfg):
                self.created.append(cfg)
                self._exists = True

            def upsert(self, points, collection=None):
                self.upserted.extend(points)
                return len(points)

            def search(self, _vector, _top_k=10, _collection=None, **_kw):
                return self.hits

        fake_model = _FakeModel()
        fake_store = _FakeStore()
        from agents.rag_agent.vector_store import VectorRecord

        fake_store.hits = [
            VectorRecord(
                id=0,
                payload={
                    "nl_query": "统计员工总数",
                    "sql": "SELECT COUNT(*) FROM employees",
                    "tables": ["employees"],
                },
            )
        ]

        with (
            patch("agents.ingestion_agent.store.get_embedding_model", return_value=fake_model),
            patch("agents.ingestion_agent.store.get_vector_store", return_value=fake_store),
        ):
            ctx = _run(get_schema_context("统计员工总数"))

        # Semantic example should be injected
        assert "SELECT COUNT(*) FROM employees" in ctx
        assert self._td._qdrant_ready is True
        assert len(fake_store.upserted) == len(EXAMPLE_QUERIES)
        # Collection created with detected dimension
        assert fake_store.created[0].vector_size == 4

    def test_semantic_fallback_when_search_fails(self):
        os.environ["FDE_NL2SQL_USE_QDRANT"] = "true"

        class _FakeResult:
            def __init__(self, vec):
                self.vector = vec

        class _FakeModel:
            async def embed(self, _text, **_kw):
                return _FakeResult([0.1, 0.2, 0.3, 0.4])

            async def embed_batch(self, texts, **_kw):
                return [_FakeResult([0.1, 0.2, 0.3, 0.4]) for _ in texts]

        class _FakeStore:
            def __init__(self):
                self.upserted: list[Any] = []
                self._exists = False

            def collection_exists(self, _name=None):
                return self._exists

            def create_collection(self, _cfg):
                self._exists = True

            def upsert(self, points, collection=None):
                self.upserted.extend(points)
                return len(points)

            def search(self, *_a, **_kw):
                raise RuntimeError("Qdrant search unavailable")

        with (
            patch("agents.ingestion_agent.store.get_embedding_model", return_value=_FakeModel()),
            patch("agents.ingestion_agent.store.get_vector_store", return_value=_FakeStore()),
        ):
            ctx = _run(get_schema_context("统计员工总数"))

        # Falls back to keyword retrieval
        assert "Example Queries" in ctx
        assert "SELECT" in ctx


# ══════════════════════════════════════════════════════════════════
# Test: Executor
# ══════════════════════════════════════════════════════════════════


class TestMockExecutor:
    """Test MockExecutor in-memory query execution."""

    def test_execute_select_all(self):
        executor = MockExecutor()
        result = _run(executor.execute("SELECT * FROM employees"))
        assert result.row_count == 10
        assert "id" in result.columns
        assert "name" in result.columns

    def test_execute_select_columns(self):
        executor = MockExecutor()
        result = _run(executor.execute("SELECT name, salary FROM employees"))
        assert result.row_count == 10
        assert set(result.columns) == {"name", "salary"}

    def test_execute_where_gt(self):
        executor = MockExecutor()
        result = _run(executor.execute("SELECT name, salary FROM employees WHERE salary > 200000"))
        assert result.row_count > 0
        assert all(row["salary"] > 200000 for row in result.rows)

    def test_execute_where_eq(self):
        executor = MockExecutor()
        result = _run(executor.execute("SELECT * FROM employees WHERE department = 'eng'"))
        assert result.row_count > 0
        assert all(row["department"] == "eng" for row in result.rows)

    def test_execute_count(self):
        executor = MockExecutor()
        result = _run(executor.execute("SELECT COUNT(*) FROM employees"))
        assert result.row_count == 1
        assert result.rows[0]["count"] == 10

    def test_execute_order_by_desc(self):
        executor = MockExecutor()
        result = _run(
            executor.execute("SELECT name, salary FROM employees ORDER BY salary DESC LIMIT 5")
        )
        assert result.row_count == 5
        salaries = [r["salary"] for r in result.rows]
        assert salaries == sorted(salaries, reverse=True)

    def test_execute_limit(self):
        executor = MockExecutor()
        result = _run(executor.execute("SELECT * FROM employees LIMIT 3"))
        assert result.row_count == 3

    def test_execute_empty_result(self):
        executor = MockExecutor()
        result = _run(executor.execute("SELECT * FROM employees WHERE salary > 999999999"))
        assert result.row_count == 0
        assert result.rows == []

    def test_execute_blocked_sql(self):
        executor = MockExecutor()
        result = _run(executor.execute("DELETE FROM employees"))
        assert result.row_count == 0
        assert result.rows == []

    def test_execute_unknown_table(self):
        executor = MockExecutor()
        result = _run(executor.execute("SELECT * FROM nonexistent_table"))
        assert result.row_count == 0

    def test_execute_has_execution_time(self):
        executor = MockExecutor()
        result = _run(executor.execute("SELECT * FROM employees"))
        assert result.execution_time_ms >= 0.0

    def test_execute_truncation(self):
        executor = MockExecutor()
        result = _run(executor.execute("SELECT * FROM employees", max_results=3))
        assert result.row_count == 3
        assert result.truncated is True

    def test_get_executor_singleton(self):
        e1 = get_executor()
        e2 = get_executor()
        assert e1 is e2


# ══════════════════════════════════════════════════════════════════
# Test: Integration (Tool Registration)
# ══════════════════════════════════════════════════════════════════


class TestIntegration:
    """Test ToolRegistry integration."""

    def test_register_analysis_tools(self):
        registry = ToolRegistry()
        register_analysis_tools(registry)

        tools = registry.get_tools_for_worker("analysis")
        assert len(tools) == 4

        tool_names = {t.name for t in tools}
        assert "nl2sql" in tool_names
        assert "sql_execute" in tool_names
        assert "schema_list" in tool_names
        assert "query_chart_data" in tool_names

    def test_tools_not_dangerous(self):
        registry = ToolRegistry()
        register_analysis_tools(registry)

        dangerous = registry.get_dangerous_tools()
        analysis_dangerous = [t for t in dangerous if t.worker == "analysis"]
        assert len(analysis_dangerous) == 0

    def test_dispatch_nl2sql(self):
        registry = ToolRegistry()
        register_analysis_tools(registry)

        result = _run(registry.dispatch("nl2sql", query="查询所有员工"))
        assert result["success"] is True
        assert "SELECT" in result["sql"]
        assert result["safety_check_passed"] is True

    def test_dispatch_nl2sql_empty_query(self):
        registry = ToolRegistry()
        register_analysis_tools(registry)

        result = _run(registry.dispatch("nl2sql", query=""))
        assert result["success"] is False
        assert "query is required" in result["error"]

    def test_dispatch_nl2sql_no_match(self):
        registry = ToolRegistry()
        register_analysis_tools(registry)

        result = _run(registry.dispatch("nl2sql", query="今天天气怎么样"))
        assert result["success"] is False
        assert result["source"] == "llm"

    def test_dispatch_sql_execute(self):
        registry = ToolRegistry()
        register_analysis_tools(registry)

        result = _run(registry.dispatch("sql_execute", sql="SELECT * FROM employees LIMIT 5"))
        assert result["row_count"] == 5
        assert len(result["columns"]) > 0

    def test_dispatch_sql_execute_blocked(self):
        registry = ToolRegistry()
        register_analysis_tools(registry)

        result = _run(registry.dispatch("sql_execute", sql="DELETE FROM employees"))
        assert result["row_count"] == 0

    def test_dispatch_schema_list(self):
        registry = ToolRegistry()
        register_analysis_tools(registry)

        result = _run(registry.dispatch("schema_list"))
        assert "tables" in result
        assert len(result["tables"]) == 4
        table_names = {t["table_name"] for t in result["tables"]}
        assert "employees" in table_names

    def test_dispatch_query_chart_data(self):
        registry = ToolRegistry()
        register_analysis_tools(registry)

        result = _run(
            registry.dispatch(
                "query_chart_data",
                query="查询员工姓名和薪资",
                chart_type="bar",
            ),
        )
        assert result["chart_type"] == "bar"
        assert len(result["labels"]) > 0
        assert len(result["datasets"]) > 0

    def test_dispatch_query_chart_data_invalid_type(self):
        registry = ToolRegistry()
        register_analysis_tools(registry)

        result = _run(
            registry.dispatch(
                "query_chart_data",
                query="查询员工姓名和薪资",
                chart_type="invalid_type",
            ),
        )
        # Invalid chart type falls back to "bar"
        assert result["chart_type"] == "bar"

    def test_dispatch_query_chart_data_empty_query(self):
        registry = ToolRegistry()
        register_analysis_tools(registry)

        result = _run(
            registry.dispatch("query_chart_data", query="", chart_type="line"),
        )
        assert result["labels"] == []
        assert result["datasets"] == []

    def test_dispatch_nl2sql_sales_query_ac001(self):
        """AC-001: 查询所有销售额大于100万的记录 → SELECT ... WHERE amount > 1000000"""
        registry = ToolRegistry()
        register_analysis_tools(registry)

        result = _run(
            registry.dispatch("nl2sql", query="查询所有销售额大于100万的记录"),
        )
        assert result["success"] is True
        assert ">" in result["sql"]
        assert "1000000" in result["sql"]
        assert result["result"] is not None
        assert result["result"]["row_count"] >= 0

    def test_dispatch_sql_execute_blocked_ac002(self):
        """AC-002: DELETE FROM table → blocked"""
        registry = ToolRegistry()
        register_analysis_tools(registry)

        result = _run(
            registry.dispatch("sql_execute", sql="DELETE FROM employees WHERE id = 1"),
        )
        assert result["row_count"] == 0
