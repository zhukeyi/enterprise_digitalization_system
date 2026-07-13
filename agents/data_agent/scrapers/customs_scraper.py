"""Customs scraper — multi-provider adapter for the customs data base (P1-C).

Implements ``BaseScraper`` for ``SourceType.CUSTOMS`` and dispatches to a
provider selected via ``config.metadata["provider"]``:

* ``un_comtrade`` — Tier-1 UN Comtrade statistical API (HS / partner / value,
  **no buyer name**).
* ``importyeti`` — Tier-2 US bill-of-lading (consignee-level, free tier).
* ``zauba`` — Tier-2 India bill-of-lading (consignee-level, free tier).

Tier-2 adapters return ``BuyerEntity`` derivative profiles (never raw BOL rows)
to respect redistribution licensing (P1-C compliance red line #1).

Usage:
    registry = ScraperRegistry().create_default()
    scraper = registry.get(SourceType.CUSTOMS)
    config = SourceConfig(
        source_type=SourceType.CUSTOMS,
        url="https://comtradeapi.un.org/public/v1/get/HS",
        metadata={"provider": "un_comtrade", "reporter": "842", "year": "2023"},
    )
    result = await scraper.fetch_records(config)   # rich, normalized
    items = await scraper.fetch(config)            # pipeline-conformant CollectedItem
"""

from __future__ import annotations

import base64
import json
import logging
import re
from typing import Any

import httpx

from agents.data_agent.customs_models import (
    BolShipment,
    BuyerEntity,
    CustomsFetchResult,
    DataSourceTier,
    TradeFlow,
    TradeRecord,
    normalize_buyer_name,
    normalize_hs_code,
    normalize_port_name,
)
from agents.data_agent.models import CollectedItem, SourceConfig, SourceType
from agents.data_agent.scrapers.base import BaseScraper, ScrapingError

logger = logging.getLogger("fde.data.scrapers.customs")

# Provider id → internal handler name. Selected via config.metadata["provider"].
_TIER1_PROVIDERS = {"un_comtrade"}
_TIER2_PROVIDERS = {"importyeti", "zauba"}

# Field aliases for tolerant BOL JSON / HTML parsing (Tier-2).
_BOL_FIELD_ALIASES: dict[str, list[str]] = {
    "shipper": ["shipper", "supplier", "exporter", "exporter_name"],
    "consignee": ["consignee", "buyer", "importer", "importer_name"],
    "notify": ["notify", "notify_party"],
    "port_of_loading": ["port_of_loading", "loading_port", "load_port", "origin_port"],
    "port_of_discharge": ["port_of_discharge", "discharge_port", "destination_port"],
    "hs_code": ["hs_code", "hs", "commodity_code", "hs_code_raw"],
    "hs_description": ["hs_description", "description", "product_description", "goods"],
    "weight_kg": ["weight_kg", "weight", "gross_weight", "gross_weight_kg"],
    "quantity": ["quantity", "packages", "no_of_packages", "pkg_count"],
    "origin_country": ["origin_country", "country_of_origin", "origin"],
    "arrival_date": ["arrival_date", "date", "eta", "arrival"],
    "value_usd": ["value_usd", "cif_value", "fob_value", "value"],
}


__all__ = ["CustomsScraper"]


