"""P2a 归一化与入库管线单元测试（≥10）。

覆盖 mapping_loader 归一化、render/hash 工具，以及核心 ``IngestionPipeline``
在内存依赖（sqlite + 内存向量库 + 假嵌入）下的行为。
"""

from __future__ import annotations

import io

import openpyxl
import pytest
from sqlalchemy import select

from agents.ingestion_agent.database.models import CanonicalDocument as CanonicalDocumentORM
from agents.ingestion_agent.mapping_loader import (
    build_identity_mapping,
    normalize_field_name,
    normalize_rows,
)
from agents.ingestion_agent.pipeline import (
    IngestionPipeline,
    compute_content_hash,
    render_canonical_text,
)

# ── mapping_loader 归一化 ────────────────────────────────────────


def test_normalize_field_name_strips_and_underscores() -> None:
    assert normalize_field_name(" 客户 名称 ") == "客户_名称"


def test_normalize_field_name_hyphen() -> None:
    assert normalize_field_name("Order-No") == "Order_No"


def test_normalize_field_name_empty() -> None:
    assert normalize_field_name("   ") == ""


def test_build_identity_mapping_rules() -> None:
    headers = ["客户 名称", "订单号", "金额"]
    mapping = build_identity_mapping(headers, doc_type="sales")
    assert len(mapping.rules) == 3
    assert mapping.doc_type == "sales"
    assert mapping.rules[0].source_path == "客户 名称"
    assert mapping.rules[0].target_field == "客户_名称"


def test_normalize_rows_maps_to_normalized_keys() -> None:
    headers = ["客户 名称", "金额"]
    rows = [{"客户 名称": "张三", "金额": 100}]
    docs = normalize_rows(headers, rows)
    assert len(docs) == 1
    assert docs[0].fields == {"客户_名称": "张三", "金额": 100}


def test_normalize_rows_skips_empty_header() -> None:
    headers = ["名称", "", "金额"]
    rows = [{"名称": "A", "": "x", "金额": 1}]
    docs = normalize_rows(headers, rows)
    assert "金额" in docs[0].fields
    assert "" not in docs[0].fields


# ── 工具函数 ────────────────────────────────────────────────────


def test_render_canonical_text_includes_title_and_fields() -> None:
    cd = type("CD", (), {"title": "张三", "fields": {"金额": 100, "空": None}})()
    text = render_canonical_text(cd)
    assert "张三" in text
    assert "金额: 100" in text
    assert "空" not in text  # 空值被跳过


def test_compute_content_hash_deterministic_and_distinct() -> None:
    a = compute_content_hash({"x": 1})
    b = compute_content_hash({"x": 1})
    c = compute_content_hash({"x": 2})
    assert a == b
    assert a != c
    assert len(a) == 64


# ── 管线：sqlite + 内存依赖 ───────────────────────────────────────


@pytest.mark.asyncio
async def test_ingest_rows_stores_canonical_and_returns_counts(session, fake_vs, fake_em) -> None:
    headers = ["名称", "金额"]
    rows = [{"名称": "张三", "金额": 100}, {"名称": "李四", "金额": 200}]
    result = await IngestionPipeline.ingest_rows(
        headers,
        rows,
        doc_type="sales",
        source_ref="local://t.xlsx",
        session=session,
        vector_store=fake_vs,
        embedding_model=fake_em,
    )
    assert result["rows"] == 2
    assert result["canonical"] == 2
    assert result["indexed_vectors"] == 2

    stored = (await session.scalars(select(CanonicalDocumentORM))).all()
    assert len(stored) == 2
    assert stored[0].doc_type == "sales"
    # 归一化后字段名可见
    assert "名称" in stored[0].canonical_payload


@pytest.mark.asyncio
async def test_ingest_rows_empty_raises(session, fake_vs, fake_em) -> None:
    with pytest.raises(ValueError):
        await IngestionPipeline.ingest_rows(
            ["名称"],
            [],
            session=session,
            vector_store=fake_vs,
            embedding_model=fake_em,
        )


@pytest.mark.asyncio
async def test_ingest_excel_roundtrip_and_search_hit(session, fake_vs, fake_em) -> None:
    wb = openpyxl.Workbook()
    ws = wb.active
    # 故意用「乱列名」：多余空格 + 中文
    ws.append([" 客户 名称 ", "订单号", "金额"])
    ws.append(["张三", "ORD-1001", 1234.5])
    ws.append(["李四", "ORD-1002", 5678.0])
    buf = io.BytesIO()
    wb.save(buf)
    data = buf.getvalue()

    result = await IngestionPipeline.ingest_excel(
        data,
        "销售数据.xlsx",
        session=session,
        vector_store=fake_vs,
        embedding_model=fake_em,
    )
    assert result["rows"] == 2
    assert result["doc_type"] == "销售数据"

    # 校验乱列名被归一化
    stored = (await session.scalars(select(CanonicalDocumentORM))).all()
    assert any("客户_名称" in s.canonical_payload for s in stored)

    # 检索「张三」应命中其所在记录
    q_vec = (await fake_em.encode_queries(["张三"]))[0]
    recs = await fake_vs.async_search(q_vec, top_k=5)
    assert recs, "应当检索到至少一条记录"
    assert "张三" in recs[0].payload["text"]


@pytest.mark.asyncio
async def test_ingest_excel_empty_file_raises(session, fake_vs, fake_em) -> None:
    wb = openpyxl.Workbook()
    buf = io.BytesIO()
    wb.save(buf)
    with pytest.raises(ValueError):
        await IngestionPipeline.ingest_excel(
            buf.getvalue(),
            "empty.xlsx",
            session=session,
            vector_store=fake_vs,
            embedding_model=fake_em,
        )
