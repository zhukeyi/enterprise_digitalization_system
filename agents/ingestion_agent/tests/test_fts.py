"""P3b FTS5 词法索引测试（Postgres GIN 的 SQLite 等价实现）。"""

from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import StaticPool

from agents.governance_agent.database.session import Base
from agents.ingestion_agent.database.models import CanonicalDocument
from agents.ingestion_agent.fts import (
    ensure_fts_table,
    fts_lexical_search,
    index_canonical,
)


@pytest.mark.asyncio
async def test_ensure_fts_table_idempotent() -> None:
    """CREATE VIRTUAL TABLE IF NOT EXISTS 重复调用不报错。"""
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await ensure_fts_table(engine)
    await ensure_fts_table(engine)  # 第二次不报错
    async with engine.connect() as conn:
        res = await conn.execute(
            text("SELECT name FROM sqlite_master WHERE type='table' AND name='canonical_fts'")
        )
        assert res.first() is not None
    await engine.dispose()


@pytest.mark.asyncio
async def test_index_and_search_ascii(session) -> None:
    orm = CanonicalDocument(
        id="c1",
        doc_type="t",
        title="GDP report 2024",
        canonical_payload={"text": "GDP grew 5 percent in 2024"},
    )
    session.add(orm)
    await session.flush()
    await index_canonical(session, orm, raw_document_id="r1")

    hits = await fts_lexical_search(session, "GDP 2024", limit=10)
    assert any(h["canonical_document_id"] == "c1" for h in hits)


@pytest.mark.asyncio
async def test_index_and_search_cjk_like(session) -> None:
    """中文无空格，走 LIKE 兜底召回。"""
    orm = CanonicalDocument(
        id="c2",
        doc_type="t",
        title="杭州客户清单",
        canonical_payload={"城市": "杭州", "客户": "阿里巴巴"},
    )
    session.add(orm)
    await session.flush()
    await index_canonical(session, orm, raw_document_id="r2")

    hits = await fts_lexical_search(session, "杭州", limit=10)
    assert any(h["canonical_document_id"] == "c2" for h in hits)
