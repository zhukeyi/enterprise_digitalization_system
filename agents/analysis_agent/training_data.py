"""Training Data — DDL + example SQL context for NL2SQL LLM fallback.

A-2: Provides schema context (DDL + example queries) to inject into
the NL2SQL LLM prompt, improving SQL generation accuracy.

Two modes:
1. **In-memory keyword** (default, ``FDE_NL2SQL_USE_QDRANT`` unset/off):
   Pre-built DDL + examples from the mock schema, ranked by keyword
   overlap. Zero external dependencies.
2. **Qdrant semantic** (opt-in, ``FDE_NL2SQL_USE_QDRANT=true``): The
   training chunks are vectorised with the shared BGE embedding model
   and retrieved by semantic similarity to the user query. Falls back
   to in-memory keyword retrieval if Qdrant / embedding is unreachable.

Usage::

    from agents.analysis_agent.training_data import get_schema_context

    context = await get_schema_context("统计薪资大于50万的员工数量")
    # → DDL + relevant example SQL injected into LLM prompt
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field

logger = logging.getLogger("fde.analysis.training_data")

# ══════════════════════════════════════════════════════════════════
# DDL Definitions (mock schema)
# ══════════════════════════════════════════════════════════════════

MOCK_DDL = """\
-- Employee master records
CREATE TABLE employees (
    id          INTEGER PRIMARY KEY,
    name        VARCHAR(100) NOT NULL,
    department  VARCHAR(50),
    salary      NUMERIC(12,2),
    hire_date   DATE NOT NULL,
    status      VARCHAR(20) NOT NULL DEFAULT 'active'
);

-- Department master records
CREATE TABLE departments (
    id          INTEGER PRIMARY KEY,
    name        VARCHAR(100) NOT NULL,
    budget      NUMERIC(15,2),
    manager_id  INTEGER
);

-- Sales transaction records
CREATE TABLE sales (
    id          INTEGER PRIMARY KEY,
    employee_id INTEGER NOT NULL,
    amount      NUMERIC(12,2) NOT NULL,
    sale_date   TIMESTAMP NOT NULL,
    product     VARCHAR(100),
    region      VARCHAR(50)
);

