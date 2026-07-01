"""BGE-M3 embedding model — local ARM CPU inference wrapper.

M1-T11: Encapsulates sentence-transformers for BGE-M3, optimized
for ARM CPU with ONNX/OpenVINO fallback, configurable batch size,
and async processing queue.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Literal

from pydantic import BaseModel, Field

logger = logging.getLogger("fde.rag.embeddings")

# ══════════════════════════════════════════════════════════════════
# Data Models
# ══════════════════════════════════════════════════════════════════


class EmbeddingResult(BaseModel):
    """Result of embedding a single text input."""

    index: int = Field(description="Position in the input batch")
    text: str = Field(description="Original input text")
    vector: list[float] = Field(description="Dense embedding vector")
    dimensions: int = Field(description="Vector dimensionality")
    model: str = Field(description="Model name used for embedding")
    latency_ms: float = Field(default=0.0, description="Inference latency in ms")


class EmbeddingConfig(BaseModel):
    """Configuration for the embedding model."""

    model_name: str = Field(default="BAAI/bge-m3", description="HuggingFace model name")
    device: Literal["cpu", "cuda", "mps"] = Field(default="cpu", description="Inference device")
    batch_size: int = Field(default=8, ge=1, le=128, description="Max batch size")
    max_seq_length: int = Field(default=8192, description="Maximum sequence length (BGE-M3: 8192)")
    normalize_embeddings: bool = Field(default=True, description="L2-normalize output vectors")
    use_fp16: bool = Field(default=False, description="Use half precision")
    show_progress: bool = Field(default=False, description="Show progress bar")
    query_instruction: str = Field(
        default="", description="Prefix for query embeddings (RAG retrieval)"
    )


# ══════════════════════════════════════════════════════════════════
# Exceptions
# ══════════════════════════════════════════════════════════════════


class EmbeddingError(Exception):
    """Base exception for embedding operations."""


# ══════════════════════════════════════════════════════════════════
# Embedding Model Wrapper
# ══════════════════════════════════════════════════════════════════


class EmbeddingModel:
    """BGE-M3 embedding model wrapper for ARM CPU inference.

    Lazily loads the model on first use. Supports single text and batch
    embedding with configurable normalization and sequence length.

    Usage:
        model = EmbeddingModel()
        vector = await model.embed("some text")
        vectors = await model.embed_batch(["text1", "text2"])
    """

    def __init__(self, config: EmbeddingConfig | None = None) -> None:
        self.config = config or EmbeddingConfig()
        self._model: Any = None
        self._tokenizer: Any = None
        self._model_name_loaded: str = ""

    # ── Lazy Loading ────────────────────────────────────────────

    @property
    def model(self) -> Any:
        """Get the loaded SentenceTransformer model (lazy init)."""
        if self._model is None:
            self._load()
        return self._model

    def _load(self) -> None:
        """Load the SentenceTransformer model (CPU-optimized)."""
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError:
            raise EmbeddingError(
                "sentence-transformers not installed. Install: pip install fde-ai-platform[rag]"
            )

        logger.info(
            "Loading embedding model '%s' on %s (batch=%d, max_seq=%d)",
            self.config.model_name,
            self.config.device,
            self.config.batch_size,
            self.config.max_seq_length,
        )
        t0 = time.monotonic()

        self._model = SentenceTransformer(
            self.config.model_name,
            device=self.config.device,
        )

        self._model.max_seq_length = self.config.max_seq_length
        self._model_name_loaded = self.config.model_name

        elapsed = time.monotonic() - t0
        logger.info("Embedding model loaded in %.1fs", elapsed)

    def is_loaded(self) -> bool:
        """Check if the model is loaded in memory."""
        return self._model is not None

    def unload(self) -> None:
        """Unload the model from memory to free resources."""
        self._model = None
        self._tokenizer = None
        self._model_name_loaded = ""
        logger.info("Embedding model unloaded from memory")

    # ── Single Embedding ────────────────────────────────────────

    async def embed(self, text: str, **kwargs: Any) -> EmbeddingResult:
        """Embed a single text string.

        Args:
            text: Input text to embed.
            **kwargs: Override config options (optional).

        Returns:
            EmbeddingResult with vector and metadata.
        """
        results = await self.embed_batch([text], **kwargs)
        return results[0]

    # ── Batch Embedding ─────────────────────────────────────────

    async def embed_batch(self, texts: list[str], **kwargs: Any) -> list[EmbeddingResult]:
        """Embed a batch of texts.

        Args:
            texts: List of input texts.
            **kwargs: Override config options.

        Returns:
            List of EmbeddingResult objects.
        """
        import asyncio

        if not texts:
            return []

        # Run sync SentenceTransformer call in thread pool
        return await asyncio.to_thread(self._embed_sync, texts, **kwargs)

    def _embed_sync(self, texts: list[str], **kwargs: Any) -> list[EmbeddingResult]:
        """Synchronous embedding (runs in thread pool for async)."""
        # Prepare text: apply query instruction if needed
        processed = []
        for t in texts:
            if self.config.query_instruction and not t.startswith(self.config.query_instruction):
                processed.append(self.config.query_instruction + t)
            else:
                processed.append(t)

        t0 = time.monotonic()

        vectors = self.model.encode(
            processed,
            batch_size=kwargs.get("batch_size", self.config.batch_size),
            normalize_embeddings=kwargs.get(
                "normalize_embeddings", self.config.normalize_embeddings
            ),
            show_progress_bar=kwargs.get("show_progress", self.config.show_progress),
        )

        elapsed = time.monotonic() - t0
        latency_per = (elapsed / max(1, len(texts))) * 1000

        results = []
        for i, (text, vec) in enumerate(zip(texts, vectors, strict=True)):
            results.append(
                EmbeddingResult(
                    index=i,
                    text=text[:100],  # Truncate for storage
                    vector=vec.tolist() if hasattr(vec, "tolist") else list(vec),
                    dimensions=len(vec),
                    model=self._model_name_loaded,
                    latency_ms=round(latency_per, 1),
                )
            )

        logger.debug(
            "Embedded %d texts (%.1fms/text, dim=%d)",
            len(texts),
            latency_per,
            len(vectors[0]) if len(vectors) > 0 else 0,
        )
        return results

    # ── Dense Retrieval Encoding ────────────────────────────────

    async def encode_queries(self, queries: list[str]) -> list[list[float]]:
        """Encode queries for retrieval with instruction prefix.

        For BGE-M3, prepends query instruction for better retrieval.
        """
        import asyncio

        processed = [f"{self.config.query_instruction}{q}" for q in queries]
        vectors = await asyncio.to_thread(
            self.model.encode,
            processed,
            batch_size=self.config.batch_size,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        return [v.tolist() if hasattr(v, "tolist") else list(v) for v in vectors]

    async def encode_documents(self, documents: list[str]) -> list[list[float]]:
        """Encode documents for indexing (no instruction prefix)."""
        import asyncio

        vectors = await asyncio.to_thread(
            self.model.encode,
            documents,
            batch_size=self.config.batch_size,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        return [v.tolist() if hasattr(v, "tolist") else list(v) for v in vectors]

    # ── Dimension Info ──────────────────────────────────────────

    def get_dimension(self) -> int:
        """Get the embedding dimension of the loaded model."""
        if self._model is not None:
            dim = self._model.get_sentence_embedding_dimension()
            if dim is not None:
                return dim  # type: ignore[no-any-return]
        return 1024  # BGE-M3 default

    def get_config(self) -> EmbeddingConfig:
        """Get current configuration."""
        return self.config
