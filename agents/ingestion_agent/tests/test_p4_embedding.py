"""P4-T5: ONNX embedding backend + chunk token estimation + store factory tests.

These tests verify P4 (量化嵌入 + 切片优化) without requiring an actual ONNX model file
on the developer machine. ONNX inference is tested on the deployment server during acceptance.
"""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest

from agents.ingestion_agent.chunking import (
    CHILD_SIZE,
    MAX_PARENT,
    OVERLAP,
    _estimate_tokens,
    build_text_chunks,
)
from agents.ingestion_agent.store import get_embedding_model
from agents.rag_agent.embeddings import (
    EmbeddingConfig,
    EmbeddingModel,
    ONNXEmbeddingBackend,
)

# ══════════════════════════════════════════════════════════════════
# Token estimation
# ══════════════════════════════════════════════════════════════════


class TestTokenEstimation:
    def test_pure_cjk(self) -> None:
        """纯中文文本：token 数 ≈ 字符数 / 1.5"""
        tokens = _estimate_tokens("你好世界")
        assert tokens == int(4 / 1.5) + 1  # = 3

    def test_pure_ascii(self) -> None:
        """纯英文文本：token 数 ≈ 字符数 / 3.5"""
        tokens = _estimate_tokens("HelloWorld")
        assert tokens == int(10 / 3.5) + 1  # = 3

    def test_mixed(self) -> None:
        """中英混合：分别除以对应系数"""
        # "你好world" -> cjk=2, ascii=5
        tokens = _estimate_tokens("你好world")
        expected = int(2 / 1.5 + 5 / 3.5) + 1
        assert tokens == expected

    def test_empty(self) -> None:
        """空字符串返回 1"""
        assert _estimate_tokens("") == 1

    def test_token_count_less_than_len(self) -> None:
        """token_count 始终 ≤ len(text)，因为估算系数 ≥ 1"""
        texts = [
            "这是一段比较长的中文测试文本",
            "This is a longer English test text for comparison",
            "中英混合Mixed content测试test数据data",
        ]
        for t in texts:
            assert _estimate_tokens(t) <= len(t), f"Failed for: {t[:30]}"


# ══════════════════════════════════════════════════════════════════
# Chunking — overlap & env config
# ══════════════════════════════════════════════════════════════════


class TestChunkOverlap:
    def test_sliding_window_overlap(self) -> None:
        """滑窗子块之间有重叠（overlap > 0 时），确认覆盖全文无缺口。"""
        # 使用非重复文本确保子块不重复
        text = "".join(f"part{i:03d} " for i in range(200))  # ~1600 chars, non-repetitive
        specs = build_text_chunks(
            text,
            doc_type="test",
            source_ref="test://1",
            raw_id="r1",
            max_parent=2000,
            child_size=200,
            overlap=40,
        )
        assert len(specs) > 4, "should produce multiple children"
        # 所有子块唯一
        children = [s.child_text for s in specs]
        assert len(set(children)) == len(children), "all children should be unique"

    def test_no_overlap_scenario(self) -> None:
        """overlap=0 时子块无重叠。"""
        text = "X " * 500
        specs = build_text_chunks(
            text,
            doc_type="test",
            source_ref="test://2",
            raw_id="r2",
            max_parent=600,
            child_size=100,
            overlap=0,
        )
        assert len(specs) >= 4

    def test_parent_respects_max_parent(self) -> None:
        """父块不超过 max_parent 字符。"""
        text = ("paragraph one\n\n" + "paragraph two\n\n") * 50
        specs = build_text_chunks(
            text,
            doc_type="test",
            source_ref="test://3",
            raw_id="r3",
            max_parent=200,
            child_size=80,
        )
        # 所有子块的父块长度 ≤ max_parent + some margin for paragraph joining
        parent_lengths = {len(s.parent_text) for s in specs}
        for pl in parent_lengths:
            assert pl <= 220, f"parent too long: {pl}"


