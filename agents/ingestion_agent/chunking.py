"""父子 chunking（P2b / 完整本地文件入库）。

* **父块 parent**：表格全文 / 文本段落组（上限 ``max_parent`` 字符）。
* **子块 child**：表格的每一行 / 文本在父块内的滑窗切片。

子块用于嵌入与向量检索（粒度细、召回准）；命中后通过 ``parent_text`` 回带父块
上下文（信息完整）。所有依赖经参数注入，测试可用内存实现替换。
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any

from agents.ingestion_agent.parsers import Block


def _content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:64]


@dataclass
class ChunkSpec:
    """一个待入库的子块规格。"""

    parent_text: str
    child_text: str
    metadata: dict[str, Any] = field(default_factory=dict)
    content_hash: str = ""


def render_table(headers: list[str], rows: list[dict[str, Any]]) -> str:
    """把表格渲染为可读全文（父块文本）。"""
    lines = []
    for i, row in enumerate(rows):
        cells = ", ".join(f"{h}={row.get(h)}" for h in headers if row.get(h) not in (None, ""))
        lines.append(f"行{i + 1}: {cells}")
    return "\n".join(lines)


def build_table_chunks(
    block: Block,
    *,
    doc_type: str,
    source_ref: str,
    raw_id: str,
    loc: dict[str, Any] | None = None,
) -> list[ChunkSpec]:
    """表格 → 父块(全文) + 每个行一个子块。"""
    headers = block.table_headers or []
    rows = block.table or []
    parent_text = render_table(headers, rows)
    specs: list[ChunkSpec] = []
    for i, row in enumerate(rows):
        cells = ", ".join(f"{h}={row.get(h)}" for h in headers if row.get(h) not in (None, ""))
        child = f"行{i + 1}: {cells}" if cells else f"行{i + 1}"
        specs.append(
            ChunkSpec(
                parent_text=parent_text,
                child_text=child,
                metadata={
                    "block_kind": "table",
                    "row_index": i,
                    "doc_type": doc_type,
                    "source_ref": source_ref,
                    "raw_id": raw_id,
                    **(loc or {}),
                },
                content_hash=_content_hash(child),
            )
        )
    return specs


def build_text_chunks(
    text: str,
    *,
    doc_type: str,
    source_ref: str,
    raw_id: str,
    loc: dict[str, Any] | None = None,
    max_parent: int = 1200,
    child_size: int = 220,
    overlap: int = 40,
) -> list[ChunkSpec]:
    """文本 → 父块(段落组) + 父块内滑窗子块。

    父块按段落边界切分（不超过 ``max_parent``）；父块内再按 ``child_size`` 字符滑窗
    （步长 ``child_size - overlap``）生成子块。``parent_text`` 始终携带完整父块。
    """
    paragraphs = [p for p in text.split("\n") if p.strip() != ""]
    # 切分为父块
    parents: list[str] = []
    cur = ""
    for p in paragraphs:
        if cur and len(cur) + len(p) + 1 > max_parent:
            parents.append(cur)
            cur = p
        else:
            cur = f"{cur}\n{p}" if cur else p
    if cur:
        parents.append(cur)

    specs: list[ChunkSpec] = []
    for pi, parent in enumerate(parents):
        if len(parent) <= child_size:
            children = [parent]
        else:
            children = []
            start = 0
            while start < len(parent):
                children.append(parent[start : start + child_size])
                if start + child_size >= len(parent):
                    break
                start += max(1, child_size - overlap)
        for ci, child in enumerate(children):
            specs.append(
                ChunkSpec(
                    parent_text=parent,
                    child_text=child,
                    metadata={
                        "block_kind": "text",
                        "parent_index": pi,
                        "child_index": ci,
                        "doc_type": doc_type,
                        "source_ref": source_ref,
                        "raw_id": raw_id,
                        **(loc or {}),
                    },
                    content_hash=_content_hash(child),
                )
            )
    return specs


__all__ = ["ChunkSpec", "build_table_chunks", "build_text_chunks", "render_table"]
