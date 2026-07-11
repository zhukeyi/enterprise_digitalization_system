"""多格式文件解析器（P2b / 完整本地文件入库）。

把 ``.xlsx / .xlsm / .csv / .pdf / .docx / .pptx`` 解析为统一的 ``ParsedDocument``
（blocks：``text`` / ``table`` / ``heading``），供 normalization + chunking + 入库复用。

解析库均为**惰性导入**（函数内 ``import``），缺失某个库只影响对应类型，不会让整个
ingestion router 注册失败。规划允许 Docling 经 P0.5 spike 不通过时回退到
``pdfplumber + python-docx + openpyxl``——本实现即采用该回退路径，避免 ARM 机器上
约 1.5G 的 torch 依赖（见 docs/master-delivery-plan.md P0.5 / P2b）。
"""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any

# 扩展名 → 解析器类型
_EXT_LOADERS: dict[str, str] = {
    ".xlsx": "excel",
    ".xlsm": "excel",
    ".csv": "csv",
    ".pdf": "pdf",
    ".docx": "docx",
    ".pptx": "pptx",
}


class BlockType(StrEnum):
    """解析块类型。"""

    TEXT = "text"
    TABLE = "table"
    HEADING = "heading"


@dataclass
class Block:
    """一个解析块（文本段 / 表格 / 标题）。

    ``table`` 与 ``table_headers`` 仅当 ``kind == TABLE`` 时使用；行字典的键为
    **原始表头**（保留空格），归一化在 normalization 层完成，避免与映射契约错位。
    """

    kind: BlockType
    text: str = ""
    table: list[dict[str, Any]] | None = None
    table_headers: list[str] | None = None
    loc: dict[str, Any] = field(default_factory=dict)


@dataclass
class ParsedDocument:
    """一次解析的产物。"""

    doc_type: str
    source_ref: str
    blocks: list[Block] = field(default_factory=list)
    meta: dict[str, Any] = field(default_factory=dict)


def detect_file_type(filename: str, data: bytes) -> str:
    """按扩展名（辅以 magic bytes 兜底）判断文件类型。"""
    ext = Path(filename).suffix.lower()
    if ext in _EXT_LOADERS:
        return _EXT_LOADERS[ext]
    if data[:4] == b"%PDF":
        return "pdf"
    if data[:2] == b"PK":
        return "docx"  # docx/pptx 均为 zip，扩展名兜底更准确
    return "unknown"


def _grid_to_table(grid: list[list[Any]]) -> tuple[list[str], list[dict[str, Any]]]:
    """把 PDF/DOCX/PPTX 的二维单元格网格转成 (原始表头, 行字典列表)。

    行字典键使用**原始表头**（保留空格、自动去重），归一化交给 normalization 层。
    """
    if not grid:
        return [], []
    raw_headers = [str(c).strip() if c is not None else "" for c in grid[0]]
    headers: list[str] = []
    seen: dict[str, int] = {}
    for i, h in enumerate(raw_headers):
        base = h if h else f"col_{i}"
        if base in seen:
            seen[base] += 1
            base = f"{base}_{seen[base]}"
        else:
            seen[base] = 0
        headers.append(base)
    rows: list[dict[str, Any]] = []
    for r in grid[1:]:
        if r is None or all(c is None or str(c).strip() == "" for c in r):
            continue
        row = {headers[i]: (r[i] if i < len(r) else None) for i in range(len(headers))}
        rows.append(row)
    return headers, rows


def _table_block(headers: list[str], rows: list[dict[str, Any]], loc: dict[str, Any]) -> Block:
    return Block(kind=BlockType.TABLE, table=rows, table_headers=headers, loc=loc)


def parse_file(filename: str, data: bytes) -> ParsedDocument:
    """解析任意受支持的文件，返回 ``ParsedDocument``。"""
    ftype = detect_file_type(filename, data)
    if ftype == "excel":
        return _parse_excel(data, filename)
    if ftype == "csv":
        return _parse_csv(data, filename)
    if ftype == "pdf":
        return _parse_pdf(data, filename)
    if ftype == "docx":
        return _parse_docx(data, filename)
    if ftype == "pptx":
        return _parse_pptx(data, filename)
    raise ValueError(f"不支持的文件类型: {filename}")


