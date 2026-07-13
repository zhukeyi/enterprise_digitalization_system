"""Tests for the customs scraper (P1-C C-2 / C-3)."""

from __future__ import annotations

import httpx
import pytest

from agents.data_agent.customs_models import (
    DataSourceTier,
    TradeRecord,
    normalize_buyer_name,
    normalize_hs_code,
)
from agents.data_agent.models import SourceConfig, SourceType
from agents.data_agent.scrapers.base import ScrapingError
from agents.data_agent.scrapers.customs_scraper import CustomsScraper

# ── Fixtures ─────────────────────────────────────────────────────


def _comtrade_transport() -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "data": [
                    {
                        "cmdCode": "8517",
                        "cmdDesc": "Electrical apparatus for line telephony",
                        "rtTitle": "United States",
                        "ptTitle": "China",
                        "rgCode": 1,
                        "period": 2023,
                        "primaryValue": 12345678,
                        "qty": 1000,
                        "qtyUnitAbbr": "No",
                    },
                    {
                        "cmdCode": "85 . 17",  # messy code to test normalization
                        "cmdDesc": "Other telecom equipment",
                        "rtTitle": "United States",
                        "ptTitle": "Germany",
                        "rgCode": 1,
                        "period": 2023,
                        "primaryValue": 500,
                        "qty": 2,
                        "qtyUnitAbbr": "No",
                    },
                ]
            },
        )

    return httpx.MockTransport(handler)


# ── Normalization helpers ────────────────────────────────────────


class TestNormalization:
    def test_normalize_hs_code_strips_dots(self) -> None:
        assert normalize_hs_code("85 . 17") == "8517"
        assert normalize_hs_code(" 8517 ") == "8517"

    def test_normalize_buyer_name_strips_legal_forms(self) -> None:
        assert normalize_buyer_name("ACME, Inc.") == "acme"
        assert normalize_buyer_name("Globex Corp LLC") == "globex"
        assert normalize_buyer_name("Wayne Enterprises GmbH") == "wayne enterprises"


# ── Tier-1: UN Comtrade ─────────────────────────────────────────


class TestUnComtradeAdapter:
    async def test_fetch_records_normalizes(self) -> None:
        scraper = CustomsScraper(transport=_comtrade_transport())
        config = SourceConfig(
            source_type=SourceType.CUSTOMS,
            url="https://comtradeapi.un.org/public/v1/get/HS",
            max_items=50,
            metadata={"provider": "un_comtrade", "reporter": "842", "year": "2023"},
        )
        result = await scraper.fetch_records(config)
        assert result.tier == DataSourceTier.TIER1
        assert result.provider == "un_comtrade"
        assert len(result.trade_records) == 2

        first = result.trade_records[0]
        assert isinstance(first, TradeRecord)
        assert first.hs_code == "8517"
        assert first.reporter_country == "United States"
        assert first.partner_country == "China"
        assert first.value_usd == 12345678
        assert first.trade_flow.value == "import"
        # messy code normalized
        assert result.trade_records[1].hs_code == "8517"

    async def test_fetch_returns_collected_items(self) -> None:
        scraper = CustomsScraper(transport=_comtrade_transport())
        config = SourceConfig(
            source_type=SourceType.CUSTOMS,
            url="https://comtradeapi.un.org/public/v1/get/HS",
            max_items=50,
            metadata={"provider": "un_comtrade", "reporter": "842", "year": "2023"},
        )
        items = await scraper.fetch(config)
        assert len(items) == 2
        assert items[0].source == SourceType.CUSTOMS
        assert items[0].metadata["hs_code"] == "8517"
        assert items[0].metadata["tier"] == "tier1"

    async def test_unknown_provider_raises(self) -> None:
        scraper = CustomsScraper(transport=_comtrade_transport())
        config = SourceConfig(
            source_type=SourceType.CUSTOMS,
            url="https://example.com",
            metadata={"provider": "no_such_provider"},
        )
        with pytest.raises(ScrapingError):
            await scraper.fetch_records(config)


# ── Tier-2: BOL JSON parsing (no network) ───────────────────────


