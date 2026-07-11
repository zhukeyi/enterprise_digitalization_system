"""Query Service — 基于已入库数据的检索问答（P2a / MVS 核心）。

MVS 验收「问答命中该数据」：嵌入查询 → Qdrant 向量检索 → 返回命中的
归一化记录 + 一句直白的答案（默认模板合成，可注入 LLM 生成更自然的回答）。
"""

from __future__ import annotations

from typing import Any

from agents.rag_agent.embeddings import EmbeddingModel
from agents.rag_agent.query_rewrite import QueryRewriter, get_default_rewriter
from agents.rag_agent.reranker import (
    MAX_RERANK_CANDIDATES,
    Reranker,
    get_default_reranker,
)
from agents.rag_agent.vector_store import VectorStore

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
    ) -> dict[str, Any]:
        """检索并回答（P3：查询改写 + 重排）。

        Args:
            query: 用户自然语言问题。
            top_k: 返回命中数上限。
            doc_type: 可选限定文档类型。
            vector_store: Qdrant 向量库（需实现 ``async_search``）。
            embedding_model: 嵌入模型（需实现 ``encode_queries``）。
            llm: 可选 LLM 调用 ``llm(context, question) -> str``，注入后生成自然回答。
            reranker: 可选重排器（默认 LexicalReranker，见 reranker.py）。
            query_rewriter: 可选查询改写器（默认规则式，见 query_rewrite.py）。

        Returns:
            ``{query, answer, sources, count}``。
        """
        if not query or not query.strip():
            raise ValueError("query 不能为空")

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

        rk = reranker or get_default_reranker()
        records = rk.rerank(effective_query, candidates, top_k)
        sources = [r.payload for r in records]

        if llm is not None and sources:
            context = "\n\n".join(s.get("text", "") for s in sources)
            try:
                answer = await llm(context=context, question=query)
                return {
                    "query": query,
                    "answer": answer,
                    "sources": sources,
                    "count": len(sources),
                }
            except Exception:  # LLM 失败回退模板
                pass

        return {
            "query": query,
            "answer": _synthesize(query, sources),
            "sources": sources,
            "count": len(sources),
        }


__all__ = ["QueryService"]
