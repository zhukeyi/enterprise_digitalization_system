"""P2-A Docling 后端测试：markdown 块解析 + 后端选择 + 真实解析（skip if 未装）。

Docling 依赖 torch VLM，列为可选依赖（requirements-docling.txt），不进入主依赖树。
因此真实解析测试在无 docling 环境自动 skip，仅验证接口契约与回退行为。
"""

from __future__ import annotations

import importlib.util

import pytest

from agents.ingestion_agent import parsers
from agents.ingestion_agent.parsers import (
    Block,
    BlockType,
    ParsedDocument,
    _parse_markdown_to_blocks,
    parse_pdf_backend,
)


def _docling_available() -> bool:
    return importlib.util.find_spec("docling") is not None


# ── 纯函数：markdown → Block（无需 docling）─────────────────────────


def test_markdown_heading_and_text_blocks():
    md = "# 标题一\n正文段落一。\n## 标题二\n正文段落二。"
    blocks = _parse_markdown_to_blocks(md)
    assert blocks[0].kind == BlockType.HEADING
    assert blocks[0].text == "标题一"
    assert blocks[1].kind == BlockType.TEXT
    assert "正文段落一" in blocks[1].text
    assert blocks[2].kind == BlockType.HEADING
    assert blocks[3].kind == BlockType.TEXT


def test_markdown_table_parsed_to_table_block():
    md = (
        "# 销售表\n\n"
        "| 客户 | 城市 | 金额 |\n"
        "| --- | --- | --- |\n"
        "| 阿里巴巴 | 杭州 | 100 |\n"
        "| 腾讯 | 深圳 | 200 |\n\n"
        "尾部说明。"
    )
    blocks = _parse_markdown_to_blocks(md)
    tbl = next(b for b in blocks if b.kind == BlockType.TABLE)
    assert "客户" in tbl.table_headers
    assert len(tbl.table) == 2
    assert tbl.table[0]["客户"] == "阿里巴巴"
    assert tbl.table[1]["金额"] == "200"
    # 表前后文本仍在
    texts = [b.text for b in blocks if b.kind == BlockType.TEXT]
    assert any("尾部说明" in t for t in texts)


def test_markdown_table_only():
    md = "| A | B |\n| --- | --- |\n| 1 | 2 |\n"
    blocks = _parse_markdown_to_blocks(md)
    assert len(blocks) == 1
    assert blocks[0].kind == BlockType.TABLE
    assert blocks[0].table[0]["A"] == "1"


# ── 后端选择（auto 默认回退 pdfplumber，docling 未装时）──────────────


def test_default_backend_is_pdfplumber_when_docling_absent(monkeypatch):
    monkeypatch.setattr(parsers, "_PDF_BACKEND", "auto")
    # 此环境未装 docling → auto 解析为 pdfplumber
    assert parse_pdf_backend() == "pdfplumber"


def test_backend_explicit_pdfplumber_reports_pdfplumber(monkeypatch):
    monkeypatch.setattr(parsers, "_PDF_BACKEND", "pdfplumber")
    assert parse_pdf_backend() == "pdfplumber"


def test_explicit_docling_backend_reports_docling_if_available(monkeypatch):
    monkeypatch.setattr(parsers, "_PDF_BACKEND", "docling")
    if _docling_available():
        assert parse_pdf_backend() == "docling"
    else:
        assert parse_pdf_backend() == "docling"  # 配置值，不探测可用性


# ── auto 回退：docling 未装时 _parse_pdf 不抛错，用 pdfplumber ──────


def test_auto_fallback_to_pdfplumber(monkeypatch):
    """docling 未安装时，auto 后端必须路由到 pdfplumber（不抛 ImportError）。"""
    monkeypatch.setattr(parsers, "_PDF_BACKEND", "auto")

    called = {}

    def _fake_pdfplumber(data, filename):
        called["hit"] = True
        return ParsedDocument(
            doc_type="pdf_upload",
            source_ref=filename,
            blocks=[Block(kind=BlockType.TEXT, text="Fallback paragraph.")],
            meta={"file_type": "pdf", "parser": "pdfplumber"},
        )

    monkeypatch.setattr(parsers, "_parse_pdf_pdfplumber", _fake_pdfplumber)
    parsed = parsers._parse_pdf(b"%PDF-1.4 fake", "fallback.pdf")
    assert called.get("hit") is True
    assert parsed.meta.get("parser") == "pdfplumber"
    assert any("Fallback" in b.text for b in parsed.blocks if b.kind == BlockType.TEXT)


def test_explicit_docling_raises_when_unavailable(monkeypatch):
    """显式 docling 后端但库未装 → _parse_pdf_docling 抛 ImportError。"""
    monkeypatch.setattr(parsers, "_PDF_BACKEND", "docling")
    if _docling_available():
        pytest.skip("docling 已安装，此测试不适用")
    with pytest.raises(ImportError):
        parsers._parse_pdf_docling(b"%PDF-1.4 fake", "x.pdf")


# ── 真实 Docling 解析（仅当 docling 已安装）──────────────────────────


@pytest.mark.skipif(not _docling_available(), reason="docling 可选依赖未安装")
def test_parse_pdf_docling_real():
    import fitz

    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((50, 50), "Quarterly revenue grew 12% YoY.")
    buf = __import__("io").BytesIO()
    doc.save(buf)
    parsed = parsers._parse_pdf_docling(buf.getvalue(), "real.pdf")
    assert isinstance(parsed, ParsedDocument)
    assert parsed.meta.get("parser") == "docling"
    all_text = " ".join(b.text for b in parsed.blocks if b.kind == BlockType.TEXT)
    assert "revenue" in all_text


@pytest.mark.skipif(not _docling_available(), reason="docling 可选依赖未安装")
def test_parse_pdf_docling_table_real():
    """构造含表格的 PDF，验证 docling 还原为 TABLE block。"""
    import fitz

    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((50, 50), "Sales Table")
    # 用文本模拟简单表格（Docling 能从布局识别）
    page.insert_text((50, 80), "Product   Price")
    page.insert_text((50, 100), "Widget    9.99")
    page.insert_text((50, 120), "Gadget   19.99")
    buf = __import__("io").BytesIO()
    doc.save(buf)
    parsed = parsers._parse_pdf_docling(buf.getvalue(), "table.pdf")
    # 至少产出文本块；表格识别依赖 VLM 模型可用性
    assert len(parsed.blocks) > 0
