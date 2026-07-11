"""Query Service — 基于已入库数据的检索问答（P2a / MVS 核心）。

MVS 验收「问答命中该数据」：嵌入查询 → Qdrant 向量检索 → 返回命中的
归一化记录 + 一句直白的答案（默认模板合成，可注入 LLM 生成更自然的回答）。

P3b 增强（本文件）：
* **结果缓存**（C4）：相同 (query, top_k, doc_type) 命中缓存直接返回，降低
  向量检索 + 重排开销（``cache`` 注入，默认内存 LRU，可切 Redis）。
* **词法召回**（GIN 等价 / FTS5）：当注入 ``session`` 时，额外走 FTS5 词法召回并
  合并进重排候选，纠正纯向量检索对关键词的语义漂移（best-effort，失败不影响主链路）。
"""

from __future__ import annotations

import hashlib
import logging
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from agents.ingestion_agent.cache import Cache
from agents.ingestion_agent.fts import fts_lexical_search
from agents.rag_agent.embeddings import EmbeddingModel
from agents.rag_agent.query_rewrite import QueryRewriter, get_default_rewriter
from agents.rag_agent.reranker import (
    MAX_RERANK_CANDIDATES,
    Reranker,
    get_default_reranker,
)
from agents.rag_agent.vector_store import VectorRecord, VectorStore

logger = logging.getLogger("fde.ingestion.query")

# 重排候选放大倍数：先多召回再重排，提升精度。硬上限见 MAX_RERANK_CANDIDATES。
_CANDIDATE_MULTIPLIER = 4


def _synthesize(query: str, sources: list[dict[str, Any]]) -> str:
    """把命中的来源合成为一句答案（MVS 默认模板；保证数据可见即「命中」）。"""
    if not sources:
        return "未在知识库中找到相关内容。请先通过「上传」页导入数据文件。"
    top = sources[0]
    # 优先回带父块上下文（父子 chunk），否则回退子块文本
    text = top.get("parent_text") or top.get("text", "")
    return f"根据已上传的数据，找到 {len(sources)} 条相关记录。最相关的一条：\n{text}"


async def _load_chunk_for_canonical(
    session: AsyncSession, canonical_document_id: str
) -> dict[str, Any] | None:
    """取某 CanonicalDocument 的最佳（首个）chunk 文本，用于词法召回回填。

    返回 ``{id, content, parent_text}`` 或 None（无 chunk）。
    """
    row = await session.execute(
        text(
            "SELECT id, content, metadata_json FROM document_chunks "
            "WHERE canonical_document_id = :cid ORDER BY chunk_index ASC LIMIT 1"
        ),
        {"cid": canonical_document_id},
    )
    r = row.first()
    if r is None:
        return None
    cid, content, meta = r
    parent = (meta or {}).get("parent_text") or content
    return {"id": cid, "content": content, "parent_text": parent}


class QueryService:
    """基于 Qdrant 的轻量检索问答服务（无状态，依赖注入）。"""

    @staticmethod
    async def ask(
        query: str,
        *,
        top_k: int = 5,
        doc_type: str | None = None,
        vector_store: VectorStore,
        embedding_model: EmbeddingModel,
        llm: Any | None = None,
        reranker: Reranker | None = None,
        query_rewriter: QueryRewriter | None = None,
        cache: Cache | None = None,
        session: AsyncSession | None = None,
    ) -> dict[str, Any]:
        """检索并回答（P3：查询改写 + 重排；P3b：缓存 + 词法召回）。

        Args:
            query: 用户自然语言问题。
            top_k: 返回命中数上限。
            doc_type: 可选限定文档类型。
            vector_store: Qdrant 向量库（需实现 ``async_search``）。
            embedding_model: 嵌入模型（需实现 ``encode_queries``）。
            llm: 可选 LLM 调用 ``llm(context, question) -> str``。
            reranker: 可选重排器（默认 LexicalReranker）。
            query_rewriter: 可选查询改写器（默认规则式）。
            cache: 可选结果缓存（默认注入内存/Redis）。
            session: 可选 DB 会话，注入后启用 FTS 词法召回。

        Returns:
            ``{query, answer, sources, count, cached}``。
        """
        if not query or not query.strip():
            raise ValueError("query 不能为空")

        # 结果缓存（C4 + P3b）：命中直接返回
        cache_key: str | None = None
        if cache is not None:
            raw_key = f"{query}|{top_k}|{doc_type}"
            cache_key = "ask:" + hashlib.sha256(raw_key.encode("utf-8")).hexdigest()[:32]
            cached = await cache.get(cache_key)
            if cached is not None:
                cached["cached"] = True
                return cached

        rewriter = query_rewriter or get_default_rewriter()
        effective_query = rewriter.rewrite(query)

        q_vecs = await embedding_model.encode_queries([effective_query])
        q_vec = q_vecs[0]

        # 多召回候选（放大倍数，硬上限 MAX_RERANK_CANDIDATES=20），再重排。
        candidate_k = min(max(top_k * _CANDIDATE_MULTIPLIER, top_k + 8), MAX_RERANK_CANDIDATES)
        filter_conditions = {"doc_type": doc_type} if doc_type else None
        candidates = await vector_store.async_search(
            vector=q_vec,
            top_k=candidate_k,
            filter_conditions=filter_conditions,
        )

        # 词法召回（P3b GIN 等价 / FTS5）：best-effort 合并，失败不影响向量召回
        if session is not None:
            try:
                lexical = await fts_lexical_search(session, effective_query, limit=candidate_k)
                for item in lexical:
                    chunk = await _load_chunk_for_canonical(session, item["canonical_document_id"])
                    if chunk is None:
                        continue
                    candidates.append(
                        VectorRecord(
                            id=chunk["id"],
                            vector=None,
                            payload={
                                "title": item.get("title") or "",
                                "text": chunk["content"],
                                "parent_text": chunk["parent_text"],
                                "canonical": {},
                                "source": "",
                                "doc_type": "",
                            },
                            score=item["score"],
                        )
                    )
            except Exception as exc:  # 词法召回异常绝不影响主链路
                logger.debug("FTS lexical recall skipped: %s", exc)

        rk = reranker or get_default_reranker()
        records = rk.rerank(effective_query, candidates, top_k)
        sources = [r.payload for r in records]

        if llm is not None and sources:
            context = "\n\n".join(s.get("text", "") for s in sources)
            try:
                answer = await llm(context=context, question=query)
                result: dict[str, Any] = {
                    "query": query,
                    "answer": answer,
                    "sources": sources,
                    "count": len(sources),
                    "cached": False,
                }
                return result
            except Exception:
                pass

        result = {
            "query": query,
            "answer": _synthesize(query, sources),
            "sources": sources,
            "count": len(sources),
            "cached": False,
        }
        if cache is not None and cache_key is not None:
            await cache.set(cache_key, result)
        return result


__all__ = ["QueryService"]