class CustomsScraper(BaseScraper):
    """Multi-provider customs data scraper (P1-C)."""

    source_type = SourceType.CUSTOMS

    def __init__(self, timeout: float = 30.0, max_pages: int = 20, transport: Any = None) -> None:
        """Initialize the customs scraper.

        Args:
            timeout: HTTP timeout in seconds.
            max_pages: Max pagination pages per fetch.
            transport: Optional ``httpx.AsyncBaseTransport`` (for tests via MockTransport).
        """
        self._timeout = timeout
        self._max_pages = max_pages
        self._transport = transport

    # ── Public API ──────────────────────────────────────────────

    async def fetch(self, config: SourceConfig) -> list[CollectedItem]:
        """Fetch customs data and return pipeline-conformant ``CollectedItem`` list.

        Args:
            config: Source config; ``metadata["provider"]`` selects the adapter.

        Returns:
            List of CollectedItem (one per trade record, or per buyer for Tier-2).

        Raises:
            ScrapingError: If the provider is unknown or the fetch fails.
        """
        if config.source_type != SourceType.CUSTOMS:
            raise ScrapingError(f"CustomsScraper received non-customs source: {config.source_type}")

        result = await self.fetch_records(config)
        items: list[CollectedItem] = []
        if result.tier == DataSourceTier.TIER1:
            for rec in result.trade_records:
                items.append(self._record_to_item(rec, config.url))
        else:
            for buyer in result.buyers:
                items.append(self._buyer_to_item(buyer, config.url))
        logger.info("CustomsScraper: produced %d CollectedItem(s) from %s", len(items), config.url)
        return items

    async def fetch_records(self, config: SourceConfig) -> CustomsFetchResult:
        """Fetch and normalize customs data into ``TradeRecord`` / ``BuyerEntity``.

        Args:
            config: Source config; ``metadata["provider"]`` selects the adapter.

        Returns:
            CustomsFetchResult with normalized records and (Tier-2) buyer entities.

        Raises:
            ScrapingError: If the provider is unknown or the fetch fails.
        """
        provider = (config.metadata or {}).get("provider", "un_comtrade")
        if provider not in _TIER1_PROVIDERS and provider not in _TIER2_PROVIDERS:
            raise ScrapingError(
                f"Unknown customs provider: {provider!r}. "
                f"Supported: {sorted(_TIER1_PROVIDERS | _TIER2_PROVIDERS)}"
            )

        tier = DataSourceTier.TIER2 if provider in _TIER2_PROVIDERS else DataSourceTier.TIER1
        headers = self._build_headers(config)

        async with httpx.AsyncClient(
            timeout=self._timeout,
            headers=headers,
            follow_redirects=True,
            transport=self._transport,
        ) as client:
            if provider == "un_comtrade":
                records = await self._fetch_un_comtrade(config, client)
                return CustomsFetchResult(provider=provider, tier=tier, trade_records=records)
            # Tier-2 BOL providers
            shipments = await self._fetch_bol(provider, config, client)
            buyers = self._aggregate_buyers(shipments)
            return CustomsFetchResult(
                provider=provider, tier=tier, trade_records=[], buyers=buyers
            )

    # ── Tier-1: UN Comtrade ─────────────────────────────────────

    async def _fetch_un_comtrade(
        self, config: SourceConfig, client: httpx.AsyncClient
    ) -> list[TradeRecord]:
        """Pull and normalize UN Comtrade HS statistical records."""
        meta = config.metadata or {}
        reporter = str(meta.get("reporter", "842"))  # default: United States
        partner = str(meta.get("partner", "all"))
        hs_code = str(meta.get("hsCode", "ALL"))
        year = str(meta.get("year", "2023"))
        rg = str(meta.get("rg", "1"))  # 1 = imports

        records: list[TradeRecord] = []
        page = 1
        while len(records) < config.max_items and page <= self._max_pages:
            params = {
                "freq": "A",
                "ps": year,
                "r": reporter,
                "p": partner,
                "px": "HS",
                "cc": hs_code,
                "rg": rg,
                "page": page,
            }
            try:
                response = await client.get(config.url, params=params)
                response.raise_for_status()
            except (httpx.HTTPStatusError, httpx.RequestError, httpx.TimeoutException) as e:
                if records:
                    logger.warning("UN Comtrade stopped at page %d: %s", page, e)
                    break
                raise ScrapingError(f"UN Comtrade fetch failed: {e}") from e

            data = response.json()
            rows = data.get("data") if isinstance(data, dict) else None
            if not rows:
                break
            for row in rows:
                if len(records) >= config.max_items:
                    break
                records.append(self._comtrade_row_to_record(row, rg))
            if len(rows) < 100:  # Comtrade page size is 100
                break
            page += 1

        logger.info("UN Comtrade: normalized %d records", len(records))
        return records

    @staticmethod
    def _comtrade_row_to_record(row: dict[str, Any], rg: str) -> TradeRecord:
        """Map a UN Comtrade data row to a normalized ``TradeRecord``."""
        code = normalize_hs_code(str(row.get("cmdCode", "")))
        rg_code = row.get("rgCode", rg)
        flow = TradeFlow.EXPORT if str(rg_code) == "2" else TradeFlow.IMPORT
        try:
            year = int(row.get("period", 0))
        except (TypeError, ValueError):
            year = 0
        unit = row.get("qtyUnitAbbr") or row.get("qtyUnitCode")
        try:
            qty = float(row["qty"]) if row.get("qty") not in (None, "") else None
        except (TypeError, ValueError):
            qty = None
        return TradeRecord(
            hs_code=code,
            hs_description=str(row.get("cmdDesc", "")),
            reporter_country=str(row.get("rtTitle", "")),
            partner_country=str(row.get("ptTitle", "")),
            port="",  # Port-level not provided by Comtrade aggregate API
            trade_flow=flow,
            value_usd=float(row.get("primaryValue", 0.0) or 0.0),
            quantity=qty,
            quantity_unit=str(unit) if unit is not None else None,
            year=year,
            period=str(row.get("period", "")),
            tier=DataSourceTier.TIER1,
            provider="un_comtrade",
        )

    # ── Tier-2: BOL (ImportYeti / Zauba) ────────────────────────

    async def _fetch_bol(
        self, provider: str, config: SourceConfig, client: httpx.AsyncClient
    ) -> list[BolShipment]:
        """Fetch and normalize Tier-2 bill-of-lading shipments."""
        try:
            response = await client.get(config.url, params=config.metadata or {})
            response.raise_for_status()
        except (httpx.HTTPStatusError, httpx.RequestError, httpx.TimeoutException) as e:
            raise ScrapingError(f"{provider} fetch failed: {e}") from e

        content_type = response.headers.get("content-type", "")
        if "json" in content_type or (config.url.endswith(".json")):
            try:
                payload = response.json()
            except (ValueError, TypeError) as e:
                raise ScrapingError(f"{provider} response is not valid JSON: {e}") from e
            rows = payload.get("data") if isinstance(payload, dict) else None
            if rows is None:
                rows = payload if isinstance(payload, list) else []
            return self._parse_bol_json(rows, provider)

        # HTML response — best-effort reference parser (free tiers embed JSON or tables)
        html = response.text
        extracted = self._extract_json_from_html(html)
        if extracted:
            return self._parse_bol_json(extracted, provider)
        return self._parse_bol_html_table(html, provider)

    @staticmethod
    def _parse_bol_json(rows: list[Any], provider: str) -> list[BolShipment]:
        """Map a list of BOL dicts (flexible keys) to ``BolShipment`` records."""
        shipments: list[BolShipment] = []
        for raw in rows:
            if not isinstance(raw, dict):
                continue
            kwargs: dict[str, Any] = {"provider": provider, "raw": raw}
            for field, aliases in _BOL_FIELD_ALIASES.items():
                value = None
                for alias in aliases:
                    if alias in raw and raw[alias] not in (None, ""):
                        value = raw[alias]
                        break
                if value is not None:
                    kwargs[field] = str(value)
            if kwargs.get("hs_code"):
                kwargs["hs_code"] = normalize_hs_code(kwargs["hs_code"])
            if kwargs.get("port_of_loading"):
                kwargs["port_of_loading"] = normalize_port_name(kwargs["port_of_loading"])
            if kwargs.get("port_of_discharge"):
                kwargs["port_of_discharge"] = normalize_port_name(kwargs["port_of_discharge"])
            if "weight_kg" in kwargs:
                try:
                    kwargs["weight_kg"] = float(kwargs["weight_kg"])
                except (TypeError, ValueError):
                    kwargs.pop("weight_kg", None)
            if "quantity" in kwargs:
                try:
                    kwargs["quantity"] = float(kwargs["quantity"])
                except (TypeError, ValueError):
                    kwargs.pop("quantity", None)
            if "value_usd" in kwargs:
                try:
                    kwargs["value_usd"] = float(kwargs["value_usd"])
                except (TypeError, ValueError):
                    kwargs.pop("value_usd", None)
            shipments.append(BolShipment(**kwargs))
        logger.info("%s: parsed %d BOL shipments from JSON", provider, len(shipments))
        return shipments

    @staticmethod
    def _extract_json_from_html(html: str) -> list[dict[str, Any]]:
        """Best-effort extraction of embedded JSON arrays from HTML."""
        # 1) Next.js / JSON-LD style script blobs
        candidates = re.findall(
            r"<script[^>]*id=[\"']__NEXT_DATA__[\"'][^>]*>(.*?)</script>",
            html,
            re.DOTALL | re.IGNORECASE,
        )
        for blob in candidates:
            try:
                obj = json.loads(blob)
            except (ValueError, TypeError):
                continue
            found = _deep_search_list(obj)
            if found:
                return found
        # 2) Any <script type="application/json"> blobs
        for blob in re.findall(
            r"<script[^>]*type=[\"']application/json[\"'][^>]*>(.*?)</script>",
            html,
            re.DOTALL | re.IGNORECASE,
        ):
            try:
                obj = json.loads(blob)
            except (ValueError, TypeError):
                continue
            found = _deep_search_list(obj)
            if found:
                return found
        return []

    @staticmethod
    def _parse_bol_html_table(html: str, provider: str) -> list[BolShipment]:
        """Fallback parser for HTML ``<table>`` BOL listings with header rows."""
        # Find a table whose headers contain shipping terms
        table_match = re.search(r"<table[^>]*>(.*?)</table>", html, re.DOTALL | re.IGNORECASE)
        if not table_match:
            return []
        table_html = table_match.group(1)
        headers = [
            h.strip().lower()
            for h in re.findall(r"<th[^>]*>(.*?)</th>", table_html, re.DOTALL | re.IGNORECASE)
        ]
        if not headers:
            return []
        # Map header index → canonical field
        index_map: dict[int, str] = {}
        for idx, header in enumerate(headers):
            for field, aliases in _BOL_FIELD_ALIASES.items():
                if any(alias.replace("_", " ") in header or alias in header for alias in aliases):
                    index_map[idx] = field
                    break
        shipments: list[BolShipment] = []
        for row_html in re.findall(r"<tr[^>]*>(.*?)</tr>", table_html, re.DOTALL | re.IGNORECASE):
            cells = re.findall(r"<td[^>]*>(.*?)</td>", row_html, re.DOTALL | re.IGNORECASE)
            if len(cells) < len(headers):
                continue
            raw: dict[str, Any] = {}
            for idx, field in index_map.items():
                if idx < len(cells):
                    raw[field] = re.sub(r"<[^>]+>", "", cells[idx]).strip()
            if not raw:
                continue
            kwargs: dict[str, Any] = {"provider": provider, "raw": raw}
            for field, value in raw.items():
                if field in _BOL_FIELD_ALIASES:
                    kwargs[field] = value
            if kwargs.get("hs_code"):
                kwargs["hs_code"] = normalize_hs_code(kwargs["hs_code"])
            shipments.append(BolShipment(**kwargs))
        logger.info("%s: parsed %d BOL shipments from HTML table", provider, len(shipments))
        return shipments

    @staticmethod
    def _aggregate_buyers(shipments: list[BolShipment]) -> list[BuyerEntity]:
        """Aggregate BOL shipments into derivative ``BuyerEntity`` profiles.

        Groups by normalized consignee name (+ country). Buyer-level raw rows are
        intentionally NOT retained — only aggregated footprint is delivered.
        """
        groups: dict[str, dict[str, Any]] = {}
        for s in shipments:
            name = s.consignee or s.notify
            if not name:
                continue
            key_name = normalize_buyer_name(name)
            if not key_name:
                continue
            key = key_name
            g = groups.setdefault(
                key,
                {
                    "raw_name": name,
                    "normalized_name": key_name,
                    "country": None,
                    "source_country": None,
                    "import_count": 0,
                    "total_value_usd": 0.0,
                    "hs_codes": {},
                    "ports": {},
                    "first_seen": s.arrival_date,
                    "last_seen": s.arrival_date,
                },
            )
            g["import_count"] += 1
            if s.weight_kg is not None:
                g["total_value_usd"] += s.weight_kg  # proxy when value absent
            if s.hs_code:
                g["hs_codes"][s.hs_code] = g["hs_codes"].get(s.hs_code, 0) + 1
            if s.port_of_discharge:
                g["ports"][s.port_of_discharge] = g["ports"].get(s.port_of_discharge, 0) + 1
            if s.arrival_date:
                g["first_seen"] = min(g["first_seen"] or s.arrival_date, s.arrival_date)
                g["last_seen"] = max(g["last_seen"] or s.arrival_date, s.arrival_date)

        buyers: list[BuyerEntity] = []
        for _key, g in groups.items():
            top_hs = sorted(g["hs_codes"], key=lambda k: g["hs_codes"][k], reverse=True)[:5]
            top_ports = sorted(g["ports"], key=lambda k: g["ports"][k], reverse=True)[:5]
            buyers.append(
                BuyerEntity(
                    raw_name=g["raw_name"],
                    normalized_name=g["normalized_name"],
                    country=g["country"],
                    source_country=g["source_country"],
                    import_count=g["import_count"],
                    total_value_usd=round(g["total_value_usd"], 2),
                    top_hs_codes=top_hs,
                    top_ports=top_ports,
                    first_seen=g["first_seen"],
                    last_seen=g["last_seen"],
                )
            )
        buyers.sort(key=lambda b: b.import_count, reverse=True)
        return buyers

    # ── Helpers ─────────────────────────────────────────────────

    def _build_headers(self, config: SourceConfig) -> dict[str, str]:
        """Build auth headers; supports bearer, api-key, basic, and Comtrade sub-key."""
        headers: dict[str, str] = dict(config.headers)
        auth = config.auth_config or {}
        if not auth:
            return headers
        bearer = auth.get("bearer_token")
        if bearer:
            headers["Authorization"] = f"Bearer {bearer}"
            return headers
        api_key = auth.get("api_key")
        if api_key:
            key_header = auth.get("api_key_header", "X-API-Key")
            headers[str(key_header)] = str(api_key)
            return headers
        sub_key = auth.get("subscription_key")
        if sub_key:
            headers["Ocp-Apim-Subscription-Key"] = str(sub_key)
            return headers
        basic = auth.get("basic_auth")
        if basic and isinstance(basic, dict):
            creds = base64.b64encode(
                f"{basic.get('username','')}:{basic.get('password','')}".encode()
            ).decode()
            headers["Authorization"] = f"Basic {creds}"
        return headers

    @staticmethod
    def _record_to_item(rec: TradeRecord, source_url: str) -> CollectedItem:
        """Convert a Tier-1 ``TradeRecord`` to a ``CollectedItem``."""
        title = f"{rec.hs_code} {rec.hs_description}".strip()
        content = (
            f"{rec.reporter_country} → {rec.partner_country} | "
            f"{rec.trade_flow.value} | ${rec.value_usd:,.0f} | {rec.period}"
        )
        return CollectedItem(
            source=SourceType.CUSTOMS,
            source_url=source_url,
            title=title,
            content=content,
            raw_html=None,
            metadata={
                "hs_code": rec.hs_code,
                "hs_description": rec.hs_description,
                "reporter_country": rec.reporter_country,
                "partner_country": rec.partner_country,
                "port": rec.port,
                "trade_flow": rec.trade_flow.value,
                "value_usd": rec.value_usd,
                "quantity": rec.quantity,
                "quantity_unit": rec.quantity_unit,
                "year": rec.year,
                "period": rec.period,
                "tier": rec.tier.value,
                "provider": rec.provider,
            },
        )

    @staticmethod
    def _buyer_to_item(buyer: BuyerEntity, source_url: str) -> CollectedItem:
        """Convert a Tier-2 ``BuyerEntity`` derivative to a ``CollectedItem``."""
        title = f"Buyer: {buyer.raw_name}"
        content = (
            f"Shipments: {buyer.import_count} | "
            f"Top HS: {', '.join(buyer.top_hs_codes) or 'n/a'} | "
            f"Top ports: {', '.join(buyer.top_ports) or 'n/a'}"
        )
        return CollectedItem(
            source=SourceType.CUSTOMS,
            source_url=source_url,
            title=title,
            content=content,
            raw_html=None,
            metadata={
                "normalized_name": buyer.normalized_name,
                "country": buyer.country,
                "source_country": buyer.source_country,
                "import_count": buyer.import_count,
                "total_value_usd": buyer.total_value_usd,
                "top_hs_codes": buyer.top_hs_codes,
                "top_ports": buyer.top_ports,
                "tier": DataSourceTier.TIER2.value,
            },
        )


# ── Internal utility ────────────────────────────────────────────


def _deep_search_list(obj: Any) -> list[dict[str, Any]]:
    """Recursively search a parsed JSON object for a list of dicts (BOL rows)."""
    if isinstance(obj, list):
        if obj and all(isinstance(x, dict) for x in obj):
            return [x for x in obj if isinstance(x, dict)]
        # Could be a list of lists — recurse one level
        for item in obj:
            found = _deep_search_list(item)
            if found:
                return found
        return []
    if isinstance(obj, dict):
        for value in obj.values():
            found = _deep_search_list(value)
            if found:
                return found
    return []
