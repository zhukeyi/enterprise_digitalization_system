"""Tests for document parser factory.

M1-T9: Tests cover format detection, parser selection, and parsing logic
for all supported formats. Large libraries (PyMuPDF, python-docx, etc.)
are mocked to keep tests fast and dependency-free.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from agents.rag_agent.document_parser import (
    Document,
    DocxParser,
    MarkdownParser,
    ParserError,
    ParserFactory,
    PdfParser,
    PlainTextParser,
    PptxParser,
    UnsupportedFormatError,
    XlsxParser,
    detect_format,
)

# ══════════════════════════════════════════════════════════════════
# Format Detection Tests
# ══════════════════════════════════════════════════════════════════


class TestDetectFormat:
    def test_pdf(self) -> None:
        assert detect_format("doc.pdf") == "application/pdf"

    def test_docx(self) -> None:
        assert detect_format("doc.docx") == (
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        )

    def test_xlsx(self) -> None:
        assert detect_format("data.xlsx") == (
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

    def test_pptx(self) -> None:
        assert detect_format("slide.pptx") == (
            "application/vnd.openxmlformats-officedocument.presentationml.presentation"
        )

    def test_markdown(self) -> None:
        assert detect_format("readme.md") == "text/markdown"
        assert detect_format("doc.markdown") == "text/markdown"

    def test_plain_text(self) -> None:
        assert detect_format("notes.txt") == "text/plain"
        assert detect_format("data.csv") == "text/plain"
        assert detect_format("config.json") == "text/plain"

    def test_unknown_extension(self) -> None:
        assert detect_format("file.xyzz") == "text/plain"


# ══════════════════════════════════════════════════════════════════
# Parser Factory Tests
# ══════════════════════════════════════════════════════════════════


class TestParserFactory:
    def test_get_pdf_parser(self) -> None:
        factory = ParserFactory()
        parser = factory.get_parser("doc.pdf")
        assert isinstance(parser, PdfParser)

    def test_get_docx_parser(self) -> None:
        factory = ParserFactory()
        parser = factory.get_parser("doc.docx")
        assert isinstance(parser, DocxParser)

    def test_get_xlsx_parser(self) -> None:
        factory = ParserFactory()
        parser = factory.get_parser("data.xlsx")
        assert isinstance(parser, XlsxParser)

    def test_get_pptx_parser(self) -> None:
        factory = ParserFactory()
        parser = factory.get_parser("slide.pptx")
        assert isinstance(parser, PptxParser)

    def test_get_markdown_parser(self) -> None:
        factory = ParserFactory()
        parser = factory.get_parser("readme.md")
        assert isinstance(parser, MarkdownParser)

    def test_get_text_parser(self) -> None:
        factory = ParserFactory()
        parser = factory.get_parser("notes.txt")
        assert isinstance(parser, PlainTextParser)

    def test_unsupported_format(self) -> None:
        factory = ParserFactory()
        with pytest.raises(UnsupportedFormatError, match="No parser available"):
            factory.get_parser("archive.rar")

    def test_list_supported_formats(self) -> None:
        factory = ParserFactory()
        formats = factory.list_supported_formats()
        assert len(formats) >= 6  # At least 6 parsers
        names = {f["parser"] for f in formats}
        assert "PdfParser" in names
        assert "DocxParser" in names
        assert "MarkdownParser" in names

    def test_detect_and_parse_text_file(self, tmp_path: Path) -> None:
        factory = ParserFactory()
        test_file = tmp_path / "hello.txt"
        test_file.write_text("Hello, World!\nThis is a test.", encoding="utf-8")

        docs = factory.parse(str(test_file))
        assert len(docs) == 1
        assert "Hello, World!" in docs[0].content
        assert docs[0].metadata["format"] == "text"

    async def test_async_parse_text_file(self, tmp_path: Path) -> None:
        factory = ParserFactory()
        test_file = tmp_path / "async_test.txt"
        test_file.write_text("Async content", encoding="utf-8")

        docs = await factory.async_parse(str(test_file))
        assert len(docs) == 1
        assert docs[0].content == "Async content"


# ══════════════════════════════════════════════════════════════════
# Markdown Parser Tests
# ══════════════════════════════════════════════════════════════════


class TestMarkdownParser:
    def test_parse_markdown(self, tmp_path: Path) -> None:
        md_file = tmp_path / "test.md"
        md_file.write_text("# Title\n\nThis is **bold** text.", encoding="utf-8")

        parser = MarkdownParser()
        docs = parser.parse(str(md_file))
        assert len(docs) == 1
        assert "# Title" in docs[0].content
        assert docs[0].metadata["format"] == "markdown"

    def test_empty_file(self, tmp_path: Path) -> None:
        md_file = tmp_path / "empty.md"
        md_file.write_text("", encoding="utf-8")

        parser = MarkdownParser()
        docs = parser.parse(str(md_file))
        assert len(docs) == 0

    def test_file_not_found(self) -> None:
        parser = MarkdownParser()
        with pytest.raises(ParserError, match="File not found"):
            parser.parse("/nonexistent/file.md")


# ══════════════════════════════════════════════════════════════════
# Plain Text Parser Tests
# ══════════════════════════════════════════════════════════════════


class TestPlainTextParser:
    def test_parse_text(self, tmp_path: Path) -> None:
        txt_file = tmp_path / "notes.txt"
        txt_file.write_text("Line 1\nLine 2\nLine 3", encoding="utf-8")

        parser = PlainTextParser()
        docs = parser.parse(str(txt_file))
        assert len(docs) == 1
        assert docs[0].content == "Line 1\nLine 2\nLine 3"

    def test_parse_json_file(self, tmp_path: Path) -> None:
        json_file = tmp_path / "data.json"
        data = {"key": "value", "numbers": [1, 2, 3]}
        json_file.write_text(json.dumps(data), encoding="utf-8")

        parser = PlainTextParser()
        docs = parser.parse(str(json_file))
        assert len(docs) == 1
        assert '"key"' in docs[0].content

    def test_latin1_fallback(self, tmp_path: Path) -> None:
        """Should fall back to latin-1 for non-UTF-8 files."""
        txt_file = tmp_path / "latin1.txt"
        txt_file.write_bytes(b"Latin-1 text: \xe9\xe0\xf9")  # é à ù

        parser = PlainTextParser()
        docs = parser.parse(str(txt_file))
        assert len(docs) == 1
        assert docs[0].content


# ══════════════════════════════════════════════════════════════════
# PDF Parser Tests (mocked)
# ══════════════════════════════════════════════════════════════════


class TestPdfParser:
    def test_parse_with_mocked_pymupdf(self, tmp_path: Path) -> None:
        pdf_file = tmp_path / "test.pdf"
        pdf_file.write_text("fake pdf content")

        # Mock PyMuPDF
        mock_page = MagicMock()
        mock_page.get_text.return_value = "Page 1 content\nMore text."

        mock_doc = MagicMock()
        mock_doc.__len__ = MagicMock(return_value=1)
        mock_doc.__enter__ = MagicMock(return_value=mock_doc)
        mock_doc.__exit__ = MagicMock(return_value=None)
        mock_doc.__iter__ = MagicMock(return_value=iter([mock_page]))

        with patch("pymupdf.open", return_value=mock_doc):
            parser = PdfParser()
            docs = parser.parse(str(pdf_file))
            assert len(docs) == 1
            assert "Page 1 content" in docs[0].content
            assert docs[0].metadata["page"] == 1
            assert docs[0].metadata["format"] == "pdf"

    def test_missing_dependency(self, tmp_path: Path) -> None:
        pdf_file = tmp_path / "test.pdf"
        pdf_file.write_text("fake")

        with patch.dict("sys.modules", {"pymupdf": None}):
            parser = PdfParser()
            with pytest.raises(ParserError, match="PyMuPDF not installed"):
                parser.parse(str(pdf_file))


# ══════════════════════════════════════════════════════════════════
# DOCX Parser Tests (mocked)
# ══════════════════════════════════════════════════════════════════


class TestDocxParser:
    def test_parse_with_mocked_docx(self, tmp_path: Path) -> None:
        docx_file = tmp_path / "test.docx"
        docx_file.write_text("fake docx")

        # Mock python-docx
        mock_doc = MagicMock()
        p1 = MagicMock()
        p1.text = "Paragraph 1"
        p2 = MagicMock()
        p2.text = "Paragraph 2"
        mock_doc.paragraphs = [p1, p2]

        with patch("docx.Document", return_value=mock_doc):
            parser = DocxParser()
            docs = parser.parse(str(docx_file))
            assert len(docs) == 1
            assert "Paragraph 1" in docs[0].content
            assert docs[0].metadata["paragraphs"] == 2

    def test_empty_document(self, tmp_path: Path) -> None:
        docx_file = tmp_path / "empty.docx"
        docx_file.write_text("")

        mock_doc = MagicMock()
        empty_p = MagicMock()
        empty_p.text = ""
        mock_doc.paragraphs = [empty_p, empty_p]

        with patch("docx.Document", return_value=mock_doc):
            parser = DocxParser()
            docs = parser.parse(str(docx_file))
            assert len(docs) == 0


# ══════════════════════════════════════════════════════════════════
# XLSX Parser Tests (mocked)
# ══════════════════════════════════════════════════════════════════


class TestXlsxParser:
    def test_parse_with_mocked_openpyxl(self, tmp_path: Path) -> None:
        xlsx_file = tmp_path / "data.xlsx"
        xlsx_file.write_text("fake xlsx")

        # Mock openpyxl
        mock_ws = MagicMock()
        mock_ws.iter_rows.return_value = [
            ("Name", "Age", "City"),
            ("Alice", "30", "Beijing"),
            ("Bob", "25", "Shanghai"),
        ]
        mock_wb = MagicMock()
        mock_wb.sheetnames = ["Sheet1"]
        mock_wb.__getitem__ = MagicMock(return_value=mock_ws)
        mock_wb.__enter__ = MagicMock()
        mock_wb.__exit__ = MagicMock()

        with patch("openpyxl.load_workbook", return_value=mock_wb):
            parser = XlsxParser()
            docs = parser.parse(str(xlsx_file))
            assert len(docs) == 1
            assert "Alice" in docs[0].content
            assert docs[0].metadata["sheet"] == "Sheet1"

    def test_empty_sheet(self, tmp_path: Path) -> None:
        xlsx_file = tmp_path / "empty.xlsx"
        xlsx_file.write_text("")

        mock_ws = MagicMock()
        mock_ws.iter_rows.return_value = []
        mock_wb = MagicMock()
        mock_wb.sheetnames = ["Empty"]
        mock_wb.__getitem__ = MagicMock(return_value=mock_ws)

        with patch("openpyxl.load_workbook", return_value=mock_wb):
            parser = XlsxParser()
            docs = parser.parse(str(xlsx_file))
            assert len(docs) == 0


# ══════════════════════════════════════════════════════════════════
# PPTX Parser Tests (mocked)
# ══════════════════════════════════════════════════════════════════


class TestPptxParser:
    def test_parse_with_mocked_pptx(self, tmp_path: Path) -> None:
        pptx_file = tmp_path / "slide.pptx"
        pptx_file.write_text("fake pptx")

        # Mock python-pptx
        mock_shape = MagicMock()
        mock_shape.text = "Slide 1 content"
        mock_shape.has_table = False

        mock_slide = MagicMock()
        mock_slide.shapes = [mock_shape]

        mock_prs = MagicMock()
        mock_prs.slides = [mock_slide]

        with patch("pptx.Presentation", return_value=mock_prs):
            parser = PptxParser()
            docs = parser.parse(str(pptx_file))
            assert len(docs) == 1
            assert "Slide 1 content" in docs[0].content
            assert docs[0].metadata["slide"] == 1

    def test_slide_with_table(self, tmp_path: Path) -> None:
        pptx_file = tmp_path / "table.pptx"
        pptx_file.write_text("fake")

        # Mock table
        mock_cell = MagicMock()
        mock_cell.text = "Cell"
        mock_row = MagicMock()
        mock_row.cells = [mock_cell, mock_cell]
        mock_table = MagicMock()
        mock_table.rows = [mock_row]

        mock_shape = MagicMock()
        mock_shape.text = ""
        mock_shape.has_table = True
        mock_shape.table = mock_table

        mock_slide = MagicMock()
        mock_slide.shapes = [mock_shape]

        mock_prs = MagicMock()
        mock_prs.slides = [mock_slide]

        with patch("pptx.Presentation", return_value=mock_prs):
            parser = PptxParser()
            docs = parser.parse(str(pptx_file))
            assert len(docs) == 1
            assert "Cell | Cell" in docs[0].content


# ══════════════════════════════════════════════════════════════════
# Document Model Tests
# ══════════════════════════════════════════════════════════════════


class TestDocument:
    def test_default_values(self) -> None:
        doc = Document(content="hello")
        assert doc.id == ""
        assert doc.metadata == {}
        assert doc.source == ""
        assert doc.mime_type == "text/plain"
        assert doc.page_number is None

    def test_all_fields(self) -> None:
        doc = Document(
            id="doc-1",
            content="test content",
            metadata={"key": "val"},
            source="/path/to/file.pdf",
            mime_type="application/pdf",
            page_number=2,
        )
        assert doc.id == "doc-1"
        assert doc.metadata["key"] == "val"
        assert doc.page_number == 2
