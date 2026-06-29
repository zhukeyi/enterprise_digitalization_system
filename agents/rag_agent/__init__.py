"""RAG Agent — Enterprise knowledge base retrieval.

Modules:
- vector_store: Qdrant client wrapper (sync/async)
- document_parser: Multi-format document parser factory
- chunking: Configurable chunking strategies
- embeddings: BGE-M3 embedding model wrapper
- retriever: Hybrid search engine (BM25 + vector + RRF)
"""

from __future__ import annotations

from agents.rag_agent.chunking import ChunkerFactory, chunk_documents
from agents.rag_agent.chunking import Document as ChunkDocument
from agents.rag_agent.document_parser import Document as ParsedDocument
from agents.rag_agent.document_parser import ParserFactory
from agents.rag_agent.embeddings import EmbeddingConfig, EmbeddingModel, EmbeddingResult
from agents.rag_agent.retriever import HybridSearchConfig, HybridSearchEngine, SearchResult
from agents.rag_agent.vector_store import CollectionConfig, QdrantConfig, VectorRecord, VectorStore

__all__ = [
    "ChunkDocument",
    "ChunkerFactory",
    "CollectionConfig",
    "EmbeddingConfig",
    "EmbeddingModel",
    "EmbeddingResult",
    "HybridSearchConfig",
    "HybridSearchEngine",
    "ParsedDocument",
    "ParserFactory",
    "QdrantConfig",
    "SearchResult",
    "VectorRecord",
    "VectorStore",
    "chunk_documents",
]
