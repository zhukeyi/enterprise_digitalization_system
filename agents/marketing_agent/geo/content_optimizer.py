"""Content Optimizer — scores content on E-E-A-T (Experience, Expertise,
Authoritativeness, Trustworthiness) and on citation-friendliness (how likely an
AI search engine is to quote/reference it). Returns actionable suggestions.

Heuristic, dependency-free scorer: counts factual claims (numbers), citations
(URLs / "据/引用/来源"), author signals, recency and structural clarity. This is
the core of "GEO content optimization" — making content machine-citable.
"""

from __future__ import annotations

import re

from agents.marketing_agent.models import ContentScore

_NUM_RE = re.compile(r"\d+(?:\.\d+)?\s*(?:%|倍|个|项|万元|亿元|人|天|月|年|倍率)")
_CITE_RE = re.compile(r"(引用|来源|据|研究表明|报告|基准|公开数据|第三方|\[|\]|http[s]?://)")
_STRUCT_RE = re.compile(r"(#{1,6}\s|[-•]\s|\n\n|\d+\.\s)")


class ContentOptimizer:
    """Scores and improves web content for AI-engine citation."""

    def score(self, title: str, body: str) -> ContentScore:
        text = f"{title}\n{body}"

        # Experience: first-person / case wording
        exp = 60.0
        if re.search(r"(我们|实测|实践|落地|案例|客户)", text):
            exp += 22.0
        if re.search(r"(亲自|试用|跑通|上线后)", text):
            exp += 10.0

        # Expertise: technical specificity + numbers
        nums = len(_NUM_RE.findall(text))
        expertise = min(100.0, 50.0 + nums * 6.0)

        # Authoritativeness: citations / references
        cites = len(_CITE_RE.findall(text))
        authoritativeness = min(100.0, 40.0 + cites * 9.0)

        # Trustworthiness: balanced + dated + source-linked
        trust = 55.0
        if re.search(r"(20\d\d[-年/]\d{1,2})", text):
            trust += 12.0
        if "http" in text or "来源" in text:
            trust += 12.0
        if re.search(r"(免责|仅供参考|风险|不构成建议)", text):
            trust += 6.0  # responsible disclosure helps trust

        # Citation-friendliness: concise factual statements + structure
        sentences = [s for s in re.split(r"[。！？\n]", text) if len(s.strip()) > 6]
        short_factual = sum(1 for s in sentences if len(s) <= 60 and _NUM_RE.search(s))
        struct = len(_STRUCT_RE.findall(text))
        citation = min(100.0, 35.0 + short_factual * 8.0 + min(struct, 6) * 3.0)

        eeat = round((exp + expertise + authoritativeness + trust) / 4.0, 1)

        suggestions = self._suggest(title, body, nums, cites, struct, sentences)
        return ContentScore(
            eeat_score=eeat,
            experience=round(exp, 1),
            expertise=round(expertise, 1),
            authoritativeness=round(authoritativeness, 1),
            trustworthiness=round(trust, 1),
            citation_score=round(citation, 1),
            suggestions=suggestions,
        )

    def _suggest(
        self, title: str, body: str, nums: int, cites: int, struct: int, sentences: list[str]
    ) -> list[str]:
        s: list[str] = []
        if nums < 3:
            s.append("增加可验证的量化数据（如提升 3 倍、成本降低 40%），AI 引擎更倾向引用含具体数字的内容。")
        if cites < 2:
            s.append("补充引用来源（第三方报告 / 公开基准 / 研究），提升权威性与可引用性。")
        if struct < 2:
            s.append("使用清晰的小标题与列表结构，便于 AI 引擎抽取关键事实。")
        if not re.search(r"(20\d\d[-年/]\d{1,2})", body):
            s.append("标注内容日期或数据时效，增强时效可信度。")
        if len(sentences) and max((len(x) for x in sentences), default=0) > 90:
            s.append("拆分过长句子，每条事实控制在 60 字以内，提升被直接引用的概率。")
        if not s:
            s.append("内容已达较高 GEO 标准，建议持续监测 AI 引擎引用率。")
        return s


__all__ = ["ContentOptimizer"]
