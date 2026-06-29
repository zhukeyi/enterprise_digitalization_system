"""RAG Agent — Enterprise knowledge base retrieval.

Modules:
- vector_store: Qdrant client wrapper (sync/async)
- document_parser: Multi-format document parser factory
- chunking: Configurable chunking strategies
- embeddings: BGE-M3 embedding model wrapper
- retriever: Hybrid search engine (BM25 + vector + RRF)
"""

from __future__ import annotations

from agents.rag_agent.vector_store import VectorStore, VectorRecord, CollectionConfig, QdrantConfig
from agents.rag_agent.document_parser import ParserFactory, Document as ParsedDocument
from agents.rag_agent.chunking import ChunkerFactory, chunk_documents, Document as ChunkDocument
from agents.rag_agent.embeddings import EmbeddingModel, EmbeddingConfig, EmbeddingResult
from agents.rag_agent.retriever import HybridSearchEngine, HybridSearchConfig, SearchResult

__all__ = [
    "VectorStore",
    "VectorRecord",
    "CollectionConfig",
    "QdrantConfig",
    "ParserFactory",
    "ParsedDocument",
    "ChunkerFactory",
    "chunk_documents",
    "ChunkDocument",
    "EmbeddingModel",
    "EmbeddingConfig",
    "EmbeddingResult",
    "HybridSearchEngine",
    "HybridSearchConfig",
    "SearchResult",
]