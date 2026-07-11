"""BGE-M3 embedding model — local ARM CPU inference wrapper.

M1-T11: Encapsulates sentence-transformers for BGE-M3, optimized
for ARM CPU with ONNX/OpenVINO fallback, configurable batch size,
and async processing queue.
"""

from __future__ import annotations

import json as _json
import logging
import os as _os
import time
from pathlib import Path
from typing import Any, Literal

import numpy as np
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


def _default_model_name() -> str:
    """Default embedding model, overridable via env (FDE_RAG_EMBEDDING_MODEL).

    Deployments that have a different model cached locally (e.g. a smaller
    BGE variant) can switch without code changes. The Qdrant collection
    vector size is derived from the loaded model at ingest time, so the
    dimension stays consistent automatically.
    """
    import os

    return os.environ.get("FDE_RAG_EMBEDDING_MODEL", "BAAI/bge-m3")


def _default_query_instruction(model_name: str) -> str:
    """BGE models need a query instruction prefix at retrieval time so that
    queries and documents live in the same embedding space (otherwise
    cosine scores are artificially low even for relevant hits).

    - bge-m3 (multilingual): English instruction from the BGE training recipe.
    - Chinese BGE variants (bge-small-zh, bge-base-zh, ...): Chinese instruction.
    - others: no prefix.
    """
    name = model_name.lower()
    if "bge-m3" in name:
        return "Represent this sentence for searching relevant passages:"
    if "bge" in name and ("zh" in name or "small" in name or "base" in name):
        return "为这个句子生成表示以用于检索相关文章："
    return ""


