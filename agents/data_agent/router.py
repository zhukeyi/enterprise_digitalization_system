"""Data Agent — HTTP router for Intelligence Portal (V5-④).

Exposes data_agent capabilities via REST API:

* ``GET  /api/intelligence/overview``  — 情报总览统计
* ``GET  /api/intelligence/sources``   — 数据源列表
* ``POST /api/intelligence/collect``   — 触发采集
* ``GET  /api/intelligence/items``     — 采集到的情报条目
* ``GET  /api/intelligence/trends``    — 趋势分析数据
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

from agents.data_agent.models import (
    CleanedItem,
    PipelineResult,
    SourceConfig,
    SourceType,
)
from agents.data_agent.pipeline import DataPipeline, get_datastore

logger = logging.getLogger("fde.data.router")

router = APIRouter(prefix="/api/intelligence", tags=["intelligence"])

# ══════════════════════════════════════════════════════════════════
# Response Models
# ══════════════════════════════════════════════════════════════════


class OverviewStats(BaseModel):
    """情报总览统计。"""

    total_items: int
    total_sources: int
    source_types: list[dict[str, Any]]
    recent_items: list[dict[str, Any]]
    daily_collection: list[dict[str, Any]]
    sentiment_distribution: dict[str, int]


class SourceInfo(BaseModel):
    """数据源信息。"""

    source_type: str
    url: str
    max_items: int
    label: str
    active: bool = True


class CollectRequest(BaseModel):
    """采集请求。"""

    source_type: str = "rss"
    query: str = ""
    url: str = ""
    max_items: int = 20
    label: str = ""
    metadata: dict[str, Any] | None = None


class CollectResponse(BaseModel):
    """采集响应。"""

    success: bool
    items_collected: int
    items: list[dict[str, Any]]
    error: str | None = None


class TrendItem(BaseModel):
    """趋势数据点。"""

    date: str
    count: int
    keywords: list[str] = []


# ══════════════════════════════════════════════════════════════════
# In-memory sample data (production: replace with DB queries)
# ══════════════════════════════════════════════════════════════════

# 预置数据源（演示用）
_SAMPLE_SOURCES: list[SourceInfo] = [
    SourceInfo(source_type="rss", url="https://feeds.bbci.co.uk/news/world/rss.xml",
               max_items=50, label="BBC World News"),
    SourceInfo(source_type="rss", url="https://rss.nytimes.com/services/xml/rss/nyt/HomePage.xml",
               max_items=50, label="NYT Home"),
    SourceInfo(source_type="rss", url="https://www.theguardian.com/world/rss",
               max_items=50, label="Guardian World"),
    SourceInfo(source_type="web", url="https://news.ycombinator.com",
               max_items=30, label="Hacker News"),
    SourceInfo(source_type="api", url="https://api.github.com/events",
               max_items=30, label="GitHub Events"),
]


def _generate_mock_items(count: int = 20) -> list[dict[str, Any]]:
    """生成模拟情报条目（当 datastore 为空时用于演示）。"""
    titles = [
        "AI芯片市场竞争加剧：新玩家入场",
        "全球供应链重塑：东南亚制造业崛起",
        "新能源车企Q2财报超预期",
        "半导体出口管制政策更新",
        "科技巨头加码大模型投资",
        "跨境电商新规影响出海企业",
        "量子计算商用化进程加速",
        "数据安全法实施细则发布",
        "云服务市场格局变化分析",
        "开源生态对商业软件的冲击",
    ]
    sources = ["BBC", "NYT", "Guardian", "Hacker News", "GitHub"]
    sentiments = ["positive", "neutral", "negative"]
    keywords_pool = [
        "AI", "芯片", "供应链", "新能源", "半导体", "大模型",
        "量子计算", "数据安全", "云服务", "开源", "跨境电商",
    ]

    import random
    random.seed(42)
    items = []
    now = datetime.now(UTC)
    for i in range(count):
        t = now - timedelta(hours=random.randint(1, 72))
        title = titles[i % len(titles)]
        sentiment = sentiments[i % 3]
        kws = random.sample(keywords_pool, k=min(3, len(keywords_pool)))
        items.append({
            "id": f"intel-{i+1:04d}",
            "title": title,
            "source": sources[i % len(sources)],
            "url": f"https://example.com/article/{i+1}",
            "summary": f"本文分析了{title}的背景、影响和未来趋势。",
            "sentiment": sentiment,
            "keywords": kws,
            "collected_at": t.isoformat(),
            "language": "zh" if i % 2 == 0 else "en",
        })
    return items


# ══════════════════════════════════════════════════════════════════
# Endpoints
# ══════════════════════════════════════════════════════════════════


@router.get("/overview", response_model=OverviewStats)
async def overview() -> OverviewStats:
    """情报总览统计。"""
    datastore = get_datastore()
    all_items: list[CleanedItem] = []
    for items_list in datastore.values():
        all_items.extend(items_list)

    # 如果没有真实数据，用模拟数据
    use_mock = len(all_items) == 0
    mock_items = _generate_mock_items(30) if use_mock else []

    total_items = len(all_items) if not use_mock else len(mock_items)
    total_sources = len(datastore) if not use_mock else len(_SAMPLE_SOURCES)

    # source type distribution
    if use_mock:
        source_types = [
            {"name": st.value, "count": sum(1 for s in _SAMPLE_SOURCES if s.source_type == st.value)}
            for st in SourceType
        ]
    else:
        source_types = [
            {"name": st, "count": sum(1 for s in datastore if st in s)}
            for st in ["rss", "web", "api"]
        ]
    source_types = [s for s in source_types if s["count"] > 0]

    # recent items
    if use_mock:
        recent = mock_items[:10]
    else:
        recent = [
            {
                "id": item.id,
                "title": item.title or "Untitled",
                "source": item.source_url or "",
                "summary": (item.content or "")[:200],
                "sentiment": getattr(item, "sentiment", "neutral"),
                "keywords": getattr(item, "keywords", []),
                "collected_at": item.collected_at.isoformat() if hasattr(item, "collected_at") else "",
            }
            for item in all_items[:10]
        ]

    # daily collection (7 days)
    now = datetime.now(UTC)
    daily = []
    for i in range(6, -1, -1):
        day_start = (now - timedelta(days=i)).replace(hour=0, minute=0, second=0, microsecond=0)
        day_end = day_start + timedelta(days=1)
        if use_mock:
            count = sum(1 for m in mock_items if day_start <= datetime.fromisoformat(m["collected_at"]) < day_end)
        else:
            count = sum(
                1 for item in all_items
                if hasattr(item, "collected_at") and day_start <= item.collected_at < day_end
            )
        daily.append({"date": day_start.strftime("%m-%d"), "count": count})

    # sentiment distribution
    if use_mock:
        sentiment_dist = {
            "positive": sum(1 for m in mock_items if m["sentiment"] == "positive"),
            "neutral": sum(1 for m in mock_items if m["sentiment"] == "neutral"),
            "negative": sum(1 for m in mock_items if m["sentiment"] == "negative"),
        }
    else:
        sentiment_dist = {"positive": 0, "neutral": 0, "negative": 0}
        for item in all_items:
            s = getattr(item, "sentiment", "neutral")
            if s in sentiment_dist:
                sentiment_dist[s] += 1

    return OverviewStats(
        total_items=total_items,
        total_sources=total_sources,
        source_types=source_types,
        recent_items=recent,
        daily_collection=daily,
        sentiment_distribution=sentiment_dist,
    )


@router.get("/sources", response_model=list[SourceInfo])
async def list_sources() -> list[SourceInfo]:
    """列出所有数据源。"""
    return _SAMPLE_SOURCES


@router.post("/collect", response_model=CollectResponse)
async def collect(req: CollectRequest) -> CollectResponse:
    """触发一次数据采集。"""
    try:
        st = SourceType(req.source_type)
    except ValueError:
        return CollectResponse(
            success=False, items_collected=0, items=[],
            error=f"未知数据源类型: {req.source_type}",
        )

    url = req.url or req.query
    if not url:
        return CollectResponse(
            success=False, items_collected=0, items=[],
            error="url 或 query 必填一个",
        )

    config = SourceConfig(
        source_type=st,
        url=url,
        max_items=req.max_items,
        metadata=req.metadata,
    )

    try:
        pipeline = DataPipeline()
        result: PipelineResult = await pipeline.run(config)

        # PipelineResult does not carry items directly; retrieve from datastore
        from agents.data_agent.pipeline import get_datastore

        cleaned_items = get_datastore().get(result.dataset_id, [])
        items = [
            {
                "id": item.id,
                "title": item.title or "Untitled",
                "source": item.source_url or url,
                "summary": (item.content or "")[:200],
            }
            for item in cleaned_items
        ]
        return CollectResponse(
            success=True,
            items_collected=result.cleaned_count,
            items=items,
        )
    except (ValueError, RuntimeError, OSError) as e:
        logger.error("Collection failed: %s", e)
        return CollectResponse(
            success=False, items_collected=0, items=[],
            error=str(e),
        )


@router.get("/items", response_model=list[dict[str, Any]])
async def list_items(limit: int = 50) -> list[dict[str, Any]]:
    """获取采集到的情报条目。"""
    datastore = get_datastore()
    all_items: list[CleanedItem] = []
    for items_list in datastore.values():
        all_items.extend(items_list)

    if not all_items:
        return _generate_mock_items(limit)

    return [
        {
            "id": item.id,
            "title": item.title or "Untitled",
            "source": item.source_url or "",
            "summary": (item.content or "")[:200],
            "sentiment": getattr(item, "sentiment", "neutral"),
            "keywords": getattr(item, "keywords", []),
            "collected_at": item.collected_at.isoformat() if hasattr(item, "collected_at") else "",
        }
        for item in all_items[:limit]
    ]


@router.get("/trends", response_model=list[TrendItem])
async def trends(days: int = 7) -> list[TrendItem]:
    """获取趋势分析数据。"""
    mock_items = _generate_mock_items(30)
    now = datetime.now(UTC)

    keywords_by_day: dict[str, list[str]] = {}
    counts_by_day: dict[str, int] = {}

    for i in range(days - 1, -1, -1):
        day_start = (now - timedelta(days=i)).replace(hour=0, minute=0, second=0, microsecond=0)
        date_key = day_start.strftime("%m-%d")
        counts_by_day[date_key] = 0
        keywords_by_day[date_key] = []

    for m in mock_items:
        t = datetime.fromisoformat(m["collected_at"])
        day_start = t.replace(hour=0, minute=0, second=0, microsecond=0)
        date_key = day_start.strftime("%m-%d")
        if date_key in counts_by_day:
            counts_by_day[date_key] += 1
            keywords_by_day[date_key].extend(m["keywords"])

    # deduplicate keywords per day
    for k in keywords_by_day:
        keywords_by_day[k] = list(set(keywords_by_day[k]))[:5]

    return [
        TrendItem(date=d, count=counts_by_day[d], keywords=keywords_by_day[d])
        for d in counts_by_day
    ]


@router.get("/rsshub/routes", response_model=dict[str, list[str]])
async def rsshub_routes() -> dict[str, list[str]]:
    """返回预置的 RSSHub 贸易情报路由分类。"""
    from agents.data_agent.scrapers.rsshub_scraper import TRADE_INTEL_ROUTES

    return TRADE_INTEL_ROUTES


@router.get("/source-types", response_model=list[dict[str, str]])
async def source_types() -> list[dict[str, str]]:
    """返回所有支持的数据源类型及说明。"""
    return [
        {"type": "web", "label": "Web Page (HTTP)", "description": "直接 HTTP 抓取网页"},
        {"type": "rss", "label": "RSS/Atom Feed", "description": "标准 RSS/Atom 订阅源"},
        {"type": "api", "label": "REST API", "description": "JSON REST API 端点"},
        {"type": "customs", "label": "Customs Data", "description": "海关贸易数据"},
        {"type": "rsshub", "label": "RSSHub Route", "description": "自托管 RSSHub 1000+ 路由"},
        {"type": "crawl4ai", "label": "crawl4ai (LLM-ready)", "description": "深度网页抓取，输出 Markdown"},
    ]


__all__ = ["router"]
