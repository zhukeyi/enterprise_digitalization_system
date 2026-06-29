"""Tests for BGE-M3 embedding model wrapper.

M1-T11: All tests mock sentence_transformers to avoid loading
the real model (which requires PyTorch + transformers).
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agents.rag_agent.embeddings import EmbeddingConfig, EmbeddingError, EmbeddingModel, EmbeddingResult


# ══════════════════════════════════════════════════════════════════
# Fixtures
# ══════════════════════════════════════════════════════════════════


@pytest.fixture
def config() -> EmbeddingConfig:
    return EmbeddingConfig(model_name="BAAI/bge-m3", device="cpu", batch_size=4)


@pytest.fixture
def mock_sentence_transformer() -> MagicMock:
    """Mock the SentenceTransformer model."""
    model = MagicMock()
    model.max_seq_length = 8192
    model.get_sentence_embedding_dimension.return_value = 1024

    # Mock encode to return numpy-like arrays
    import numpy as np

    model.encode.return_value = np.array([[0.1] * 1024, [0.2] * 1024])

    return model


@pytest.fixture
def model(config: EmbeddingConfig) -> EmbeddingModel:
    return EmbeddingModel(config=config)


# ══════════════════════════════════════════════════════════════════
# EmbeddingConfig Tests
# ══════════════════════════════════════════════════════════════════


class TestEmbeddingConfig:
    def test_defaults(self) -> None:
        cfg = EmbeddingConfig()
        assert cfg.model_name == "BAAI/bge-m3"
        assert cfg.device == "cpu"
        assert cfg.batch_size == 8
        assert cfg.max_seq_length == 8192
        assert cfg.normalize_embeddings is True
        assert cfg.use_fp16 is False

    def test_custom(self) -> None:
        cfg = EmbeddingConfig(model_name="custom/model", batch_size=16)
        assert cfg.model_name == "custom/model"
        assert cfg.batch_size == 16


# ══════════════════════════════════════════════════════════════════
# EmbeddingModel Tests (mocked)
# ══════════════════════════════════════════════════════════════════


class TestEmbeddingModelLoad:
    def test_lazy_load(
        self, model: EmbeddingModel, mock_sentence_transformer: MagicMock
    ) -> None:
        """Model should not load until first use."""
        assert model._model is None
        assert model.is_loaded() is False

    def test_load_on_access(
        self, model: EmbeddingModel, mock_sentence_transformer: MagicMock
    ) -> None:
        """Accessing .model should trigger load."""
        with patch(
            "sentence_transformers.SentenceTransformer", return_value=mock_sentence_transformer
        ):
            _ = model.model
            assert model._model is not None
            assert model.is_loaded() is True

    def test_unload(self, model: EmbeddingModel) -> None:
        model._model = MagicMock()
        model._model_name_loaded = "test"
        model.unload()
        assert model._model is None
        assert model.is_loaded() is False

    def test_missing_dependency(self, config: EmbeddingConfig) -> None:
        model = EmbeddingModel(config=config)
        with patch.dict("sys.modules", {"sentence_transformers": None}):
            with pytest.raises(EmbeddingError, match="sentence-transformers not installed"):
                _ = model.model


class TestEmbeddingSingle:
    @patch("sentence_transformers.SentenceTransformer")
    async def test_embed_single(
        self, mock_st: MagicMock, model: EmbeddingModel
    ) -> None:
        """Single text embedding returns EmbeddingResult."""
        mock_instance = MagicMock()
        import numpy as np

        mock_instance.encode.return_value = np.array([[0.5] * 1024])
        mock_instance.get_sentence_embedding_dimension.return_value = 1024
        mock_st.return_value = mock_instance

        result = await model.embed("hello world")
        assert isinstance(result, EmbeddingResult)
        assert result.index == 0
        assert len(result.vector) == 1024
        assert result.dimensions == 1024
        assert result.model == "BAAI/bge-m3"

    @patch("sentence_transformers.SentenceTransformer")
    async def test_embed_with_empty_string(
        self, mock_st: MagicMock, model: EmbeddingModel
    ) -> None:
        """Should handle empty input."""
        mock_instance = MagicMock()
        import numpy as np

        mock_instance.encode.return_value = np.array([[0.0] * 1024])
        mock_instance.get_sentence_embedding_dimension.return_value = 1024
        mock_st.return_value = mock_instance

        result = await model.embed("")
        assert isinstance(result, EmbeddingResult)


class TestEmbeddingBatch:
    @patch("sentence_transformers.SentenceTransformer")
    async def test_embed_batch(
        self, mock_st: MagicMock, model: EmbeddingModel
    ) -> None:
        """Batch embedding returns correct number of results."""
        mock_instance = MagicMock()
        import numpy as np

        mock_instance.encode.return_value = np.array(
            [[0.1] * 1024, [0.2] * 1024, [0.3] * 1024]
        )
        mock_instance.get_sentence_embedding_dimension.return_value = 1024
        mock_st.return_value = mock_instance

        results = await model.embed_batch(["text1", "text2", "text3"])
        assert len(results) == 3
        assert results[0].index == 0
        assert results[1].index == 1
        assert results[2].index == 2

    @patch("sentence_transformers.SentenceTransformer")
    async def test_empty_batch(
        self, mock_st: MagicMock, model: EmbeddingModel
    ) -> None:
        """Empty batch returns empty list."""
        results = await model.embed_batch([])
        assert results == []


class TestEncodeQueriesDocuments:
    @patch("sentence_transformers.SentenceTransformer")
    async def test_encode_queries(
        self, mock_st: MagicMock, model: EmbeddingModel
    ) -> None:
        mock_instance = MagicMock()
        import numpy as np

        mock_instance.encode.return_value = np.array([[0.1] * 1024])
        mock_instance.get_sentence_embedding_dimension.return_value = 1024
        mock_st.return_value = mock_instance

        model.config.query_instruction = "query: "
        vectors = await model.encode_queries(["test query"])
        assert len(vectors) == 1
        assert len(vectors[0]) == 1024

    @patch("sentence_transformers.SentenceTransformer")
    async def test_encode_documents(
        self, mock_st: MagicMock, model: EmbeddingModel
    ) -> None:
        mock_instance = MagicMock()
        import numpy as np

        mock_instance.encode.return_value = np.array([[0.2] * 1024])
        mock_instance.get_sentence_embedding_dimension.return_value = 1024
        mock_st.return_value = mock_instance

        vectors = await model.encode_documents(["doc text"])
        assert len(vectors) == 1


class TestDimension:
    def test_get_dimension_when_loaded(
        self, model: EmbeddingModel, mock_sentence_transformer: MagicMock
    ) -> None:
        model._model = mock_sentence_transformer
        dim = model.get_dimension()
        assert dim == 1024

    def test_get_dimension_when_not_loaded(self, model: EmbeddingModel) -> None:
        dim = model.get_dimension()
        assert dim == 1024  # Default fallback


# ══════════════════════════════════════════════════════════════════
# EmbeddingResult Tests
# ══════════════════════════════════════════════════════════════════


class TestEmbeddingResult:
    def test_defaults(self) -> None:
        result = EmbeddingResult(
            index=0, text="hello", vector=[0.1, 0.2, 0.3], dimensions=3, model="test"
        )
        assert result.index == 0
        assert result.text == "hello"
        assert result.latency_ms == 0.0

    def test_with_latency(self) -> None:
        result = EmbeddingResult(
            index=1,
            text="world",
            vector=[0.1, 0.2],
            dimensions=2,
            model="test",
            latency_ms=12.5,
        )
        assert result.latency_ms == 12.5