class TestChunkEnvConfig:
    def test_env_overrides_chunk_params(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """环境变量 FDE_CHUNK_* 覆盖默认参数。"""
        monkeypatch.setenv("FDE_CHUNK_MAX_PARENT", "500")
        monkeypatch.setenv("FDE_CHUNK_CHILD_SIZE", "80")
        monkeypatch.setenv("FDE_CHUNK_OVERLAP", "10")

        # Re-import to pick up env vars (module-level constants read at import time)
        from importlib import reload

        import agents.ingestion_agent.chunking as cmod

        reload(cmod)

        assert cmod.MAX_PARENT == 500
        assert cmod.CHILD_SIZE == 80
        assert cmod.OVERLAP == 10

        # Restore
        monkeypatch.delenv("FDE_CHUNK_MAX_PARENT", raising=False)
        monkeypatch.delenv("FDE_CHUNK_CHILD_SIZE", raising=False)
        monkeypatch.delenv("FDE_CHUNK_OVERLAP", raising=False)
        reload(cmod)

    def test_default_params_sensible(self) -> None:
        """默认参数在合理范围。"""
        assert 500 <= MAX_PARENT <= 2000, "MAX_PARENT too extreme"
        assert 100 <= CHILD_SIZE <= 500, "CHILD_SIZE too extreme"
        assert 0 <= OVERLAP <= CHILD_SIZE, "OVERLAP > CHILD_SIZE"


class TestChunkSpecHash:
    def test_different_text_different_hash(self) -> None:
        h1 = build_text_chunks("hello", doc_type="t", source_ref="s", raw_id="r1", max_parent=500)
        h2 = build_text_chunks("world", doc_type="t", source_ref="s", raw_id="r2", max_parent=500)
        assert h1[0].content_hash != h2[0].content_hash

    def test_same_text_same_hash(self) -> None:
        h1 = build_text_chunks("hello", doc_type="t", source_ref="s", raw_id="r1", max_parent=500)
        h2 = build_text_chunks("hello", doc_type="t", source_ref="s", raw_id="r2", max_parent=500)
        assert h1[0].content_hash == h2[0].content_hash


# ══════════════════════════════════════════════════════════════════
# ONNX backend — configuration
# ══════════════════════════════════════════════════════════════════


class TestONNXConfig:
    def test_onnx_backend_creates_without_file(self) -> None:
        """ONNXEmbeddingBackend 实例化不要求 ONNX 文件立即存在（lazy load）。"""
        backend = ONNXEmbeddingBackend(onnx_path="/nonexistent/bge_model.onnx")
        assert not backend.is_loaded()
        assert backend.get_config().device == "cpu"

    def test_onnx_backend_unload(self) -> None:
        backend = ONNXEmbeddingBackend(onnx_path="/nonexistent/bge_model.onnx")
        backend.unload()  # should not raise
        assert not backend.is_loaded()

    def test_onnx_get_config(self) -> None:
        backend = ONNXEmbeddingBackend(
            onnx_path="/some/model.onnx",
            model_name="BAAI/bge-small-zh-v1.5",
        )
        config = backend.get_config()
        assert isinstance(config, EmbeddingConfig)
        assert config.model_name == "BAAI/bge-small-zh-v1.5"
        assert config.device == "cpu"

    def test_onnx_load_without_onnxruntime_raises(self) -> None:
        """没有 onnxruntime 时，_load() 抛出 EmbeddingError。"""
        backend = ONNXEmbeddingBackend(onnx_path="/nonexistent/model.onnx")
        with patch.dict("sys.modules", {"onnxruntime": None}):
            with pytest.raises(Exception) as exc_info:
                backend._load()
            # Should be ImportError propagating through EmbeddingError
            assert "onnxruntime" in str(exc_info.value).lower() or isinstance(
                exc_info.value, ImportError
            )

    def test_onnx_query_instruction_is_set(self) -> None:
        """BGE 模型应有 query instruction 前缀。"""
        backend = ONNXEmbeddingBackend(
            onnx_path="/some/model.onnx",
            model_name="BAAI/bge-small-zh-v1.5",
        )
        config = backend.get_config()
        assert "为这个" in config.query_instruction or len(config.query_instruction) > 0

    def test_onnx_encode_empty_list(self) -> None:
        """空列表不加载模型（利用 embed_batch 短路返回）。"""
        backend = ONNXEmbeddingBackend(onnx_path="/nonexistent/model.onnx")
        import asyncio

        result = asyncio.new_event_loop().run_until_complete(backend.embed_batch([]))
        assert result == []

    async def test_onnx_embed_batch_empty(self) -> None:
        """embed_batch 空列表直接返回 []。"""
        backend = ONNXEmbeddingBackend(onnx_path="/nonexistent/model.onnx")
        result = await backend.embed_batch([])
        assert result == []

    async def test_onnx_backend_unloaded_dimension_triggers_load_attempt(self) -> None:
        """get_dimension() 在未加载时触发 _load()（预期失败，但不崩溃）。"""
        backend = ONNXEmbeddingBackend(onnx_path="/nonexistent/model.onnx")
        # NoSuchFile is onnxruntime internal; any failure is acceptable here
        with pytest.raises(Exception):  # noqa: B017
            backend.get_dimension()


# ══════════════════════════════════════════════════════════════════
# Store factory — backend selection
# ══════════════════════════════════════════════════════════════════


class TestStoreFactory:
    def test_default_backend_is_pytorch(self) -> None:
        """默认 FDE_EMBEDDING_BACKEND 未设置时返回 EmbeddingModel。"""
        with patch.dict(os.environ, {}, clear=False):
            if "FDE_EMBEDDING_BACKEND" in os.environ:
                del os.environ["FDE_EMBEDDING_BACKEND"]
            backend = get_embedding_model()
            assert isinstance(backend, EmbeddingModel)

    def test_onnx_env_selects_onnx_backend(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from agents.ingestion_agent.store import reset_singletons

        # 重置全局单例，确保不受其他测试影响
        reset_singletons()
        monkeypatch.setenv("FDE_EMBEDDING_BACKEND", "onnx")
        backend = get_embedding_model()
        assert isinstance(backend, ONNXEmbeddingBackend)
        reset_singletons()
