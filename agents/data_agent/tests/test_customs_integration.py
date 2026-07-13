"""Integration tests for the customs data base (P1-C, C-7).

Exercises the full adapter → store → API pipeline and the compliance linkage
(sanctions screening + enterprise outreach gate) that protects the GEO
marketing use case. No network: UN Comtrade is served via ``httpx.MockTransport``.
"""

from __future__ import annotations

import asyncio

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from agents.data_agent import customs_router, customs_store
from agents.data_agent.compliance_guard import (
    OutreachComplianceGate,
    SanctionsGuard,
    append_unsubscribe_footer,
    enterprise_outreach_allowed,
    screen_sanctions,
)
from agents.data_agent.customs_models import DataSourceTier
from agents.data_agent.customs_store import CustomsStore
from agents.data_agent.models import SourceConfig, SourceType
from agents.data_agent.scrapers.customs_scraper import CustomsScraper


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
                    }
                ]
            },
        )

    return httpx.MockTransport(handler)


def _bol_transport() -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "data": [
                    {
                        "consignee": "Acme Importers Inc.",
                        "hs_code": "8517.62",
                        "port_of_discharge": "Los Angeles, US",
                        "weight_kg": 1200,
                        "arrival_date": "2023-05-01",
                    },
                    {
                        "buyer": "Acme Importers Inc",
                        "hs": "8517",
                        "discharge_port": "Los Angeles",
                        "gross_weight": 800,
                        "arrival_date": "2023-06-15",
                    },
                ]
            },
        )

    return httpx.MockTransport(handler)


@pytest.fixture
def store() -> CustomsStore:
    return CustomsStore(db_path=":memory:")


@pytest.fixture
def api_client(store: CustomsStore, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    # Point the process-wide singleton at an isolated in-memory store.
    monkeypatch.setattr(customs_store, "_store_singleton", store)
    app = FastAPI()
    app.include_router(customs_router.router)
    return TestClient(app)


def _comtrade_config() -> SourceConfig:
    return SourceConfig(
        source_type=SourceType.CUSTOMS,
        url="https://comtradeapi.un.org/public/v1/get/HS",
        metadata={"provider": "un_comtrade", "reporter": "842", "year": "2023"},
    )


# ── Adapter → store → query pipeline ──────────────────────────────


async def test_scraper_to_store_pipeline(store: CustomsStore) -> None:
    scraper = CustomsScraper(transport=_comtrade_transport())
    result = await scraper.fetch_records(_comtrade_config())
    assert result.tier == DataSourceTier.TIER1
    assert len(result.trade_records) == 1

    stored = await store.upsert_trade_records(result.trade_records)
    assert stored == 1

    rows = await store.search(hs_code="8517")
    assert len(rows) == 1
    assert rows[0].reporter_country == "United States"
    assert rows[0].partner_country == "China"

    trend = await store.trend(hs_code="8517")
    assert trend and trend[0]["value_usd"] == 12345678

    assert await store.count_trade_records() == 1


async def test_bol_to_buyer_entity_pipeline(store: CustomsStore) -> None:
    scraper = CustomsScraper(transport=_bol_transport())
    config = SourceConfig(
        source_type=SourceType.CUSTOMS,
        url="https://importyeti.com/api",
        metadata={"provider": "importyeti"},
    )
    result = await scraper.fetch_records(config)
    assert result.tier == DataSourceTier.TIER2
    # Two rows, same consignee → one aggregated buyer entity (no raw BOL retained).
    assert len(result.buyers) == 1
    assert result.buyers[0].import_count == 2

    stored = await store.upsert_buyers(result.buyers)
    assert stored == 1
    top = await store.top_buyers()
    assert len(top) == 1
    assert top[0].normalized_name == "acme importers"
    assert await store.count_buyers() == 1


# ── HTTP API surface ──────────────────────────────────────────────


def test_api_trade_records_and_trends(api_client: TestClient, store: CustomsStore) -> None:
    scraper = CustomsScraper(transport=_comtrade_transport())
    result = asyncio.run(scraper.fetch_records(_comtrade_config()))
    asyncio.run(store.upsert_trade_records(result.trade_records))

    resp = api_client.get("/api/customs/trade-records", params={"hs_code": "8517"})
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["reporter_country"] == "United States"

    trend_resp = api_client.get("/api/customs/trends", params={"hs_code": "8517"})
    assert trend_resp.status_code == 200
    assert trend_resp.json()[0]["value_usd"] == 12345678


def test_api_overview_counts(api_client: TestClient, store: CustomsStore) -> None:
    scraper = CustomsScraper(transport=_comtrade_transport())
    result = asyncio.run(scraper.fetch_records(_comtrade_config()))
    asyncio.run(store.upsert_trade_records(result.trade_records))

    resp = api_client.get("/api/customs/overview")
    assert resp.status_code == 200
    assert resp.json()["trade_record_count"] == 1
    assert resp.json()["tier1_available"] is True


def test_api_buyers_endpoint(api_client: TestClient, store: CustomsStore) -> None:
    scraper = CustomsScraper(transport=_bol_transport())
    config = SourceConfig(
        source_type=SourceType.CUSTOMS,
        url="https://importyeti.com/api",
        metadata={"provider": "importyeti"},
    )
    result = asyncio.run(scraper.fetch_records(config))
    asyncio.run(store.upsert_buyers(result.buyers))

    resp = api_client.get("/api/customs/buyers")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["normalized_name"] == "acme importers"
    # Raw BOL fields (consignee/shipper) must NOT be present in the derivative.
    assert "consignee" not in data[0]
    assert "shipper" not in data[0]


# ── Compliance linkage (red lines R1/R2/R3) ───────────────────────


def test_compliance_sanctions_blocks_denied_buyer() -> None:
    guard = SanctionsGuard(
        denylist=[{"name": "Bad Imports LLC", "list_name": "TEST", "aliases": []}]
    )
    hit = guard.screen("Bad Imports LLC", "RU")
    assert hit.blocked is True
    ok = guard.screen("Good Buyer Inc", "US")
    assert ok.blocked is False


def test_compliance_enterprise_outreach_gate() -> None:
    gate = OutreachComplianceGate()
    # Free mailbox → denied (privacy red line).
    denied = gate.evaluate(
        buyer_name="Acme", country="US", email="buyer@gmail.com", consent=True
    )
    assert denied.allowed is False
    # Enterprise channel + consent + unsubscribe → allowed.
    allowed = gate.evaluate(
        buyer_name="Acme",
        country="US",
        email="buyer@acme-corp.com",
        consent=True,
        unsubscribe_url="https://acme.example.com/unsub",
    )
    assert allowed.allowed is True


def test_compliance_helper_functions() -> None:
    # Convenience singleton screen.
    assert screen_sanctions("SANCTIONED SAMPLE CORP").blocked is True
    # Enterprise channel helper.
    assert enterprise_outreach_allowed("buyer@corp.com", consent=True) is True
    assert enterprise_outreach_allowed("buyer@gmail.com", consent=True) is False
    assert enterprise_outreach_allowed(None, consent=False) is False
    # Unsubscribe footer present.
    footer = append_unsubscribe_footer("Hi", "https://x/unsub")
    assert "unsubscribe" in footer.lower()
