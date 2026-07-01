"""RAG Agent integration with LangGraph Orchestrator.

Bridges the existing RAG pipeline (Qdrant + BM25 + BGE-M3) to the
Supervisor-Worker framework via ToolRegistry.

Registered tools:
- rag_search: Hybrid search (BM25 + vector + RRF fusion)
- rag_ingest: Ingest documents into vector store
- rag_answer: Generate answer from retrieved context (future)

M1-T4: RAGFlow migration to LangGraph
"""

from __future__ import annotations

import logging
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

logger = logging.getLogger("fde.rag.integration")

# Module-level cached VectorStore singleton (avoids creating new Qdrant
# connections on every _rag_ingest_handler call)
_vector_store_instance: VectorStore | None = None


def _get_vector_store() -> VectorStore:
    """Get or create a singleton VectorStore instance."""
    global _vector_store_instance
    if _vector_store_instance is None:
        _vector_store_instance = VectorStore(QdrantConfig())
    return _vector_store_instance


def _reset_vector_store() -> None:
    """Reset the VectorStore singleton (for testing)."""
    global _vector_store_instance
    _vector_store_instance = None


# ══════════════════════════════════════════════════════════════════
# RAG Tool Handlers
# ══════════════════════════════════════════════════════════════════


async def _rag_search_handler(query: str, top_k: int = 5) -> dict[str, Any]:
    """Execute hybrid search via BM25 + vector + RRF fusion.

    NOTE: The hybrid search engine must have documents indexed before use.
    Use rag_ingest first to populate the vector store / BM25 index.
    Without indexed documents, this returns an empty result set.

    Args:
        query: Search query string.
        top_k: Number of results to return.

    Returns:
        Dictionary with search results (may be empty if index is empty).
    """
    try:
        config = HybridSearchConfig(top_k_final=top_k)
        engine = HybridSearchEngine(config=config)
        results = await engine.search(query)

        return {
            "query": query,
            "total_results": len(results),
            "results": [
                {
                    "content": r.content[:200],
                    "score": r.score,
                    "source": r.source or r.metadata.get("source", "unknown"),
                    "chunk_id": r.id,
                }
                for r in results
            ],
        }
    except (RuntimeError, ValueError, TypeError, ConnectionError, TimeoutError, OSError) as e:
        logger.error("rag_search failed: %s", e)
        return {"error": str(e), "query": query}


def _rag_ingest_handler(
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
    try:
        vector_store = _get_vector_store()

        # Create collection if needed
        collection_config = CollectionConfig(name=collection_name)
        vector_store.create_collection(collection_config)

        ingested_count = 0
        errors: list[str] = []

        for doc_info in documents:
            try:
                # Validate required keys
                doc_path = doc_info.get("path")
                if not doc_path:
                    raise ValueError(f"Document info missing 'path' key: {doc_info}")

                # Parse document — returns list[Document] (Pydantic BaseModel)
                parser = ParserFactory().get_parser(doc_path)
                parsed_pages = parser.parse(doc_path)

                # Chunk documents — chunk_documents now accepts the unified
                # Document model from document_parser.py
                chunks = chunk_documents(parsed_pages)

                # Store chunks — convert Chunk to VectorRecord
                from agents.rag_agent.vector_store import VectorRecord

                for chunk in chunks:
                    vr = VectorRecord(
                        id=chunk.chunk_id or f"chunk-{chunk.chunk_index}",
                        payload={
                            "text": chunk.content,
                            "source": chunk.source,
                            "chunk_index": chunk.chunk_index,
                            "chunk_strategy": chunk.chunk_strategy,
                            **chunk.metadata,
                        },
                    )
                    vector_store.upsert(
                        points=[vr],
                        collection=collection_name,
                    )
                ingested_count += 1
            except (RuntimeError, ValueError, TypeError, KeyError, OSError) as e:
                errors.append(f"Document {doc_info.get('path', '?')}: {e}")

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

    logger.info(
        "Registered %d RAG tools with auth filter (user=%s)",
        len(registry.get_tools_for_worker("rag")),
        user_id,
    )