class EmbeddingConfig(BaseModel):
    """Configuration for the embedding model."""

    model_name: str = Field(default_factory=_default_model_name, description="HuggingFace model name")
    device: Literal["cpu", "cuda", "mps"] = Field(default="cpu", description="Inference device")
    batch_size: int = Field(default=8, ge=1, le=128, description="Max batch size")
    max_seq_length: int = Field(default=8192, description="Maximum sequence length (BGE-M3: 8192)")
    normalize_embeddings: bool = Field(default=True, description="L2-normalize output vectors")
    use_fp16: bool = Field(default=False, description="Use half precision")
    show_progress: bool = Field(default=False, description="Show progress bar")
    query_instruction: str = Field(
        default_factory=lambda: _default_query_instruction(_default_model_name()),
        description="Prefix for query embeddings (RAG retrieval)",
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


# ══════════════════════════════════════════════════════════════════
# ONNX Runtime Backend (P4 T2b)
# ══════════════════════════════════════════════════════════════════


def _to_numpy(tensor: Any) -> Any:
    """Safely convert a tensor (PyTorch or NumPy) to a NumPy array."""
    if hasattr(tensor, "cpu"):
        return tensor.cpu().numpy()
    return np.asarray(tensor)


class ONNXEmbeddingBackend:
    """P4 T2b: ONNX Runtime embedding backend — replaces PyTorch for lower memory.

    Loads a pre-exported ONNX model (e.g. via ``scripts/export_onnx.py``)
    and runs inference with ``onnxruntime``. Tokenization reuses
    ``transformers.AutoTokenizer`` (already installed, ~few MB overhead).
    Mean pooling + L2 normalization in NumPy — parity with ``sentence-transformers``.

    Activate via: ``FDE_EMBEDDING_BACKEND=onnx``;
    set ``FDE_ONNX_MODEL_PATH`` to the ``.onnx`` file
    (default ``~/.cache/fde/bge_model_int8.onnx``).

    Memory: ~24 MB (INT8) vs ~400 MB (PyTorch FP32) — 16x reduction for model weights.
    """

    def __init__(
        self,
        onnx_path: str | None = None,
        model_name: str | None = None,
        max_seq_length: int = 512,
    ) -> None:
        self._session: Any = None
        self._tokenizer: Any = None
        self._onnx_path = onnx_path or _os.getenv(
            "FDE_ONNX_MODEL_PATH",
            _os.path.expanduser("~/.cache/fde/bge_model_int8.onnx"),
        )
        self._model_name = model_name or _os.getenv(
            "FDE_RAG_EMBEDDING_MODEL", "BAAI/bge-small-zh-v1.5"
        )
        self._max_seq_length = max_seq_length
        self._dimension: int = 0
        self._query_instruction: str = _default_query_instruction(self._model_name)
        self._loaded = False

    @property
    def model(self) -> Any:
        if self._session is None:
            self._load()
        return self._session

    # ── Lazy loading ─────────────────────────────────────────

    def _load(self) -> None:
        try:
            import onnxruntime as ort
        except ImportError as exc:
            raise EmbeddingError(
                "onnxruntime not installed. Install: pip install onnxruntime"
            ) from exc

        # Load config.json alongside the model for dimension / seq_len
        config_path = Path(self._onnx_path).with_suffix(".config.json")
        if config_path.exists():
            cfg = _json.loads(config_path.read_text())
            self._dimension = cfg.get("dimension", 512)
            self._max_seq_length = cfg.get("max_seq_length", self._max_seq_length)
            tokenizer_name = cfg.get("tokenizer_name", self._model_name)
        else:
            tokenizer_name = self._model_name

        logger.info(
            "Loading ONNX embedding model from %s (dim=%d)",
            self._onnx_path,
            self._dimension,
        )
        print(f"[ONNX] Loading model: {self._onnx_path} dim={self._dimension}", flush=True)

        self._session = ort.InferenceSession(
            self._onnx_path,
            providers=["CPUExecutionProvider"],
        )

        # Load tokenizer from the lightweight 'tokenizers' library (Rust, no torch)
        tokenizer_path = Path(self._onnx_path).with_suffix(".tokenizer.json")
        try:
            from tokenizers import Tokenizer

            self._tokenizer = Tokenizer.from_file(str(tokenizer_path))
            # Enable padding + truncation (not automatic in tokenizers lib)
            pad_id = self._tokenizer.token_to_id("[PAD]") or 0
            self._tokenizer.enable_padding(
                pad_id=pad_id,
                pad_token="[PAD]",
                length=self._max_seq_length,
            )
            self._tokenizer.enable_truncation(max_length=self._max_seq_length)
            logger.info(
                "ONNX tokenizer loaded from %s (pure Rust, no torch)",
                tokenizer_path,
            )
        except (ImportError, FileNotFoundError):
            # Fallback to transformers.AutoTokenizer (brings in torch)
            from transformers import AutoTokenizer

            self._tokenizer = AutoTokenizer.from_pretrained(tokenizer_name)
            logger.warning("tokenizers library not available, falling back to transformers")
        self._loaded = True

        # Determine dimension from model output if config is missing
        if self._dimension == 0:
            dummy = self._tokenizer(
                ["test"],
                padding="max_length",
                truncation=True,
                max_length=self._max_seq_length,
                return_tensors="np",
            )
            outputs = self._session.run(
                None,
                {
                    "input_ids": _to_numpy(dummy["input_ids"]),
                    "attention_mask": _to_numpy(dummy["attention_mask"]),
                },
            )
            self._dimension = outputs[0].shape[-1]

        logger.info(
            "ONNX model loaded (dim=%d, max_seq=%d)",
            self._dimension,
            self._max_seq_length,
        )

    def is_loaded(self) -> bool:
        return self._loaded

    def unload(self) -> None:
        self._session = None
        self._tokenizer = None
        self._loaded = False
        self._dimension = 0
        logger.info("ONNX embedding model unloaded")

    # ── Dimension / Config ──────────────────────────────────

    def get_dimension(self) -> int:
        if not self._loaded:
            self._load()
        return self._dimension

    def get_config(self) -> EmbeddingConfig:
        return EmbeddingConfig(
            model_name=self._model_name,
            device="cpu",
            max_seq_length=self._max_seq_length,
            query_instruction=self._query_instruction,
        )

    # ── Public encode APIs ──────────────────────────────────

    async def encode_queries(self, queries: list[str]) -> list[list[float]]:
        processed = [f"{self._query_instruction}{q}" for q in queries]
        return await self._encode(processed)

    async def encode_documents(self, documents: list[str]) -> list[list[float]]:
        if not documents:
            return []
        return await self._encode(documents)

    async def embed_batch(
        self, texts: list[str], **kwargs: Any
    ) -> list[EmbeddingResult]:

        if not texts:
            return []

        t0 = time.monotonic()
        vectors = await self._encode(texts)
        elapsed = time.monotonic() - t0
        latency_per = (elapsed / max(1, len(texts))) * 1000

        return [
            EmbeddingResult(
                index=i,
                text=t[:100],
                vector=v,
                dimensions=len(v),
                model=f"onnx:{self._model_name}",
                latency_ms=round(latency_per, 1),
            )
            for i, (t, v) in enumerate(zip(texts, vectors, strict=True))
        ]

    # ── internal ────────────────────────────────────────────

    async def _encode(self, texts: list[str]) -> list[list[float]]:
        import asyncio as _asyncio

        if not self._loaded:
            self._load()
        return await _asyncio.to_thread(self._encode_sync, texts)

    def _encode_sync(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []

        # tokenizers.Tokenizer (Rust) vs transformers.AutoTokenizer (PyTorch)
        from tokenizers import Tokenizer as _RustTokenizer

        if isinstance(self._tokenizer, _RustTokenizer):
            encodings = self._tokenizer.encode_batch(list(texts))
            input_ids = np.array([e.ids for e in encodings], dtype=np.int64)
            attention_mask = np.array(
                [e.attention_mask for e in encodings], dtype=np.int64
            )
        else:
            # transformers.AutoTokenizer (legacy fallback)
            tokens = self._tokenizer(
                list(texts),
                padding=True,
                truncation=True,
                max_length=self._max_seq_length,
                return_tensors="np",
            )
            input_ids = _to_numpy(tokens["input_ids"]).astype(np.int64)
            attention_mask = _to_numpy(tokens["attention_mask"]).astype(np.int64)

        outputs = self._session.run(
            None,
            {
                "input_ids": input_ids,
                "attention_mask": attention_mask,
            },
        )
        # first output = last_hidden_state: (batch, seq_len, hidden_dim)
        last_hidden = np.asarray(outputs[0], dtype=np.float32)

        # Mean pooling with attention mask
        mask = np.expand_dims(attention_mask, -1).astype(np.float32)
        summed = (last_hidden * mask).sum(axis=1)
        counts = mask.sum(axis=1).clip(min=1e-9)
        pooled = summed / counts

        # L2 normalize
        norms = np.linalg.norm(pooled, axis=1, keepdims=True)
        normalized = pooled / norms.clip(min=1e-9)

        return [normalized[i].tolist() for i in range(normalized.shape[0])]
