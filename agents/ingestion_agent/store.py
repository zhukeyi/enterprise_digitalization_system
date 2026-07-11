"""Ingestion Agent — 共享资源单例（P2a / MVS 核心）。

复用 RAG 模块的 ``VectorStore``（Qdrant）与 ``EmbeddingModel``（BGE-M3），
以懒加载单例形式提供给 ingestion router / pipeline 使用，避免重复加载模型。

测试可通过覆盖依赖注入（``router.dependency_overrides``）替换为内存实现。
"""

from __future__ import annotations

from agents.rag_agent.embeddings import EmbeddingModel
from agents.rag_agent.vector_store import VectorStore

_vector_store: VectorStore | None = None
_embedding_model: EmbeddingModel | None = None


def get_vector_store() -> VectorStore:
    """返回（懒加载）Qdrant 向量库单例。"""
    global _vector_store
    if _vector_store is None:
        _vector_store = VectorStore()
    return _vector_store


def get_embedding_model() -> EmbeddingModel:
    """返回（懒加载）BGE-M3 嵌入模型单例。"""
    global _embedding_model
    if _embedding_model is None:
        _embedding_model = EmbeddingModel()
    return _embedding_model


def reset_singletons() -> None:
    """清空单例（主要用于测试隔离）。"""
    global _vector_store, _embedding_model
    _vector_store = None
    _embedding_model = None
