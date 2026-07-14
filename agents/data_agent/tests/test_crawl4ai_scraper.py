"""Tests for Crawl4AIScraper and RSSHubScraper (P1-A I-5).

Tests cover:
- Crawl4AIScraper fallback path (httpx + HTML-to-Markdown)
- Crawl4AIScraper HTML-to-Markdown converter
- RSSHubScraper URL resolution
- RSSHubScraper batch route subscription
- ScraperRegistry registration of new scrapers
- Integration with DataPipeline
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from agents.data_agent.models import CollectedItem, SourceConfig, SourceType
from agents.data_agent.scrapers import Crawl4AIScraper, RSSHubScraper, ScraperRegistry
from agents.data_agent.scrapers.crawl4ai_scraper import (
    _extract_title,
    _html_to_markdown,
)
from agents.data_agent.scrapers.rsshub_scraper import (
    TRADE_INTEL_ROUTES,
    get_default_routes,
    get_rsshub_base_url,
)

# ══════════════════════════════════════════════════════════════════
# HTML-to-Markdown converter tests
# ══════════════════════════════════════════════════════════════════


class TestHtmlToMarkdown:
    """Test the fallback HTML-to-Markdown converter."""

    def test_basic_conversion(self) -> None:
        html = "<h1>Title</h1><p>Paragraph text</p>"
        md = _html_to_markdown(html)
        assert "# Title" in md
        assert "Paragraph text" in md

    def test_strips_script_style(self) -> None:
        html = "<p>Visible</p><script>evil()</script><style>.x{}</style>"
        md = _html_to_markdown(html)
        assert "Visible" in md
        assert "evil" not in md
        assert ".x{}" not in md

    def test_strips_nav_footer(self) -> None:
        html = "<article><p>Main content</p></article><nav>Menu</nav><footer>Copyright</footer>"
        md = _html_to_markdown(html)
        assert "Main content" in md
        assert "Menu" not in md
        assert "Copyright" not in md

    def test_links(self) -> None:
        html = '<p><a href="https://example.com">Link text</a></p>'
        md = _html_to_markdown(html)
        assert "[Link text](https://example.com)" in md

    def test_bold_italic(self) -> None:
        html = "<p><strong>Bold</strong> and <em>italic</em></p>"
        md = _html_to_markdown(html)
        assert "**Bold**" in md
        assert "*italic*" in md

    def test_lists(self) -> None:
        html = "<ul><li>Item 1</li><li>Item 2</li></ul>"
        md = _html_to_markdown(html)
        assert "- Item 1" in md
        assert "- Item 2" in md

    def test_code_blocks(self) -> None:
        html = "<pre>code line</pre>"
        md = _html_to_markdown(html)
        assert "```" in md
        assert "code line" in md

    def test_truncation(self) -> None:
        html = "<p>" + "A" * 100000 + "</p>"
        md = _html_to_markdown(html, max_length=1000)
        assert len(md) <= 1100  # truncation + some headroom

    def test_empty_html(self) -> None:
        assert _html_to_markdown("") == ""

    def test_extract_title(self) -> None:
        assert _extract_title("<html><head><title>My Page</title></head>") == "My Page"
        assert _extract_title("<html><body>No title</body></html>") == ""


# ══════════════════════════════════════════════════════════════════
# Crawl4AIScraper tests
# ══════════════════════════════════════════════════════════════════


class TestCrawl4AIScraper:
    """Test Crawl4AIScraper with fallback backend."""

    @pytest.mark.asyncio
    async def test_fallback_fetch_success(self) -> None:
        """Crawl4AIScraper falls back to HTTP when crawl4ai not installed."""
        scraper = Crawl4AIScraper(timeout=5.0)
        # Force fallback mode
        scraper._use_crawl4ai = False

        html = """
        <html><head><title>Test Page</title></head>
        <body>
            <script>evil()</script>
            <article><h1>Article Title</h1><p>Article content here.</p></article>
            <nav>Menu</nav>
        </body></html>
        """
        mock_response = MagicMock()
        mock_response.text = html
        mock_response.status_code = 200
        mock_response.headers = {"content-type": "text/html"}
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client_cls.return_value = mock_client

            config = SourceConfig(
                source_type=SourceType.CRAWL4AI,
                url="https://example.com/article",
                max_items=5,
            )
            items = await scraper.fetch(config)

        assert len(items) == 1
        assert items[0].source == SourceType.CRAWL4AI
        assert "Article Title" in items[0].content
        assert "evil" not in items[0].content
        assert items[0].metadata["backend"] == "fallback-http"

    @pytest.mark.asyncio
    async def test_fallback_fetch_error(self) -> None:
        """Crawl4AIScraper raises ScrapingError on HTTP failure."""
        scraper = Crawl4AIScraper(timeout=5.0)
        scraper._use_crawl4ai = False

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client.get = AsyncMock(side_effect=httpx.ConnectError("Connection refused"))
            mock_client_cls.return_value = mock_client

            config = SourceConfig(
                source_type=SourceType.CRAWL4AI,
                url="https://unreachable.example.com",
                max_items=5,
            )
            with pytest.raises(Exception, match="HTTP fetch failed"):
                await scraper.fetch(config)

    @pytest.mark.asyncio
    async def test_empty_html_returns_empty(self) -> None:
        """Empty HTML page returns empty list."""
        scraper = Crawl4AIScraper(timeout=5.0)
        scraper._use_crawl4ai = False

        mock_response = MagicMock()
        mock_response.text = "<html><body></body></html>"
        mock_response.status_code = 200
        mock_response.headers = {"content-type": "text/html"}
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client_cls.return_value = mock_client

            config = SourceConfig(
                source_type=SourceType.CRAWL4AI,
                url="https://example.com/empty",
                max_items=5,
            )
            items = await scraper.fetch(config)

        assert len(items) == 0


# ══════════════════════════════════════════════════════════════════
# RSSHubScraper tests
# ══════════════════════════════════════════════════════════════════


class TestRSSHubScraper:
    """Test RSSHubScraper."""

    def test_resolve_url_full(self) -> None:
        """Full URL is returned as-is."""
        scraper = RSSHubScraper()
        url = "http://rsshub.example.com/reuters/business"
        assert scraper._resolve_url(url) == url

    def test_resolve_url_path(self) -> None:
        """Route path is expanded with base URL."""
        scraper = RSSHubScraper()
        resolved = scraper._resolve_url("/reuters/business")
        assert resolved == f"{get_rsshub_base_url()}/reuters/business"

    def test_resolve_url_no_leading_slash(self) -> None:
        """Route path without leading slash gets one."""
        scraper = RSSHubScraper()
        resolved = scraper._resolve_url("reuters/business")
        assert resolved == f"{get_rsshub_base_url()}/reuters/business"

    @pytest.mark.asyncio
    async def test_batch_routes(self) -> None:
        """RSSHubScraper fetches multiple routes from metadata."""
        scraper = RSSHubScraper()

        # Mock RSSScraper.fetch to return one item per route
        async def mock_fetch(config: SourceConfig) -> list[CollectedItem]:
            return [
                CollectedItem(
                    source=SourceType.RSS,
                    source_url=config.url,
                    title=f"Item from {config.url}",
                    content="content",
                )
            ]

        with patch.object(scraper._rss_scraper, "fetch", side_effect=mock_fetch):
            config = SourceConfig(
                source_type=SourceType.RSSHUB,
                url="",  # no single URL
                max_items=10,
                metadata={
                    "routes": ["/reuters/business", "/bbc/world"],
                },
            )
            items = await scraper.fetch(config)

        assert len(items) == 2
        assert all(item.source == SourceType.RSSHUB for item in items)
        assert items[0].metadata["rsshub_route"] == "/reuters/business"
        assert items[1].metadata["rsshub_route"] == "/bbc/world"

    @pytest.mark.asyncio
    async def test_no_routes_raises(self) -> None:
        """Missing routes and URL raises ScrapingError."""
        scraper = RSSHubScraper()
        config = SourceConfig(
            source_type=SourceType.RSSHUB,
            url="",
            max_items=10,
        )
        with pytest.raises(Exception, match="no routes specified"):
            await scraper.fetch(config)

    @pytest.mark.asyncio
    async def test_all_routes_failed_raises(self) -> None:
        """If all routes fail, ScrapingError is raised."""
        scraper = RSSHubScraper()

        from agents.data_agent.scrapers.base import ScrapingError

        async def mock_fetch(config: SourceConfig) -> list[CollectedItem]:
            raise ScrapingError("Connection refused")

        with patch.object(scraper._rss_scraper, "fetch", side_effect=mock_fetch):
            config = SourceConfig(
                source_type=SourceType.RSSHUB,
                url="/reuters/business",
                max_items=10,
            )
            with pytest.raises(Exception, match="all routes failed"):
                await scraper.fetch(config)

    def test_default_routes_not_empty(self) -> None:
        """Predefined routes cover key categories."""
        routes = get_default_routes()
        assert len(routes) >= 5
        assert any("reuters" in r for r in routes)
        assert any("bbc" in r for r in routes)

    def test_trade_intel_categories(self) -> None:
        """TRADE_INTEL_ROUTES has the expected categories."""
        assert "news_global" in TRADE_INTEL_ROUTES
        assert "tech_industry" in TRADE_INTEL_ROUTES
        assert len(TRADE_INTEL_ROUTES["news_global"]) >= 3


# ══════════════════════════════════════════════════════════════════
# ScraperRegistry integration tests
# ══════════════════════════════════════════════════════════════════


class TestScraperRegistryIntegration:
    """Test that new scrapers are properly registered."""

    def test_registry_has_crawl4ai(self) -> None:
        """ScraperRegistry.create_default registers Crawl4AIScraper."""
        registry = ScraperRegistry().create_default()
        assert SourceType.CRAWL4AI in registry
        scraper = registry.get(SourceType.CRAWL4AI)
        assert scraper is not None
        assert isinstance(scraper, Crawl4AIScraper)

    def test_registry_has_rsshub(self) -> None:
        """ScraperRegistry.create_default registers RSSHubScraper."""
        registry = ScraperRegistry().create_default()
        assert SourceType.RSSHUB in registry
        scraper = registry.get(SourceType.RSSHUB)
        assert scraper is not None
        assert isinstance(scraper, RSSHubScraper)

    def test_registry_has_all_six_types(self) -> None:
        """All 6 source types are registered."""
        registry = ScraperRegistry().create_default()
        types = registry.list_types()
        assert SourceType.WEB in types
        assert SourceType.RSS in types
        assert SourceType.API in types
        assert SourceType.CUSTOMS in types
        assert SourceType.CRAWL4AI in types
        assert SourceType.RSSHUB in types
        assert len(types) == 6
