"""Qdrant vector store — client wrapper and collection management.

M1-T8: Qdrant connection config and client encapsulation.
Supports async operations with connection pooling, health checks,
collection CRUD, and point (vector) operations.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, Field

logger = logging.getLogger("fde.rag.vector_store")

# ══════════════════════════════════════════════════════════════════
# Data Models
# ══════════════════════════════════════════════════════════════════


class VectorRecord(BaseModel):
    """A single vector record for upsert / search results."""

    id: str | int
    vector: list[float] | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    score: float | None = None


class CollectionConfig(BaseModel):
    """Configuration for creating a new collection."""

    name: str
    vector_size: int = 1024  # BGE-M3 default, override per model
    distance: str = "Cosine"  # Cosine | Dot | Euclid
    hnsw_config: dict[str, Any] = Field(
        default_factory=lambda: {
            "m": 16,
            "ef_construct": 100,
            "full_scan_threshold": 10000,
        }
    )
    optimizers_config: dict[str, Any] = Field(
        default_factory=lambda: {
            "default_segment_number": 2,
            "indexing_threshold": 20000,
        }
    )

    @property
    def distance_metric(self) -> str:
        """Map distance string to Qdrant's internal enum."""
        mapping = {"Cosine": "Cosine", "Dot": "Dot", "Euclid": "Euclid"}
        return mapping.get(self.distance, "Cosine")


# ══════════════════════════════════════════════════════════════════
# Exceptions
# ══════════════════════════════════════════════════════════════════


class VectorStoreError(Exception):
    """Base exception for vector store operations."""


# ══════════════════════════════════════════════════════════════════
# Configuration
# ══════════════════════════════════════════════════════════════════


@dataclass
class QdrantConfig:
    """Qdrant connection configuration loaded from environment."""

    host: str = "localhost"
    port: int = 6333
    grpc_port: int = 6334
    prefer_grpc: bool = False
    api_key: str | None = None
    timeout: int = 10
    collection_name: str = "fde_documents"

    @classmethod
    def from_env(cls) -> QdrantConfig:
        """Load configuration from environment variables.

        Reads:
            QDRANT_HOST          (default: localhost)
            QDRANT_REST_PORT     (default: 6333)
            QDRANT_GRPC_PORT     (default: 6334)
            QDRANT_PREFER_GRPC   (default: false)
            QDRANT_API_KEY       (default: None)
            QDRANT_TIMEOUT       (default: 10)
            QDRANT_COLLECTION    (default: fde_documents)
        """
        import os

        return cls(
            host=os.environ.get("QDRANT_HOST", "localhost"),
            port=int(os.environ.get("QDRANT_REST_PORT", "6333")),
            grpc_port=int(os.environ.get("QDRANT_GRPC_PORT", "6334")),
            prefer_grpc=os.environ.get("QDRANT_PREFER_GRPC", "").lower() == "true",
            api_key=os.environ.get("QDRANT_API_KEY") or None,
            timeout=int(os.environ.get("QDRANT_TIMEOUT", "10")),
            collection_name=os.environ.get("QDRANT_COLLECTION", "fde_documents"),
        )


# ══════════════════════════════════════════════════════════════════
# Vector Store — Qdrant Client Wrapper
# ══════════════════════════════════════════════════════════════════


