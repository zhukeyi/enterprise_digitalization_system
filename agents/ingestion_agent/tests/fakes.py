"""P2a 测试用内存替身：向量库 + 嵌入模型（无需真实 Qdrant / BGE-M3）。"""

from __future__ import annotations

import hashlib
import math
import re
from typing import Any

from agents.rag_agent.vector_store import VectorRecord


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=False))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


class FakeEmbeddingModel:
    """确定性哈希嵌入：相同/相似文本 → 高余弦，足以验证「命中」。"""

    def __init__(self, dim: int = 64) -> None:
        self.dim = dim

    def get_dimension(self) -> int:
        return self.dim

    def _embed(self, text: str) -> list[float]:
        vec = [0.0] * self.dim
        # CJK 逐字分词（保证「杭州」能命中「总部位于杭州」中的字），ASCII 词整体。
        tokens = re.findall(r"[A-Za-z0-9]+|[\u4e00-\u9fff]", text or "")
        for tok in tokens:
            h = int(hashlib.md5(tok.encode("utf-8")).hexdigest(), 16) % self.dim
            vec[h] += 1.0
        norm = math.sqrt(sum(v * v for v in vec)) or 1.0
        return [v / norm for v in vec]

    async def encode_queries(self, queries: list[str]) -> list[list[float]]:
        return [self._embed(q) for q in queries]

    async def encode_documents(self, documents: list[str]) -> list[list[float]]:
        return [self._embed(d) for d in documents]


class InMemoryVectorStore:
    """内存向量库：余弦检索 + payload 过滤，行为对齐 ``VectorStore`` 关键方法。"""

    def __init__(self) -> None:
        self.points: dict[str, tuple[list[float], dict[str, Any]]] = {}
        self.collection_created = False

    async def async_create_collection(self, config=None) -> dict[str, Any]:
        self.collection_created = True
        return {"status": "ok"}

    async def async_collection_exists(self, name=None) -> bool:
        return True

    async def async_upsert(self, points: list[VectorRecord], collection=None) -> int:
        for p in points:
            if p.vector is not None:
                self.points[str(p.id)] = (p.vector, p.payload)
        return len(points)

    async def async_search(
        self,
        vector: list[float],
        top_k: int = 10,
        collection=None,
        score_threshold: float | None = None,
        filter_conditions: dict[str, Any] | None = None,
    ) -> list[VectorRecord]:
        results: list[VectorRecord] = []
        for pid, (vec, payload) in self.points.items():
            if filter_conditions:
                ok = all(payload.get(k) == v for k, v in filter_conditions.items())
                if not ok:
                    continue
            score = _cosine(vector, vec)
            if score_threshold is not None and score < score_threshold:
                continue
            results.append(VectorRecord(id=pid, payload=payload, score=round(score, 6)))
        results.sort(key=lambda r: r.score, reverse=True)
        return results[:top_k]

    async def async_count(self, collection=None) -> int:
        return len(self.points)
