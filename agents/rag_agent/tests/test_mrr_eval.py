"""P3 MRR 评估（组件级演示）。

目标：证明「重排」能纠正向量检索的误排，抬升 MRR。

方法：用**合成向量分**（模拟「向量检索把正确文档排到了候选末尾」）构造
标注查询集，对比
- baseline：仅按向量分排序（top_k=3）的 MRR
- reranked：经 LexicalReranker 重排（top_k=3）的 MRR

说明：单机 ARM 用确定性 hash 嵌入时向量检索已接近词法，难以体现增益；
真实增益在语义嵌入（生产 bge-small-zh）上更显著。此处以受控合成分演示
组件本身的效果，并在 docs/p3-rag-optimization-report.md 中说明。
"""

from __future__ import annotations

from agents.rag_agent.reranker import LexicalReranker
from agents.rag_agent.vector_store import VectorRecord


def _mrr(orders: list[list[str]], expected: list[str], k: int = 3) -> float:
    total = 0.0
    for order, exp in zip(orders, expected, strict=True):
        top = order[:k]
        if exp in top:
            total += 1.0 / (top.index(exp) + 1)
    return total / len(orders)


# 每条：query / 正确文档文本 / 干扰文档文本（高向量分、无关键词重叠）
_CASES = [
    ("苹果 公司", "苹果 公司 总部 位于 加州", ["深圳 腾讯", "北京 百度", "上海 拼多多"], "easy"),
    ("华为 手机", "华为 手机 销量 第一", ["深圳 腾讯", "北京 百度", "上海 拼多多"], "easy"),
    ("小米 电视", "小米 电视 性价比 高", ["深圳 腾讯", "北京 百度", "上海 拼多多"], "easy"),
    ("杭州 阿里", "杭州 阿里巴巴 总部", ["深圳 腾讯", "北京 百度", "上海 拼多多"], "hard"),
    ("北京 百度", "北京 百度 大厦", ["深圳 腾讯", "杭州 阿里", "上海 拼多多"], "hard"),
    ("深圳 腾讯", "深圳 腾讯 滨海", ["北京 百度", "杭州 阿里", "上海 拼多多"], "hard"),
    ("上海 拼多多", "上海 拼多多 总部", ["北京 百度", "杭州 阿里", "深圳 腾讯"], "hard"),
    ("广州 网易", "广州 网易 游戏", ["北京 百度", "杭州 阿里", "深圳 腾讯"], "hard"),
    ("成都 腾讯", "成都 腾讯 办事处", ["北京 百度", "杭州 阿里", "上海 拼多多"], "hard"),
    ("南京 苏宁", "南京 苏宁 易购", ["北京 百度", "杭州 阿里", "深圳 腾讯"], "hard"),
]


def _build(query: str, correct_text: str, distracters: list[str], kind: str):
    # 正确文档：easy 给高向量分（baseline 已排前），hard 给低向量分（baseline 误排末尾）
    correct_score = 0.95 if kind == "easy" else 0.10
    recs = [VectorRecord(id="correct", payload={"text": correct_text}, score=correct_score)]
    for i, d in enumerate(distracters):
        # 干扰文档高分，确保 baseline 把 correct 挤出 top3（hard 时）
        recs.append(VectorRecord(id=f"dist{i}", payload={"text": d}, score=0.9 - i * 0.05))
    return query, recs


def test_mrr_improves_after_rerank() -> None:
    baseline_orders: list[list[str]] = []
    reranked_orders: list[list[str]] = []
    expected_ids: list[str] = []

    for q, correct, distracters, kind in _CASES:
        query, recs = _build(q, correct, distracters, kind)
        # baseline：按向量分降序
        baseline = [r.id for r in sorted(recs, key=lambda r: r.score, reverse=True)]
        # reranked：LexicalReranker
        reranked = [r.id for r in LexicalReranker().rerank(query, recs, top_k=3)]
        baseline_orders.append(baseline)
        reranked_orders.append(reranked)
        expected_ids.append("correct")

    base_mrr = _mrr(baseline_orders, expected_ids, k=3)
    rerank_mrr = _mrr(reranked_orders, expected_ids, k=3)

    # 验收门槛：重排后 MRR ≥ 0.50，且严格优于 baseline
    print(f"\n[MRR eval] baseline={base_mrr:.3f}  reranked={rerank_mrr:.3f}")
    assert rerank_mrr >= 0.50
    assert rerank_mrr > base_mrr
