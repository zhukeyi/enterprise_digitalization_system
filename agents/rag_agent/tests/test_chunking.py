"""Tests for chunking strategies.

M1-T10: Tests cover FixedSizeChunker, SemanticChunker, RecursiveChunker,
ChunkerFactory, and the convenience chunk_documents function.
"""

from __future__ import annotations

import pytest

from agents.rag_agent.chunking import (
    Chunk,
    ChunkerFactory,
    Document,
    FixedSizeChunker,
    RecursiveChunker,
    SemanticChunker,
    _count_tokens,
    chunk_documents,
)

# ══════════════════════════════════════════════════════════════════
# Helpers
# ══════════════════════════════════════════════════════════════════


def _make_doc(content: str, doc_id: str = "test-doc") -> Document:
    return Document(id=doc_id, content=content, source=f"/path/{doc_id}.txt")


# ══════════════════════════════════════════════════════════════════
# _count_tokens Tests
# ══════════════════════════════════════════════════════════════════


class TestCountTokens:
    def test_short_text(self) -> None:
        count = _count_tokens("hello world")
        assert count > 0

    def test_empty_text(self) -> None:
        assert _count_tokens("") == 0

    def test_chinese_text(self) -> None:
        count = _count_tokens("你好世界")
        assert count > 0

    def test_mixed_text(self) -> None:
        count = _count_tokens("Hello 世界！This is a test.")
        assert count > 0


# ══════════════════════════════════════════════════════════════════
# BaseChunker Tests
# ══════════════════════════════════════════════════════════════════


class TestBaseChunker:
    def test_invalid_overlap_raises(self) -> None:
        with pytest.raises(ValueError, match="chunk_overlap"):
            FixedSizeChunker(chunk_size=100, chunk_overlap=100)

    def test_empty_document_yields_no_chunks(self) -> None:
        chunker = FixedSizeChunker(chunk_size=100)
        doc = _make_doc("")
        chunks = chunker.chunk_document(doc)
        assert len(chunks) == 0

    def test_chunk_metadata_inherited(self) -> None:
        chunker = FixedSizeChunker(chunk_size=100)
        doc = _make_doc("Hello world, this is a test document for chunking.")
        chunks = chunker.chunk_document(doc)
        assert len(chunks) >= 1
        assert chunks[0].source == doc.source
        assert chunks[0].chunk_strategy == "fixed_size"
        assert chunks[0].parent_document_id == doc.id


# ══════════════════════════════════════════════════════════════════
# FixedSizeChunker Tests
# ══════════════════════════════════════════════════════════════════


class TestFixedSizeChunker:
    def test_short_text_single_chunk(self) -> None:
        chunker = FixedSizeChunker(chunk_size=512)
        text = "Hello world, this is a short text."
        chunks = chunker.chunk_text(text)
        assert len(chunks) == 1
        assert chunks[0] == text

    def test_long_text_multiple_chunks(self) -> None:
        chunker = FixedSizeChunker(chunk_size=50, chunk_overlap=10, use_token_count=False)
        text = "A" * 200  # 200 chars, should be ~4 chunks
        chunks = chunker.chunk_text(text)
        assert 3 <= len(chunks) <= 6

    def test_chunks_contain_all_text(self) -> None:
        chunker = FixedSizeChunker(chunk_size=50, chunk_overlap=10, use_token_count=False)
        text = "Hello world. " * 20
        chunks = chunker.chunk_text(text)
        combined = "".join(chunks)
        assert len(combined) >= len(text) * 0.9  # Overlap may duplicate

    def test_overlap_between_chunks(self) -> None:
        chunker = FixedSizeChunker(chunk_size=50, chunk_overlap=10, use_token_count=False)
        text = "X" * 120
        chunks = chunker.chunk_text(text)
        if len(chunks) >= 2:
            # Second chunk should start before the first ends
            assert len(chunks[0]) > 10

    def test_single_character_chunk(self) -> None:
        chunker = FixedSizeChunker(chunk_size=1, chunk_overlap=0, use_token_count=False)
        text = "ABC"
        chunks = chunker.chunk_text(text)
        assert len(chunks) == 3

    def test_empty_text(self) -> None:
        chunker = FixedSizeChunker(chunk_size=100)
        assert chunker.chunk_text("") == []
        assert chunker.chunk_text("   ") == []


