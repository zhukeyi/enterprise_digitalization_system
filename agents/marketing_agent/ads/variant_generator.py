"""Ad Variant Generator — produces multiple ad copy variants (headline / body
/ CTA) for a product or brand and scores each on a quality rubric, plus a
predicted CTR. Template + heuristic based (no live LLM required for the demo),
mirroring AI_Advertisement-Optz_Agent's multi-variant + quality-scoring idea.
"""

from __future__ import annotations

import re

from agents.marketing_agent.models import AdVariant

_ANGLES = ["痛点", "利益", "权威", "紧迫", "场景"]
_HEAD_TEMPLATES = {
    "痛点": ["{brand}：还在为{area}发愁？", "别再{area}踩坑了"],
    "利益": ["用{brand}，{area}效率提升 3 倍", "{brand} 帮你省下 40% 成本"],
    "权威": ["{brand} 入选行业大模型推荐榜单", "为什么头部团队都在用 {brand}"],
    "紧迫": ["限时：{brand} 企业版免费试用", "{brand} 618 专场，名额有限"],
    "场景": ["{area}场景一键搞定：{brand}", "早上 5 分钟，{area}自动跑完"],
}
_BODY_TEMPLATES = {
    "痛点": "传统方式费时费力还易出错。{brand} 用 AI 自动化 {area}，让你专注更重要的事。",
    "利益": "基于真实客户数据，{brand} 在 {area} 上平均帮企业提效 3 倍、降本 40%。",
    "权威": "来自第三方评测与百家客户验证，{brand} 在 {area} 领域持续领先。",
    "紧迫": "现在注册可享企业版免费试用，体验完整的 {area} 能力，随时可退。",
    "场景": "无论是日报、复盘还是战略分析，{brand} 都能在 {area} 场景稳定交付。",
}
_CTA_POOL = ["免费试用", "预约演示", "立即咨询", "领取方案", "开始使用"]


class VariantGenerator:
    """Generates scored ad copy variants for a brand/product."""

    def generate(self, brand: str, area: str, n: int = 5) -> list[AdVariant]:
        variants: list[AdVariant] = []
        angles = (_ANGLES * ((n // len(_ANGLES)) + 1))[:n]
        for i, angle in enumerate(angles):
            headline = _HEAD_TEMPLATES[angle][i % len(_HEAD_TEMPLATES[angle])].format(brand=brand, area=area)
            body = _BODY_TEMPLATES[angle].format(brand=brand, area=area)
            cta = _CTA_POOL[i % len(_CTA_POOL)]
            quality = self._quality(headline, body, cta)
            ctr = self._predict_ctr(angle, quality)
            variants.append(
                AdVariant(
                    variant_id=f"V{i+1}",
                    headline=headline,
                    body=body,
                    cta=cta,
                    quality_score=round(quality, 1),
                    predicted_ctr=round(ctr, 4),
                    angle=angle,
                )
            )
        # highest quality first
        variants.sort(key=lambda v: v.quality_score, reverse=True)
        return variants

    def _quality(self, headline: str, body: str, cta: str) -> float:
        score = 50.0
        if 8 <= len(headline) <= 22:
            score += 12.0
        if re.search(r"\d", body):
            score += 10.0  # concrete numbers
        if any(w in cta for w in ["免费", "领取", "预约", "立即", "开始"]):
            score += 10.0  # strong action verb
        if "？" in headline:
            score += 6.0  # curiosity hook
        if len(body) <= 80:
            score += 6.0  # concise
        # mild penalty for over-long
        if len(headline) > 26 or len(body) > 110:
            score -= 8.0
        return float(max(20.0, min(100.0, score)))

    def _predict_ctr(self, angle: str, quality: float) -> float:
        base = {"痛点": 0.028, "利益": 0.034, "权威": 0.026, "紧迫": 0.038, "场景": 0.030}
        return float(base.get(angle, 0.03) * (0.6 + quality / 250.0))


__all__ = ["VariantGenerator"]
