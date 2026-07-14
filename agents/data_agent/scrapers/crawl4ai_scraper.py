"""crawl4ai Scraper -- LLM-ready Markdown extraction (P1-A / I-2).

crawl4ai is an async web crawler that produces clean Markdown output
optimized for LLM ingestion: removes boilerplate, extracts main content,
handles JavaScript-rendered pages via a headless browser.

This scraper is registered in ScraperRegistry under SourceType.CRAWL4AI.
It degrades gracefully when crawl4ai is not installed -- falling back to
HTTPScraper + a simple HTML-to-Markdown converter.

Environment variables:
    FDE_CRAWL4AI_BACKEND   -- "crawl4ai" (default) or "fallback"
    FDE_CRAWL4AI_TIMEOUT   -- per-page timeout in seconds (default: 60)
"""

from __future__ import annotations

import logging
import re

from agents.data_agent.models import CollectedItem, SourceConfig, SourceType
from agents.data_agent.scrapers.base import BaseScraper, ScrapingError

logger = logging.getLogger("fde.data.scrapers.crawl4ai")

__all__ = ["Crawl4AIScraper"]

# ══════════════════════════════════════════════════════════════════
# crawl4ai availability check
# ══════════════════════════════════════════════════════════════════

try:
    from crawl4ai import AsyncWebCrawler  # type: ignore[import-untyped]
    from crawl4ai.async_configs import (  # type: ignore[import-untyped]
        BrowserConfig,
        CrawlerRunConfig,
    )

    _HAS_CRAWL4AI = True
except ImportError:
    _HAS_CRAWL4AI = False
    logger.debug("crawl4ai not installed -- Crawl4AIScraper will use HTTP fallback")


# ══════════════════════════════════════════════════════════════════
# HTML -> Markdown fallback converter
# ══════════════════════════════════════════════════════════════════

# Tag -> Markdown patterns for a minimal but useful conversion
_TAG_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"<h1[^>]*>(.*?)</h1>", re.DOTALL | re.IGNORECASE), r"# \1\n\n"),
    (re.compile(r"<h2[^>]*>(.*?)</h2>", re.DOTALL | re.IGNORECASE), r"## \1\n\n"),
    (re.compile(r"<h3[^>]*>(.*?)</h3>", re.DOTALL | re.IGNORECASE), r"### \1\n\n"),
    (re.compile(r"<h4[^>]*>(.*?)</h4>", re.DOTALL | re.IGNORECASE), r"#### \1\n\n"),
    (re.compile(r"<li[^>]*>(.*?)</li>", re.DOTALL | re.IGNORECASE), r"- \1\n"),
    (re.compile(r"<p[^>]*>(.*?)</p>", re.DOTALL | re.IGNORECASE), r"\1\n\n"),
    (re.compile(r"<br\s*/?>", re.IGNORECASE), "\n"),
    (re.compile(r"<strong[^>]*>(.*?)</strong>", re.DOTALL | re.IGNORECASE), r"**\1**"),
    (re.compile(r"<b[^>]*>(.*?)</b>", re.DOTALL | re.IGNORECASE), r"**\1**"),
    (re.compile(r"<em[^>]*>(.*?)</em>", re.DOTALL | re.IGNORECASE), r"*\1*"),
    (re.compile(r"<i[^>]*>(.*?)</i>", re.DOTALL | re.IGNORECASE), r"*\1*"),
    (re.compile(r"<a[^>]*href=[\"']([^\"']*)[\"'][^>]*>(.*?)</a>", re.DOTALL | re.IGNORECASE), r"[\2](\1)"),
    (re.compile(r"<code[^>]*>(.*?)</code>", re.DOTALL | re.IGNORECASE), r"`\1`"),
    (re.compile(r"<pre[^>]*>(.*?)</pre>", re.DOTALL | re.IGNORECASE), r"```\n\1\n```\n\n"),
]

_BLOCK_TAGS = re.compile(
    r"<(script|style|nav|footer|header|aside|form|noscript|iframe|svg)[^>]*>.*?</\1>",
    re.DOTALL | re.IGNORECASE,
)


def _html_to_markdown(html: str, max_length: int = 50000) -> str:
    """Convert HTML to a minimal Markdown representation.

    This is NOT a full HTML-to-Markdown engine -- it strips boilerplate
    and applies regex substitutions for common tags. It's the fallback
    when crawl4ai is not available.
    """
    # Remove script/style/nav/footer blocks
    clean = _BLOCK_TAGS.sub("", html)
    # Apply tag patterns
    for pattern, replacement in _TAG_PATTERNS:
        clean = pattern.sub(replacement, clean)
    # Strip remaining tags
    clean = re.sub(r"<[^>]+>", "", clean)
    # Decode common HTML entities (named entities first, bare & last)
    clean = clean.replace("<", "<")
    clean = clean.replace(">", ">")
    clean = clean.replace('"', '"')
    clean = clean.replace("&#39;", "'")
    clean = clean.replace("&nbsp;", " ")
    clean = clean.replace("&", "&")
    # Collapse excessive whitespace
    clean = re.sub(r"\n{3,}", "\n\n", clean)
    clean = re.sub(r"[ \t]{2,}", " ", clean)
    return clean.strip()[:max_length]


def _extract_title(html: str) -> str:
    """Extract <title> from HTML."""
    m = re.search(r"<title[^>]*>(.*?)</title>", html, re.DOTALL | re.IGNORECASE)
    return m.group(1).strip() if m else ""


