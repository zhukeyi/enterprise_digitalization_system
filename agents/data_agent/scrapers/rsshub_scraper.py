"""RSSHub Scraper — self-hosted RSSHub route subscriber (P1-A / I-1).

RSSHub generates RSS feeds from 1000+ websites. This scraper wraps
RSSScraper with RSSHub-specific conveniences:

1. Accepts RSSHub route paths (e.g. "/reuters/business") and
   auto-expands to full URLs using FDE_RSSHUB_BASE_URL.
2. Can batch-subscribe to multiple routes via the metadata field.
3. Deduplicates against the RSSHub route registry.

Environment variables:
    FDE_RSSHUB_BASE_URL — RSSHub base URL (default: http://localhost:1200)
"""

from __future__ import annotations

import logging
import os

from agents.data_agent.models import CollectedItem, SourceConfig, SourceType
from agents.data_agent.scrapers.base import BaseScraper, ScrapingError
from agents.data_agent.scrapers.rss_scraper import RSSScraper

logger = logging.getLogger("fde.data.scrapers.rsshub")

__all__ = ["RSSHubScraper", "get_rsshub_base_url"]

# ══════════════════════════════════════════════════════════════════
# Config
# ══════════════════════════════════════════════════════════════════


def get_rsshub_base_url() -> str:
    """Return the RSSHub base URL from env or default."""
    return os.environ.get("FDE_RSSHUB_BASE_URL", "http://localhost:1200").rstrip("/")


# ══════════════════════════════════════════════════════════════════
# Predefined RSSHub routes for foreign-trade intelligence
# ══════════════════════════════════════════════════════════════════

# These routes cover the main use cases for the FDE intelligence module.
# Users can add more routes via the SourceConfig.metadata["routes"] field.

TRADE_INTEL_ROUTES: dict[str, list[str]] = {
    "news_global": [
        "/reuters/business",
        "/bbc/world",
        "/nytimes/home",
        "/theguardian/world",
    ],
    "tech_industry": [
        "/hackernews",
        "/techcrunch",
        "/theverge/tech",
    ],
    "trade_policy": [
        "/wti/news",       # WTO
        "/unctad/news",    # UNCTAD
    ],
    "china_trade": [
        "/cs/news",        # Customs China
        "/mofcom/news",    # MOFCOM
    ],
}


def get_default_routes() -> list[str]:
    """Return all predefined RSSHub routes for trade intelligence."""
    all_routes: list[str] = []
    for routes in TRADE_INTEL_ROUTES.values():
        all_routes.extend(routes)
    return all_routes


# ══════════════════════════════════════════════════════════════════
# RSSHubScraper
# ══════════════════════════════════════════════════════════════════


class RSSHubScraper(BaseScraper):
    """RSSHub route subscriber — fetches feeds from a self-hosted RSSHub.

    Accepts either:
    - A full RSSHub URL in config.url (e.g. http://localhost:1200/reuters/business)
    - A route path in config.url (e.g. /reuters/business) — auto-expanded
    - Multiple routes in config.metadata["routes"] (list of paths)

    Delegates actual RSS parsing to RSSScraper.
    """

    source_type = SourceType.RSSHUB

    def __init__(self, timeout: float = 30.0) -> None:
        self._timeout = timeout
        self._rss_scraper = RSSScraper(timeout=timeout)

    def _resolve_url(self, url: str) -> str:
        """Expand a route path to a full RSSHub URL."""
        if url.startswith("http://") or url.startswith("https://"):
            return url
        # Treat as a route path
        if not url.startswith("/"):
            url = "/" + url
        return f"{get_rsshub_base_url()}{url}"

    async def fetch(self, config: SourceConfig) -> list[CollectedItem]:
        """Fetch one or more RSSHub routes.

        Args:
            config: Source config. Set config.url to a route path or full URL.
                For batch mode, put route paths in config.metadata["routes"].

        Returns:
            Aggregated list of CollectedItem from all routes.
        """
        # Determine which routes to fetch
        routes: list[str] = []
        if config.metadata and "routes" in config.metadata:
            raw_routes = config.metadata["routes"]
            if isinstance(raw_routes, list):
                routes = [str(r) for r in raw_routes]
        if config.url:
            routes.insert(0, config.url)

        if not routes:
            raise ScrapingError("RSSHubScraper: no routes specified (set url or metadata['routes'])")

        # Fetch each route via RSSScraper
        all_items: list[CollectedItem] = []
        errors: list[str] = []

        for route in routes:
            full_url = self._resolve_url(route)
            rss_config = SourceConfig(
                source_type=SourceType.RSS,
                url=full_url,
                max_items=config.max_items,
                headers=config.headers,
                auth_config=config.auth_config,
            )
            try:
                items = await self._rss_scraper.fetch(rss_config)
                # Re-tag items as RSSHUB source
                for item in items:
                    item.source = SourceType.RSSHUB
                    item.metadata["rsshub_route"] = route
                all_items.extend(items)
                logger.info("RSSHubScraper: %d items from %s", len(items), route)
            except ScrapingError as e:
                logger.warning("RSSHubScraper: route %s failed: %s", route, e)
                errors.append(f"{route}: {e}")

        if not all_items and errors:
            raise ScrapingError(
                f"RSSHubScraper: all routes failed: {'; '.join(errors)}"
            )

        logger.info(
            "RSSHubScraper: total %d items from %d routes (%d failed)",
            len(all_items),
            len(routes),
            len(errors),
        )
        return all_items
