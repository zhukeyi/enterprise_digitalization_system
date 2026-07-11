"""P2a 端到端测试：经真实 FastAPI 路由验证「上传 Excel → 问答命中」。

用内存依赖（sqlite + 内存向量库 + 假嵌入）替换生产依赖，无需真实
Postgres / Qdrant / BGE-M3。验证 MVS 验收标准：上传乱列名 Excel 后，
对话问答能命中该数据。
"""

from __future__ import annotations

import io
from typing import Any

import openpyxl
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

import agents.ingestion_agent.pipeline  # noqa: F401  # 注册 ingestion 表
from agents.governance_agent.database.session import Base, get_async_session
from agents.ingestion_agent.fts import ensure_fts_table
from agents.ingestion_agent.storage import FakeStorage, get_storage
from agents.ingestion_agent.store import get_embedding_model, get_vector_store
from agents.ingestion_agent.tests.fakes import FakeEmbeddingModel, InMemoryVectorStore
from agents.router_agent.main import app


def _make_xlsx(headers: list[str], rows: list[list[Any]]) -> bytes:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(headers)
    for r in rows:
        ws.append(r)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


@pytest_asyncio.fixture
async def client():
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await ensure_fts_table(engine)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    fake_vs = InMemoryVectorStore()
    fake_em = FakeEmbeddingModel()

    async def override_get_session():
        async with factory() as s:
            yield s

    app.dependency_overrides[get_async_session] = override_get_session
    app.dependency_overrides[get_vector_store] = lambda: fake_vs
    app.dependency_overrides[get_embedding_model] = lambda: fake_em
    app.dependency_overrides[get_storage] = lambda: FakeStorage()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        c.fake_vs = fake_vs  # type: ignore[attr-defined]
        c.fake_em = fake_em  # type: ignore[attr-defined]
        yield c

    app.dependency_overrides.clear()
    await engine.dispose()


@pytest.mark.asyncio
async def test_upload_and_ask_hits_data(client: AsyncClient) -> None:
    data = _make_xlsx(
        [" 客户 名称 ", "订单号", "金额"],
        [["张三", "ORD-1001", 1234.5], ["李四", "ORD-1002", 5678.0]],
    )
    files = {
        "file": (
            "销售数据.xlsx",
            data,
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    }
    resp = await client.post("/ingest/upload", files=files, data={"doc_type": "sales"})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["rows"] == 2
    assert body["canonical"] == 2
    assert body["indexed_vectors"] == 2

    # 对话问答：查询「张三」应命中其记录
    ask = await client.post("/api/data/ask", json={"query": "张三", "top_k": 3})
    assert ask.status_code == 200, ask.text
    ans = ask.json()
    assert ans["count"] >= 1
    assert "张三" in ans["sources"][0]["text"]


@pytest.mark.asyncio
async def test_ask_before_upload_returns_empty(client: AsyncClient) -> None:
    ask = await client.post("/api/data/ask", json={"query": "任意问题"})
    assert ask.status_code == 200
    ans = ask.json()
    assert ans["count"] == 0
    assert "在知识库中" in ans["answer"]


@pytest.mark.asyncio
async def test_upload_rejects_non_xlsx(client: AsyncClient) -> None:
    resp = await client.post(
        "/ingest/upload",
        files={"file": ("note.txt", b"hello", "text/plain")},
        data={"doc_type": "x"},
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_ask_rejects_empty_query(client: AsyncClient) -> None:
    resp = await client.post("/api/data/ask", json={"query": "   "})
    assert resp.status_code == 400
