"""P6a tests: async ingestion tasks, queue, worker, endpoints."""

from __future__ import annotations

import hashlib
import uuid

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool

import agents.ingestion_agent.pipeline  # noqa: F401 — register ingestion ORM tables
from agents.governance_agent.database.session import Base
from agents.ingestion_agent.fts import ensure_fts_table
from agents.ingestion_agent.task_models import (
    STATUS_FAILED,
    STATUS_PENDING,
    STATUS_PROCESSING,
    IngestTask,
)
from agents.ingestion_agent.tasks import IngestTaskQueue

# ════════════════════════════════════════════════════════════════
# Fixtures
# ════════════════════════════════════════════════════════════════


@pytest_asyncio.fixture
async def db_session():
    """SQLite in-memory session with all tables + FTS."""
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # Create ingest_tasks table (not yet in Base.metadata for new model)
        await conn.run_sync(
            lambda sync_conn: sync_conn.exec_driver_sql(
                """CREATE TABLE IF NOT EXISTS ingest_tasks (
                    id VARCHAR(36) PRIMARY KEY,
                    status VARCHAR(20) NOT NULL DEFAULT 'pending',
                    filename VARCHAR(512) NOT NULL,
                    file_hash VARCHAR(128),
                    doc_type VARCHAR(128) NOT NULL,
                    content_type VARCHAR(128),
                    progress_pct INTEGER DEFAULT 0,
                    total_chunks INTEGER DEFAULT 0,
                    indexed_chunks INTEGER DEFAULT 0,
                    canonical_count INTEGER DEFAULT 0,
                    result JSON,
                    error_message TEXT,
                    raw_id VARCHAR(36),
                    storage_ref VARCHAR(512),
                    created_at DATETIME NOT NULL DEFAULT (datetime('now')),
                    updated_at DATETIME NOT NULL DEFAULT (datetime('now'))
                )"""
            )
        )
    await ensure_fts_table(engine)

    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as s:
        yield s
    await engine.dispose()


# ════════════════════════════════════════════════════════════════
# Task Queue
# ════════════════════════════════════════════════════════════════


class TestTaskQueue:
    @pytest.mark.asyncio
    async def test_enqueue_dequeue(self) -> None:
        queue = IngestTaskQueue()
        await queue.enqueue("task-1")
        assert queue.size == 1
        tid = await queue.dequeue()
        assert tid == "task-1"
        assert queue.size == 0

    @pytest.mark.asyncio
    async def test_queue_ordering(self) -> None:
        queue = IngestTaskQueue()
        ids = ["a", "b", "c"]
        for i in ids:
            await queue.enqueue(i)
        results = []
        for _ in range(3):
            results.append(await queue.dequeue())
        assert results == ids  # FIFO


# ════════════════════════════════════════════════════════════════
# Task model lifecycle
# ════════════════════════════════════════════════════════════════


class TestTaskLifecycle:
    @pytest.mark.asyncio
    async def test_create_pending(self, db_session: AsyncSession) -> None:
        tid = str(uuid.uuid4())
        task = IngestTask(
            id=tid, status=STATUS_PENDING,
            filename="test.csv", doc_type="test",
        )
        db_session.add(task)
        await db_session.commit()

        fetched = await db_session.get(IngestTask, tid)
        assert fetched is not None
        assert fetched.status == STATUS_PENDING

    @pytest.mark.asyncio
    async def test_lifecycle_pending_to_completed(self, db_session: AsyncSession) -> None:
        tid = str(uuid.uuid4())
        task = IngestTask(id=tid, status=STATUS_PENDING, filename="f.csv", doc_type="d")
        db_session.add(task)
        await db_session.commit()

        # processing
        task = await db_session.get(IngestTask, tid)
        task.status = STATUS_PROCESSING
        task.progress_pct = 50
        await db_session.commit()

        fetched = await db_session.get(IngestTask, tid)
        assert fetched.status == STATUS_PROCESSING
        assert fetched.progress_pct == 50

    @pytest.mark.asyncio
    async def test_lifecycle_failed(self, db_session: AsyncSession) -> None:
        tid = str(uuid.uuid4())
        task = IngestTask(id=tid, status=STATUS_PENDING, filename="f.csv", doc_type="d")
        db_session.add(task)
        await db_session.commit()

        task = await db_session.get(IngestTask, tid)
        task.status = STATUS_FAILED
        task.error_message = "Parse error: invalid encoding"
        await db_session.commit()

        fetched = await db_session.get(IngestTask, tid)
        assert fetched.status == STATUS_FAILED
        assert "Parse error" in fetched.error_message

    @pytest.mark.asyncio
    async def test_content_hash_is_set(self, db_session: AsyncSession) -> None:
        tid = str(uuid.uuid4())
        h = hashlib.sha256(b"content").hexdigest()
        task = IngestTask(
            id=tid, status=STATUS_PENDING,
            filename="f.csv", doc_type="d", file_hash=h,
        )
        db_session.add(task)
        await db_session.commit()

        fetched = await db_session.get(IngestTask, tid)
        assert fetched.file_hash == h


# ════════════════════════════════════════════════════════════════
# Router E2E — async endpoint
# ════════════════════════════════════════════════════════════════


class TestAsyncUploadEndpoint:
    @pytest.mark.asyncio
    async def test_async_upload_returns_task_id(self, db_session: AsyncSession) -> None:
        """Verify POST /ingest/upload/async returns task_id and creates task."""
        from fastapi.testclient import TestClient

        from agents.ingestion_agent.storage import get_storage
        from agents.ingestion_agent.tests.fakes import FakeStorage
        from agents.router_agent.main import app

        # Override storage to fake
        app.dependency_overrides[get_storage] = lambda: FakeStorage()
        from agents.governance_agent.database.session import get_async_session

        async def override_session():
            yield db_session

        app.dependency_overrides[get_async_session] = override_session

        client = TestClient(app)
        resp = client.post(
            "/ingest/upload/async",
            files={"file": ("test.csv", b"a,b\n1,2\n", "text/csv")},
            data={"doc_type": "p6a-test"},
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert "task_id" in data
        assert data["status"] == STATUS_PENDING

    @pytest.mark.asyncio
    async def test_task_status_returns_404_for_unknown(self, db_session: AsyncSession) -> None:
        from fastapi.testclient import TestClient

        from agents.governance_agent.database.session import get_async_session
        from agents.router_agent.main import app

        async def override_session():
            yield db_session

        app.dependency_overrides[get_async_session] = override_session

        client = TestClient(app)
        resp = client.get("/ingest/tasks/nonexistent-id")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_async_rejects_unsupported_ext(self, db_session: AsyncSession) -> None:
        from fastapi.testclient import TestClient

        from agents.ingestion_agent.storage import get_storage
        from agents.ingestion_agent.tests.fakes import FakeStorage
        from agents.router_agent.main import app

        app.dependency_overrides[get_storage] = lambda: FakeStorage()
        from agents.governance_agent.database.session import get_async_session

        async def override_session():
            yield db_session

        app.dependency_overrides[get_async_session] = override_session

        client = TestClient(app)
        resp = client.post(
            "/ingest/upload/async",
            files={"file": ("test.exe", b"bad", "application/octet-stream")},
            data={"doc_type": "bad"},
        )
        assert resp.status_code == 400
