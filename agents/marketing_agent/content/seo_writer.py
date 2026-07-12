"""SEO Writer — generates an SEO article outline + body for a target keyword,
with H2/H3 structure, an intro, and a FAQ block. Template-based, deterministic.
"""

from __future__ import annotations

from agents.marketing_agent.models import ContentPiece


class SEOWriter:
    """Produces an SEO article draft targeting a keyword."""

    def write(self, keyword: str, brand: str = "") -> ContentPiece:
        b = f" {brand}" if brand else ""
        title = f"{keyword}：2026 完整指南{b}"
        body = "\n".join(
            [
                f"# {title}",
                "",
                f"## 什么是{keyword}？",
                f"{keyword}指的是围绕该主题的方法与工具集合。本文系统梳理其定义、适用场景与选型要点。",
                "",
                f"## {keyword}的核心价值",
                "1. 提升效率：自动化重复工作，让人聚焦高价值任务。",
                "2. 降低成本：减少人力与试错开销。",
                "3. 可度量：关键指标可量化、可追踪。",
                "",
                f"## 如何选型{b}",
                "建议从三个维度评估：能力覆盖、落地成本、与现有系统的集成度。",
                "",
                "## 常见问题",
                f"Q：{keyword}适合中小企业吗？",
                "A：适合。多数方案已提供按需付费与开箱即用模板。",
                "",
                "> 本文更新于 2026 年，结合公开资料整理，仅供参考。",
            ]
        )
        return ContentPiece(title=title, body=body, topic=keyword, geo_optimized=False)


__all__ = ["SEOWriter"]