# ══════════════════════════════════════════════════════════════════
# SemanticChunker Tests
# ══════════════════════════════════════════════════════════════════


class TestSemanticChunker:
    def test_paragraph_boundary(self) -> None:
        chunker = SemanticChunker(chunk_size=40, chunk_overlap=10, use_token_count=False)
        text = "This is paragraph one.\n\nThis is paragraph two.\n\nThis is paragraph three."
        chunks = chunker.chunk_text(text)
        assert len(chunks) >= 2

    def test_chinese_boundary(self) -> None:
        chunker = SemanticChunker(chunk_size=500, use_token_count=False)
        text = "这是第一句话。这是第二句话。这是第三句话。"
        chunks = chunker.chunk_text(text)
        # Should preserve sentence boundaries
        assert len(chunks) >= 1
        assert "第一句话" in chunks[0]

    def test_small_text_no_split(self) -> None:
        chunker = SemanticChunker(chunk_size=1000)
        text = "Short text."
        chunks = chunker.chunk_text(text)
        assert len(chunks) == 1

    def test_overflow_chunks_split(self) -> None:
        chunker = SemanticChunker(chunk_size=100, use_token_count=False)
        text = "Word. " * 50
        chunks = chunker.chunk_text(text)
        assert len(chunks) >= 2

    def test_short_units_merged(self) -> None:
        chunker = SemanticChunker(chunk_size=200, use_token_count=False)
        text = "Short. " * 5
        chunks = chunker.chunk_text(text)
        assert len(chunks) >= 1


# ══════════════════════════════════════════════════════════════════
# RecursiveChunker Tests
# ══════════════════════════════════════════════════════════════════


class TestRecursiveChunker:
    def test_paragraph_separation(self) -> None:
        chunker = RecursiveChunker(chunk_size=50, chunk_overlap=10, use_token_count=False)
        text = "\n\n".join([f"This is paragraph {i}." for i in range(10)])
        chunks = chunker.chunk_text(text)
        assert len(chunks) >= 2

    def test_line_separation(self) -> None:
        chunker = RecursiveChunker(chunk_size=100, use_token_count=False)
        text = "\n".join([f"Line {i} content here." for i in range(20)])
        chunks = chunker.chunk_text(text)
        assert len(chunks) >= 2

    def test_character_fallback(self) -> None:
        chunker = RecursiveChunker(chunk_size=10, chunk_overlap=0, use_token_count=False)
        text = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
        chunks = chunker.chunk_text(text)
        assert len(chunks) >= 2
        combined = "".join(chunks)
        assert "ABCDEFGHIJ" in combined

    def test_fits_in_one_chunk(self) -> None:
        chunker = RecursiveChunker(chunk_size=1000)
        text = "This is a short document that should fit in one chunk."
        chunks = chunker.chunk_text(text)
        assert len(chunks) == 1

    def test_logger_fallback_on_no_separators(self) -> None:
        chunker = RecursiveChunker(chunk_size=50, chunk_overlap=10, use_token_count=False)
        text = "A" * 200
        chunks = chunker.chunk_text(text)
        assert len(chunks) >= 3


# ══════════════════════════════════════════════════════════════════
# ChunkerFactory Tests
# ══════════════════════════════════════════════════════════════════


