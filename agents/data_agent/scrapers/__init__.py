"""Scraper package — multi-source data collection (M3-T1).

Provides:
- BaseScraper: 抽象基类，所有采集器实现此接口
- HTTPScraper: 网页爬虫 (httpx + selectolax)
- RSSScraper: RSS/Atom Feed 采集器 (feedparser)
- APIScraper: REST API 采集器 (httpx)

Usage:
    from agents.data_agent.scrapers import HTTPScraper, RSSScraper, APIScraper
    scraper = HTTPScraper()
    items = await scraper.fetch(config)
"""

from __future__ import annotations

from agents.data_agent.scrapers.api_scraper import APIScraper
from agents.data_agent.scrapers.base import BaseScraper, ScraperRegistry
from agents.data_agent.scrapers.http_scraper import HTTPScraper
from agents.data_agent.scrapers.rss_scraper import RSSScraper

__all__ = [
    "APIScraper",
    "BaseScraper",
    "HTTPScraper",
    "RSSScraper",
    "ScraperRegistry",
]