class VectorStore:
    """Qdrant vector store wrapper with async operations.

    Provides connection management, health checks, collection CRUD,
    and point-level operations. Designed to be used as a singleton
    per agent process.
    """

    def __init__(self, config: QdrantConfig | None = None) -> None:
        self.config = config or QdrantConfig.from_env()
        self._client: Any = None  # qdrant_client.QdrantClient
        self._async_client: Any = None  # qdrant_client.AsyncQdrantClient
        self._connected: bool = False

    # ── Connection Management ────────────────────────────────────

    @property
    def client(self) -> Any:
        """Get or create sync Qdrant client (lazy init)."""
        if self._client is None:
            self._connect_sync()
        return self._client

    @property
    def async_client(self) -> Any:
        """Get or create async Qdrant client (lazy init)."""
        if self._async_client is None:
            self._connect_async()
        return self._async_client

    def _connect_sync(self) -> None:
        """Initialize the synchronous Qdrant client."""
        try:
            from qdrant_client import QdrantClient
            from qdrant_client.http import models as qmodels  # noqa: F401
        except ImportError:
            raise VectorStoreError(
                "qdrant-client is not installed. Install: pip install fde-ai-platform[rag]"
            )

        self._client = QdrantClient(
            host=self.config.host,
            port=self.config.port,
            grpc_port=self.config.grpc_port,
            prefer_grpc=self.config.prefer_grpc,
            api_key=self.config.api_key,
            timeout=self.config.timeout,
        )
        self._connected = True
        logger.info("Qdrant sync client connected to %s:%s", self.config.host, self.config.port)

    def _connect_async(self) -> None:
        """Initialize the asynchronous Qdrant client."""
        try:
            from qdrant_client import AsyncQdrantClient
            from qdrant_client.http import models as qmodels  # noqa: F401
        except ImportError:
            raise VectorStoreError(
                "qdrant-client is not installed. Install: pip install fde-ai-platform[rag]"
            )

        self._async_client = AsyncQdrantClient(
            host=self.config.host,
            port=self.config.port,
            grpc_port=self.config.grpc_port,
            prefer_grpc=self.config.prefer_grpc,
            api_key=self.config.api_key,
            timeout=self.config.timeout,
        )
        logger.info("Qdrant async client connected to %s:%s", self.config.host, self.config.port)

    def close(self) -> None:
        """Close all connections."""
        if self._client is not None:
            self._client.close()
            self._client = None
        if self._async_client is not None:
            import asyncio
            from contextlib import suppress

            with suppress(RuntimeError):
                asyncio.get_event_loop().run_until_complete(self._async_client.close())
            self._async_client = None
        self._connected = False

    # ── Health Check ─────────────────────────────────────────────

    def health_check(self) -> dict[str, str]:
        """Check Qdrant server health.

        Returns:
            Dict with status and version info.

        Raises:
            VectorStoreError: If Qdrant is unreachable.
        """
        try:

            collections = self.client.get_collections()
            return {
                "status": "ok",
                "collections": str(len(collections.collections)),
                "host": f"{self.config.host}:{self.config.port}",
            }
        except Exception as e:
            raise VectorStoreError(f"Qdrant health check failed: {e}") from e

    async def async_health_check(self) -> dict[str, str]:
        """Async health check."""
        try:
            collections = await self.async_client.get_collections()
            return {
                "status": "ok",
                "collections": str(len(collections.collections)),
                "host": f"{self.config.host}:{self.config.port}",
            }
        except Exception as e:
            raise VectorStoreError(f"Qdrant async health check failed: {e}") from e

    # ── Collection Operations ────────────────────────────────────

    def collection_exists(self, name: str | None = None) -> bool:
        """Check if a collection exists."""
        name = name or self.config.collection_name
        try:
            collections = self.client.get_collections()
            return any(c.name == name for c in collections.collections)
        except Exception:
            return False

    async def async_collection_exists(self, name: str | None = None) -> bool:
        """Async check if a collection exists."""
        name = name or self.config.collection_name
        try:
            collections = await self.async_client.get_collections()
            return any(c.name == name for c in collections.collections)
        except Exception:
            return False

    def create_collection(self, config: CollectionConfig | None = None) -> dict[str, Any]:
        """Create a new vector collection.

        Args:
            config: Collection configuration (uses defaults if None).

        Returns:
            Created collection info.
        """
        from qdrant_client.http import models as qmodels

        cfg = config or CollectionConfig(name=self.config.collection_name)

        if self.collection_exists(cfg.name):
            logger.info("Collection '%s' already exists, skipping creation", cfg.name)
            return {"name": cfg.name, "status": "exists"}

        self.client.create_collection(
            collection_name=cfg.name,
            vectors_config=qmodels.VectorParams(
                size=cfg.vector_size,
                distance=qmodels.Distance[cfg.distance.upper()],
                hnsw_config=qmodels.HnswConfigDiff(**cfg.hnsw_config),
            ),
            optimizers_config=qmodels.OptimizersConfigDiff(**cfg.optimizers_config),
        )

        logger.info(
            "Created collection '%s' (size=%d, distance=%s)",
            cfg.name,
            cfg.vector_size,
            cfg.distance,
        )
        return {"name": cfg.name, "status": "created"}

    async def async_create_collection(
        self, config: CollectionConfig | None = None
    ) -> dict[str, Any]:
        """Async: create a new vector collection."""
        from qdrant_client.http import models as qmodels

        cfg = config or CollectionConfig(name=self.config.collection_name)

        if await self.async_collection_exists(cfg.name):
            logger.info("Collection '%s' already exists (async), skipping", cfg.name)
            return {"name": cfg.name, "status": "exists"}

        await self.async_client.create_collection(
            collection_name=cfg.name,
            vectors_config=qmodels.VectorParams(
                size=cfg.vector_size,
                distance=qmodels.Distance[cfg.distance.upper()],
                hnsw_config=qmodels.HnswConfigDiff(**cfg.hnsw_config),
            ),
            optimizers_config=qmodels.OptimizersConfigDiff(**cfg.optimizers_config),
        )

        logger.info("Async created collection '%s'", cfg.name)
        return {"name": cfg.name, "status": "created"}

    def delete_collection(self, name: str | None = None) -> bool:
        """Delete a collection. Returns True if deleted."""
        name = name or self.config.collection_name
        if not self.collection_exists(name):
            logger.warning("Collection '%s' does not exist, cannot delete", name)
            return False

        self.client.delete_collection(collection_name=name)
        logger.info("Deleted collection '%s'", name)
        return True

    async def async_delete_collection(self, name: str | None = None) -> bool:
        """Async: delete a collection."""
        name = name or self.config.collection_name
        if not await self.async_collection_exists(name):
            logger.warning("Collection '%s' does not exist (async), cannot delete", name)
            return False

        await self.async_client.delete_collection(collection_name=name)
        logger.info("Async deleted collection '%s'", name)
        return True

    # ── Point (Vector) Operations ────────────────────────────────

    def upsert(self, points: list[VectorRecord], collection: str | None = None) -> int:
        """Upsert vectors into the store.

        Args:
            points: List of VectorRecord objects with id, vector, and payload.
            collection: Target collection name (default from config).

        Returns:
            Number of upserted points.
        """
        from qdrant_client.http import models as qmodels

        collection = collection or self.config.collection_name

        qdrant_points = [
            qmodels.PointStruct(
                id=p.id,
                vector=p.vector,
                payload=p.payload,
            )
            for p in points
            if p.vector is not None
        ]

        if not qdrant_points:
            logger.warning("No valid points to upsert (all missing vectors)")
            return 0

        self.client.upsert(
            collection_name=collection,
            points=qdrant_points,
            wait=True,
        )
        logger.debug("Upserted %d points to '%s'", len(qdrant_points), collection)
        return len(qdrant_points)

    async def async_upsert(self, points: list[VectorRecord], collection: str | None = None) -> int:
        """Async: upsert vectors."""
        from qdrant_client.http import models as qmodels

        collection = collection or self.config.collection_name

        qdrant_points = [
            qmodels.PointStruct(
                id=p.id,
                vector=p.vector,
                payload=p.payload,
            )
            for p in points
            if p.vector is not None
        ]

        if not qdrant_points:
            logger.warning("No valid points to upsert (async, all missing vectors)")
            return 0

        await self.async_client.upsert(
            collection_name=collection,
            points=qdrant_points,
            wait=True,
        )
        logger.debug("Async upserted %d points to '%s'", len(qdrant_points), collection)
        return len(qdrant_points)

    def search(
        self,
        vector: list[float],
        top_k: int = 10,
        collection: str | None = None,
        score_threshold: float | None = None,
        filter_conditions: dict[str, Any] | None = None,
    ) -> list[VectorRecord]:
        """Search for similar vectors.

        Args:
            vector: Query vector.
            top_k: Number of results to return.
            collection: Target collection name.
            score_threshold: Minimum similarity score.
            filter_conditions: Payload filter conditions.

        Returns:
            List of VectorRecord results ordered by score descending.
        """
        from qdrant_client.http import models as qmodels

        collection = collection or self.config.collection_name

        query_filter = None
        if filter_conditions:
            query_filter = qmodels.Filter(must=_build_filter_conditions(filter_conditions))

        search_params = qmodels.SearchParams(
            hnsw_ef=128,
            exact=False,
        )

        results = self.client.search(
            collection_name=collection,
            query_vector=vector,
            limit=top_k,
            search_params=search_params,
            query_filter=query_filter,
            score_threshold=score_threshold,
        )

        return [
            VectorRecord(
                id=r.id,
                payload=r.payload,
                score=r.score,
            )
            for r in results
        ]

    async def async_search(
        self,
        vector: list[float],
        top_k: int = 10,
        collection: str | None = None,
        score_threshold: float | None = None,
        filter_conditions: dict[str, Any] | None = None,
    ) -> list[VectorRecord]:
        """Async: search for similar vectors."""
        from qdrant_client.http import models as qmodels

        collection = collection or self.config.collection_name

        query_filter = None
        if filter_conditions:
            query_filter = qmodels.Filter(must=_build_filter_conditions(filter_conditions))

        search_params = qmodels.SearchParams(
            hnsw_ef=128,
            exact=False,
        )

        results = await self.async_client.search(
            collection_name=collection,
            query_vector=vector,
            limit=top_k,
            search_params=search_params,
            query_filter=query_filter,
            score_threshold=score_threshold,
        )

        return [
            VectorRecord(
                id=r.id,
                payload=r.payload,
                score=r.score,
            )
            for r in results
        ]

    def count(self, collection: str | None = None) -> int:
        """Count points in a collection."""
        collection = collection or self.config.collection_name
        result: Any = self.client.count(collection_name=collection)
        return result.count  # type: ignore[no-any-return]

    async def async_count(self, collection: str | None = None) -> int:
        """Async: count points in a collection."""
        collection = collection or self.config.collection_name
        result: Any = await self.async_client.count(collection_name=collection)
        return result.count  # type: ignore[no-any-return]

    def delete_points(
        self,
        point_ids: list[str | int],
        collection: str | None = None,
    ) -> int:
        """Delete specific points by ID."""
        collection = collection or self.config.collection_name
        self.client.delete(
            collection_name=collection,
            points_selector=point_ids,
            wait=True,
        )
        logger.debug("Deleted %d points from '%s'", len(point_ids), collection)
        return len(point_ids)

    async def async_delete_points(
        self,
        point_ids: list[str | int],
        collection: str | None = None,
    ) -> int:
        """Async: delete specific points by ID."""
        collection = collection or self.config.collection_name
        await self.async_client.delete(
            collection_name=collection,
            points_selector=point_ids,
            wait=True,
        )
        logger.debug("Async deleted %d points from '%s'", len(point_ids), collection)
        return len(point_ids)


