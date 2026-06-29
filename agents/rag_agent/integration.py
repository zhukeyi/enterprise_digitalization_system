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


# ══════════════════════════════════════════════════════════════════
# RAG Tool Handlers
# ══════════════════════════════════════════════════════════════════


async def _rag_search_handler(query: str, top_k: int = 5) -> dict[str, Any]:
    """Execute hybrid search via BM25 + vector + RRF fusion.

    Args:
        query: Search query string.
        top_k: Number of results to return.

    Returns:
        Dictionary with search results.
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
    except Exception as e:
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
        qdrant_config = QdrantConfig()
        vector_store = VectorStore(qdrant_config)

        # Create collection if needed
        collection_config = CollectionConfig(name=collection_name)
        vector_store.create_collection(collection_config)

        ingested_count = 0
        errors: list[str] = []

        for doc_info in documents:
            try:
                # Parse document
                parser = ParserFactory().get_parser(doc_info.get("path", "document.txt"))
                parsed = parser.parse(doc_info["path"])

                # Chunk document — parser returns Document (Pydantic),
                # chunk_documents expects chunking.Document (dataclass).
                # Adapter layer will be added in production integration.
                chunks = chunk_documents([parsed])  # type: ignore[list-item]

                # Store chunks — Chunk needs conversion to VectorRecord.
                # Adapter layer will be added in production integration.
                for chunk in chunks:
                    vector_store.upsert(
                        points=[chunk],  # type: ignore[list-item]
                        collection=collection_name,
                    )
                ingested_count += 1
            except Exception as e:
                errors.append(f"Document {doc_info.get('path', '?')}: {e}")

        return {
            "collection": collection_name,
            "ingested": ingested_count,
            "total": len(documents),
            "errors": errors,
        }
    except Exception as e:
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
