"""P2b 父子 chunking 测试：表格父子 + 文本滑窗。"""

from __future__ import annotations

from agents.ingestion_agent.chunking import build_table_chunks, build_text_chunks
from agents.ingestion_agent.parsers import Block, BlockType


def _table_block() -> Block:
    headers = ["customer_name", "city"]
    rows = [
        {"customer_name": "阿里巴巴", "city": "杭州"},
        {"customer_name": "腾讯", "city": "深圳"},
    ]
    return Block(kind=BlockType.TABLE, table=rows, table_headers=headers, loc={"page": 1})


def test_build_table_chunks_parent_contains_all_rows() -> None:
    specs = build_table_chunks(
        _table_block(), doc_type="sales", source_ref="local://x", raw_id="r1"
    )
    assert len(specs) == 2
    parent = specs[0].parent_text
    assert "阿里巴巴" in parent and "腾讯" in parent
    assert "行1" in specs[0].child_text and "阿里巴巴" in specs[0].child_text
    assert specs[0].metadata["row_index"] == 0


def test_build_text_chunks_single_parent_short() -> None:
    text = "阿里巴巴 总部在杭州。"
    specs = build_text_chunks(text, doc_type="pdf", source_ref="s", raw_id="r")
    assert len(specs) == 1
    assert specs[0].parent_text == text
    assert specs[0].child_text == text


def test_build_text_chunks_sliding_window_long() -> None:
    text = "。".join(f"第{i}句内容用于测试切片长度是否足够触发多块生成" for i in range(40))
    specs = build_text_chunks(
        text, doc_type="pdf", source_ref="s", raw_id="r", child_size=50, overlap=10
    )
    assert len(specs) > 1
    assert specs[0].parent_text == text
    assert all(len(s.child_text) <= 50 for s in specs)