# ══════════════════════════════════════════════════════════════════
# Internal Helpers
# ══════════════════════════════════════════════════════════════════


def _build_filter_conditions(
    conditions: dict[str, Any],
) -> list[Any]:
    """Build Qdrant filter conditions from a simple dict.

    Supported key patterns:
        - key: value       → match value
        - key__gt: value   → greater than
        - key__gte: value  → greater than or equal
        - key__lt: value   → less than
        - key__lte: value  → less than or equal
        - key__in: [a,b]   → match any in list
    """
    from qdrant_client.http import models as qmodels

    must_conditions: list[Any] = []

    for key, value in conditions.items():
        if "__" in key:
            field, op = key.rsplit("__", 1)
            if op == "gt":
                must_conditions.append(
                    qmodels.FieldCondition(key=field, range=qmodels.Range(gt=value))
                )
            elif op == "gte":
                must_conditions.append(
                    qmodels.FieldCondition(key=field, range=qmodels.Range(gte=value))
                )
            elif op == "lt":
                must_conditions.append(
                    qmodels.FieldCondition(key=field, range=qmodels.Range(lt=value))
                )
            elif op == "lte":
                must_conditions.append(
                    qmodels.FieldCondition(key=field, range=qmodels.Range(lte=value))
                )
            elif op == "in":
                must_conditions.append(
                    qmodels.FieldCondition(key=field, match=qmodels.MatchAny(any=value))
                )
        else:
            must_conditions.append(
                qmodels.FieldCondition(key=key, match=qmodels.MatchValue(value=value))
            )

    return must_conditions
