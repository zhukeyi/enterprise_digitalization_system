"""Tests for hybrid search engine (BM25 + Vector + RRF).

M1-T12: Tests cover BM25 index, RRF fusion, and the HybridSearchEngine
with mocked vector store and embedding model.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from agents.rag_agent.retriever import (
    BM25Index,
    HybridSearchConfig,
    HybridSearchEngine,
    SearchResult,
    build_hybrid_search,
    rrf_fusion,
)
from agents.rag_agent.vector_store import VectorRecord


# ══════════════════════════════════════════════════════════════════
# Fixtures
# ══════════════════════════════════════════════════════════════════


@pytest.fixture
def sample_documents() -> list[str]:
    return [
        "The quick brown fox jumps over the lazy dog",
        "Machine learning is transforming artificial intelligence",
        "Python is a popular programming language for data science",
        "Beijing is the capital of China with a rich history",
        "Natural language processing enables computers to understand text",
    ]


@pytest.fixture
def sample_ids() -> list[str]:
    return ["doc-1", "doc-2", "doc-3", "doc-4", "doc-5"]


@pytest.fixture
def bm25_index(sample_documents: list[str], sample_ids: list[str]) -> BM25Index:
    idx = BM25Index(language="mixed")
    idx.index_documents(sample_documents, sample_ids)
    return idx


# ══════════════════════════════════════════════════════════════════
# BM25Index Tests
# ══════════════════════════════════════════════════════════════════


class TestBM25Index:
    def test_index_and_search(self, bm25_index: BM25Index) -> None:
        """Search returns relevant results sorted by score."""
        results = bm25_index.search("machine learning AI", top_k=5)
        assert len(results) > 0
        # "Machine learning" doc should be ranked high
        assert any("machine" in r.content.lower() for r in results)
        assert all(r.bm25_score is not None for r in results)

    def test_search_empty_index(self) -> None:
        idx = BM25Index()
        results = idx.search("test")
        assert results == []

    def test_search_relevance_ranking(self, bm25_index: BM25Index) -> None:
        """Documents matching more query terms rank higher."""
        results = bm25_index.search("machine learning AI", top_k=3)
        if len(results) >= 1:
            # The ML doc should be first
            assert results[0].rank == 1
            assert "machine" in results[0].content.lower()

    def test_ids_and_metadata(self) -> None:
        idx = BM25Index()
        idx.index_documents(
            ["hello world", "foo bar", "machine learning", "data science", "python programming"],
            ids=["custom-1", "custom-2", "custom-3", "custom-4", "custom-5"],
            metadatas=[
                {"type": "greeting"}, {"type": "test"}, {"type": "ml"},
                {"type": "data"}, {"type": "lang"},
            ],
        )
        results = idx.search("hello", top_k=5)
        assert len(results) >= 1, f"Expected at least 1 result, got {len(results)}"
        assert results[0].id == "custom-1"
        assert results[0].metadata.get("type") == "greeting"

    def test_chinese_tokenization(self) -> None:
        idx = BM25Index(language="chinese")
        idx.index_documents(
            ["学习编程很有用", "人工智能发展迅速", "机器学习很强大", "数据科学很热门"],
        )
        results = idx.search("编程", top_k=5)
        assert len(results) >= 1, f"Expected >=1 results for Chinese query, got {len(results)}"

    def test_document_count(self, bm25_index: BM25Index) -> None:
        assert bm25_index.document_count == 5

    def test_zero_score_filter(self, bm25_index: BM25Index) -> None:
        """Documents with zero BM25 score should be excluded."""
        results = bm25_index.search("zzzzzzz_nonexistent_word_xxxxx", top_k=5)
        assert len(results) == 0


# ══════════════════════════════════════════════════════════════════
# RRF Fusion Tests
# ══════════════════════════════════════════════════════════════════


class TestRRFFusion:
    def test_fusion_combines_results(self) -> None:
        """Two ranked lists should be combined with RRF."""
        list_a = [
            SearchResult(id="a", content="doc a", rank=1),
            SearchResult(id="b", content="doc b", rank=2),
        ]
        list_b = [
            SearchResult(id="b", content="doc b", rank=1),
            SearchResult(id="c", content="doc c", rank=2),
        ]

        fused = rrf_fusion([list_a, list_b], top_k=5)
        assert len(fused) == 3  # a, b, c combined
        # b appears in both lists so should rank higher
        assert any(r.id == "b" for r in fused)
        assert any(r.id == "a" for r in fused)
        assert any(r.id == "c" for r in fused)

    def test_fusion_with_weights(self) -> None:
        list_a = [
            SearchResult(id="a", content="doc a", rank=1),
            SearchResult(id="b", content="doc b", rank=2),
        ]
        list_b = [
            SearchResult(id="b", content="doc b", rank=1),
        ]

        # Heavier weight on list_a
        fused = rrf_fusion([list_a, list_b], weights=[2.0, 1.0], top_k=5)
        assert len(fused) >= 2

    def test_empty_lists(self) -> None:
        assert rrf_fusion([]) == []
        assert rrf_fusion([[]]) == []

    def test_top_k_limit(self) -> None:
        docs_a = [SearchResult(id=f"doc-{i}", content=f"doc {i}", rank=i + 1) for i in range(20)]
        fused = rrf_fusion([docs_a], top_k=5)
        assert len(fused) == 5

    def test_weight_mismatch_raises(self) -> None:
        with pytest.raises(ValueError, match="weights length"):
            rrf_fusion([[SearchResult(id="a", content="a")]], weights=[1.0, 2.0])

    def test_shared_id_boost(self) -> None:
        """Documents appearing in multiple ranked lists get a score boost."""
        list_a = [SearchResult(id="x", content="shared", rank=1)]
        list_b = [SearchResult(id="x", content="shared", rank=2)]

        fused = rrf_fusion([list_a, list_b], top_k=5)
        assert len(fused) == 1
        # Score should be sum of both ranks' contributions
        assert fused[0].score > 0.01


# ══════════════════════════════════════════════════════════════════
# HybridSearchEngine Tests (mocked)
# ══════════════════════════════════════════════════════════════════


class TestHybridSearchEngine:
    async def test_search_with_mocked_vector(
        self, sample_documents: list[str], sample_ids: list[str]
    ) -> None:
        """Full hybrid search with mocked vector and BM25."""
        engine = HybridSearchEngine()
        engine.index_documents(sample_documents, sample_ids)

        # Mock embedding model
        mock_embed = AsyncMock()
        mock_embed.encode_queries.return_value = [[0.1] * 1024]

        # Mock vector store
        mock_store = MagicMock()
        mock_store.search.return_value = [
            VectorRecord(id="doc-2", payload={"text": "ML text"}, score=0.9),
        ]

        engine.embedding_model = mock_embed
        engine.vector_store = mock_store

        results = await engine.search("machine learning")
        assert len(results) >= 1
        mock_embed.encode_queries.assert_called_once()
        mock_store.search.assert_called_once()

    async def test_search_bm25_only(self, sample_documents: list[str], sample_ids: list[str]) -> None:
        """Search should work with BM25 only (no vector configured)."""
        engine = HybridSearchEngine()
        engine.index_documents(sample_documents, sample_ids)

        results = await engine.search("machine learning")
        assert len(results) >= 1
        assert all(r.bm25_score is not None for r in results)

    async def test_search_no_index(self) -> None:
        engine = HybridSearchEngine()
        results = await engine.search("test")
        assert results == []

    async def test_index_no_ids(self) -> None:
        engine = HybridSearchEngine()
        engine.index_documents(["hello world", "foo bar", "machine learning"])
        results = await engine.search("hello")
        assert len(results) >= 1
        assert "doc-0" in results[0].id

    async def test_vector_search_fallback_on_error(
        self, sample_documents: list[str], sample_ids: list[str]
    ) -> None:
        """If vector search fails, engine should gracefully fall back to BM25."""
        engine = HybridSearchEngine()
        engine.index_documents(sample_documents, sample_ids)

        mock_embed = AsyncMock()
        mock_embed.encode_queries.side_effect = RuntimeError("API error")

        mock_store = MagicMock()
        engine.embedding_model = mock_embed
        engine.vector_store = mock_store

        results = await engine.search("machine learning")
        assert len(results) >= 1  # Should fall back to BM25 results

    async def test_config_weights(self) -> None:
        config = HybridSearchConfig(bm25_weight=2.0, vector_weight=0.5)
        engine = HybridSearchEngine(config=config)
        assert engine.config.bm25_weight == 2.0
        assert engine.config.vector_weight == 0.5


# ══════════════════════════════════════════════════════════════════
# Build Helper Tests
# ══════════════════════════════════════════════════════════════════


class TestBuildHybridSearch:
    async def test_build(self) -> None:
        mock_store = MagicMock()
        mock_embed = MagicMock()

        engine = await build_hybrid_search(
            vector_store=mock_store,
            embedding_model=mock_embed,
            texts=["hello", "world"],
            ids=["h1", "w1"],
        )
        assert isinstance(engine, HybridSearchEngine)
        assert engine.bm25_index.document_count == 2


# ══════════════════════════════════════════════════════════════════
# SearchResult Tests
# ══════════════════════════════════════════════════════════════════


class TestSearchResult:
    def test_defaults(self) -> None:
        r = SearchResult(id="d1", content="test")
        assert r.score == 0.0
        assert r.vector_score is None
        assert r.bm25_score is None
        assert r.metadata == {}
        assert r.source == ""
        assert r.rank == 0

    def test_all_fields(self) -> None:
        r = SearchResult(
            id="d1",
            content="content",
            score=0.95,
            vector_score=0.9,
            bm25_score=0.8,
            metadata={"type": "pdf"},
            source="/path/doc.pdf",
            rank=1,
        )
        assert r.score == 0.95
        assert r.vector_score == 0.9
        assert r.source == "/path/doc.pdf"