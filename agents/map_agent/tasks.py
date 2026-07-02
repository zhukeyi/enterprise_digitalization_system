"""MapAgent async tasks — background analysis execution (M3-T11).

Provides async task execution for long-running analysis operations:
1. Run analysis pipeline in background (FastAPI BackgroundTasks)
2. Push progress updates via WebSocket
3. Store results for retrieval

Uses FastAPI BackgroundTasks for lightweight async execution.
Celery can be added later for heavy-duty task queuing.

Usage:
    from agents.map_agent.tasks import run_analysis_async
    from fastapi import BackgroundTasks

    @router.post("/analysis/async")
    async def start_analysis(body: AnalysisRequest, bg: BackgroundTasks):
        task_id = run_analysis_async(bg, body, session_id="sess_123")
        return {"task_id": task_id, "status": "started"}
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from agents.map_agent.foolproof import validate_analysis_request
from agents.map_agent.models import AnalysisRequest, AnalysisResult
from agents.map_agent.websocket import get_manager

logger = logging.getLogger("fde.map.tasks")

__all__ = [
    "TaskInfo",
    "TaskStore",
    "get_task_store",
    "run_analysis_async",
    "run_analysis_background",
]


# ══════════════════════════════════════════════════════════════════
# Task State
# ══════════════════════════════════════════════════════════════════


@dataclass
class TaskInfo:
    """Information about a background analysis task.

    Attributes:
        task_id: Unique task identifier.
        session_id: WebSocket session for progress push.
        status: Current status (pending, running, completed, failed).
        entity_ids: Entity IDs being analyzed.
        result: Analysis result (None until completed).
        error: Error message (None unless failed).
        created_at: Task creation timestamp.
        completed_at: Task completion timestamp.
        progress: Progress percentage (0-100).
    """

    task_id: str
    session_id: str
    status: str = "pending"
    entity_ids: list[str] = field(default_factory=list)
    result: AnalysisResult | None = None
    error: str | None = None
    created_at: float = field(default_factory=time.time)
    completed_at: float | None = None
    progress: int = 0


class TaskStore:
    """In-memory store for background task states."""

    def __init__(self) -> None:
        self._tasks: dict[str, TaskInfo] = {}

    def create(self, task_id: str, session_id: str, entity_ids: list[str]) -> TaskInfo:
        info = TaskInfo(task_id=task_id, session_id=session_id, entity_ids=entity_ids)
        self._tasks[task_id] = info
        return info

    def get(self, task_id: str) -> TaskInfo | None:
        return self._tasks.get(task_id)

    def update(self, task_id: str, **kwargs: Any) -> TaskInfo | None:
        info = self._tasks.get(task_id)
        if info is None:
            return None
        for key, val in kwargs.items():
            setattr(info, key, val)
        return info

    def list_all(self) -> list[TaskInfo]:
        return list(self._tasks.values())

    def cleanup(self, max_age: float = 3600) -> int:
        """Remove tasks older than max_age seconds. Returns count removed."""
        now = time.time()
        to_remove = [
            tid
            for tid, info in self._tasks.items()
            if now - info.created_at > max_age and info.status in ("completed", "failed")
        ]
        for tid in to_remove:
            del self._tasks[tid]
        return len(to_remove)


# Singleton
_store: TaskStore | None = None


def get_task_store() -> TaskStore:
    """Get the singleton TaskStore instance."""
    global _store
    if _store is None:
        _store = TaskStore()
    return _store


# ══════════════════════════════════════════════════════════════════
# Async Analysis Execution
# ══════════════════════════════════════════════════════════════════


def run_analysis_async(
    background_tasks: Any,
    request: AnalysisRequest,
    session_id: str = "",
) -> str:
    """Queue an analysis task to run in the background.

    Args:
        background_tasks: FastAPI BackgroundTasks instance.
        request: The analysis request with entity IDs.
        session_id: WebSocket session ID for progress push.

    Returns:
        The task ID for tracking.
    """
    task_id = f"task_{uuid.uuid4().hex[:8]}"
    store = get_task_store()
    store.create(task_id, session_id, request.entity_ids)

    # Add to FastAPI background tasks
    background_tasks.add_task(
        _execute_analysis_task,
        task_id=task_id,
        request=request,
        session_id=session_id,
    )

    logger.info("Queued analysis task: %s (session: %s)", task_id, session_id)
    return task_id


async def _execute_analysis_task(
    task_id: str,
    request: AnalysisRequest,
    session_id: str,
) -> None:
    """Execute the analysis pipeline asynchronously with progress push.

    This function runs in a background task and:
    1. Validates the request (foolproof)
    2. Runs the 3-node pipeline (fetch -> correlate -> interpret)
    3. Pushes progress updates via WebSocket at each stage
    4. Stores the final result in TaskStore
    """
    store = get_task_store()
    manager = get_manager()

    store.update(task_id, status="running")

    # Validate
    validation = validate_analysis_request(request.entity_ids)
    if not validation.ok:
        store.update(task_id, status="failed", error=validation.message)
        await manager.send_error(session_id, validation.message)
        logger.error("Task %s validation failed: %s", task_id, validation.message)
        return

    try:
        # Stage 1: fetch entities
        await manager.send_progress(session_id, "fetch_entities", 25, "正在获取实体数据...")
        store.update(task_id, progress=25)

        from agents.map_agent.langgraph_nodes import run_pipeline

        start = time.monotonic()
        state = run_pipeline(
            entity_ids=request.entity_ids,
            method=request.method,
            query=request.query,
        )
        total_ms = int((time.monotonic() - start) * 1000)

        # Stage 2: correlation (part of pipeline)
        await manager.send_progress(session_id, "compute_correlation", 60, "正在计算相关性...")
        store.update(task_id, progress=60)

        # Stage 3: interpretation (part of pipeline)
        await manager.send_progress(session_id, "generate_interpretation", 85, "正在生成解读...")
        store.update(task_id, progress=85)

        # Build result
        correlation = state.get("correlation")
        entities = state.get("entities", [])

        result = AnalysisResult(
            entity_ids=request.entity_ids,
            entities=entities,
            correlation=correlation,
            interpretation=state.get("interpretation", ""),
            execution_time_ms=total_ms,
            nodes_traced=state.get("nodes_traced", []),
            errors=state.get("errors", []),
        )

        # Complete
        store.update(
            task_id,
            status="completed",
            progress=100,
            result=result,
            completed_at=time.time(),
        )

        await manager.send_progress(session_id, "complete", 100, "分析完成")
        await manager.send_result(session_id, result.model_dump())

        logger.info("Task %s completed in %dms", task_id, total_ms)

    except Exception as e:
        store.update(task_id, status="failed", error=str(e), completed_at=time.time())
        await manager.send_error(session_id, f"分析失败: {e}")
        logger.error("Task %s failed: %s", task_id, e)


async def run_analysis_background(
    request: AnalysisRequest,
    session_id: str = "",
) -> str:
    """Start analysis as an asyncio task (alternative to FastAPI BackgroundTasks).

    Useful when not inside a FastAPI request context.

    Args:
        request: The analysis request.
        session_id: WebSocket session ID for progress.

    Returns:
        The task ID.
    """
    task_id = f"task_{uuid.uuid4().hex[:8]}"
    store = get_task_store()
    store.create(task_id, session_id, request.entity_ids)

    _task = asyncio.create_task(
        _execute_analysis_task(task_id=task_id, request=request, session_id=session_id)
    )
    _task.add_done_callback(lambda _: logger.info("Analysis task %s completed", task_id))

    return task_id
