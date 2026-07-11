"""Ingestion Agent — HTTP 路由（P2a / MVS 核心）。

挂载到 FastAPI 主应用后提供：

* ``POST /ingest/upload``  — 上传 Excel（仅 .xlsx/.xlsm）→ 归一化入库 + 进 Qdrant
* ``POST /api/data/ask``  — 基于已入库数据的检索问答（MVS 对话页后端）

所有重依赖（DB session / 向量库 / 嵌入模型）通过 ``Depends`` 注入，便于测试用
``app.dependency_overrides`` 替换为内存实现。
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from agents.governance_agent.database.session import get_async_session
from agents.ingestion_agent.pipeline import IngestionPipeline
from agents.ingestion_agent.query import QueryService
from agents.ingestion_agent.store import get_embedding_model, get_vector_store
from agents.rag_agent.embeddings import EmbeddingModel
from agents.rag_agent.vector_store import VectorStore

router = APIRouter(tags=["ingestion"])


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


@router.post("/ingest/upload")
async def upload_excel(
    file: UploadFile = File(...),
    doc_type: str = Form("excel_upload"),
    session: AsyncSession = Depends(get_async_session),
    vector_store: VectorStore = Depends(get_vector_store),
    embedding_model: EmbeddingModel = Depends(get_embedding_model),
) -> dict[str, Any]:
    """上传 Excel 并入库（归一化 → Postgres + Qdrant）。

    仅接受 ``.xlsx`` / ``.xlsm``（openpyxl 不支持旧版 ``.xls``）。
    """
    filename = file.filename or ""
    if not filename.lower().endswith((".xlsx", ".xlsm")):
        raise HTTPException(status_code=400, detail="仅支持 .xlsx / .xlsm 文件")
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="上传文件为空")

    try:
        result = await IngestionPipeline.ingest_excel(
            data,
            filename,
            doc_type=doc_type,
            session=session,
            vector_store=vector_store,
            embedding_model=embedding_model,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return result


@router.post("/api/data/ask", response_model=AskResponse)
async def ask(
    req: AskRequest,
    vector_store: VectorStore = Depends(get_vector_store),
    embedding_model: EmbeddingModel = Depends(get_embedding_model),
) -> AskResponse:
    """基于已入库数据的检索问答。"""
    try:
        result = await QueryService.ask(
            req.query,
            top_k=req.top_k,
            doc_type=req.doc_type,
            vector_store=vector_store,
            embedding_model=embedding_model,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return AskResponse(
        query=result["query"],
        answer=result["answer"],
        count=result["count"],
        sources=result["sources"],
    )


__all__ = ["router"]
