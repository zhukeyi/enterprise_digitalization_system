"""RAG Agent integration with LangGraph Orchestrator.

Bridges the existing RAG pipeline (Qdrant + BM25 + BGE-M3) to the
Supervisor-Worker framework via ToolRegistry.

Registered tools:
- rag_search: Hybrid search (BM25 + vector + RRF fusion)
- rag_ingest: Ingest documents into vector store
- rag_answer: Generate grounded answer from retrieved context (zero hallucination)

M1-T4: RAGFlow migration to LangGraph
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from collections.abc import Callable
from typing import Any

from agents.orchestrator.tools.registry import ToolDefinition, ToolRegistry
from agents.rag_agent import (
    CollectionConfig,
    HybridSearchConfig,
    HybridSearchEngine,
    ParserFactory,
    QdrantConfig,
    VectorStore,
    chunk_documents,
)
from agents.rag_agent.embeddings import EmbeddingConfig, EmbeddingError, EmbeddingModel

logger = logging.getLogger("fde.rag.integration")

# Module-level cached singletons (avoids creating new Qdrant connections
# and reloading the embedding model on every call)
_vector_store_instance: VectorStore | None = None
_embedding_model_instance: EmbeddingModel | None = None

# Default collection name for RAG operations
_DEFAULT_COLLECTION = "fde_knowledge"

# Namespace for deriving stable UUID point IDs from chunk IDs.
# Qdrant requires point IDs to be unsigned ints or UUIDs, while our
# chunk IDs are path-based strings. We hash them to a UUID so the BM25
# index and the Qdrant vector store share one ID space (required for
# correct RRF fusion and result enrichment).
_CHUNK_ID_NAMESPACE = uuid.NAMESPACE_URL


def _get_vector_store() -> VectorStore:
    """Get or create a singleton VectorStore instance.

    Defaults to the RAG knowledge collection so search/ingest share the
    same collection name (QdrantConfig's own default is 'fde_documents',
    which would otherwise diverge from the integration's _DEFAULT_COLLECTION).
    """
    global _vector_store_instance
    if _vector_store_instance is None:
        _vector_store_instance = VectorStore(QdrantConfig(collection_name=_DEFAULT_COLLECTION))
    return _vector_store_instance


def _get_embedding_model() -> EmbeddingModel:
    """Get or create a singleton EmbeddingModel instance.

    The BGE-M3 model is lazily loaded on first use (first embed call
    takes ~60s for model loading; subsequent calls are fast).
    """
    global _embedding_model_instance
    if _embedding_model_instance is None:
        _embedding_model_instance = EmbeddingModel(EmbeddingConfig())
    return _embedding_model_instance


def _reset_vector_store() -> None:
    """Reset the VectorStore singleton (for testing)."""
    global _vector_store_instance
    _vector_store_instance = None


def _reset_embedding_model() -> None:
    """Reset the EmbeddingModel singleton (for testing)."""
    global _embedding_model_instance
    if _embedding_model_instance is not None:
        _embedding_model_instance.unload()
    _embedding_model_instance = None


# ══════════════════════════════════════════════════════════════════
# RAG Tool Handlers
# ══════════════════════════════════════════════════════════════════


# ══════════════════════════════════════════════════════════════════
# Shared BM25 Index (populated by rag_ingest, used by rag_search)
# ══════════════════════════════════════════════════════════════════

_bm25_engine: HybridSearchEngine | None = None


def _rebuild_bm25_index(texts: list[str], ids: list[str]) -> None:
    """Rebuild the shared BM25 index after ingesting new documents.

    This index is used by _rag_search_handler for the BM25 leg of
    hybrid search. The vector leg queries Qdrant directly.
    """
    global _bm25_engine
    try:
        vs = _get_vector_store()
        em = _get_embedding_model()
    except Exception:
        vs = None  # type: ignore[assignment]
        em = None  # type: ignore[assignment]

    _bm25_engine = HybridSearchEngine(
        vector_store=vs,
        embedding_model=em,
        config=HybridSearchConfig(),
    )
    _bm25_engine.index_documents(texts, ids)
    logger.info("BM25 index rebuilt with %d chunks", len(texts))


async def _rag_search_handler(query: str, top_k: int = 5) -> dict[str, Any]:
    """Execute hybrid search via BM25 + vector + RRF fusion.

    Uses the singleton VectorStore and EmbeddingModel for vector search,
    plus an in-memory BM25 index built from documents ingested via
    rag_ingest. If the embedding model or vector store is unavailable,
    degrades gracefully to BM25-only search.

    Args:
        query: Search query string.
        top_k: Number of results to return.

    Returns:
        Dictionary with search results (may be empty if index is empty).
    """
    try:
        config = HybridSearchConfig(top_k_final=top_k)

        # Use the shared engine (built by rag_ingest with both BM25 index
        # and vector store + embedding model). If not yet built (no docs
        # ingested), create a fresh one with vector search only.
        global _bm25_engine
        if _bm25_engine is not None:
            _bm25_engine.config = config
            engine = _bm25_engine
        else:
            try:
                vs = _get_vector_store()
                em = _get_embedding_model()
                engine = HybridSearchEngine(
                    vector_store=vs,
                    embedding_model=em,
                    config=config,
                )
            except Exception as e:
                logger.warning("Vector search components unavailable, BM25-only: %s", e)
                engine = HybridSearchEngine(config=config)

        results = await engine.search(query)

        return {
            "query": query,
            "total_results": len(results),
            "results": [
                {
                    "content": r.content[:200],
                    "score": r.score,
                    "vector_score": r.vector_score,
                    "source": r.source or r.metadata.get("source", "unknown"),
                    "chunk_id": r.id,
                }
                for r in results
            ],
        }
    except (RuntimeError, ValueError, TypeError, ConnectionError, TimeoutError, OSError) as e:
        logger.error("rag_search failed: %s", e)
        return {"error": str(e), "query": query}


# ══════════════════════════════════════════════════════════════════
# RAG Answer Handler (Zero-Hallucination LLM Synthesis)
# ══════════════════════════════════════════════════════════════════


# Confidence threshold below which a low-confidence warning is emitted
_LOW_CONFIDENCE_THRESHOLD = 0.3


async def _rag_answer_handler(
    query: str,
    top_k: int = 5,
    context_chunks: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Generate a grounded answer from retrieved context (zero hallucination).

    Uses a deterministic extractive summarizer in dev mode:
    - Takes the top-scoring chunk as the primary answer
    - Lists all sources with their relevance scores
    - If top score < 0.3, emits a low-confidence warning
    - Never fabricates information outside the provided context

    In production, this would call an LLM with a grounding prompt that
    instructs the model to only use provided context and cite sources.

    Args:
        query: User's question.
        top_k: Number of chunks to retrieve (ignored if context_chunks given).
        context_chunks: Pre-retrieved chunks to synthesize from. If None,
            rag_search is called automatically.

    Returns:
        Dictionary with answer, sources, query, confidence, total_sources.
    """
    # Step 1: Get context chunks (from caller or via search)
    if context_chunks is None:
        search_result = await _rag_search_handler(query=query, top_k=top_k)
        if "error" in search_result:
            return {
                "answer": "检索失败，无法生成答案。",
                "sources": [],
                "query": query,
                "confidence": 0.0,
                "total_sources": 0,
                "error": search_result["error"],
            }
        context_chunks = search_result.get("results", [])

    # Step 2: Handle empty results
    if not context_chunks:
        return {
            "answer": "未找到相关文档，无法生成答案。",
            "sources": [],
            "query": query,
            "confidence": 0.0,
            "total_sources": 0,
        }

    # Step 3: Extractive summarization (deterministic, no LLM needed)
    top_chunk = context_chunks[0]
    # Confidence should reflect the actual semantic similarity (vector_score),
    # not the RRF fusion score (which is rank-based and ~0.016 for any query).
    top_score = float(top_chunk.get("vector_score") or top_chunk.get("score", 0.0))
    confidence = min(top_score, 1.0)

    # Primary answer: top-scoring chunk content
    primary_content = str(top_chunk.get("content", ""))[:500]

    # Build sources list
    sources = [
        {
            "content_preview": str(c.get("content", ""))[:200],
            "score": c.get("score", 0.0),
            "source": c.get("source", "unknown"),
            "chunk_id": c.get("chunk_id", ""),
        }
        for c in context_chunks
    ]

    # Step 4: Generate answer with confidence assessment
    if confidence < _LOW_CONFIDENCE_THRESHOLD:
        answer = (
            f"基于检索到的文档，置信度较低（{confidence:.2f}）。"
            f"最相关的内容为：{primary_content}"
        )
    else:
        answer = f"根据知识库文档，{primary_content}"

    return {
        "answer": answer,
        "sources": sources,
        "query": query,
        "confidence": round(confidence, 4),
        "total_sources": len(sources),
    }


async def _rag_ingest_handler(
    documents: list[dict[str, Any]],
    collection_name: str = "fde_knowledge",
) -> dict[str, Any]:
    """Ingest documents into the vector store.

    Args:
        documents: List of document dicts with 'path' and 'format' keys.
        collection_name: Target collection name.

    Returns:
        Dictionary with ingestion results.
    """
    return await asyncio.to_thread(_rag_ingest_sync, documents, collection_name)


def _rag_ingest_sync(
    documents: list[dict[str, Any]],
    collection_name: str = "fde_knowledge",
) -> dict[str, Any]:
    """Synchronous implementation of RAG ingest (offloaded to thread).

    Full pipeline: parse → chunk → embed (BGE-M3) → upsert to Qdrant.
    Also builds the in-memory BM25 index for hybrid search.
    """
    try:
        vector_store = _get_vector_store()

        # Get embedding model (lazy load on first call)
        embedding_model = _get_embedding_model()

        # Force-load the model so we know its true embedding dimension,
        # then create the collection with a matching vector size.
        try:
            _ = embedding_model.model  # triggers lazy load / download
        except EmbeddingError as e:
            logger.warning("Embedding model unavailable, using default dim 1024: %s", e)
        vector_size = embedding_model.get_dimension()
        collection_config = CollectionConfig(name=collection_name, vector_size=vector_size)
        vector_store.create_collection(collection_config)

        ingested_count = 0
        errors: list[str] = []
        all_chunks_text: list[str] = []
        all_chunks_ids: list[str] = []

        for doc_info in documents:
            try:
                # Validate required keys
                doc_path = doc_info.get("path")
                if not doc_path:
                    raise ValueError(f"Document info missing 'path' key: {doc_info}")

                # Parse document — returns list[Document] (Pydantic BaseModel)
                parser = ParserFactory().get_parser(doc_path)
                parsed_pages = parser.parse(doc_path)

                # Chunk documents
                chunks = chunk_documents(parsed_pages)
                logger.info("Parsed %s → %d chunks", doc_path, len(chunks))

                # Batch embed all chunks from this document
                chunk_texts = [c.content for c in chunks]
                # Qdrant requires point IDs to be unsigned ints or UUIDs,
                # but chunk IDs are path-based strings. Derive a stable
                # UUID so BM25 and the vector store share one ID space.
                chunk_ids = [
                    str(uuid.uuid5(_CHUNK_ID_NAMESPACE, c.chunk_id or f"chunk-{c.chunk_index}"))
                    for c in chunks
                ]

                if chunk_texts:
                    # Generate embeddings via BGE-M3
                    embed_results = embedding_model._embed_sync(chunk_texts)
                    vectors = [r.vector for r in embed_results]

                    # Build VectorRecords with actual vectors
                    from agents.rag_agent.vector_store import VectorRecord

                    records = []
                    for chunk, vec, cid in zip(chunks, vectors, chunk_ids, strict=True):
                        vr = VectorRecord(
                            id=cid,
                            vector=vec,
                            payload={
                                "text": chunk.content,
                                "source": chunk.source,
                                "chunk_id": chunk.chunk_id,
                                "chunk_index": chunk.chunk_index,
                                "chunk_strategy": chunk.chunk_strategy,
                                **chunk.metadata,
                            },
                        )
                        records.append(vr)

                    # Batch upsert to Qdrant
                    vector_store.upsert(points=records, collection=collection_name)

                    # Collect for BM25 index
                    all_chunks_text.extend(chunk_texts)
                    all_chunks_ids.extend(chunk_ids)

                ingested_count += 1
                logger.info("Ingested %s: %d chunks embedded + stored", doc_path, len(chunks))
            except (RuntimeError, ValueError, TypeError, KeyError, OSError) as e:
                errors.append(f"Document {doc_info.get('path', '?')}: {e}")

        # Rebuild BM25 index with all ingested chunks
        if all_chunks_text:
            _rebuild_bm25_index(all_chunks_text, all_chunks_ids)

        return {
            "collection": collection_name,
            "ingested": ingested_count,
            "total": len(documents),
            "errors": errors,
        }
    except (RuntimeError, ValueError, TypeError, ConnectionError, OSError) as e:
        logger.error("rag_ingest failed: %s", e)
        return {"error": str(e), "collection": collection_name}


# ══════════════════════════════════════════════════════════════════
# Registration
# ══════════════════════════════════════════════════════════════════


def register_rag_tools(registry: ToolRegistry) -> None:
    """Register all RAG tools with the orchestrator tool registry.

    This function is called during orchestrator initialization to
    connect the RAG pipeline to the Supervisor-Worker framework.

    Args:
        registry: The orchestrator's ToolRegistry instance.
    """
    registry.register(
        ToolDefinition(
            name="rag_search",
            description="Search enterprise knowledge base using hybrid retrieval (BM25 + vector + RRF fusion)",
            worker="rag",
            handler=_rag_search_handler,
            parameters={
                "query": {"type": "string", "required": True, "description": "Search query"},
                "top_k": {
                    "type": "integer",
                    "required": False,
                    "default": 5,
                    "description": "Number of results",
                },
            },
            category="retrieval",
        )
    )

    registry.register(
        ToolDefinition(
            name="rag_ingest",
            description="Ingest documents into the enterprise knowledge base (parse + chunk + embed + store)",
            worker="rag",
            handler=_rag_ingest_handler,
            parameters={
                "documents": {
                    "type": "array",
                    "required": True,
                    "description": "List of documents with path and format",
                },
                "collection_name": {
                    "type": "string",
                    "required": False,
                    "default": "fde_knowledge",
                    "description": "Target collection name",
                },
            },
            category="retrieval",
        )
    )

    registry.register(
        ToolDefinition(
            name="rag_answer",
            description="Search knowledge base and generate a grounded answer with citations (zero hallucination)",
            worker="rag",
            handler=_rag_answer_handler,
            parameters={
                "query": {
                    "type": "string",
                    "required": True,
                    "description": "User's question",
                },
                "top_k": {
                    "type": "integer",
                    "required": False,
                    "default": 5,
                    "description": "Number of chunks to retrieve",
                },
                "context_chunks": {
                    "type": "array",
                    "required": False,
                    "description": "Pre-retrieved chunks to synthesize from (skips search if provided)",
                },
            },
            category="retrieval",
        )
    )

    logger.info("Registered %d RAG tools", len(registry.get_tools_for_worker("rag")))


# ══════════════════════════════════════════════════════════════════
# Permission-Aware Search (M2-T2)
# ══════════════════════════════════════════════════════════════════


def _create_auth_search_handler(
    user_id: str | None,
    session_factory: Any,
) -> Callable[..., Any]:
    """Create a search handler that applies permission filtering.

    The returned handler is identical to _rag_search_handler but appends
    a permission filter step after hybrid search results are returned.

    Args:
        user_id: The authenticated user ID (None if auth is disabled).
        session_factory: Async session factory for DB queries.

    Returns:
        An async handler function with the same signature as _rag_search_handler.
    """

    async def _auth_search_handler(query: str, top_k: int = 5) -> dict[str, Any]:
        # Step 1: Perform hybrid search
        base_result = await _rag_search_handler(query=query, top_k=top_k)

        if "error" in base_result:
            return base_result

        # Step 2: Apply permission filter if user_id is available
        if user_id is None:
            logger.debug("No user_id for auth filter — returning unfiltered results")
            return base_result

        try:
            from agents.rag_agent.auth_filter import filter_by_permission

            async with session_factory() as session:
                from sqlalchemy import select

                from agents.governance_agent.database.models import User

                result = await session.execute(select(User).where(User.id == user_id))
                user = result.scalar_one_or_none()

                if user is None:
                    logger.warning("User=%s not found for auth filter", user_id)
                    return base_result

                filtered = await filter_by_permission(
                    results=base_result.get("results", []),
                    user=user,
                    session=session,
                )

                base_result["results"] = filtered
                base_result["total_results"] = len(filtered)
                base_result["filtered"] = True

                return base_result
        except ImportError:
            logger.debug("Auth filter not available — returning unfiltered results")
            return base_result

    return _auth_search_handler


def register_rag_tools_with_auth(
    registry: ToolRegistry,
    user_id: str | None,
    session_factory: Any,
) -> None:
    """Register RAG tools with permission-aware search filter (M2-T2).

    This is the authenticated variant of register_rag_tools(). It wraps
    rag_search with a permission filter that excludes results the user
    is not authorized to see.

    Args:
        registry: The orchestrator's ToolRegistry instance.
        user_id: Authenticated user ID or None.
        session_factory: SQLAlchemy async_sessionmaker for permission queries.
    """
    auth_handler = _create_auth_search_handler(user_id, session_factory)

    registry.register(
        ToolDefinition(
            name="rag_search",
            description="Search enterprise knowledge base (permission-filtered) using hybrid retrieval",
            worker="rag",
            handler=auth_handler,
            parameters={
                "query": {
                    "type": "string",
                    "required": True,
                    "description": "Search query",
                },
                "top_k": {
                    "type": "integer",
                    "required": False,
                    "default": 5,
                    "description": "Number of results",
                },
            },
            category="retrieval",
        )
    )

    registry.register(
        ToolDefinition(
            name="rag_ingest",
            description="Ingest documents into the enterprise knowledge base (parse + chunk + embed + store)",
            worker="rag",
            handler=_rag_ingest_handler,
            parameters={
                "documents": {
                    "type": "array",
                    "required": True,
                    "description": "List of documents with path and format",
                },
                "collection_name": {
                    "type": "string",
                    "required": False,
                    "default": "fde_knowledge",
                    "description": "Target collection name",
                },
            },
            category="retrieval",
        )
    )

    registry.register(
        ToolDefinition(
            name="rag_answer",
            description="Search knowledge base and generate a grounded answer with citations (zero hallucination)",
            worker="rag",
            handler=_rag_answer_handler,
            parameters={
                "query": {
                    "type": "string",
                    "required": True,
                    "description": "User's question",
                },
                "top_k": {
                    "type": "integer",
                    "required": False,
                    "default": 5,
                    "description": "Number of chunks to retrieve",
                },
                "context_chunks": {
                    "type": "array",
                    "required": False,
                    "description": "Pre-retrieved chunks to synthesize from (skips search if provided)",
                },
            },
            category="retrieval",
        )
    )

    logger.info(
        "Registered %d RAG tools with auth filter (user=%s)",
        len(registry.get_tools_for_worker("rag")),
        user_id,
    )