-- Product catalog
CREATE TABLE products (
    id          INTEGER PRIMARY KEY,
    name        VARCHAR(200) NOT NULL,
    category    VARCHAR(50),
    price       NUMERIC(10,2) NOT NULL,
    stock       INTEGER NOT NULL DEFAULT 0
);
"""

# ══════════════════════════════════════════════════════════════════
# Example SQL Queries (Chinese NL → SQL pairs)
# ══════════════════════════════════════════════════════════════════


@dataclass
class ExampleQuery:
    """A training example pairing natural language with SQL."""

    nl_query: str
    sql: str
    tables: list[str] = field(default_factory=list)


EXAMPLE_QUERIES: list[ExampleQuery] = [
    ExampleQuery(
        nl_query="查询所有员工姓名和薪资",
        sql="SELECT name, salary FROM employees LIMIT 100",
        tables=["employees"],
    ),
    ExampleQuery(
        nl_query="统计员工总数",
        sql="SELECT COUNT(*) FROM employees",
        tables=["employees"],
    ),
    ExampleQuery(
        nl_query="薪资大于50000的员工有哪些",
        sql="SELECT name, salary FROM employees WHERE salary > 50000 ORDER BY salary DESC",
        tables=["employees"],
    ),
    ExampleQuery(
        nl_query="各部门平均薪资",
        sql="SELECT department, AVG(salary) FROM employees GROUP BY department ORDER BY AVG(salary) DESC",
        tables=["employees"],
    ),
    ExampleQuery(
        nl_query="入职日期在2023年之后的员工",
        sql="SELECT name, hire_date FROM employees WHERE hire_date > '2023-01-01'",
        tables=["employees"],
    ),
    ExampleQuery(
        nl_query="销售额最高的前10条记录",
        sql="SELECT * FROM sales ORDER BY amount DESC LIMIT 10",
        tables=["sales"],
    ),
    ExampleQuery(
        nl_query="各区域的销售总额",
        sql="SELECT region, SUM(amount) FROM sales GROUP BY region ORDER BY SUM(amount) DESC",
        tables=["sales"],
    ),
    ExampleQuery(
        nl_query="库存低于100的产品",
        sql="SELECT name, stock FROM products WHERE stock < 100 ORDER BY stock ASC",
        tables=["products"],
    ),
    ExampleQuery(
        nl_query="各部门预算总和",
        sql="SELECT name, SUM(budget) FROM departments GROUP BY name",
        tables=["departments"],
    ),
    ExampleQuery(
        nl_query="每个产品类别的平均价格",
        sql="SELECT category, AVG(price) FROM products GROUP BY category",
        tables=["products"],
    ),
    ExampleQuery(
        nl_query="状态为活跃的员工数量",
        sql="SELECT COUNT(*) FROM employees WHERE status = 'active'",
        tables=["employees"],
    ),
    ExampleQuery(
        nl_query="销售额超过100万的交易记录",
        sql="SELECT * FROM sales WHERE amount > 1000000 ORDER BY amount DESC",
        tables=["sales"],
    ),
]


# ══════════════════════════════════════════════════════════════════
# Schema Context Builder
# ══════════════════════════════════════════════════════════════════


def _keyword_overlap(query: str, example: ExampleQuery) -> int:
    """Simple keyword overlap score for in-memory retrieval."""
    query_chars = set(query)
    example_chars = set(example.nl_query)
    overlap = len(query_chars & example_chars)
    # Also check table name overlap
    for table in example.tables:
        if table in query.lower():
            overlap += 5
    return overlap


def build_ddl_context() -> str:
    """Return the full DDL context for the mock schema."""
    return MOCK_DDL.strip()


def build_example_context(query: str, max_examples: int = 3) -> str:
    """Return the most relevant example SQL queries for the given query.

    Uses simple keyword overlap scoring (in-memory retrieval).
    If Qdrant is configured, this can be upgraded to vector retrieval
    in the future.
    """
    if not query.strip():
        # Return first N examples as default
        selected = EXAMPLE_QUERIES[:max_examples]
    else:
        scored = [(ex, _keyword_overlap(query, ex)) for ex in EXAMPLE_QUERIES]
        scored.sort(key=lambda x: x[1], reverse=True)
        selected = [ex for ex, _ in scored[:max_examples]]

    lines: list[str] = []
    for ex in selected:
        lines.append(f"-- {ex.nl_query}")
        lines.append(ex.sql)
        lines.append("")

    return "\n".join(lines).strip()


# ══════════════════════════════════════════════════════════════════
# Qdrant Semantic Retrieval (optional upgrade over keyword)
# ══════════════════════════════════════════════════════════════════

NL2SQL_QDRANT_COLLECTION = "fde_nl2sql_examples"

# Runtime state (mutated by _ensure_initialised)
_qdrant_ready = False
_initialised = False


def _qdrant_enabled() -> bool:
    """Whether to attempt Qdrant-backed semantic retrieval.

    Default OFF (in-memory keyword mode). Opt in on the server by
    setting ``FDE_NL2SQL_USE_QDRANT=true`` (requires Qdrant + the
    shared BGE embedding model).
    """
    val = os.getenv("FDE_NL2SQL_USE_QDRANT", "off").lower()
    return val in ("1", "true", "on", "yes", "auto")


async def _ensure_initialised() -> None:
    """Lazily vectorise training examples into Qdrant (once).

    Idempotent. On any failure (Qdrant down, embedding unavailable) it
    logs a warning and leaves in-memory keyword retrieval active.
    """
    global _initialised, _qdrant_ready
    if _initialised:
        return
    _initialised = True

    if not _qdrant_enabled():
        logger.info(
            "NL2SQL training data: in-memory keyword mode (FDE_NL2SQL_USE_QDRANT=%s)",
            os.getenv("FDE_NL2SQL_USE_QDRANT", "off"),
        )
        return

    try:
        from agents.ingestion_agent.store import get_embedding_model, get_vector_store
        from agents.rag_agent.vector_store import CollectionConfig, VectorRecord

        model = get_embedding_model()
        store = get_vector_store()

        probe = (await model.embed_batch(["NL2SQL probe text"]))[0]
        dim = len(probe.vector)

        if not store.collection_exists(NL2SQL_QDRANT_COLLECTION):
            store.create_collection(
                CollectionConfig(
                    name=NL2SQL_QDRANT_COLLECTION,
                    vector_size=dim,
                    distance="Cosine",
                )
            )

        docs = [f"{ex.nl_query}\n{ex.sql}" for ex in EXAMPLE_QUERIES]
        vectors = await model.embed_batch(docs)
        points = [
            VectorRecord(
                id=idx,
                vector=vec.vector,
                payload={
                    "nl_query": ex.nl_query,
                    "sql": ex.sql,
                    "tables": ex.tables,
                },
            )
            for idx, (ex, vec) in enumerate(zip(EXAMPLE_QUERIES, vectors, strict=True))
        ]
        store.upsert(points, collection=NL2SQL_QDRANT_COLLECTION)
        _qdrant_ready = True
        logger.info(
            "NL2SQL training data vectorised → Qdrant '%s' (%d points, dim=%d)",
            NL2SQL_QDRANT_COLLECTION,
            len(points),
            dim,
        )
    except Exception as exc:  # degrade gracefully
        _qdrant_ready = False
        logger.warning(
            "NL2SQL Qdrant init failed (%s); falling back to in-memory keyword retrieval",
            exc,
        )


async def _semantic_example_context(query: str, max_examples: int = 3) -> str | None:
    """Retrieve example SQL via Qdrant semantic similarity.

    Returns the formatted example block, or ``None`` when Qdrant is
    not ready (the caller falls back to keyword retrieval).
    """
    if not _qdrant_ready or not query.strip():
        return None
    try:
        from agents.ingestion_agent.store import get_embedding_model, get_vector_store

        model = get_embedding_model()
        store = get_vector_store()
        qvec = (await model.embed_batch([query]))[0]
        hits = store.search(qvec.vector, top_k=max_examples, collection=NL2SQL_QDRANT_COLLECTION)
        if not hits:
            return None
        lines: list[str] = []
        for h in hits:
            pl = h.payload or {}
            lines.append(f"-- {pl.get('nl_query', '')}")
            lines.append(pl.get("sql", ""))
            lines.append("")
        return "\n".join(lines).strip() or None
    except Exception as exc:  # degrade gracefully
        logger.warning("NL2SQL semantic retrieval failed (%s); falling back to keyword", exc)
        return None


async def get_schema_context(query: str = "") -> str:
    """Build the full schema context for NL2SQL LLM prompt injection.

    Combines DDL definitions with relevant example SQL queries. When
    Qdrant semantic retrieval is enabled it ranks examples by vector
    similarity to the query; otherwise it uses in-memory keyword
    overlap. This context is injected into the LLM prompt to improve
    SQL generation accuracy.

    Args:
        query: The natural language query (used for example retrieval).

    Returns:
        A formatted string containing DDL and example queries.
    """
    await _ensure_initialised()
    ddl = build_ddl_context()
    examples = await _semantic_example_context(query)
    if examples is None:
        examples = build_example_context(query)

    return f"""\
{ddl}

-- Example Queries:
{examples}"""


async def init_training_data() -> None:
    """Initialize (vectorise) NL2SQL training data into Qdrant.

    Idempotent. Call explicitly at startup when semantic retrieval is
    enabled, or rely on the lazy first ``get_schema_context`` call.
    """
    await _ensure_initialised()
