"""HTTP web scraper — async HTTP + HTML parsing (M3-T1).

Uses httpx for async HTTP requests. For HTML parsing, prefers
selectolax (fast C-based parser); falls back to a standard-library
HTMLParser-based extractor when selectolax is not installed.
"""

from __future__ import annotations

import logging
import re
from html.parser import HTMLParser
from typing import Any

import httpx

from agents.data_agent.models import CollectedItem, SourceConfig, SourceType
from agents.data_agent.scrapers.base import BaseScraper, ScrapingError
from shared.utils.retry import retry_async

logger = logging.getLogger("fde.data.scrapers.http")

__all__ = ["HTTPScraper"]

# ══════════════════════════════════════════════════════════════════
# HTML Parsing — selectolax preferred, stdlib fallback
# ══════════════════════════════════════════════════════════════════

try:
    from selectolax.parser import HTMLParser as SelectolaxParser

    _HAS_SELECTOLAX = True
except ImportError:
    _HAS_SELECTOLAX = False
    logger.debug("selectolax not installed, using stdlib HTMLParser fallback")


class _StdlibArticleExtractor(HTMLParser):
    """Minimal stdlib HTML parser to extract article-like content.

    Extracts text from <article>, <div class="article|post|item|content">
    tags. This is a fallback when selectolax is unavailable.
    """

    # Tags that typically wrap article content
    _ARTICLE_TAGS = {"article"}
    _ARTICLE_CLASSES = {"article", "post", "item", "content", "entry"}

    def __init__(self) -> None:
        super().__init__()
        self.articles: list[dict[str, str]] = []
        self._current_tag: str = ""
        self._current_class: str = ""
        self._in_article = False
        self._current_title: str = ""
        self._current_text: str = ""

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr_dict = dict(attrs)
        cls = attr_dict.get("class", "") or ""

        if tag in self._ARTICLE_TAGS or (
            tag == "div" and any(c in self._ARTICLE_CLASSES for c in cls.split())
        ):
            self._in_article = True
            self._current_tag = tag
            self._current_class = cls
            self._current_title = ""
            self._current_text = ""

        if self._in_article and tag in ("h1", "h2", "h3", "title"):
            self._current_tag = tag

    def handle_endtag(self, tag: str) -> None:
        if self._in_article and tag in ("article", "div"):
            text = self._current_text.strip()
            if text:
                self.articles.append({
                    "title": self._current_title.strip() or text[:80],
                    "text": text,
                    "html": "",
                })
            self._in_article = False
            self._current_text = ""

    def handle_data(self, data: str) -> None:
        if self._in_article:
            stripped = data.strip()
            if stripped:
                if self._current_tag in ("h1", "h2", "h3", "title"):
                    self._current_title += stripped
                self._current_text += stripped + " "


def _parse_html_selectolax(html: str, max_items: int) -> list[dict[str, str]]:
    """Parse HTML using selectolax (fast C-based parser)."""
    tree = SelectolaxParser(html)
    items: list[dict[str, str]] = []

    # Try common article selectors
    nodes = tree.css("article, .article, .post, .item, .entry, .content-item")
    for node in nodes[:max_items]:
        title_node = node.css_first("h1, h2, h3, .title, .post-title")
        title = title_node.text(strip=True) if title_node else ""
        # Get text content, excluding script/style
        for tag in node.css("script, style"):
            tag.decompose()
        text = node.text(separator=" ", strip=True)
        if text:
            items.append({
                "title": title or text[:80],
                "text": text,
                "html": node.html,
            })

    return items


def _parse_html_stdlib(html: str, max_items: int) -> list[dict[str, str]]:
    """Parse HTML using stdlib HTMLParser (fallback)."""
    parser = _StdlibArticleExtractor()
    parser.feed(html)
    return parser.articles[:max_items]


def _parse_html(html: str, max_items: int) -> list[dict[str, str]]:
    """Parse HTML, using selectolax if available, else stdlib fallback."""
    if _HAS_SELECTOLAX:
        try:
            return _parse_html_selectolax(html, max_items)
        except (RuntimeError, ValueError, OSError) as e:
            logger.warning("selectolax parse failed (%s), falling back to stdlib", e)
    return _parse_html_stdlib(html, max_items)


# ══════════════════════════════════════════════════════════════════
# HTTP Scraper
# ══════════════════════════════════════════════════════════════════


class HTTPScraper(BaseScraper):
    """Async HTTP web scraper.

    Fetches web pages via httpx, parses HTML to extract article-like
    content. Uses retry_async for resilience.
    """

    source_type = SourceType.WEB

    def __init__(self, timeout: float = 30.0, max_retries: int = 3) -> None:
        self._timeout = timeout
        self._max_retries = max_retries

    async def fetch(self, config: SourceConfig) -> list[CollectedItem]:
        """Fetch and parse a web page.

        Args:
            config: Source config with url and headers.

        Returns:
            List of collected items extracted from the page.

        Raises:
            ScrapingError: If HTTP request fails after retries.
        """
        if config.source_type != SourceType.WEB:
            raise ScrapingError(
                f"HTTPScraper received non-web source type: {config.source_type}"
            )

        async with httpx.AsyncClient(
            timeout=self._timeout,
            headers=config.headers,
            follow_redirects=True,
        ) as client:
            try:
                response = await retry_async(
                    client.get,
                    config.url,
                    max_retries=self._max_retries,
                )
                response.raise_for_status()
            except (
                httpx.HTTPStatusError,
                httpx.RequestError,
                httpx.TimeoutException,
            ) as e:
                logger.error("HTTP fetch failed for %s: %s", config.url, e)
                raise ScrapingError(f"HTTP fetch failed: {e}") from e

            # Parse HTML
            parsed = _parse_html(response.text, config.max_items)

            if not parsed:
                logger.warning("No articles found at %s", config.url)

            items: list[CollectedItem] = []
            for p in parsed:
                if not p.get("text"):
                    continue
                items.append(
                    CollectedItem(
                        source=SourceType.WEB,
                        source_url=config.url,
                        title=p.get("title", ""),
                        content=p["text"],
                        raw_html=p.get("html"),
                        metadata={
                            "status_code": response.status_code,
                            "content_type": response.headers.get("content-type", ""),
                        },
                    )
                )

            logger.info("HTTPScraper: extracted %d items from %s", len(items), config.url)
            return items
