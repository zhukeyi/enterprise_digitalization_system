"""Hybrid search engine — BM25 + vector search + RRF fusion.

M1-T12: Combines keyword retrieval (BM25) with semantic retrieval
(vector embeddings) using Reciprocal Rank Fusion (RRF) for
re-ranking. Supports configurable weights per search method.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, Field

logger = logging.getLogger("fde.rag.retriever")

# ══════════════════════════════════════════════════════════════════
# Data Models
# ══════════════════════════════════════════════════════════════════


class SearchResult(BaseModel):
    """A single search result from the hybrid engine."""

    id: str
    content: str
    score: float = Field(default=0.0, description="Combined RRF score")
    vector_score: float | None = Field(default=None)
    bm25_score: float | None = Field(default=None)
    metadata: dict[str, Any] = Field(default_factory=dict)
    source: str = Field(default="")
    rank: int = Field(default=0)


# ══════════════════════════════════════════════════════════════════
# BM25 Index (in-memory)
# ══════════════════════════════════════════════════════════════════


class BM25Index:
    """In-memory BM25 index using rank_bm25 library.

    Supports Chinese text via jieba tokenization fallback,
    and English text via whitespace splitting.
    """

    def __init__(self, language: str = "mixed") -> None:
        self.language = language
        self._bm25: Any = None
        self._documents: list[str] = []
        self._doc_ids: list[str] = []
        self._doc_metadatas: list[dict[str, Any]] = []
        self._is_built: bool = False

    def index_documents(
        self,
        texts: list[str],
        ids: list[str] | None = None,
        metadatas: list[dict[str, Any]] | None = None,
    ) -> None:
        """Index a batch of documents for BM25 retrieval.

        Args:
            texts: Document text contents.
            ids: Optional document IDs (auto-generated if None).
            metadatas: Optional metadata per document.
        """
        from rank_bm25 import BM25Okapi

        self._documents = list(texts)
        self._doc_ids = list(ids) if ids else [f"doc-{i}" for i in range(len(texts))]
        self._doc_metadatas = list(metadatas) if metadatas else [{} for _ in texts]

        # Pre-tokenize and pass as list-of-lists (tokenizer=None means pre-tokenized)
        tokenized = [self._tokenize(t) for t in texts]
        self._bm25 = BM25Okapi(tokenized, tokenizer=None)
        self._is_built = True
        logger.info("BM25 index built with %d documents", len(texts))

    def _tokenize(self, text: str) -> list[str]:
        """Tokenize text for BM25.

        For Chinese text: use jieba tokenization.
        For mixed/English text: whitespace split + jieba, then merge.
        """
        if self.language == "chinese":
            return self._tokenize_chinese(text)

        # Mixed mode: jieba for Chinese + whitespace for English
        import re

        tokens: list[str] = []
        for part in re.split(r"([\u4e00-\u9fff]+)", text):
            if re.match(r"[\u4e00-\u9fff]+$", part):
                # Chinese segment: use jieba
                tokens.extend(self._tokenize_chinese(part))
            else:
                # Non-Chinese: whitespace split
                w = part.strip().lower()
                if w:
                    tokens.extend(w.split())
        return tokens

    @staticmethod
    def _tokenize_chinese(text: str) -> list[str]:
        """Tokenize Chinese text using jieba."""
        try:
            import jieba

            return list(jieba.cut(text))
        except ImportError:
            # Fallback: simple character-level for CJK
            import re

            tokens: list[str] = []
            for part in re.split(r"([\u4e00-\u9fff]+)", text):
                if re.match(r"[\u4e00-\u9fff]+", part):
                    # Chinese: character-level tokenization
                    tokens.extend(list(part))
                else:
                    # Non-Chinese: whitespace split
                    tokens.extend(part.lower().split())
            return tokens

    def search(
        self,
        query: str,
        top_k: int = 10,
    ) -> list[SearchResult]:
        """Search the BM25 index.

        Args:
            query: Search query.
            top_k: Max results to return.

        Returns:
            List of SearchResult objects with BM25 scores.
        """
        if not self._is_built or self._bm25 is None:
            logger.warning("BM25 index not built yet")
            return []

        tokenized_query = self._tokenize(query)
        scores = self._bm25.get_scores(tokenized_query)

        # Get top-k indices
        indexed = list(enumerate(scores))
        indexed.sort(key=lambda x: x[1], reverse=True)
        top_indices = indexed[:top_k]

        results: list[SearchResult] = []
        for rank, (idx, score) in enumerate(top_indices):
            if score <= 0:
                continue
            results.append(
                SearchResult(
                    id=self._doc_ids[idx] if idx < len(self._doc_ids) else f"idx-{idx}",
                    content=self._documents[idx] if idx < len(self._documents) else "",
                    bm25_score=round(float(score), 4),
                    metadata=self._doc_metadatas[idx] if idx < len(self._doc_metadatas) else {},
                    rank=rank + 1,
                )
            )

        return results

    @property
    def document_count(self) -> int:
        return len(self._documents)


# ══════════════════════════════════════════════════════════════════
# RRF (Reciprocal Rank Fusion)
# ══════════════════════════════════════════════════════════════════


def rrf_fusion(
    result_lists: list[list[SearchResult]],
    weights: list[float] | None = None,
    k: int = 60,
    top_k: int = 10,
) -> list[SearchResult]:
    """Fuse multiple ranked result lists using Reciprocal Rank Fusion.

    RRF score for each document = sum( weight_i / (k + rank_i) )

    Args:
        result_lists: List of ranked result lists from different methods.
        weights: Per-method weights (default: equal).
        k: RRF constant (default 60, typical range 30-100).
        top_k: Max results in final fused list.

    Returns:
        Fused and re-ranked list of SearchResult objects.
    """
    if not result_lists:
        return []

    if weights is None:
        weights = [1.0] * len(result_lists)

    if len(weights) != len(result_lists):
        raise ValueError("weights length must match result_lists length")

    # Accumulate RRF scores per document ID
    rrf_scores: dict[str, tuple[float, SearchResult]] = {}

    for method_idx, results in enumerate(result_lists):
        weight = weights[method_idx]
        for rank, result in enumerate(results):
            doc_id = result.id
            rrf_score = weight / (k + rank + 1)

            if doc_id in rrf_scores:
                existing_score, existing_result = rrf_scores[doc_id]
                rrf_scores[doc_id] = (
                    existing_score + rrf_score,
                    existing_result,
                )
            else:
                rrf_scores[doc_id] = (rrf_score, result)

    # Sort by RRF score descending
    sorted_results = sorted(
        rrf_scores.items(), key=lambda x: x[1][0], reverse=True
    )

    # Build final list
    fused: list[SearchResult] = []
    for rank, (doc_id, (score, result)) in enumerate(sorted_results[:top_k]):
        result.score = round(score, 4)
        result.rank = rank + 1
        fused.append(result)

    return fused


# ══════════════════════════════════════════════════════════════════
# Hybrid Search Engine
# ══════════════════════════════════════════════════════════════════


@dataclass
class HybridSearchConfig:
    """Configuration for the hybrid search engine."""

    bm25_weight: float = 1.0
    vector_weight: float = 1.0
    rrf_k: int = 60
    top_k_final: int = 10
    top_k_each: int = 20  # How many results to fetch from each method
    score_threshold: float = 0.0


class HybridSearchEngine:
    """Hybrid search engine — BM25 + Vector search + RRF fusion.

    Usage:
        engine = HybridSearchEngine(vector_store, embed_model)
        engine.index_documents(texts, ids, metadatas)
        results = await engine.search("user query")
    """

    def __init__(
        self,
        vector_store: Any | None = None,
        embedding_model: Any | None = None,
        config: HybridSearchConfig | None = None,
    ) -> None:
        self.vector_store = vector_store
        self.embedding_model = embedding_model
        self.config = config or HybridSearchConfig()
        self.bm25_index = BM25Index(language="mixed")
        self._documents: list[str] = []
        self._doc_ids: list[str] = []
        self._doc_metadatas: list[dict[str, Any]] = []

    def index_documents(
        self,
        texts: list[str],
        ids: list[str] | None = None,
        metadatas: list[dict[str, Any]] | None = None,
    ) -> None:
        """Index documents for hybrid search.

        Builds BM25 index (in-memory) and optionally stores
        metadata for result enrichment.

        Args:
            texts: Document text contents.
            ids: Document IDs.
            metadatas: Document metadata.
        """
        self._documents = list(texts)
        self._doc_ids = list(ids) if ids else [f"doc-{i}" for i in range(len(texts))]
        self._doc_metadatas = list(metadatas) if metadatas else [{} for _ in texts]

        self.bm25_index.index_documents(texts, self._doc_ids, self._doc_metadatas)
        logger.info("Hybrid search indexed %d documents", len(texts))

    async def search(
        self,
        query: str,
        filter_conditions: dict[str, Any] | None = None,
    ) -> list[SearchResult]:
        """Perform hybrid search.

        Runs BM25 search and vector search in parallel, then
        fuses results using RRF.

        Args:
            query: Search query text.
            filter_conditions: Optional filter for vector search.

        Returns:
            Fused search results.
        """
        import asyncio

        # Run BM25 + vector search concurrently
        bm25_coro = asyncio.to_thread(self._search_bm25, query)
        vector_coro = self._search_vector(query, filter_conditions)

        bm25_results, vector_results = await asyncio.gather(
            bm25_coro, vector_coro
        )

        # RRF fusion
        result_lists = []
        weights = []

        if bm25_results:
            result_lists.append(bm25_results)
            weights.append(self.config.bm25_weight)

        if vector_results:
            result_lists.append(vector_results)
            weights.append(self.config.vector_weight)

        if not result_lists:
            return []

        fused = rrf_fusion(
            result_lists,
            weights=weights,
            k=self.config.rrf_k,
            top_k=self.config.top_k_final,
        )

        # Enrich results with document metadata
        for result in fused:
            self._enrich_result(result)

        logger.info(
            "Hybrid search: query='%s' bm25=%d vector=%d fused=%d",
            query[:50],
            len(bm25_results),
            len(vector_results),
            len(fused),
        )
        return fused

    def _search_bm25(self, query: str) -> list[SearchResult]:
        """Run BM25 search."""
        return self.bm25_index.search(query, top_k=self.config.top_k_each)

    async def _search_vector(
        self,
        query: str,
        filter_conditions: dict[str, Any] | None = None,
    ) -> list[SearchResult]:
        """Run vector search via embedding + Qdrant."""
        if self.embedding_model is None or self.vector_store is None:
            logger.debug("Vector search unavailable: model or store not set")
            return []

        try:
            # Encode query
            query_vector = await self.embedding_model.encode_queries([query])
            if not query_vector:
                return []
            query_vector = query_vector[0]

            # Search Qdrant
            records = self.vector_store.search(
                vector=query_vector,
                top_k=self.config.top_k_each,
                score_threshold=self.config.score_threshold,
                filter_conditions=filter_conditions,
            )

            return [
                SearchResult(
                    id=str(r.id),
                    content=r.payload.get("text", ""),
                    vector_score=round(float(r.score), 4) if r.score else 0.0,
                    metadata=r.payload,
                    rank=i + 1,
                )
                for i, r in enumerate(records)
            ]

        except Exception as e:
            logger.warning("Vector search failed: %s", e)
            return []

    def _enrich_result(self, result: SearchResult) -> None:
        """Enrich search result with document metadata."""
        # If we have local document data, fill in content/metadata
        for idx, doc_id in enumerate(self._doc_ids):
            if doc_id == result.id and idx < len(self._documents):
                if not result.content:
                    result.content = self._documents[idx]
                if not result.metadata and idx < len(self._doc_metadatas):
                    result.metadata = self._doc_metadatas[idx]
                break


# ══════════════════════════════════════════════════════════════════
# Convenience Builder
# ══════════════════════════════════════════════════════════════════


async def build_hybrid_search(
    vector_store: Any,
    embedding_model: Any,
    texts: list[str],
    ids: list[str] | None = None,
    metadatas: list[dict[str, Any]] | None = None,
    config: HybridSearchConfig | None = None,
) -> HybridSearchEngine:
    """Convenience: build a hybrid search engine with indexed documents.

    Args:
        vector_store: Qdrant vector store instance.
        embedding_model: BGE-M3 embedding model instance.
        texts: Document texts to index.
        ids: Optional document IDs.
        metadatas: Optional metadata per document.
        config: Search configuration.

    Returns:
        Configured HybridSearchEngine.
    """
    engine = HybridSearchEngine(
        vector_store=vector_store,
        embedding_model=embedding_model,
        config=config,
    )
    engine.index_documents(texts, ids, metadatas)
    return engine