"""P3b 幂等（重复 ingest 无幽灵）+ 大文件外置对象存储测试。"""

from __future__ import annotations

import io

import openpyxl
import pytest
from sqlalchemy import select

from agents.ingestion_agent.database.models import (
    CanonicalDocument,
    RawDocument,
)
from agents.ingestion_agent.pipeline import IngestionPipeline
from agents.ingestion_agent.storage import FakeStorage
from agents.ingestion_agent.tests.fakes import FakeEmbeddingModel, InMemoryVectorStore

_CSV = "客户名称,城市\n阿里巴巴,杭州\n腾讯,深圳\n".encode()


@pytest.mark.asyncio
async def test_ingest_file_idempotent_no_ghost(
    session, fake_vs: InMemoryVectorStore, fake_em: FakeEmbeddingModel
) -> None:
    storage = FakeStorage()
    r1 = await IngestionPipeline.ingest_file(
        "c.csv", _CSV, doc_type="sales", session=session,
        vector_store=fake_vs, embedding_model=fake_em, storage=storage,
    )
    assert r1["canonical"] == 2

    r2 = await IngestionPipeline.ingest_file(
        "c.csv", _CSV, doc_type="sales", session=session,
        vector_store=fake_vs, embedding_model=fake_em, storage=storage,
    )
    assert r2["duplicated"] is True
    assert r2["raw_id"] == r1["raw_id"]
    assert r2["canonical"] == 0  # 不产生新的归一文档

    # 数据库中 RawDocument 仍只有 1 条，CanonicalDocument 仍只有 2 条（无幽灵）
    raws = (await session.execute(select(RawDocument))).scalars().all()
    canon = (await session.execute(select(CanonicalDocument))).scalars().all()
    assert len(raws) == 1
    assert len(canon) == 2


@pytest.mark.asyncio
async def test_ingest_file_large_stored_in_object_storage(
    session, fake_vs: InMemoryVectorStore, fake_em: FakeEmbeddingModel
) -> None:
    storage = FakeStorage()
    res = await IngestionPipeline.ingest_file(
        "c.csv", _CSV, doc_type="sales", session=session,
        vector_store=fake_vs, embedding_model=fake_em, storage=storage,
    )
    raw = (
        await session.execute(select(RawDocument).where(RawDocument.id == res["raw_id"]))
    ).scalars().first()
    assert raw is not None
    assert raw.content_hash is not None
    assert raw.storage_ref is not None
    assert raw.storage_ref.startswith("memory://")
    # 原始字节可回取（大文件不进 DB，存对象存储）
    assert await storage.get(raw.storage_ref) == _CSV


@pytest.mark.asyncio
async def test_ingest_excel_idempotent(
    session, fake_vs: InMemoryVectorStore, fake_em: FakeEmbeddingModel
) -> None:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["名称", "金额"])
    ws.append(["张三", 100])
    ws.append(["李四", 200])
    buf = io.BytesIO()
    wb.save(buf)
    data = buf.getvalue()

    r1 = await IngestionPipeline.ingest_excel(
        data, "t.xlsx", session=session,
        vector_store=fake_vs, embedding_model=fake_em, storage=FakeStorage(),
    )
    r2 = await IngestionPipeline.ingest_excel(
        data, "t.xlsx", session=session,
        vector_store=fake_vs, embedding_model=fake_em, storage=FakeStorage(),
    )
    assert r2["duplicated"] is True
    assert r2["raw_id"] == r1["raw_id"]
