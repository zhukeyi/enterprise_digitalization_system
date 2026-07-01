"""RSS feed scraper — async RSS/Atom feed parser (M3-T1).

Uses feedparser (sync) wrapped in run_in_executor for async usage.
Falls back to a minimal stdlib XML parser when feedparser is not installed.
"""

from __future__ import annotations

import asyncio
import logging
import re
from xml.etree.ElementTree import ParseError as XMLParseError
from xml.etree.ElementTree import fromstring

from agents.data_agent.models import CollectedItem, SourceConfig, SourceType
from agents.data_agent.scrapers.base import BaseScraper, ScrapingError

logger = logging.getLogger("fde.data.scrapers.rss")

__all__ = ["RSSScraper"]

# ══════════════════════════════════════════════════════════════════
# feedparser preferred, stdlib XML fallback
# ══════════════════════════════════════════════════════════════════

try:
    import feedparser

    _HAS_FEEDPARSER = True
except ImportError:
    _HAS_FEEDPARSER = False
    logger.debug("feedparser not installed, using stdlib XML fallback")

# RSS 2.0 / Atom XML namespaces
_RSS_NAMESPACES = {
    "atom": "http://www.w3.org/2005/Atom",
    "content": "http://purl.org/rss/1.0/modules/content/",
    "dc": "http://purl.org/dc/elements/1.1/",
}


def _parse_feed_feedparser(raw: str, max_items: int) -> list[dict[str, object]]:
    """Parse RSS/Atom feed using feedparser.

    Returns a list of dicts with keys: title, content, author, link, published, tags.
    """
    feed = feedparser.parse(raw)
    items: list[dict[str, object]] = []

    for entry in feed.entries[:max_items]:
        content = entry.get("summary", entry.get("description", ""))
        if not content:
            content = entry.get("content", [{}])[0].get("value", "") if entry.get("content") else ""

        tags = [t.get("term", "") for t in entry.get("tags", []) if t.get("term")]

        items.append({
            "title": entry.get("title", ""),
            "content": content,
            "author": entry.get("author", ""),
            "link": entry.get("link", ""),
            "published": entry.get("published", ""),
            "tags": tags,
        })

    return items


def _parse_feed_stdlib(raw: str, max_items: int) -> list[dict[str, object]]:
    """Parse RSS 2.0 / Atom feed using stdlib XML parser (fallback).

    Minimal implementation that handles the most common RSS/Atom structures.
    """
    items: list[dict[str, object]] = []

    try:
        root = fromstring(raw)
    except XMLParseError as e:
        raise ScrapingError(f"XML parse failed: {e}") from e

    # Detect feed type: RSS 2.0 (channel/item) or Atom (feed/entry)
    # Strip XML namespaces for simple matching
    tag_name = root.tag.split("}")[-1] if "}" in root.tag else root.tag

    if tag_name == "rss":
        # RSS 2.0: rss > channel > item
        channel = root.find("channel")
        if channel is None:
            return items
        entries = channel.findall("item")
    elif tag_name == "feed":
        # Atom: feed > entry
        entries = root.findall("entry")
    else:
        logger.warning("Unknown feed root tag: %s", tag_name)
        return items

    def _text(elem: object, path: str) -> str:
        """Safely get text from a child element."""
        if elem is None:
            return ""
        # Try with namespace-stripped path
        child = None
        for child_elem in elem:  # type: ignore[union-attr]
            child_tag = child_elem.tag.split("}")[-1] if "}" in child_elem.tag else child_elem.tag
            if child_tag == path:
                child = child_elem
                break
        return child.text.strip() if child is not None and child.text else ""

    for entry in entries[:max_items]:
        title = _text(entry, "title")
        content = _text(entry, "description") or _text(entry, "summary") or _text(entry, "content")
        author = _text(entry, "author") or _text(entry, "creator")
        link = _text(entry, "link")
        published = _text(entry, "pubDate") or _text(entry, "published") or _text(entry, "updated")

        items.append({
            "title": title,
            "content": content,
            "author": author,
            "link": link,
            "published": published,
            "tags": [],
        })

    return items


def _parse_feed(raw: str, max_items: int) -> list[dict[str, object]]:
    """Parse RSS/Atom feed, using feedparser if available, else stdlib."""
    if _HAS_FEEDPARSER:
        try:
            return _parse_feed_feedparser(raw, max_items)
        except (RuntimeError, ValueError, AttributeError, OSError) as e:
            logger.warning("feedparser failed (%s), falling back to stdlib", e)
    return _parse_feed_stdlib(raw, max_items)


# ══════════════════════════════════════════════════════════════════
# RSS Scraper
# ══════════════════════════════════════════════════════════════════


class RSSScraper(BaseScraper):
    """Async RSS/Atom feed scraper.

    Fetches the feed via httpx (async), then parses with feedparser
    (sync, wrapped in run_in_executor) or stdlib XML parser fallback.
    """

    source_type = SourceType.RSS

    def __init__(self, timeout: float = 30.0) -> None:
        self._timeout = timeout

    async def fetch(self, config: SourceConfig) -> list[CollectedItem]:
        """Fetch and parse an RSS/Atom feed.

        Args:
            config: Source config with feed URL.

        Returns:
            List of collected items from the feed.

        Raises:
            ScrapingError: If fetch or parse fails.
        """
        if config.source_type != SourceType.RSS:
            raise ScrapingError(
                f"RSSScraper received non-rss source type: {config.source_type}"
            )

        import httpx

        async with httpx.AsyncClient(
            timeout=self._timeout,
            headers=config.headers,
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
                logger.error("RSS fetch failed for %s: %s", config.url, e)
                raise ScrapingError(f"RSS fetch failed: {e}") from e

        # Parse feed (sync operation → run in executor)
        loop = asyncio.get_event_loop()
        try:
            parsed = await loop.run_in_executor(
                None, _parse_feed, response.text, config.max_items
            )
        except ScrapingError:
            raise
        except (RuntimeError, ValueError, XMLParseError, OSError) as e:
            raise ScrapingError(f"Feed parse failed: {e}") from e

        if not parsed:
            logger.warning("No entries found in feed: %s", config.url)

        items: list[CollectedItem] = []
        for entry in parsed:
            content = str(entry.get("content", ""))
            if not content:
                continue
            items.append(
                CollectedItem(
                    source=SourceType.RSS,
                    source_url=config.url,
                    title=str(entry.get("title", "")),
                    content=content,
                    raw_html=None,
                    metadata={
                        "author": str(entry.get("author", "")),
                        "link": str(entry.get("link", "")),
                        "published": str(entry.get("published", "")),
                        "tags": entry.get("tags", []),
                    },
                )
            )

        logger.info("RSSScraper: extracted %d items from %s", len(items), config.url)
        return items