class TestBolJsonAdapter:
    def _shipments(self) -> list[dict]:
        return [
            {
                "shipper": "Shenzhen Maker Co",
                "consignee": "Acme Importers Inc.",
                "notify": "Acme Importers Inc.",
                "port_of_loading": "Shanghai, CN",
                "port_of_discharge": "Los Angeles, US",
                "hs_code": "8517.62",
                "description": "Smartphones",
                "weight_kg": 1200,
                "packages": 40,
                "country_of_origin": "CN",
                "arrival_date": "2023-05-01",
            },
            {
                "supplier": "Guangzhou Widget Ltd",
                "buyer": "Acme Importers Inc",  # alias + legal-form variant
                "discharge_port": "Los Angeles",
                "hs": "8517",
                "hs_description": "Phone parts",
                "gross_weight": 800,
                "arrival_date": "2023-06-15",
            },
            {
                "shipper": "Berlin Parts GmbH",
                "importer_name": "Globex Corp",
                "destination_port": "New York",
                "commodity_code": "8471",
                "goods": "Laptops",
                "weight": 500,
                "arrival_date": "2023-07-20",
            },
        ]

    def test_parse_bol_json(self) -> None:
        scraper = CustomsScraper()
        shipments = scraper._parse_bol_json(self._shipments(), "importyeti")
        assert len(shipments) == 3
        # alias mapping + normalization
        assert shipments[0].consignee == "Acme Importers Inc."
        assert shipments[0].hs_code == "851762"
        assert shipments[0].port_of_discharge == "los angeles us"
        assert shipments[1].consignee == "Acme Importers Inc"  # alias "buyer"
        assert shipments[1].hs_code == "8517"
        assert shipments[2].consignee == "Globex Corp"
        assert shipments[2].hs_code == "8471"

    def test_aggregate_buyers_dedupes(self) -> None:
        scraper = CustomsScraper()
        shipments = scraper._parse_bol_json(self._shipments(), "importyeti")
        buyers = scraper._aggregate_buyers(shipments)
        # Acme appears twice (Inc. / Inc, alias buyer) → one entity
        acme = [b for b in buyers if b.normalized_name == "acme importers"]
        assert len(acme) == 1
        assert acme[0].import_count == 2
        assert "8517" in acme[0].top_hs_codes
        assert "los angeles" in acme[0].top_ports
        # Globex separate
        assert any(b.normalized_name == "globex" for b in buyers)


# ── Tier-2: HTML parsing (reference fallback) ───────────────────


class TestBolHtmlAdapter:
    def _html_table(self) -> str:
        return """
        <html><body>
        <table>
          <tr><th>Shipper</th><th>Consignee</th><th>HS Code</th>
              <th>Port of Discharge</th><th>Weight</th><th>Arrival Date</th></tr>
          <tr><td>Shenzhen Maker</td><td>Acme Importers Inc.</td><td>8517</td>
              <td>Los Angeles</td><td>1200</td><td>2023-05-01</td></tr>
          <tr><td>Berlin Parts</td><td>Globex Corp</td><td>8471</td>
              <td>New York</td><td>500</td><td>2023-07-20</td></tr>
        </table>
        </body></html>
        """

    def test_parse_html_table(self) -> None:
        scraper = CustomsScraper()
        shipments = scraper._parse_bol_html_table(self._html_table(), "zauba")
        assert len(shipments) == 2
        assert shipments[0].consignee == "Acme Importers Inc."
        assert shipments[0].hs_code == "8517"
        assert shipments[1].consignee == "Globex Corp"

    def test_extract_json_from_next_data(self) -> None:
        html = (
            '<html><body><script id="__NEXT_DATA__" type="application/json">'
            '{"props":{"pageProps":{"shipments":['
            '{"consignee":"Acme Importers Inc.","hs_code":"8517","port_of_discharge":"LA"},'
            '{"buyer":"Globex Corp","hs":"8471"}]}}}'
            "</script></body></html>"
        )
        scraper = CustomsScraper()
        extracted = scraper._extract_json_from_html(html)
        assert len(extracted) == 2
        shipments = scraper._parse_bol_json(extracted, "importyeti")
        assert shipments[0].consignee == "Acme Importers Inc."


# ── Source-type guard ───────────────────────────────────────────


class TestSourceTypeGuard:
    async def test_wrong_source_type_rejected(self) -> None:
        scraper = CustomsScraper(transport=_comtrade_transport())
        config = SourceConfig(source_type=SourceType.API, url="https://x")
        with pytest.raises(ScrapingError):
            await scraper.fetch(config)