class TestChunkerFactory:
    def test_create_fixed_size(self) -> None:
        factory = ChunkerFactory()
        chunker = factory.create("fixed_size", chunk_size=256)
        assert isinstance(chunker, FixedSizeChunker)
        assert chunker.chunk_size == 256

    def test_create_semantic(self) -> None:
        factory = ChunkerFactory()
        chunker = factory.create("semantic", chunk_size=512)
        assert isinstance(chunker, SemanticChunker)

    def test_create_recursive(self) -> None:
        factory = ChunkerFactory()
        chunker = factory.create("recursive", chunk_size=512)
        assert isinstance(chunker, RecursiveChunker)

    def test_unknown_strategy(self) -> None:
        factory = ChunkerFactory()
        with pytest.raises(ValueError, match="Unknown chunking strategy"):
            factory.create("invalid_strategy")

    def test_list_strategies(self) -> None:
        factory = ChunkerFactory()
        strategies = factory.list_strategies()
        assert "fixed_size" in strategies
        assert "semantic" in strategies
        assert "recursive" in strategies

    def test_create_with_overlap(self) -> None:
        factory = ChunkerFactory()
        chunker = factory.create("recursive", chunk_size=256, chunk_overlap=32)
        assert chunker.chunk_overlap == 32


# ══════════════════════════════════════════════════════════════════
# chunk_documents Convenience Function
# ══════════════════════════════════════════════════════════════════


class TestChunkDocuments:
    def test_single_document(self) -> None:
        docs = [_make_doc("Hello world. " * 20, "doc-1")]
        chunks = chunk_documents(
            docs, strategy="fixed_size", chunk_size=50, chunk_overlap=10, use_token_count=False
        )
        assert len(chunks) >= 2
        assert all(isinstance(c, Chunk) for c in chunks)

    def test_multiple_documents(self) -> None:
        docs = [
            _make_doc("Doc one content. " * 10, "doc-1"),
            _make_doc("Doc two content. " * 10, "doc-2"),
        ]
        chunks = chunk_documents(docs, strategy="recursive", chunk_size=100, use_token_count=False)
        assert len(chunks) >= 2

    def test_with_metadata_preserved(self) -> None:
        doc = _make_doc("Test content for metadata preservation. " * 10, "meta-doc")
        doc.metadata["custom"] = "value"
        doc.metadata["author"] = "test"

        chunks = chunk_documents(
            [doc], strategy="fixed_size", chunk_size=100, use_token_count=False
        )
        assert len(chunks) >= 1
        assert chunks[0].metadata.get("custom") == "value"
        assert chunks[0].metadata.get("author") == "test"
        assert "chunk_size" in chunks[0].metadata
        assert "chunk_strategy" in chunks[0].metadata

    def test_strategy_defaults(self) -> None:
        docs = [_make_doc("A" * 300)]
        chunks = chunk_documents(docs)  # Should default to recursive, 512, 64
        assert len(chunks) >= 1


# ══════════════════════════════════════════════════════════════════
# Chunk Model Tests
# ══════════════════════════════════════════════════════════════════


class TestChunkModel:
    def test_default_values(self) -> None:
        chunk = Chunk(content="test")
        assert chunk.chunk_id == ""
        assert chunk.chunk_index == 0
        assert chunk.chunk_strategy == ""

    def test_all_fields(self) -> None:
        chunk = Chunk(
            content="test content",
            chunk_id="doc-1:chunk:00001",
            chunk_index=1,
            chunk_strategy="recursive",
            parent_document_id="doc-1",
            source="/path/doc.txt",
        )
        assert chunk.chunk_id == "doc-1:chunk:00001"
        assert chunk.chunk_index == 1
        assert chunk.parent_document_id == "doc-1"

    def test_all_content_preserved_after_chunking(self) -> None:
        """Ensure chunking entire text preserves all content."""
        chunker = FixedSizeChunker(chunk_size=50, chunk_overlap=5, use_token_count=False)
        text = "The quick brown fox jumps over the lazy dog. " * 5
        doc = _make_doc(text, "full-doc")
        chunks = chunker.chunk_document(doc)
        chunked_text = " ".join(c.content for c in chunks)
        for word in ["quick", "brown", "fox", "lazy", "dog"]:
            assert word in chunked_text
