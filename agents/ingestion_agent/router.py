"""Ingestion Agent — HTTP 路由（P2a / MVS 核心 + P2b 文件入库）。

挂载到 FastAPI 主应用后提供：

* ``POST /ingest/upload``  — 上传本地文件（xlsx/xlsm/csv/pdf/docx/pptx）→ 归一化
  入库 + 进 Qdrant（P2b 起支持多格式；P2a 仅 Excel 的部分仍兼容）
* ``POST /api/data/ask``  — 基于已入库数据的检索问答（MVS 对话页后端）

所有重依赖（DB session / 向量库 / 嵌入模型）通过 ``Depends`` 注入，便于测试用
``app.dependency_overrides`` 替换为内存实现。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from agents.governance_agent.database.session import get_async_session
from agents.ingestion_agent.cache import Cache, get_cache
from agents.ingestion_agent.pipeline import IngestionPipeline
from agents.ingestion_agent.query import QueryService
from agents.ingestion_agent.storage import ObjectStorage, get_storage
from agents.ingestion_agent.store import get_embedding_model, get_vector_store
from agents.rag_agent.embeddings import EmbeddingModel
from agents.rag_agent.vector_store import VectorStore

router = APIRouter(tags=["ingestion"])

# 受支持的上传扩展名（P2b 起）
ALLOWED_EXTENSIONS = {".xlsx", ".xlsm", ".csv", ".pdf", ".docx", ".pptx"}
# 上传大小上限（20MB），H2b 会补更严格的 magic-bytes 校验
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


@router.post("/ingest/upload")
async def upload_file(
    file: UploadFile = File(...),
    doc_type: str = Form("file_upload"),
    session: AsyncSession = Depends(get_async_session),
    vector_store: VectorStore = Depends(get_vector_store),
    embedding_model: EmbeddingModel = Depends(get_embedding_model),
    storage: ObjectStorage = Depends(get_storage),
) -> dict[str, Any]:
    """上传本地文件并入库（解析 → 三层归一化 → 父子 chunk → Postgres + Qdrant）。

    支持 ``.xlsx / .xlsm / .csv / .pdf / .docx / .pptx``。Excel 走 P2a 的
    ``ingest_excel``（保留零配置 identity 路径），其余格式走 P2b 的 ``ingest_file``。
    """
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
                data,
                filename,
                doc_type=doc_type,
                session=session,
                vector_store=vector_store,
                embedding_model=embedding_model,
                storage=storage,
            )
        else:
            result = await IngestionPipeline.ingest_file(
                filename,
                data,
                doc_type=doc_type,
                session=session,
                vector_store=vector_store,
                embedding_model=embedding_model,
                storage=storage,
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
    session: AsyncSession = Depends(get_async_session),
    cache: Cache = Depends(get_cache),
) -> AskResponse:
    """基于已入库数据的检索问答（P3b：启用缓存 + FTS 词法召回）。"""
    try:
        result = await QueryService.ask(
            req.query,
            top_k=req.top_k,
            doc_type=req.doc_type,
            vector_store=vector_store,
            embedding_model=embedding_model,
            cache=cache,
            session=session,
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
