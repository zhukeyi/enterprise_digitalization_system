"""Base scraper — abstract interface for all data collectors (M3-T1).

All scrapers (HTTP, RSS, API) implement this interface.
The pipeline uses ScraperRegistry to route by SourceType.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Any

from agents.data_agent.models import CollectedItem, SourceConfig, SourceType

logger = logging.getLogger("fde.data.scrapers.base")

__all__ = ["BaseScraper", "ScraperRegistry", "ScrapingError"]


class ScrapingError(Exception):
    """Raised when data scraping fails."""


class BaseScraper(ABC):
    """Abstract base class for all data scrapers.

    Each scraper implementation:
    1. Receives a SourceConfig
    2. Fetches data from the specified source
    3. Returns a list of CollectedItem (unified model)

    Implementations must set ``source_type`` and implement ``fetch()``.
    """

    source_type: SourceType

    @abstractmethod
    async def fetch(self, config: SourceConfig) -> list[CollectedItem]:
        """Fetch data from the configured source.

        Args:
            config: Source configuration (url, auth, max_items).

        Returns:
            List of collected items.

        Raises:
            ScrapingError: If fetching fails after retries.
        """
        ...


class ScraperRegistry:
    """Registry mapping SourceType → BaseScraper instance.

    Usage:
        registry = ScraperRegistry()
        registry.register(HTTPScraper())
        scraper = registry.get(SourceType.WEB)
        items = await scraper.fetch(config)
    """

    def __init__(self) -> None:
        self._scrapers: dict[SourceType, BaseScraper] = {}

    def register(self, scraper: BaseScraper) -> None:
        """Register a scraper instance.

        Args:
            scraper: Scraper instance with ``source_type`` attribute.
        """
        self._scrapers[scraper.source_type] = scraper
        logger.debug("Registered scraper for source type: %s", scraper.source_type)

    def get(self, source_type: SourceType) -> BaseScraper | None:
        """Get the scraper for a source type.

        Args:
            source_type: The data source type.

        Returns:
            Scraper instance or None if not registered.
        """
        return self._scrapers.get(source_type)

    def get_or_raise(self, source_type: SourceType) -> BaseScraper:
        """Get the scraper or raise if not found.

        Args:
            source_type: The data source type.

        Returns:
            Scraper instance.

        Raises:
            ScrapingError: If no scraper is registered for the type.
        """
        scraper = self._scrapers.get(source_type)
        if scraper is None:
            raise ScrapingError(
                f"No scraper registered for source type: {source_type}. "
                f"Available: {list(self._scrapers.keys())}"
            )
        return scraper

    def list_types(self) -> list[SourceType]:
        """List all registered source types."""
        return list(self._scrapers.keys())

    def create_default(self) -> ScraperRegistry:
        """Register all default scrapers and return self.

        Convenience method for pipeline initialization.
        """
        from agents.data_agent.scrapers.api_scraper import APIScraper
        from agents.data_agent.scrapers.http_scraper import HTTPScraper
        from agents.data_agent.scrapers.rss_scraper import RSSScraper

        self.register(HTTPScraper())
        self.register(RSSScraper())
        self.register(APIScraper())
        return self

    def __len__(self) -> int:
        return len(self._scrapers)

    def __contains__(self, source_type: Any) -> bool:
        if isinstance(source_type, SourceType):
            return source_type in self._scrapers
        if isinstance(source_type, str):
            try:
                return SourceType(source_type) in self._scrapers
            except ValueError:
                return False
        return False
