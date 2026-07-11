"""Ingestion Agent — 共享资源单例（P2a / MVS 核心）。

复用 RAG 模块的 ``VectorStore``（Qdrant）与 ``EmbeddingModel``（BGE-M3），
以懒加载单例形式提供给 ingestion router / pipeline 使用，避免重复加载模型。

测试可通过覆盖依赖注入（``router.dependency_overrides``）替换为内存实现。

P4 T2b: ``get_embedding_model`` 支持 ``FDE_EMBEDDING_BACKEND=onnx`` 切换至
``ONNXEmbeddingBackend``（INT8 量化, ~24MB vs ~400MB, 16x 内存节省）。
"""

from __future__ import annotations

import os

from agents.rag_agent.embeddings import EmbeddingModel, ONNXEmbeddingBackend
from agents.rag_agent.vector_store import VectorStore

EmbeddingBackend = EmbeddingModel | ONNXEmbeddingBackend

_vector_store: VectorStore | None = None
_embedding_model: EmbeddingBackend | None = None


def get_vector_store() -> VectorStore:
    """返回（懒加载）Qdrant 向量库单例。"""
    global _vector_store
    if _vector_store is None:
        _vector_store = VectorStore()
    return _vector_store


def get_embedding_model() -> EmbeddingBackend:
    """返回（懒加载）嵌入模型单例（PyTorch 或 ONNX，由 FDE_EMBEDDING_BACKEND 控制）。"""
    global _embedding_model
    if _embedding_model is None:
        backend = os.getenv("FDE_EMBEDDING_BACKEND", "pytorch").lower()
        if backend == "onnx":
            import logging
            logging.getLogger("router").info("Backend selection: ONNX (FDE_EMBEDDING_BACKEND=onnx)")
            _embedding_model = ONNXEmbeddingBackend()
        else:
            import logging
            logging.getLogger("router").info("Backend selection: PyTorch (FDE_EMBEDDING_BACKEND=%s)", backend)
            _embedding_model = EmbeddingModel()
    return _embedding_model


def reset_singletons() -> None:
    """清空单例（主要用于测试隔离）。"""
    global _vector_store, _embedding_model
    _vector_store = None
    _embedding_model = None
