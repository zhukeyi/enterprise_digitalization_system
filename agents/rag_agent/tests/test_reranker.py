"""P3 重排器单元测试：LexicalReranker 排序正确性 + FlashRank 可选后端。

验收要求：重排/改写 ≥5 测试（本文件覆盖重排核心）。
"""

from __future__ import annotations

import pytest

from agents.rag_agent.reranker import (
    FlashRankReranker,
    LexicalReranker,
    MAX_RERANK_CANDIDATES,
    get_default_reranker,
)
from agents.rag_agent.vector_store import VectorRecord


def _rec(rid: str, text: str, score: float) -> VectorRecord:
    return VectorRecord(id=rid, payload={"title": rid, "text": text}, score=score)


def test_lexical_rerank_orders_by_overlap() -> None:
    """含查询全部关键词的候选应排在最前。"""
    query = "杭州 客户"
    cands = [
        _rec("C2", "深圳 腾讯 科技", 0.95),          # 高向量分但无关键词
        _rec("C1", "客户名称 阿里巴巴 城市 杭州", 0.50),  # 命中 杭州+客户
        _rec("C3", "杭州 天气 预报", 0.60),          # 仅命中 杭州
    ]
    out = LexicalReranker().rerank(query, cands, top_k=3)
    assert [r.id for r in out] == ["C1", "C3", "C2"]


def test_lexical_rerank_breaks_vector_tie_by_lexical() -> None:
    """向量分相同时，词汇重叠更高的候选优先。"""
    query = "杭州 客户 合同"
    cands = [
        _rec("A", "杭州", 0.5),
        _rec("B", "杭州 客户 合同 金额", 0.5),
    ]
    out = LexicalReranker().rerank(query, cands, top_k=2)
    assert out[0].id == "B"


def test_rerank_empty_returns_empty() -> None:
    assert LexicalReranker().rerank("杭州", [], top_k=5) == []


def test_rerank_respects_top_k() -> None:
    query = "杭州"
    cands = [_rec(f"D{i}", f"杭州 文档 {i}", 0.9 - i * 0.1) for i in range(5)]
    out = LexicalReranker().rerank(query, cands, top_k=2)
    assert len(out) == 2


def test_lexical_reranker_weights_must_be_positive() -> None:
    with pytest.raises(ValueError):
        LexicalReranker(lexical_weight=0.0, vector_weight=0.0)


def test_flashrank_unavailable_falls_back() -> None:
    """未装 flashrank 时默认重排器回退到 Lexical（不抛错）。"""
    import importlib.util

    if importlib.util.find_spec("flashrank") is not None:
        pytest.skip("flashrank 已安装，跳过回退断言")
    with pytest.raises(ImportError):
        FlashRankReranker()
    # 默认工厂在缺 flashrank 时返回 Lexical 实例
    assert isinstance(get_default_reranker(), LexicalReranker)


def test_max_rerank_candidates_constant() -> None:
    assert MAX_RERANK_CANDIDATES == 20
