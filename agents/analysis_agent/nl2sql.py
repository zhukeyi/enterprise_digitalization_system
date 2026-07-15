"""NL2SQL Engine — natural language to SQL conversion.

M3-T3: Rule-based NL2SQL with LLM fallback.
A-1: LLM fallback now calls OpenAI-compatible endpoint (Ollama/LiteLLM).

Architecture:
1. Rule Engine: keyword → table/column/operator mapping → SELECT statement
2. LLM Fallback: when rule engine can't match, call LLM to generate SQL,
   then validate with sql_safety before returning.

The rule engine covers common query patterns:
- Table detection: "员工" → employees, "部门" → departments, "销售额" → sales, "产品" → products
- Column detection: "姓名" → name, "薪资" → salary, "日期" → date, "金额" → amount
- Operator detection: "大于" → >, "小于" → <, "等于" → =, "不等于" → !=
- Aggregation: "统计/总数/平均/最大/最小" → COUNT/AVG/MAX/MIN
- Ordering: "排序/从高到低/从低到高" → ORDER BY ... DESC/ASC
- Limiting: "前N条" → LIMIT N
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass

from agents.analysis_agent.models import NL2SQLRequest
from agents.analysis_agent.schema_extractor import BaseSchemaExtractor

logger = logging.getLogger("fde.analysis.nl2sql")

# ══════════════════════════════════════════════════════════════════
# LLM Configuration (environment-driven, mirrors map_agent pattern)
# ══════════════════════════════════════════════════════════════════

_NL2SQL_LLM_MODEL = os.getenv("FDE_NL2SQL_LLM_MODEL", "").strip()
_LITELLM_PROXY_URL = os.getenv("LITELLM_PROXY_URL", "").strip().rstrip("/")


# ══════════════════════════════════════════════════════════════════
# Keyword Mapping Tables
# ══════════════════════════════════════════════════════════════════

# Chinese → table name
TABLE_KEYWORDS: dict[str, str] = {
    "员工": "employees",
    "雇员": "employees",
    "人员": "employees",
    "职工": "employees",
    "部门": "departments",
    "组织": "departments",
    "科室": "departments",
    "销售": "sales",
    "交易": "sales",
    "订单": "sales",
    "产品": "products",
    "商品": "products",
    "货品": "products",
}

# Chinese → column name (applied within the context of a detected table)
COLUMN_KEYWORDS: dict[str, str] = {
    "姓名": "name",
    "名字": "name",
    "名称": "name",
    "薪资": "salary",
    "工资": "salary",
    "薪水": "salary",
    "部门": "department",
    "状态": "status",
    "入职日期": "hire_date",
    "入职时间": "hire_date",
    "雇佣日期": "hire_date",
    "预算": "budget",
    "金额": "amount",
    "销售额": "amount",
    "价格": "price",
    "单价": "price",
    "库存": "stock",
    "数量": "stock",
    "类别": "category",
    "分类": "category",
    "地区": "region",
    "区域": "region",
    "日期": "sale_date",
    "时间": "sale_date",
}

# Chinese → SQL operator
OPERATOR_KEYWORDS: dict[str, str] = {
    "大于": ">",
    "超过": ">",
    "高于": ">",
    "小于": "<",
    "低于": "<",
    "不超过": "<=",
    "等于": "=",
    "是": "=",
    "为": "=",
    "不等于": "!=",
    "不是": "!=",
    "至少": ">=",
    "最多": "<=",
}

# Chinese → aggregation function
AGGREGATION_KEYWORDS: dict[str, str] = {
    "统计": "COUNT",
    "总数": "COUNT",
    "数量": "COUNT",
    "多少": "COUNT",
    "平均": "AVG",
    "均值": "AVG",
    "最大": "MAX",
    "最高": "MAX",
    "最小": "MIN",
    "最低": "MIN",
    "总和": "SUM",
    "总计": "SUM",
    "合计": "SUM",
}

# Chinese → ORDER BY direction
ORDER_KEYWORDS: dict[str, str] = {
    "从高到低": "DESC",
    "降序": "DESC",
    "从大到小": "DESC",
    "从低到高": "ASC",
    "升序": "ASC",
    "从小到大": "ASC",
}


# ══════════════════════════════════════════════════════════════════
# Conversion Result
# ══════════════════════════════════════════════════════════════════


@dataclass
class ConversionResult:
    """Result of NL2SQL conversion."""

    sql: str = ""
    source: str = "rule_engine"  # "rule_engine" | "llm"
    matched: bool = False
    table: str = ""
    reason: str = ""
    llm_error: str = ""  # non-empty when LLM fallback was attempted but failed


# ══════════════════════════════════════════════════════════════════
# NL2SQL Rule Engine
# ══════════════════════════════════════════════════════════════════


class NL2SQLEngine:
    """Rule-based natural language to SQL conversion engine.

    Uses keyword mapping tables to detect tables, columns, operators,
    and aggregations from Chinese natural language input. Falls back
    to LLM routing when the rule engine cannot produce a valid query.
    """

    def __init__(self, extractor: BaseSchemaExtractor | None = None) -> None:
        self._extractor = extractor

    async def convert(self, request: NL2SQLRequest) -> ConversionResult:
        """Convert a natural language query to SQL.

        Args:
            request: The NL2SQL request containing the query text.

        Returns:
            ConversionResult with the generated SQL and metadata.
        """
        query = request.query.strip()
        if not query:
            return ConversionResult(source="rule_engine", matched=False, reason="Empty query")

        # Step 1: Detect target table
        table = self._detect_table(query)
        if not table:
            return ConversionResult(
                source="llm",
                matched=False,
                reason="No table keyword matched — requires LLM routing",
            )

        # Step 2: Detect columns
        columns = self._detect_columns(query, table)

        # Step 3: Detect aggregation
        aggregation = self._detect_aggregation(query)

        # Step 4: Detect WHERE conditions
        where_clause = self._detect_where(query, table)

        # Step 5: Detect ORDER BY
        order_clause = self._detect_order(query, columns)

        # Step 6: Detect LIMIT
        limit = self._detect_limit(query, request.max_results)

        # Step 7: Build SQL
        sql = self._build_sql(
            table=table,
            columns=columns,
            aggregation=aggregation,
            where_clause=where_clause,
            order_clause=order_clause,
            limit=limit,
        )

        logger.info("NL2SQL: '%s' → '%s'", query, sql)
        return ConversionResult(
            sql=sql,
            source="rule_engine",
            matched=True,
            table=table,
        )

    # ────────────────────────────────────────────────────────────────
    # Detection Methods
    # ────────────────────────────────────────────────────────────────

    def _detect_table(self, query: str) -> str:
        """Detect the target table from the query."""
        for keyword, table_name in TABLE_KEYWORDS.items():
            if keyword in query:
                return table_name
        return ""

    def _detect_columns(self, query: str, table: str) -> list[str]:
        """Detect requested columns from the query."""
        columns: list[str] = []

        for keyword, col_name in COLUMN_KEYWORDS.items():
            if keyword in query and col_name not in columns:
                columns.append(col_name)

        # If no specific columns detected, use SELECT *
        if not columns:
            return ["*"]

        return columns

    def _detect_aggregation(self, query: str) -> tuple[str, str] | None:
        """Detect aggregation function and target column.

        Returns:
            Tuple of (function, column) or None if no aggregation detected.
        """
        for keyword, func in AGGREGATION_KEYWORDS.items():
            if keyword in query:
                # Find the column to aggregate on
                for col_kw, col_name in COLUMN_KEYWORDS.items():
                    if col_kw in query:
                        return (func, col_name)
                # Default: COUNT(*)
                if func == "COUNT":
                    return ("COUNT", "*")
                return (func, "")
        return None

    def _detect_where(self, query: str, table: str) -> str:
        """Detect WHERE clause conditions from the query."""
        conditions: list[str] = []

        # Pattern: "X大于Y" / "X小于Y" / "X等于Y" etc.
        for op_kw, op_sym in OPERATOR_KEYWORDS.items():
            if op_kw not in query:
                continue

            # Find what comes before the operator keyword (column)
            idx = query.index(op_kw)
            prefix = query[:idx]

            # Find what comes after the operator keyword (value)
            suffix = query[idx + len(op_kw) :]

            # Extract column from prefix
            col = self._extract_column_from_text(prefix)
            if not col:
                continue

            # Extract value from suffix
            value = self._extract_value_from_text(suffix)
            if value is None:
                continue

            conditions.append(f"{col} {op_sym} {value}")

        if not conditions:
            return ""
        return " WHERE " + " AND ".join(conditions)

    def _detect_order(self, query: str, columns: list[str]) -> str:
        """Detect ORDER BY clause from the query."""
        for keyword, direction in ORDER_KEYWORDS.items():
            if keyword in query:
                # Order by the first non-* column
                order_col = next((c for c in columns if c != "*"), "")
                if order_col:
                    return f" ORDER BY {order_col} {direction}"
                return f" ORDER BY id {direction}"
        return ""

    def _detect_limit(self, query: str, default_limit: int) -> int:
        """Detect LIMIT from the query (e.g., '前10条' → 10)."""
        # Pattern: "前N条" / "前N个" / "N条"
        match = re.search(r"前(\d+)(?:条|个|名)", query)
        if match:
            return int(match.group(1))

        match = re.search(r"(\d+)\s*条", query)
        if match:
            return int(match.group(1))

        return default_limit

    # ────────────────────────────────────────────────────────────────
    # SQL Builder
    # ────────────────────────────────────────────────────────────────

    def _build_sql(
        self,
        table: str,
        columns: list[str],
        aggregation: tuple[str, str] | None,
        where_clause: str,
        order_clause: str,
        limit: int,
    ) -> str:
        """Build the final SELECT statement from detected components."""
        # Aggregation overrides column selection
        if aggregation:
            func, agg_col = aggregation
            if func == "COUNT" and agg_col == "*":
                select_clause = "SELECT COUNT(*)"
            elif agg_col:
                select_clause = f"SELECT {func}({agg_col})"
            else:
                select_clause = f"SELECT {func}(*)"
        else:
            col_str = ", ".join(columns)
            select_clause = f"SELECT {col_str}"

        return f"{select_clause} FROM {table}{where_clause}{order_clause} LIMIT {limit}"

    # ────────────────────────────────────────────────────────────────
    # Text Extraction Helpers
    # ────────────────────────────────────────────────────────────────

    def _extract_column_from_text(self, text: str) -> str:
        """Extract a column name from text preceding an operator."""
        for keyword, col_name in COLUMN_KEYWORDS.items():
            if keyword in text:
                return col_name
        return ""

    def _extract_value_from_text(self, text: str) -> str | None:
        """Extract a numeric or string value from text following an operator."""
        # Try numeric value (including Chinese numbers and units)
        # Handle "100万" → 1000000, "1万" → 10000, "1千" → 1000
        match = re.search(r"(\d+(?:\.\d+)?)\s*(万|千|百)?", text)
        if match:
            num = float(match.group(1))
            unit = match.group(2)
            if unit == "万":
                num *= 10000
            elif unit == "千":
                num *= 1000
            elif unit == "百":
                num *= 100

            # Return as int if whole number, else float
            if num == int(num):
                return str(int(num))
            return str(num)

        # Try string value in quotes — escape single quotes to prevent SQL injection
        match = re.search(r"['\"]([^'\"]+)['\"]", text)
        if match:
            escaped = match.group(1).replace("'", "''")
            return f"'{escaped}'"

        return None

    # ────────────────────────────────────────────────────────────────
    # LLM Fallback
    # ────────────────────────────────────────────────────────────────

    def build_llm_prompt(self, request: NL2SQLRequest, schema_context: str = "") -> str:
        """Build a prompt for the LLM fallback channel.

        When the rule engine cannot match the query, this prompt is
        sent to the LLM endpoint for SQL generation.

        Args:
            request: The NL2SQL request containing the query text.
            schema_context: Optional DDL/schema context to inject (A-2).
        """
        schema_block = f"\nDatabase Schema:\n{schema_context}\n" if schema_context else ""
        return (
            "Convert the following natural language query to a read-only SQL SELECT statement.\n"
            f"Query: {request.query}\n"
            f"Schema ID: {request.db_schema_id}\n"
            f"{schema_block}"
            f"Max results: {request.max_results}\n"
            "Constraints:\n"
            "- Only generate SELECT or WITH ... SELECT statements.\n"
            "- No DML (INSERT/UPDATE/DELETE) or DDL (CREATE/ALTER/DROP).\n"
            "- Return ONLY the SQL statement, no explanation.\n"
        )

    async def convert_with_llm(
        self,
        request: NL2SQLRequest,
        schema_context: str = "",
    ) -> ConversionResult:
        """Attempt LLM-based NL→SQL conversion when the rule engine fails.

        Calls the OpenAI-compatible endpoint (Ollama/LiteLLM proxy) to
        generate SQL from the natural language query. The generated SQL
        is **not** executed here — callers must run ``validate_sql``
        before execution.

        Args:
            request: The NL2SQL request containing the query text.
            schema_context: Optional DDL/schema context to inject into
                the LLM prompt (populated by A-2 training data).

        Returns:
            ConversionResult with ``source="llm"``. If LLM is not
            configured or the call fails, ``matched=False`` and
            ``llm_error`` is set.
        """
        if not _NL2SQL_LLM_MODEL or not _LITELLM_PROXY_URL:
            logger.debug("NL2SQL LLM disabled (FDE_NL2SQL_LLM_MODEL/LITELLM_PROXY_URL unset)")
            return ConversionResult(
                source="llm",
                matched=False,
                reason="LLM not configured — set FDE_NL2SQL_LLM_MODEL and LITELLM_PROXY_URL",
            )

        prompt = self.build_llm_prompt(request, schema_context)
        try:
            raw = await _call_llm(prompt)
        except Exception as exc:
            logger.warning("NL2SQL LLM call failed: %s", exc)
            return ConversionResult(
                source="llm",
                matched=False,
                reason="LLM call failed",
                llm_error=str(exc),
            )

        sql = _extract_sql(raw)
        if not sql:
            logger.warning("NL2SQL LLM returned empty/unparseable response")
            return ConversionResult(
                source="llm",
                matched=False,
                reason="LLM returned empty or unparseable response",
                llm_error=f"raw={raw[:200]!r}",
            )

        logger.info("NL2SQL LLM: '%s' → '%s'", request.query, sql)
        return ConversionResult(
            sql=sql,
            source="llm",
            matched=True,
            table="",
        )


# ══════════════════════════════════════════════════════════════════
# LLM call helper (mirrors map_agent interpreter._call_llm pattern)
# ══════════════════════════════════════════════════════════════════


async def _call_llm(prompt: str) -> str:
    """Send prompt to the configured OpenAI-compatible LLM endpoint.

    Uses ``LITELLM_PROXY_URL`` as the base URL and
    ``FDE_NL2SQL_LLM_MODEL`` as the model name. Works with both
    Ollama's ``/v1/chat/completions`` and LiteLLM proxy's
    ``/chat/completions``.
    """
    import httpx

    url = f"{_LITELLM_PROXY_URL}/chat/completions"
    payload = {
        "model": _NL2SQL_LLM_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.1,
        "max_tokens": 512,
    }
    headers: dict[str, str] = {"Content-Type": "application/json"}
    master_key = os.getenv("LITELLM_MASTER_KEY", "")
    if master_key:
        headers["Authorization"] = f"Bearer {master_key}"

    async with httpx.AsyncClient(timeout=httpx.Timeout(30.0)) as client:
        resp = await client.post(url, json=payload, headers=headers)
    if resp.status_code != 200:
        raise RuntimeError(f"LLM returned {resp.status_code}: {resp.text[:300]}")
    data = resp.json()
    choices = data.get("choices", [])
    if not choices:
        raise RuntimeError("LLM returned no choices")
    content = choices[0].get("message", {}).get("content", "")
    return str(content)


def _extract_sql(raw: str) -> str:
    """Extract a SQL statement from the LLM response text.

    Strips markdown code fences (```sql ... ```) and surrounding
    whitespace. Returns an empty string if no SQL-like content found.
    """
    if not raw or not raw.strip():
        return ""
    text = raw.strip()

    # Strip markdown code fences
    if text.startswith("```"):
        # Remove opening fence (with optional language tag)
        text = re.sub(r"^```(?:sql|SQL)?\s*\n?", "", text)
        text = re.sub(r"\n?```\s*$", "", text)
        text = text.strip()

    # Verify it looks like a SQL statement
    if not text:
        return ""
    upper = text.upper().lstrip()
    if not (upper.startswith("SELECT") or upper.startswith("WITH")):
        return ""

    return text


# ══════════════════════════════════════════════════════════════════
# Module-level singleton
# ══════════════════════════════════════════════════════════════════

_engine: NL2SQLEngine | None = None


def get_engine() -> NL2SQLEngine:
    """Get the singleton NL2SQLEngine instance."""
    global _engine
    if _engine is None:
        _engine = NL2SQLEngine()
    return _engine


def reset_engine() -> None:
    """Reset the singleton engine."""
    global _engine
    _engine = None
