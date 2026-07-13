"""Tests for the customs store and buyer vector index (P1-C C-4)."""

from __future__ import annotations

from agents.data_agent.customs_models import (
    BuyerEntity,
    DataSourceTier,
    TradeFlow,
    TradeRecord,
)
from agents.data_agent.customs_store import (
    CustomsStore,
    InMemoryBuyerVectorIndex,
)


def _sample_records() -> list[TradeRecord]:
    return [
        TradeRecord(
            hs_code="8517",
            hs_description="Telecom",
            reporter_country="United States",
            partner_country="China",
            port="",
            trade_flow=TradeFlow.IMPORT,
            value_usd=1000.0,
            quantity=10.0,
            quantity_unit="No",
            year=2022,
            period="2022",
            tier=DataSourceTier.TIER1,
            provider="un_comtrade",
        ),
        TradeRecord(
            hs_code="8517",
            hs_description="Telecom",
            reporter_country="United States",
            partner_country="China",
            port="",
            trade_flow=TradeFlow.IMPORT,
            value_usd=2000.0,
            quantity=20.0,
            quantity_unit="No",
            year=2023,
            period="2023",
            tier=DataSourceTier.TIER1,
            provider="un_comtrade",
        ),
        TradeRecord(
            hs_code="8471",
            hs_description="Computers",
            reporter_country="United States",
            partner_country="Germany",
            port="",
            trade_flow=TradeFlow.IMPORT,
            value_usd=500.0,
            quantity=5.0,
            quantity_unit="No",
            year=2023,
            period="2023",
            tier=DataSourceTier.TIER1,
            provider="un_comtrade",
        ),
    ]


def _sample_buyers() -> list[BuyerEntity]:
    return [
        BuyerEntity(
            raw_name="Acme Importers Inc.",
            normalized_name="acme importers",
            country="US",
            import_count=5,
            total_value_usd=1200.0,
            top_hs_codes=["8517", "8471"],
            top_ports=["los angeles"],
        ),
        BuyerEntity(
            raw_name="Globex Corp",
            normalized_name="globex corp",
            country="US",
            import_count=2,
            total_value_usd=400.0,
            top_hs_codes=["8471"],
            top_ports=["new york"],
        ),
    ]


class TestCustomsStore:
    async def test_upsert_and_search(self) -> None:
        store = CustomsStore(":memory:")
        await store.init()
        n = await store.upsert_trade_records(_sample_records())
        assert n == 3

        by_hs = await store.search(hs_code="8517")
        assert len(by_hs) == 2
        assert all(r.hs_code == "8517" for r in by_hs)

        by_partner = await store.search(partner_country="Germany")
        assert len(by_partner) == 1
        assert by_partner[0].hs_code == "8471"

        all_records = await store.search()
        assert len(all_records) == 3
        await store.close()

    async def test_trend_aggregation(self) -> None:
        store = CustomsStore(":memory:")
        await store.init()
        await store.upsert_trade_records(_sample_records())
        trend = await store.trend("8517", group_by="year")
        # 2022: 1000, 2023: 2000
        by_bucket = {t["bucket"]: t["value_usd"] for t in trend}
        assert by_bucket.get(2022) == 1000.0
        assert by_bucket.get(2023) == 2000.0
        total = sum(t["value_usd"] for t in trend)
        assert total == 3000.0
        await store.close()

    async def test_top_buyers(self) -> None:
        store = CustomsStore(":memory:")
        await store.init()
        await store.upsert_buyers(_sample_buyers())
        top = await store.top_buyers(limit=10)
        assert len(top) == 2
        # sorted by total_value_usd desc
        assert top[0].normalized_name == "acme importers"
        await store.close()

    async def test_buyer_aggregation_merge(self) -> None:
        store = CustomsStore(":memory:")
        await store.init()
        await store.upsert_buyers(_sample_buyers())
        # Re-upsert same buyers → counts should accumulate
        await store.upsert_buyers(_sample_buyers())
        top = await store.top_buyers(limit=10)
        acme = next(b for b in top if b.normalized_name == "acme importers")
        assert acme.import_count == 10  # 5 + 5
        assert acme.total_value_usd == 2400.0
        await store.close()


class TestInMemoryBuyerVectorIndex:
    def test_search_ranks_by_similarity(self) -> None:
        index = InMemoryBuyerVectorIndex()
        for b in _sample_buyers():
            index.add(b)
        results = index.search("acme importers 8517", top_k=2)
        assert results
        assert results[0][0].normalized_name == "acme importers"
        assert results[0][1] > 0.0
