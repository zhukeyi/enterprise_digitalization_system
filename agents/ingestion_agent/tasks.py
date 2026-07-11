"""P6a: Async ingestion task queue + background worker (单机, asyncio.Queue).

Design:
- IngestTaskQueue: bounded asyncio.Queue (backpressure at CONCURRENCY_MAX)
- IngestWorker: single asyncio background task that pops from the queue,
  runs the full pipeline, and updates task status in the DB.

When the API handler receives an upload:
1. Create IngestTask (status=pending) in DB
2. Push task_id to the queue
3. Return 202 {task_id, status: "pending"}

The worker picks up the task and runs:
1. Mark status=processing
2. Parse → normalize → outbox DB → batch embed → Qdrant upsert → FTS index
3. Mark status=completed (or failed/partial)
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from agents.ingestion_agent.pipeline import IngestionPipeline
from agents.ingestion_agent.task_models import (
    STATUS_COMPLETED,
    STATUS_FAILED,
    STATUS_PROCESSING,
    IngestTask,
)

logger = logging.getLogger("fde.ingest.worker")

# ── Configurable constants ─────────────────────────────────────

# Max concurrent ingest jobs (backpressure)
INGEST_CONCURRENCY_MAX = 3
# Batch size for embedding (vectors at once)
EMBED_BATCH_SIZE = 32
# Max retries for Qdrant upsert
QDRANT_MAX_RETRIES = 3


# ════════════════════════════════════════════════════════════════
# Task Queue
# ════════════════════════════════════════════════════════════════


class IngestTaskQueue:
    """Bounded async queue for ingestion tasks (single-node, no redis/celery)."""

    def __init__(self, maxsize: int = 100) -> None:
        self._queue: asyncio.Queue[str] = asyncio.Queue(maxsize=maxsize)

    async def enqueue(self, task_id: str) -> None:
        await self._queue.put(task_id)

    async def dequeue(self) -> str:
        return await self._queue.get()

    @property
    def size(self) -> int:
        return self._queue.qsize()

    def task_done(self) -> None:
        self._queue.task_done()


# ════════════════════════════════════════════════════════════════
# Progress tracking
# ════════════════════════════════════════════════════════════════


class ProgressTracker:
    """Tracks pipeline progress per-task and updates DB status."""

    def __init__(self, task: IngestTask) -> None:
        self.task = task
        self._total_steps = 0
        self._current_step = 0

    def set_total_steps(self, n: int) -> None:
        self._total_steps = n

    async def step(self, session: AsyncSession) -> None:
        self._current_step += 1
        if self._total_steps > 0:
            pct = min(99, int(self._current_step / self._total_steps * 100))
            self.task.progress_pct = pct
        if self._current_step % 3 == 0:  # update DB every ~3 steps
            await session.flush()


# ════════════════════════════════════════════════════════════════
# Background Worker
# ════════════════════════════════════════════════════════════════


class IngestWorker:
    """Background worker that processes ingestion tasks from the queue.

    Spawns a single asyncio task that loops forever, dequeuing jobs
    and running the pipeline. Designed to run alongside the FastAPI
    app (started in the lifespan/startup handler).
    """

    def __init__(
        self,
        queue: IngestTaskQueue,
        session_factory: Any,  # async_sessionmaker
        vector_store: Any,
        embedding_model: Any,
        object_storage: Any,
    ) -> None:
        self._queue = queue
        self._session_factory = session_factory
        self._vector_store = vector_store
        self._embedding_model = embedding_model
        self._object_storage = object_storage
        self._task: asyncio.Task[None] | None = None
        self._running = False

    async def start(self) -> None:
        """Start the background worker loop."""
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._loop())
        logger.info("IngestWorker started (concurrency=%d)", INGEST_CONCURRENCY_MAX)

    async def stop(self) -> None:
        """Gracefully stop the worker."""
        self._running = False
        if self._task:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
        logger.info("IngestWorker stopped")

    async def _loop(self) -> None:
        """Main worker loop — dequeue and process forever."""
        while self._running:
            try:
                task_id = await self._queue.dequeue()
                try:
                    await self._process(task_id)
                except Exception:
                    logger.exception("Worker failed to process task %s", task_id)
                finally:
                    self._queue.task_done()
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("Worker loop error")
                await asyncio.sleep(1)

    async def _process(self, task_id: str) -> None:
        """Process a single ingestion task end-to-end."""
        t0 = time.monotonic()
        logger.info("Processing task %s", task_id)

        async with self._session_factory() as session:
            async with session.begin():
                task = await session.get(IngestTask, task_id)
                if task is None:
                    logger.warning("Task %s not found in DB", task_id)
                    return
                task.status = STATUS_PROCESSING
                task.progress_pct = 0
                await session.commit()

            try:
                # 1. Parse file from storage
                file_data = await self._object_storage.get(task.storage_ref) if task.storage_ref else None
                if file_data is None:
                    raise RuntimeError(f"File data not found at {task.storage_ref}")

                # 2. Run pipeline (outbox: DB first, then Qdrant)
                result = await IngestionPipeline.ingest_file(
                    task.filename,
                    file_data,
                    doc_type=task.doc_type,
                    session=session,
                    vector_store=self._vector_store,
                    embedding_model=self._embedding_model,
                    storage=self._object_storage,
                )

                # 3. Update task result
                async with session.begin():
                    task.status = STATUS_COMPLETED
                    task.progress_pct = 100
                    task.canonical_count = result.get("canonical", 0)
                    task.total_chunks = result.get("chunks", 0)
                    task.indexed_chunks = result.get("indexed_vectors", 0)
                    task.raw_id = result.get("raw_id")
                    task.storage_ref = result.get("storage_ref")
                    task.result = result
                    await session.commit()

                elapsed = time.monotonic() - t0
                logger.info(
                    "Task %s completed in %.1fs: canonical=%d chunks=%d vectors=%d",
                    task_id,
                    elapsed,
                    task.canonical_count,
                    task.total_chunks,
                    task.indexed_chunks,
                )

            except Exception as exc:
                logger.exception("Task %s failed", task_id)
                async with session.begin():
                    task = await session.get(IngestTask, task_id)
                    if task:
                        task.status = STATUS_FAILED
                        task.error_message = str(exc)[:2000]
                        await session.commit()


# ════════════════════════════════════════════════════════════════
# Module-level singletons (initialized at startup)
# ════════════════════════════════════════════════════════════════

_queue: IngestTaskQueue | None = None
_worker: IngestWorker | None = None


def get_queue() -> IngestTaskQueue:
    """Return the module-level task queue singleton."""
    global _queue
    if _queue is None:
        _queue = IngestTaskQueue()
    return _queue


def get_worker() -> IngestWorker | None:
    """Return the module-level worker singleton (or None if not started)."""
    return _worker


async def start_worker(
    session_factory: Any,
    vector_store: Any,
    embedding_model: Any,
    object_storage: Any,
) -> IngestWorker:
    """Initialize and start the ingest worker (called from app startup)."""
    global _worker
    queue = get_queue()
    _worker = IngestWorker(queue, session_factory, vector_store, embedding_model, object_storage)
    await _worker.start()
    return _worker


async def stop_worker() -> None:
    """Gracefully stop the ingest worker (called from app shutdown)."""
    global _worker
    if _worker:
        await _worker.stop()
        _worker = None
