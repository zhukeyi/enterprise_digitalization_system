"""Tests for Qdrant vector store wrapper.

M1-T8: Tests run without a real Qdrant instance — qdrant_client is mocked.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch

import pytest

from agents.rag_agent.vector_store import (
    CollectionConfig,
    QdrantConfig,
    VectorRecord,
    VectorStore,
    VectorStoreError,
)


# ══════════════════════════════════════════════════════════════════
# Fixtures
# ══════════════════════════════════════════════════════════════════


@pytest.fixture
def qdrant_config() -> QdrantConfig:
    return QdrantConfig(host="test-host", port=6333, timeout=5.0)


@pytest.fixture
def mock_qdrant_client() -> MagicMock:
    """Create a fully mocked Qdrant sync client."""
    client = MagicMock()
    # Mock get_collections
    collections_mock = MagicMock()
    col1 = MagicMock()
    col1.name = "test_collection"
    collections_mock.collections = [col1]
    client.get_collections.return_value = collections_mock
    # Mock count
    count_result = MagicMock()
    count_result.count = 42
    client.count.return_value = count_result
    # Mock search
    search_result = MagicMock()
    search_result.id = "doc-1"
    search_result.payload = {"text": "hello"}
    search_result.score = 0.95
    client.search.return_value = [search_result]
    return client


@pytest.fixture
def mock_qdrant_async_client() -> AsyncMock:
    """Create a fully mocked Qdrant async client."""
    client = AsyncMock()
    # Mock get_collections
    collections_mock = MagicMock()
    col1 = MagicMock()
    col1.name = "test_collection"
    collections_mock.collections = [col1]
    client.get_collections.return_value = collections_mock
    # Mock count
    count_result = MagicMock()
    count_result.count = 42
    client.count.return_value = count_result
    return client


@pytest.fixture
def store(qdrant_config: QdrantConfig) -> VectorStore:
    return VectorStore(config=qdrant_config)


# ══════════════════════════════════════════════════════════════════
# QdrantConfig Tests
# ══════════════════════════════════════════════════════════════════


class TestQdrantConfig:
    def test_default_values(self) -> None:
        config = QdrantConfig()
        assert config.host == "localhost"
        assert config.port == 6333
        assert config.grpc_port == 6334
        assert config.prefer_grpc is False
        assert config.api_key is None
        assert config.timeout == 10.0
        assert config.collection_name == "fde_documents"

    def test_custom_values(self) -> None:
        config = QdrantConfig(host="qdrant.example.com", port=6335, api_key="secret")
        assert config.host == "qdrant.example.com"
        assert config.port == 6335
        assert config.api_key == "secret"

    @patch.dict("os.environ", {"QDRANT_HOST": "env-host", "QDRANT_REST_PORT": "9999"}, clear=False)
    def test_from_env(self) -> None:
        config = QdrantConfig.from_env()
        assert config.host == "env-host"
        assert config.port == 9999


# ══════════════════════════════════════════════════════════════════
# CollectionConfig Tests
# ══════════════════════════════════════════════════════════════════


class TestCollectionConfig:
    def test_default_config(self) -> None:
        config = CollectionConfig(name="test")
        assert config.vector_size == 1024
        assert config.distance == "Cosine"
        assert config.hnsw_config["m"] == 16

    def test_custom_vector_size(self) -> None:
        config = CollectionConfig(name="test", vector_size=768)
        assert config.vector_size == 768

    def test_distance_mapping(self) -> None:
        assert CollectionConfig(name="t", distance="Cosine").distance_metric == "Cosine"
        assert CollectionConfig(name="t", distance="Dot").distance_metric == "Dot"
        assert CollectionConfig(name="t", distance="Euclid").distance_metric == "Euclid"


# ══════════════════════════════════════════════════════════════════
# VectorStore Tests (mocked)
# ══════════════════════════════════════════════════════════════════


class TestVectorStoreInit:
    def test_config_from_env_fallback(self) -> None:
        """When no config provided, should load from env defaults."""
        store = VectorStore()  # noqa: F841


class TestVectorStoreHealth:
    def test_health_check(
        self, store: VectorStore, mock_qdrant_client: MagicMock
    ) -> None:
        store._client = mock_qdrant_client
        result = store.health_check()
        assert result["status"] == "ok"
        assert "collections" in result
        assert "host" in result
        mock_qdrant_client.get_collections.assert_called_once()

    def test_health_check_failure(self, store: VectorStore) -> None:
        """Should raise VectorStoreError when Qdrant is unreachable."""
        bad_client = MagicMock()
        bad_client.get_collections.side_effect = ConnectionError("refused")
        store._client = bad_client
        with pytest.raises(VectorStoreError, match="Qdrant health check failed"):
            store.health_check()

    async def test_async_health_check(
        self, store: VectorStore, mock_qdrant_async_client: AsyncMock
    ) -> None:
        store._async_client = mock_qdrant_async_client
        result = await store.async_health_check()
        assert result["status"] == "ok"
        mock_qdrant_async_client.get_collections.assert_called_once()


class TestVectorStoreCollection:
    def test_collection_exists(
        self, store: VectorStore, mock_qdrant_client: MagicMock
    ) -> None:
        store._client = mock_qdrant_client
        exists = store.collection_exists("test_collection")
        assert exists is True
        mock_qdrant_client.get_collections.assert_called_once()

    def test_collection_not_exists(
        self, store: VectorStore, mock_qdrant_client: MagicMock
    ) -> None:
        store._client = mock_qdrant_client
        exists = store.collection_exists("nonexistent")
        assert exists is False

    def test_create_collection(
        self, store: VectorStore, mock_qdrant_client: MagicMock
    ) -> None:
        store._client = mock_qdrant_client
        config = CollectionConfig(name="new_coll", vector_size=768)
        result = store.create_collection(config)
        assert result["status"] == "created"
        assert result["name"] == "new_coll"

    def test_create_collection_exists(
        self, store: VectorStore, mock_qdrant_client: MagicMock
    ) -> None:
        store._client = mock_qdrant_client
        result = store.create_collection(CollectionConfig(name="test_collection"))
        assert result["status"] == "exists"

    def test_delete_collection(
        self, store: VectorStore, mock_qdrant_client: MagicMock
    ) -> None:
        store._client = mock_qdrant_client
        result = store.delete_collection("test_collection")
        assert result is True
        mock_qdrant_client.delete_collection.assert_called_once_with(
            collection_name="test_collection"
        )

    def test_delete_collection_not_exists(
        self, store: VectorStore, mock_qdrant_client: MagicMock
    ) -> None:
        store._client = mock_qdrant_client
        result = store.delete_collection("nonexistent")
        assert result is False


class TestVectorStorePoints:
    def test_upsert(
        self, store: VectorStore, mock_qdrant_client: MagicMock
    ) -> None:
        store._client = mock_qdrant_client
        points = [
            VectorRecord(id=1, vector=[0.1, 0.2, 0.3], payload={"text": "hello"}),
            VectorRecord(id=2, vector=[0.4, 0.5, 0.6], payload={"text": "world"}),
        ]
        count = store.upsert(points)
        assert count == 2
        mock_qdrant_client.upsert.assert_called_once()
        args, kwargs = mock_qdrant_client.upsert.call_args
        assert kwargs["collection_name"] == "fde_documents"
        assert len(kwargs["points"]) == 2

    def test_upsert_empty_vectors(
        self, store: VectorStore, mock_qdrant_client: MagicMock
    ) -> None:
        store._client = mock_qdrant_client
        points = [
            VectorRecord(id=1, vector=None, payload={"text": "no-vector"}),
        ]
        count = store.upsert(points)
        assert count == 0
        mock_qdrant_client.upsert.assert_not_called()

    def test_search(
        self, store: VectorStore, mock_qdrant_client: MagicMock
    ) -> None:
        store._client = mock_qdrant_client
        results = store.search(vector=[0.1, 0.2, 0.3], top_k=5)
        assert len(results) == 1
        assert results[0].id == "doc-1"
        assert results[0].score == 0.95
        mock_qdrant_client.search.assert_called_once()

    def test_search_with_filter(
        self, store: VectorStore, mock_qdrant_client: MagicMock
    ) -> None:
        store._client = mock_qdrant_client
        results = store.search(
            vector=[0.1, 0.2, 0.3],
            filter_conditions={"source": "pdf", "page__gte": 1},
        )
        assert len(results) == 1
        mock_qdrant_client.search.assert_called_once()
        args, kwargs = mock_qdrant_client.search.call_args
        assert kwargs["query_filter"] is not None

    def test_count(
        self, store: VectorStore, mock_qdrant_client: MagicMock
    ) -> None:
        store._client = mock_qdrant_client
        count = store.count()
        assert count == 42

    def test_delete_points(
        self, store: VectorStore, mock_qdrant_client: MagicMock
    ) -> None:
        store._client = mock_qdrant_client
        count = store.delete_points(["point-1", "point-2"])
        assert count == 2
        mock_qdrant_client.delete.assert_called_once()


class TestVectorStoreAsyncPoints:
    async def test_async_upsert(
        self, store: VectorStore, mock_qdrant_async_client: AsyncMock
    ) -> None:
        store._async_client = mock_qdrant_async_client
        points = [
            VectorRecord(id=1, vector=[0.1, 0.2], payload={"text": "hello"}),
        ]
        count = await store.async_upsert(points)
        assert count == 1
        mock_qdrant_async_client.upsert.assert_called_once()

    async def test_async_search(
        self, store: VectorStore, mock_qdrant_async_client: AsyncMock
    ) -> None:
        search_result = MagicMock()
        search_result.id = "doc-1"
        search_result.payload = {"text": "hello"}
        search_result.score = 0.95
        mock_qdrant_async_client.search.return_value = [search_result]

        store._async_client = mock_qdrant_async_client
        results = await store.async_search(vector=[0.1, 0.2])
        assert len(results) == 1
        assert results[0].id == "doc-1"

    async def test_async_count(
        self, store: VectorStore, mock_qdrant_async_client: AsyncMock
    ) -> None:
        store._async_client = mock_qdrant_async_client
        count = await store.async_count()
        assert count == 42

    async def test_async_collection_ops(
        self, store: VectorStore, mock_qdrant_async_client: AsyncMock
    ) -> None:
        store._async_client = mock_qdrant_async_client
        exists = await store.async_collection_exists("test_collection")
        assert exists is True

        result = await store.async_create_collection(
            CollectionConfig(name="new_coll")
        )
        assert result["status"] == "created"

        deleted = await store.async_delete_collection("test_collection")
        assert deleted is True

    async def test_async_collection_exists_already(
        self, store: VectorStore, mock_qdrant_async_client: AsyncMock
    ) -> None:
        store._async_client = mock_qdrant_async_client
        result = await store.async_create_collection(
            CollectionConfig(name="test_collection")
        )
        assert result["status"] == "exists"


# ══════════════════════════════════════════════════════════════════
# VectorRecord Tests
# ══════════════════════════════════════════════════════════════════


class TestVectorRecord:
    def test_record_with_all_fields(self) -> None:
        record = VectorRecord(id=1, vector=[0.1, 0.2], payload={"key": "val"}, score=0.9)
        assert record.id == 1
        assert record.vector == [0.1, 0.2]
        assert record.payload == {"key": "val"}
        assert record.score == 0.9

    def test_record_minimal(self) -> None:
        record = VectorRecord(id="abc")
        assert record.id == "abc"
        assert record.vector is None
        assert record.payload == {}
        assert record.score is None