def _parse_excel(data: bytes, filename: str) -> ParsedDocument:
    try:
        import openpyxl
    except ImportError as exc:  # pragma: no cover - openpyxl 为声明依赖
        raise RuntimeError("openpyxl 未安装，无法解析 Excel") from exc
    wb = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    blocks: list[Block] = []
    for ws in wb.worksheets:
        grid = list(ws.iter_rows(values_only=True))
        if not grid:
            continue
        headers, rows = _grid_to_table(grid)
        if rows:
            blocks.append(_table_block(headers, rows, {"sheet": ws.title}))
    return ParsedDocument(
        doc_type="excel_upload",
        source_ref=filename,
        blocks=blocks,
        meta={
            "content_type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "file_type": "excel",
        },
    )


def _parse_csv(data: bytes, filename: str) -> ParsedDocument:
    text = data.decode("utf-8-sig", errors="replace")
    reader = csv.reader(io.StringIO(text))
    grid = list(reader)
    headers, rows = _grid_to_table(grid)
    if rows:
        blocks = [_table_block(headers, rows, {"sheet": "csv"})]
    else:
        blocks = []
    return ParsedDocument(
        doc_type="csv_upload",
        source_ref=filename,
        blocks=blocks,
        meta={"content_type": "text/csv", "file_type": "csv"},
    )


def _parse_pdf(data: bytes, filename: str) -> ParsedDocument:
    try:
        import pdfplumber
    except ImportError as exc:  # pragma: no cover - pdfplumber 为声明依赖
        raise RuntimeError("pdfplumber 未安装，无法解析 PDF") from exc
    blocks: list[Block] = []
    with pdfplumber.open(io.BytesIO(data)) as pdf:
        for pi, page in enumerate(pdf.pages, start=1):
            text = page.extract_text() or ""
            for bi, para in enumerate(p for p in text.split("\n\n") if p.strip()):
                blocks.append(
                    Block(kind=BlockType.TEXT, text=para.strip(), loc={"page": pi, "block": bi})
                )
            for ti, tbl in enumerate(page.extract_tables() or []):
                headers, rows = _grid_to_table(tbl)
                if rows:
                    blocks.append(_table_block(headers, rows, {"page": pi, "table": ti}))
    return ParsedDocument(
        doc_type="pdf_upload",
        source_ref=filename,
        blocks=blocks,
        meta={"content_type": "application/pdf", "file_type": "pdf"},
    )


def _parse_docx(data: bytes, filename: str) -> ParsedDocument:
    try:
        import docx
    except ImportError as exc:  # pragma: no cover - python-docx 为声明依赖
        raise RuntimeError("python-docx 未安装，无法解析 DOCX") from exc
    document = docx.Document(io.BytesIO(data))
    blocks: list[Block] = []
    for pi, para in enumerate(document.paragraphs):
        txt = para.text.strip()
        if not txt:
            continue
        style = (para.style.name or "") if para.style else ""
        kind = BlockType.HEADING if style.startswith("Heading") else BlockType.TEXT
        blocks.append(Block(kind=kind, text=txt, loc={"paragraph": pi}))
    for ti, table in enumerate(document.tables):
        grid = [[c.text for c in row.cells] for row in table.rows]
        headers, rows = _grid_to_table(grid)
        if rows:
            blocks.append(_table_block(headers, rows, {"table": ti}))
    return ParsedDocument(
        doc_type="docx_upload",
        source_ref=filename,
        blocks=blocks,
        meta={
            "content_type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "file_type": "docx",
        },
    )


def _parse_pptx(data: bytes, filename: str) -> ParsedDocument:
    try:
        from pptx import Presentation
    except ImportError as exc:  # pragma: no cover - python-pptx 为声明依赖
        raise RuntimeError("python-pptx 未安装，无法解析 PPTX") from exc
    prs = Presentation(io.BytesIO(data))
    blocks: list[Block] = []
    for si, slide in enumerate(prs.slides, start=1):
        texts: list[str] = []
        for shape in slide.shapes:
            if shape.has_text_frame:
                t = shape.text_frame.text.strip()
                if t:
                    texts.append(t)
            if shape.has_table:
                grid = [[c.text for c in row.cells] for row in shape.table.rows]
                headers, rows = _grid_to_table(grid)
                if rows:
                    blocks.append(_table_block(headers, rows, {"slide": si, "table": 0}))
        if texts:
            blocks.append(Block(kind=BlockType.TEXT, text="\n".join(texts), loc={"slide": si}))
    return ParsedDocument(
        doc_type="pptx_upload",
        source_ref=filename,
        blocks=blocks,
        meta={
            "content_type": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
            "file_type": "pptx",
        },
    )


__all__ = [
    "Block",
    "BlockType",
    "ParsedDocument",
    "detect_file_type",
    "parse_file",
]
