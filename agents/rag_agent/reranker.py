"""RAG 重排器（P3 / T1）。

选型说明（见 master-delivery-plan.md §5 P3 + 风险登记）：
- P0.5 spike 对 BGE-Reranker-v2-M3（568M, ~1.2G）在 ARM 2C/11G 单机判定为
  「不达标」——与已运行的 Dify + Qdrant + Postgres 争内存，易 OOM。
- 按计划回退路径：**默认 LexicalReranker**（纯词汇重叠，无模型，<1ms，
  满足「ARM 单次 <50ms」），并保留 **FlashRankReranker** 作为可选可插拔后端
  （安装 flashrank 后自动启用，待 P6b GPU 微服务可常驻）。
- 重排候选数硬上限 ``MAX_RERANK_CANDIDATES = 20``（计划约束：重排限候选 ≤20）。
"""

from __future__ import annotations

import re
from typing import Protocol, runtime_checkable

from agents.rag_agent.vector_store import VectorRecord

MAX_RERANK_CANDIDATES = 20

_TOKEN_RE = re.compile(r"[A-Za-z0-9]+|[\u4e00-\u9fff]")


def tokenize(text: str) -> list[str]:
    """CJK 逐字 / ASCII 按词分词（与 FakeEmbeddingModel 一致，保证可对齐）。"""
    return _TOKEN_RE.findall(text or "")


def _payload_text(rec: VectorRecord) -> str:
    """拼接候选的可检索文本：title + text + parent_text + canonical 字段值。"""
    p = rec.payload or {}
    parts = [p.get("title") or "", p.get("text") or "", p.get("parent_text") or ""]
    canon = p.get("canonical")
    if isinstance(canon, dict):
        parts.extend(str(v) for v in canon.values())
    return " ".join(parts)


@runtime_checkable
class Reranker(Protocol):
    """重排器协议：输入查询 + 候选（含 payload 文本与向量分），输出重排后列表。"""

    def rerank(self, query: str, candidates: list[VectorRecord], top_k: int) -> list[VectorRecord]:
        """重排并返回前 ``top_k`` 个候选。"""
        ...


class LexicalReranker:
    """词汇重叠重排：query 与候选文本（title/text/parent_text/canonical）的 token
    交集打分（Jaccard），与向量分线性融合后重排。

    - 词汇信号对关键词查询鲁棒，可纠正向量检索的语义漂移（如查询「总部」时
      把字面含「总部」的文档提到含「所在地」但无「总部」的文档之前）。
    - 无模型依赖，ARM 上 ≤20 候选 <1ms，满足 <50ms 预算。
    """

    def __init__(self, lexical_weight: float = 0.7, vector_weight: float = 0.3) -> None:
        if lexical_weight + vector_weight <= 0:
            raise ValueError("lexical_weight + vector_weight 必须 > 0")
        self.lexical_weight = lexical_weight
        self.vector_weight = vector_weight

    @staticmethod
    def _lexical_score(query_tokens: set[str], text: str) -> float:
        """F1 = 2·P·R/(P+R)，其中 R=命中关键词/查询词数（召回），P=命中/文档词数（聚焦）。

        用 F1 而非 Jaccard：避免长文档因 token 多被稀释，确保「覆盖全部查询关键词」
        的文档稳定压过「仅命中部分」或「零命中」的文档（即便其向量分更高）。
        """
        if not query_tokens:
            return 0.0
        doc_tokens = set(tokenize(text))
        if not doc_tokens:
            return 0.0
        inter = query_tokens & doc_tokens
        if not inter:
            return 0.0
        recall = len(inter) / len(query_tokens)
        precision = len(inter) / len(doc_tokens)
        return 2 * precision * recall / (precision + recall)

    def rerank(self, query: str, candidates: list[VectorRecord], top_k: int) -> list[VectorRecord]:
        if not candidates:
            return []
        q_tokens = set(tokenize(query))
        vec_scores = [float(r.score or 0.0) for r in candidates]
        vmax = max(vec_scores)
        vmin = min(vec_scores)
        vspan = (vmax - vmin) or 1.0

        scored: list[tuple[float, VectorRecord]] = []
        for rec, vs in zip(candidates, vec_scores, strict=True):
            lex = self._lexical_score(q_tokens, _payload_text(rec))
            norm_vec = (vs - vmin) / vspan
            combined = self.vector_weight * norm_vec + self.lexical_weight * lex
            scored.append((combined, rec))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [r for _, r in scored[:top_k]]


class FlashRankReranker:
    """可选可插拔重排（cross-encoder）。需 ``pip install flashrank``。

    未安装时实例化抛 ``ImportError``，由调用方回退 ``LexicalReranker``。
    待 P6b GPU 微服务可常驻，作为更高质量的语义重排后端。
    """

    def __init__(self, model_name: str = "ms-marco-MiniLM-L-12-v2") -> None:
        try:
            from flashrank import Ranker  # type: ignore
        except ImportError as exc:  # pragma: no cover - 依赖可选
            raise ImportError("FlashRankReranker 需要 flashrank：pip install flashrank") from exc
        self._ranker = Ranker(model_name=model_name)

    def rerank(self, query: str, candidates: list[VectorRecord], top_k: int) -> list[VectorRecord]:
        if not candidates:
            return []
        docs = [{"id": str(r.id), "text": _payload_text(r)} for r in candidates]
        ranked = self._ranker.rank(query=query, documents=docs, top_k=min(top_k, len(docs)))
        order = {str(d["id"]): i for i, d in enumerate(ranked)}
        return sorted(candidates, key=lambda r: order.get(str(r.id), 1 << 30))[:top_k]


_default_reranker: Reranker | None = None


def get_default_reranker() -> Reranker:
    """返回默认重排器：优先 FlashRank（若已装），否则回退 Lexical（单例）。"""
    global _default_reranker
    if _default_reranker is not None:
        return _default_reranker
    try:
        _default_reranker = FlashRankReranker()
    except ImportError:
        _default_reranker = LexicalReranker()
    return _default_reranker


__all__ = [
    "MAX_RERANK_CANDIDATES",
    "FlashRankReranker",
    "LexicalReranker",
    "Reranker",
    "get_default_reranker",
    "tokenize",
]