# ══════════════════════════════════════════════════════════════════
# Crawl4AIScraper
# ══════════════════════════════════════════════════════════════════


class Crawl4AIScraper(BaseScraper):
    """Async web scraper producing LLM-ready Markdown.

    Primary backend: crawl4ai (headless Chromium, clean Markdown output).
    Fallback backend: httpx + regex HTML-to-Markdown (no JS rendering).

    The scraper selects the backend based on:
    1. FDE_CRAWL4AI_BACKEND env var (explicit override)
    2. Whether crawl4ai is importable

    Usage:
        scraper = Crawl4AIScraper()
        items = await scraper.fetch(config)
    """

    source_type = SourceType.CRAWL4AI

    def __init__(
        self,
        timeout: float = 60.0,
        max_retries: int = 2,
    ) -> None:
        self._timeout = timeout
        self._max_retries = max_retries
        import os

        env_backend = os.environ.get("FDE_CRAWL4AI_BACKEND", "").lower()
        if env_backend in ("crawl4ai", "fallback"):
            self._use_crawl4ai = env_backend == "crawl4ai" and _HAS_CRAWL4AI
        else:
            self._use_crawl4ai = _HAS_CRAWL4AI

    async def fetch(self, config: SourceConfig) -> list[CollectedItem]:
        """Fetch a URL and return LLM-ready Markdown items.

        Args:
            config: Source config with target URL. The URL should be
                a direct web page URL (not an RSS feed).

        Returns:
            List with a single CollectedItem containing Markdown content.

        Raises:
            ScrapingError: If fetch fails after retries.
        """
        if self._use_crawl4ai:
            try:
                return await self._fetch_crawl4ai(config)
            except (RuntimeError, OSError, ImportError) as e:
                logger.warning(
                    "crawl4ai backend failed (%s), falling back to HTTP", e
                )
                self._use_crawl4ai = False

        return await self._fetch_fallback(config)

    async def _fetch_crawl4ai(self, config: SourceConfig) -> list[CollectedItem]:
        """Fetch using crawl4ai AsyncWebCrawler."""
        browser_config = BrowserConfig(
            headless=True,
            verbose=False,
        )
        run_config = CrawlerRunConfig(
            word_count_threshold=50,
            exclude_external_links=True,
            remove_overlay_elements=True,
        )

        try:
            async with AsyncWebCrawler(config=browser_config) as crawler:
                result = await crawler.arun(
                    url=config.url,
                    config=run_config,
                )
        except (RuntimeError, OSError) as e:
            raise ScrapingError(f"crawl4ai fetch failed: {e}") from e

        if not result.success:
            raise ScrapingError(
                f"crawl4ai returned error: {getattr(result, 'error_message', 'unknown')}"
            )

        # crawl4ai returns Markdown in result.markdown
        markdown_content: str = getattr(result, "markdown", "") or ""
        if not markdown_content:
            logger.warning("crawl4ai returned empty markdown for %s", config.url)
            return []

        title = getattr(result, "metadata", {}).get("title", "") or ""

        # Truncate to max_items * ~2KB per item, or just cap at reasonable length
        max_chars = max(config.max_items * 2000, 10000)
        if len(markdown_content) > max_chars:
            markdown_content = markdown_content[:max_chars] + "\n\n[... truncated ...]"

        item = CollectedItem(
            source=SourceType.CRAWL4AI,
            source_url=config.url,
            title=title,
            content=markdown_content,
            raw_html=getattr(result, "html", None),
            metadata={
                "backend": "crawl4ai",
                "links_count": len(getattr(result, "links", {})),
                "media_count": len(getattr(result, "media", {})),
            },
        )
        logger.info("Crawl4AIScraper (crawl4ai): extracted 1 item from %s", config.url)
        return [item]

    async def _fetch_fallback(self, config: SourceConfig) -> list[CollectedItem]:
        """Fallback: use httpx + regex HTML-to-Markdown."""
        import httpx

        headers = {
            "User-Agent": (
                "Mozilla/5.0 (compatible; FDE-Intelligence/1.0; "
                "+https://github.com/FDE-AI)"
            ),
            **config.headers,
        }

        async with httpx.AsyncClient(
            timeout=self._timeout,
            headers=headers,
            follow_redirects=True,
        ) as client:
            try:
                response = await client.get(config.url)
                response.raise_for_status()
            except (
                httpx.HTTPStatusError,
                httpx.RequestError,
                httpx.TimeoutException,
            ) as e:
                logger.error("crawl4ai fallback fetch failed for %s: %s", config.url, e)
                raise ScrapingError(f"HTTP fetch failed: {e}") from e

        html = response.text
        title = _extract_title(html)
        markdown = _html_to_markdown(html)

        if not markdown:
            logger.warning("Fallback produced empty markdown for %s", config.url)
            return []

        # Split very long content into multiple items if max_items > 1
        max_chars = max(config.max_items * 2000, 10000)
        if len(markdown) > max_chars:
            markdown = markdown[:max_chars] + "\n\n[... truncated ...]"

        item = CollectedItem(
            source=SourceType.CRAWL4AI,
            source_url=config.url,
            title=title,
            content=markdown,
            raw_html=html,
            metadata={
                "backend": "fallback-http",
                "status_code": response.status_code,
                "content_type": response.headers.get("content-type", ""),
            },
        )
        logger.info("Crawl4AIScraper (fallback): extracted 1 item from %s", config.url)
        return [item]
