"""P2a 测试 fixtures：sqlite 内存会话 + 内存向量库/嵌入模型。"""

from __future__ import annotations

import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

# 导入 pipeline 以触发 ingestion 表注册到共享 Base.metadata。
import agents.ingestion_agent.pipeline  # noqa: F401
from agents.governance_agent.database.session import Base
from agents.ingestion_agent.fts import ensure_fts_table
from agents.ingestion_agent.tests.fakes import FakeEmbeddingModel, InMemoryVectorStore


@pytest_asyncio.fixture
async def session():
    """sqlite 内存会话（StaticPool 保证多连接共享同一库）。"""
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await ensure_fts_table(engine)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as s:
        yield s
    await engine.dispose()


@pytest_asyncio.fixture
def fake_vs() -> InMemoryVectorStore:
    return InMemoryVectorStore()


@pytest_asyncio.fixture
def fake_em() -> FakeEmbeddingModel:
    return FakeEmbeddingModel()
