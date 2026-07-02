"""REST API scraper — async REST API data collector (M3-T1).

Fetches data from REST API endpoints via httpx, with support for
Bearer token / API Key authentication and pagination.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from agents.data_agent.models import CollectedItem, SourceConfig, SourceType
from agents.data_agent.scrapers.base import BaseScraper, ScrapingError

logger = logging.getLogger("fde.data.scrapers.api")

__all__ = ["APIScraper"]

# ══════════════════════════════════════════════════════════════════
# API Scraper
# ══════════════════════════════════════════════════════════════════


class APIScraper(BaseScraper):
    """Async REST API data scraper.

    Fetches paginated JSON data from REST API endpoints.
    Supports Bearer token and API Key authentication via auth_config.

    auth_config options:
        - {"bearer_token": "..."} → Authorization: Bearer ...
        - {"api_key": "...", "api_key_header": "X-API-Key"} → custom header
        - {"basic_auth": {"username": "...", "password": "..."}} → Basic auth
    """

    source_type = SourceType.API

    def __init__(self, timeout: float = 30.0, max_pages: int = 20) -> None:
        self._timeout = timeout
        self._max_pages = max_pages

    async def fetch(self, config: SourceConfig) -> list[CollectedItem]:
        """Fetch data from a REST API endpoint.

        Args:
            config: Source config with API URL and auth.

        Returns:
            List of collected items from the API.

        Raises:
            ScrapingError: If API request fails.
        """
        if config.source_type != SourceType.API:
            raise ScrapingError(f"APIScraper received non-api source type: {config.source_type}")

        headers = self._build_headers(config)

        items: list[CollectedItem] = []
        page = 1

        async with httpx.AsyncClient(
            timeout=self._timeout,
            headers=headers,
            follow_redirects=True,
        ) as client:
            while len(items) < config.max_items and page <= self._max_pages:
                per_page = min(50, config.max_items - len(items))
                params = {"page": page, "per_page": per_page}

                try:
                    response = await client.get(config.url, params=params)
                    response.raise_for_status()
                except (
                    httpx.HTTPStatusError,
                    httpx.RequestError,
                    httpx.TimeoutException,
                ) as e:
                    if items:
                        logger.warning(
                            "API fetch stopped at page %d (error: %s), returning %d items",
                            page,
                            e,
                            len(items),
                        )
                        break
                    logger.error("API fetch failed for %s: %s", config.url, e)
                    raise ScrapingError(f"API fetch failed: {e}") from e

                try:
                    data = response.json()
                except (ValueError, TypeError) as e:
                    raise ScrapingError(f"API response is not valid JSON: {e}") from e

                records = self._extract_records(data)
                if not records:
                    break

                for record in records:
                    if len(items) >= config.max_items:
                        break
                    items.append(self._record_to_item(record, config.url))

                # Check if there are more pages
                total = self._extract_total(data)
                if total is not None and len(items) >= total:
                    break
                if len(records) < per_page:
                    break

                page += 1

        logger.info("APIScraper: extracted %d items from %s", len(items), config.url)
        return items

    def _build_headers(self, config: SourceConfig) -> dict[str, str]:
        """Build HTTP headers from config, including auth headers.

        Args:
            config: Source config with optional auth_config.

        Returns:
            Headers dict with auth applied.
        """
        headers = dict(config.headers)

        if not config.auth_config:
            return headers

        # Bearer token
        bearer = config.auth_config.get("bearer_token")
        if bearer:
            headers["Authorization"] = f"Bearer {bearer}"
            return headers

        # API Key in custom header
        api_key = config.auth_config.get("api_key")
        if api_key:
            key_header = config.auth_config.get("api_key_header", "X-API-Key")
            headers[str(key_header)] = str(api_key)
            return headers

        # Basic auth
        basic = config.auth_config.get("basic_auth")
        if basic and isinstance(basic, dict):
            username = str(basic.get("username", ""))
            password = str(basic.get("password", ""))
            # httpx supports basic auth via auth param, but we set header for simplicity
            import base64

            credentials = base64.b64encode(f"{username}:{password}".encode()).decode()
            headers["Authorization"] = f"Basic {credentials}"

        return headers

    def _extract_records(self, data: Any) -> list[dict[str, Any]]:
        """Extract the list of records from API response.

        Handles common API response shapes:
        - [...]
        - {"data": [...]}
        - {"results": [...]}
        - {"items": [...]}

        Args:
            data: Parsed JSON response.

        Returns:
            List of record dicts.
        """
        if isinstance(data, list):
            return [r for r in data if isinstance(r, dict)]
        if isinstance(data, dict):
            for key in ("data", "results", "items", "records"):
                val = data.get(key)
                if isinstance(val, list):
                    return [r for r in val if isinstance(r, dict)]
        return []

    def _extract_total(self, data: Any) -> int | None:
        """Extract total count from API response if available.

        Args:
            data: Parsed JSON response.

        Returns:
            Total count or None if not available.
        """
        if isinstance(data, dict):
            for key in ("total", "total_count", "count"):
                val = data.get(key)
                if isinstance(val, int):
                    return val
        return None

    def _record_to_item(self, record: dict[str, Any], source_url: str) -> CollectedItem:
        """Convert an API record to a CollectedItem.

        Tries common field names for title and content.

        Args:
            record: A single API record dict.
            source_url: The API endpoint URL.

        Returns:
            CollectedItem instance.
        """
        title = str(record.get("title") or record.get("name") or record.get("subject") or "")
        content = str(
            record.get("content")
            or record.get("description")
            or record.get("summary")
            or record.get("text")
            or ""
        )

        # Remove the fields we've already extracted to avoid duplication in metadata
        metadata = {
            k: v
            for k, v in record.items()
            if k not in ("title", "name", "subject", "content", "description", "summary", "text")
            and v is not None
        }

        return CollectedItem(
            source=SourceType.API,
            source_url=source_url,
            title=title,
            content=content,
            raw_html=None,
            metadata=metadata,
        )
