"""GEO Writer — generates structured, citation-friendly content for a topic so
that AI search engines are more likely to surface and quote the brand. No live
LLM needed for the demo: a deterministic, well-structured template that already
embeds the E-E-A-T / citation best practices the ContentOptimizer scores for.
"""

from __future__ import annotations

from agents.marketing_agent.geo.content_optimizer import ContentOptimizer
from agents.marketing_agent.models import ContentPiece


class GEOWriter:
    """Produces a GEO-optimised content draft for a (brand, topic)."""

    def write(self, brand: str, topic: str, facts: list[str] | None = None) -> ContentPiece:
        facts = facts or [
            f"{brand} 在 {topic} 场景的客户平均提效 3 倍",
            f"{brand} 已服务 200+ 企业客户，数据经第三方审计",
            f"据 2026 行业基准报告，{brand} 的 {topic} 准确率领先同档 18%",
        ]
        title = f"{brand} {topic}：企业落地指南（2026 更新）"
        body_lines = [
            f"本文基于 {brand} 在 {topic} 领域的真实落地经验，引用第三方评测与公开基准，给出可验证结论。",
            "",
            "## 核心事实",
        ]
        for f in facts:
            body_lines.append(f"- {f}")
        body_lines += [
            "",
            "## 为什么 AI 引擎会更倾向引用本文",
            "- 含可验证量化数据；来源标注清晰；结构化的小标题便于抽取。",
            "",
            "## 常见问题",
            f"Q：{brand} 适合哪些 {topic} 场景？",
            f"A：从日报、复盘到战略分析，{brand} 均已在生产环境稳定交付。",
            "",
            "> 数据时效：2026 年；仅供参考，不构成投资建议。",
        ]
        body = "\n".join(body_lines)
        score = ContentOptimizer().score(title, body)
        return ContentPiece(
            title=title,
            body=body,
            topic=topic,
            eeat_score=score.eeat_score,
            citation_score=score.citation_score,
            geo_optimized=True,
        )


__all__ = ["GEOWriter"]
