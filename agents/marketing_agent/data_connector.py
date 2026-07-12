"""Data Connector — demo data generator for the marketing / GEO module.

Synthesises *internally consistent* demo data: brands with strength, monitored
keywords, AI-search-engine coverage, content pieces, and cross-platform ad
campaigns. The generation is deterministic (seeded) and the relationships are
coherent — e.g. a stronger brand gets higher GEO visibility; a higher-ROAS
platform gets more budget in the allocator. Swap the getters for real
ad-platform / analytics APIs in production; the public interface is stable.
"""

from __future__ import annotations

import random
from datetime import datetime, timedelta
from typing import Any

from agents.marketing_agent.models import (
    Brand,
    ContentPiece,
    Keyword,
    PlatformPerformance,
)

_SEED = 20260712

_ENGINES = ["ChatGPT", "Claude", "Gemini", "Perplexity", "Bing Copilot"]
_PLATFORMS = ["Google Ads", "Meta", "TikTok", "Baidu", "小红书"]

# (name, domain, category, strength)
_BRAND_SEED: list[tuple[str, str, str, float]] = [
    ("云栖智能", "yunqi-ai.com", "企业 AI SaaS", 82.0),
    ("灵犀数据", "lingxi-data.cn", "数据分析平台", 64.0),
    ("智绘设计", "zhihui.design", "AIGC 设计工具", 71.0),
    ("数为科技", "shuwei.tech", "行业大模型", 55.0),
]

# intent pool for keyword generation
_INTENTS = ["informational", "commercial", "transactional", "navigational"]


class DataConnector:
    """Provides brands, keywords, content, and ad performance for the demo."""

    def __init__(self) -> None:
        self._rng = random.Random(_SEED)
        self._cache: dict[str, dict[str, Any]] = {}
        self._build()

    def _build(self) -> None:
        today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        for idx, (name, domain, cat, strength) in enumerate(_BRAND_SEED):
            bid = f"B{idx+1:03d}"
            # keywords (6-9 per brand)
            n_kw = self._rng.randint(6, 9)
            keywords: list[Keyword] = []
            for k in range(n_kw):
                term = self._kw_for(cat, k)
                volume = self._rng.randint(800, 22000)
                difficulty = round(min(98.0, max(8.0, 100 - strength * 0.8 + self._rng.uniform(-15, 15))), 1)
                # stronger brand ranks better (lower position)
                pos = round(max(1.0, 12 - strength / 12 + self._rng.uniform(-2, 3)), 1)
                keywords.append(
                    Keyword(
                        term=term,
                        intent=self._rng.choice(_INTENTS),
                        monthly_volume=volume,
                        difficulty=difficulty,
                        current_position=pos,
                    )
                )
            # content pieces
            contents = self._contents_for(bid, name, cat)
            # platform performance
            platforms = self._platforms_for(name)
            self._cache[bid] = {
                "brand": Brand(brand_id=bid, name=name, domain=domain, category=cat, strength=strength),
                "keywords": keywords,
                "content": contents,
                "platforms": platforms,
                "_today": today,
            }

    def _kw_for(self, cat: str, k: int) -> str:
        roots = {
            "企业 AI SaaS": ["企业 AI 平台", "AI 客服系统", "智能办公助手", "AI 工作流", "企业大模型"],
            "数据分析平台": ["数据分析工具", "BI 可视化", "实时数仓", "自助分析", "数据治理平台"],
            "AIGC 设计工具": ["AI 绘画", "智能设计工具", "海报生成", "品牌视觉 AI", "AIGC 素材"],
            "行业大模型": ["行业大模型", "垂直领域 LLM", "私有化部署大模型", "大模型微调", "领域知识库"],
        }
        base = roots.get(cat, ["AI 解决方案"])[k % 5]
        suffix = self._rng.choice(["", " 推荐", " 对比", " 哪家好", " 价格", " 怎么选"])
        return base + suffix

    def _contents_for(self, bid: str, name: str, cat: str) -> list[ContentPiece]:
        samples = [
            (f"{name}：企业级 {cat} 一站式解决方案", True),
            (f"2026 {cat} 选型指南：5 个关键维度", True),
            (f"{name} 客户案例：效率提升 3 倍", False),
            (f"{cat} 白皮书：从 0 到 1 落地路径", True),
        ]
        out: list[ContentPiece] = []
        for i, (title, geo) in enumerate(samples):
            body = (
                f"{title}。本文基于 {name} 在 {cat} 领域的真实落地经验，"
                f"引用第三方评测与公开基准，给出可验证结论。"
            )
            out.append(
                ContentPiece(
                    title=title,
                    body=body,
                    topic=cat,
                    geo_optimized=geo,
                    eeat_score=round(self._rng.uniform(55, 92), 1),
                    citation_score=round(self._rng.uniform(48, 90), 1),
                    created_at=datetime.now() - timedelta(days=10 * i),
                )
            )
        return out

    def _platforms_for(self, name: str) -> list[PlatformPerformance]:
        out: list[PlatformPerformance] = []
        for plat in _PLATFORMS:
            spend = round(self._rng.uniform(8000, 60000), 2)
            roas = round(self._rng.uniform(1.8, 5.5), 2)
            revenue = round(spend * roas, 2)
            impressions = int(spend * self._rng.uniform(80, 160))
            clicks = int(impressions * self._rng.uniform(0.015, 0.045))
            conversions = int(clicks * self._rng.uniform(0.03, 0.12))
            out.append(
                PlatformPerformance(
                    platform=plat,
                    spend=spend,
                    revenue=revenue,
                    impressions=impressions,
                    clicks=clicks,
                    conversions=conversions,
                    roas=roas,
                    ctr=clicks / impressions if impressions else 0.0,
                    cpc=spend / clicks if clicks else 0.0,
                    conv_rate=conversions / clicks if clicks else 0.0,
                    trend_30d=round(self._rng.uniform(-0.4, 0.8), 2),
                )
            )
        return out

    # ── public API ──

    def get_brands(self) -> list[Brand]:
        return [v["brand"] for v in self._cache.values()]

    def get_brand(self, brand_id: str) -> Brand | None:
        v = self._cache.get(brand_id)
        return v["brand"] if v else None

    def get_keywords(self, brand_id: str) -> list[Keyword]:
        v = self._cache.get(brand_id)
        return list(v["keywords"]) if v else []

    def get_content(self, brand_id: str) -> list[ContentPiece]:
        v = self._cache.get(brand_id)
        return list(v["content"]) if v else []

    def get_platforms(self, brand_id: str) -> list[PlatformPerformance]:
        v = self._cache.get(brand_id)
        return list(v["platforms"]) if v else []

    def get_engines(self) -> list[str]:
        return list(_ENGINES)

    def get_all_platforms(self) -> list[PlatformPerformance]:
        out: list[PlatformPerformance] = []
        for v in self._cache.values():
            out.extend(v["platforms"])
        return out


_connector = DataConnector()


def get_connector() -> DataConnector:
    return _connector


__all__ = ["DataConnector", "get_connector"]
