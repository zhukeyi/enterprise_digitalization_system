"""Ingestion Agent — HTTP 路由（P2a/P2b/P3b/P6a）。

挂载到 FastAPI 主应用后提供：

* ``POST /ingest/upload``       — 同步上传入库（向后兼容）
* ``POST /ingest/upload/async`` — P6a 异步上传（202 + task_id）
* ``GET /ingest/tasks/{task_id}`` — P6a 任务状态查询
* ``POST /api/data/ask``        — 基于已入库数据的检索问答
"""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from agents.governance_agent.database.session import get_async_session
from agents.ingestion_agent.cache import Cache, get_cache
from agents.ingestion_agent.pipeline import IngestionPipeline
from agents.ingestion_agent.query import QueryService
from agents.ingestion_agent.storage import ObjectStorage, get_storage, make_storage_key
from agents.ingestion_agent.store import get_embedding_model, get_vector_store
from agents.ingestion_agent.task_models import (
    STATUS_PENDING,
    IngestTask,
)
from agents.rag_agent.embeddings import EmbeddingModel
from agents.rag_agent.vector_store import VectorStore

router = APIRouter(tags=["ingestion"])

# 受支持的上传扩展名（P2b 起）
ALLOWED_EXTENSIONS = {".xlsx", ".xlsm", ".csv", ".pdf", ".docx", ".pptx"}
# 上传大小上限（20MB）
MAX_UPLOAD_BYTES = 20 * 1024 * 1024


class AskRequest(BaseModel):
    """``/api/data/ask`` 请求体。"""

    query: str
    top_k: int = 5
    doc_type: str | None = None


class AskResponse(BaseModel):
    """``/api/data/ask`` 响应体。"""

    query: str
    answer: str
    count: int
    sources: list[dict[str, Any]]
    cached: bool = False


class TaskStatusResponse(BaseModel):
    """P6a: /ingest/tasks/{task_id} 响应体。"""

    task_id: str
    status: str
    filename: str
    doc_type: str
    progress_pct: int = 0
    total_chunks: int = 0
    indexed_chunks: int = 0
    canonical_count: int = 0
    result: dict[str, Any] | None = None
    error_message: str | None = None
    created_at: str | None = None
    updated_at: str | None = None


@router.post("/ingest/upload")
async def upload_file(
    file: UploadFile = File(...),
    doc_type: str = Form("file_upload"),
    session: AsyncSession = Depends(get_async_session),
    vector_store: VectorStore = Depends(get_vector_store),
    embedding_model: EmbeddingModel = Depends(get_embedding_model),
    storage: ObjectStorage = Depends(get_storage),
) -> dict[str, Any]:
    """同步上传文件并入库（向后兼容）。大文件/批量建议用 /ingest/upload/async。"""
    filename = file.filename or ""
    ext = Path(filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"不支持的文件类型：{ext or '无扩展名'}，仅支持 {sorted(ALLOWED_EXTENSIONS)}",
        )
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="上传文件为空")
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="文件超过 20MB 上限")

    try:
        if ext in (".xlsx", ".xlsm"):
            result = await IngestionPipeline.ingest_excel(
                data, filename, doc_type=doc_type,
                session=session, vector_store=vector_store,
                embedding_model=embedding_model, storage=storage,
            )
        else:
            result = await IngestionPipeline.ingest_file(
                filename, data, doc_type=doc_type,
                session=session, vector_store=vector_store,
                embedding_model=embedding_model, storage=storage,
            )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return result


@router.post("/ingest/upload/async")
async def upload_file_async(
    file: UploadFile = File(...),
    doc_type: str = Form("file_upload"),
    session: AsyncSession = Depends(get_async_session),
    storage: ObjectStorage = Depends(get_storage),
) -> dict[str, Any]:
    """P6a: 异步上传文件并入库（立即返回 202 + task_id）。

    文件先存入对象存储，然后创建 ingest task 放入后台队列处理。
    用 ``GET /ingest/tasks/{task_id}`` 轮询进度和结果。
    """
    filename = file.filename or ""
    ext = Path(filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"不支持的文件类型：{ext or '无扩展名'}")
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="上传文件为空")
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="文件超过 20MB 上限")

    import hashlib

    file_hash = hashlib.sha256(data).hexdigest()
    storage_key = make_storage_key(filename, file_hash)
    storage_ref = await storage.put(storage_key, data)

    task_id = str(uuid.uuid4())
    task = IngestTask(
        id=task_id,
        status=STATUS_PENDING,
        filename=filename,
        file_hash=file_hash,
        doc_type=doc_type,
        content_type=file.content_type,
        storage_ref=storage_ref,
    )
    session.add(task)
    await session.commit()

    from agents.ingestion_agent.tasks import get_queue as get_ingest_queue

    queue = get_ingest_queue()
    await queue.enqueue(task_id)

    return {
        "task_id": task_id,
        "status": STATUS_PENDING,
        "filename": filename,
        "doc_type": doc_type,
        "message": "Task queued. Poll GET /ingest/tasks/{task_id} for status.",
    }


@router.get("/ingest/tasks/{task_id}", response_model=TaskStatusResponse)
async def get_task_status(
    task_id: str,
    session: AsyncSession = Depends(get_async_session),
) -> TaskStatusResponse:
    """P6a: 查询异步 ingestion 任务的状态和结果。"""
    task = await session.get(IngestTask, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail=f"任务不存在: {task_id}")

    return TaskStatusResponse(
        task_id=task.id,
        status=task.status,
        filename=task.filename,
        doc_type=task.doc_type,
        progress_pct=task.progress_pct,
        total_chunks=task.total_chunks,
        indexed_chunks=task.indexed_chunks,
        canonical_count=task.canonical_count,
        result=task.result,
        error_message=task.error_message,
        created_at=task.created_at.isoformat() if task.created_at else None,
        updated_at=task.updated_at.isoformat() if task.updated_at else None,
    )


@router.post("/api/data/ask", response_model=AskResponse)
async def ask(
    req: AskRequest,
    vector_store: VectorStore = Depends(get_vector_store),
    embedding_model: EmbeddingModel = Depends(get_embedding_model),
    session: AsyncSession = Depends(get_async_session),
    cache: Cache = Depends(get_cache),
) -> AskResponse:
    """基于已入库数据的检索问答（P3b：启用缓存 + FTS 词法召回）。"""
    try:
        result = await QueryService.ask(
            req.query, top_k=req.top_k, doc_type=req.doc_type,
            vector_store=vector_store, embedding_model=embedding_model,
            cache=cache, session=session,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return AskResponse(
        query=result["query"],
        answer=result["answer"],
        count=result["count"],
        sources=result["sources"],
        cached=bool(result.get("cached", False)),
    )


__all__ = ["router"]
