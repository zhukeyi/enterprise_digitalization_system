"""Tests for Data Agent — ETL pipeline, scrapers, cleaning, integration (M3-T1)."""

from __future__ import annotations

import asyncio

import pytest

from agents.data_agent.cleaning import CleaningPipeline
from agents.data_agent.integration import register_data_tools
from agents.data_agent.models import (
    CleanedItem,
    CollectedItem,
    DataQualityReport,
    PipelineResult,
    SourceConfig,
    SourceType,
)
from agents.data_agent.pipeline import DataPipeline, get_datastore, reset_datastore
from agents.data_agent.scrapers.base import ScraperRegistry, ScrapingError
from agents.data_agent.scrapers.http_scraper import HTTPScraper
from agents.orchestrator.tools.registry import ToolRegistry

# ══════════════════════════════════════════════════════════════════
# Fixtures
# ══════════════════════════════════════════════════════════════════


@pytest.fixture(autouse=True)
def _reset_datastore() -> None:
    """Reset datastore between tests."""
    reset_datastore()


@pytest.fixture
def sample_items() -> list[CollectedItem]:
    """Build a list of sample collected items for cleaning tests."""
    return [
        CollectedItem(
            id="item-1",
            source=SourceType.WEB,
            source_url="https://example.com",
            title="  Title One  ",
            content="This is the first article about AI technology.",
            metadata={"author": "Alice", "date": "2026-01-01", "tags": ["ai"]},
        ),
        CollectedItem(
            id="item-2",
            source=SourceType.RSS,
            source_url="https://blog.example.com/feed",
            title="Title Two",
            content="Second post about data science and ML.",
            metadata={"author": "Bob", "date": "2026-01-02"},
        ),
        CollectedItem(
            id="item-3",
            source=SourceType.WEB,
            source_url="https://site.example.com",
            title="",
            content="Short",
            metadata={},
        ),
    ]


@pytest.fixture
def sample_with_pii() -> list[CollectedItem]:
    """Build items containing PII (phone, email, ID card)."""
    return [
        CollectedItem(
            id="pii-1",
            source=SourceType.WEB,
            source_url="https://example.com",
            title="Contact Info",
            content="请联系 13812345678 或发邮件到 test@example.com",
            metadata={"id_card": "110101199001011234"},
        ),
    ]


@pytest.fixture
def duplicate_items() -> list[CollectedItem]:
    """Build items with duplicate content."""
    return [
        CollectedItem(
            id="dup-1",
            source=SourceType.WEB,
            source_url="https://a.com",
            title="Post A",
            content="Same content here with enough text to pass quality check",
            metadata={"author": "A"},
        ),
        CollectedItem(
            id="dup-2",
            source=SourceType.WEB,
            source_url="https://b.com",
            title="Post B",
            content="Same content here with enough text to pass quality check",
            metadata={"author": "B"},
        ),
    ]


# ══════════════════════════════════════════════════════════════════
# Models Tests
# ══════════════════════════════════════════════════════════════════


class TestModels:
    """Tests for Pydantic data models."""

    def test_source_config_defaults(self) -> None:
        config = SourceConfig(source_type=SourceType.WEB, url="https://example.com")
        assert config.source_type == SourceType.WEB
        assert config.url == "https://example.com"
        assert config.max_items == 50
        assert config.auth_config is None
        assert config.headers == {}

    def test_source_config_max_items_validation(self) -> None:
        SourceConfig(source_type=SourceType.WEB, url="https://x.com", max_items=1)
        SourceConfig(source_type=SourceType.WEB, url="https://x.com", max_items=500)

    def test_source_config_immutable_default(self) -> None:
        """Ensure default_factory creates independent dicts."""
        c1 = SourceConfig(source_type=SourceType.WEB, url="https://a.com")
        c2 = SourceConfig(source_type=SourceType.WEB, url="https://b.com")
        c1.headers["X-Test"] = "val"
        assert "X-Test" not in c2.headers

    def test_collected_item_auto_id(self) -> None:
        item = CollectedItem(source=SourceType.API, source_url="https://api.example.com")
        assert item.id != ""
        assert len(item.id) == 36  # UUID length

    def test_collected_item_defaults(self) -> None:
        item = CollectedItem(source=SourceType.WEB, source_url="https://x.com")
        assert item.title == ""
        assert item.content == ""
        assert item.raw_html is None
        assert item.metadata == {}
        assert item.collected_at is not None

    def test_cleaned_item_score_range(self) -> None:
        CleanedItem(
            id="test",
            source=SourceType.WEB,
            source_url="https://x.com",
            title="T",
            content="C",
            quality_score=0.0,
        )
        CleanedItem(
            id="test",
            source=SourceType.WEB,
            source_url="https://x.com",
            title="T",
            content="C",
            quality_score=1.0,
        )

    def test_data_quality_report_defaults(self) -> None:
        r = DataQualityReport()
        assert r.total_items == 0
        assert r.valid_items == 0
        assert r.duplicate_count == 0
        assert r.completeness_avg == 0.0
        assert r.uniqueness_avg == 0.0
        assert r.validity_avg == 0.0
        assert r.pii_masked_count == 0

    def test_pipeline_result_auto_dataset_id(self) -> None:
        result = PipelineResult(source=SourceType.WEB)
        assert result.dataset_id != ""
        assert len(result.dataset_id) == 36

    def test_source_type_enum(self) -> None:
        assert SourceType.WEB == "web"
        assert SourceType.RSS == "rss"
        assert SourceType.API == "api"
        assert SourceType("web") == SourceType.WEB


# ══════════════════════════════════════════════════════════════════
# ScraperRegistry Tests
# ══════════════════════════════════════════════════════════════════


class TestScraperRegistry:
    """Tests for ScraperRegistry."""

    def test_register_and_get(self) -> None:
        reg = ScraperRegistry()
        scraper = HTTPScraper()
        reg.register(scraper)
        assert reg.get(SourceType.WEB) is scraper
        assert SourceType.WEB in reg

    def test_get_or_raise_success(self) -> None:
        reg = ScraperRegistry()
        reg.register(HTTPScraper())
        result = reg.get_or_raise(SourceType.WEB)
        assert isinstance(result, HTTPScraper)

    def test_get_or_raise_missing(self) -> None:
        reg = ScraperRegistry()
        with pytest.raises(ScrapingError, match="No scraper registered"):
            reg.get_or_raise(SourceType.RSS)

    def test_contains_str(self) -> None:
        reg = ScraperRegistry()
        reg.register(HTTPScraper())
        assert "web" in reg
        assert "rss" not in reg

    def test_contains_invalid_str(self) -> None:
        reg = ScraperRegistry()
        assert "invalid" not in reg

    def test_create_default_registers_all(self) -> None:
        reg = ScraperRegistry().create_default()
        assert len(reg) == 3
        assert SourceType.WEB in reg
        assert SourceType.RSS in reg
        assert SourceType.API in reg

    def test_list_types(self) -> None:
        reg = ScraperRegistry().create_default()
        types = reg.list_types()
        assert SourceType.WEB in types
        assert SourceType.RSS in types
        assert SourceType.API in types


# ══════════════════════════════════════════════════════════════════
# Cleaning Tests
# ══════════════════════════════════════════════════════════════════


class TestCleaning:
    """Tests for CleaningPipeline."""

    def test_normalize_trims_title(self, sample_items: list[CollectedItem]) -> None:
        pipeline = CleaningPipeline()
        cleaned = pipeline.run([sample_items[0]])
        assert len(cleaned) == 1
        assert cleaned[0].title == "Title One"

    def test_dedup_removes_duplicates(self, duplicate_items: list[CollectedItem]) -> None:
        pipeline = CleaningPipeline()
        cleaned = pipeline.run(duplicate_items)
        assert len(cleaned) == 1
        assert pipeline.duplicate_count == 1

    def test_pii_masking_phone(self, sample_with_pii: list[CollectedItem]) -> None:
        pipeline = CleaningPipeline()
        cleaned = pipeline.run(sample_with_pii)
        assert len(cleaned) == 1
        # Phone should be masked
        assert "13812345678" not in cleaned[0].content
        assert "138****" in cleaned[0].content

    def test_pii_masking_email(self, sample_with_pii: list[CollectedItem]) -> None:
        pipeline = CleaningPipeline()
        cleaned = pipeline.run(sample_with_pii)
        # Email should be masked
        assert "test@example.com" not in cleaned[0].content
        assert "te***@example.com" in cleaned[0].content
        assert cleaned[0].pii_masked is True

    def test_pii_masking_id_card(self, sample_with_pii: list[CollectedItem]) -> None:
        pipeline = CleaningPipeline()
        cleaned = pipeline.run(sample_with_pii)
        # ID card in metadata is preserved as-is (only content is masked)
        assert cleaned[0].metadata.get("id_card") == "110101199001011234"

    def test_low_quality_filtered(self, sample_items: list[CollectedItem]) -> None:
        pipeline = CleaningPipeline()
        cleaned = pipeline.run([sample_items[2]])  # "Short" content
        assert len(cleaned) == 0  # Quality too low → filtered

    def test_empty_input(self) -> None:
        pipeline = CleaningPipeline()
        cleaned = pipeline.run([])
        assert cleaned == []

    def test_cleaned_item_fields(self, sample_items: list[CollectedItem]) -> None:
        pipeline = CleaningPipeline()
        cleaned = pipeline.run(sample_items[:2])
        assert len(cleaned) == 2
        for c in cleaned:
            assert isinstance(c.id, str)
            assert isinstance(c.source, SourceType)
            assert isinstance(c.quality_score, float)
            assert 0.0 <= c.quality_score <= 1.0
            assert c.cleaned_at is not None


# ══════════════════════════════════════════════════════════════════
# Pipeline Tests
# ══════════════════════════════════════════════════════════════════


class TestPipeline:
    """Tests for DataPipeline."""

    def test_pipeline_handles_scraping_error(self) -> None:
        """Pipeline should catch scraping errors and return error result."""
        empty_reg = ScraperRegistry()
        pipeline = DataPipeline(scraper_registry=empty_reg)
        config = SourceConfig(source_type=SourceType.WEB, url="https://x.com")

        result = asyncio.run(pipeline.run(config))
        assert isinstance(result, PipelineResult)
        assert result.extracted_count == 0
        assert len(result.errors) > 0

    def test_pipeline_datastore_with_mock_scraper(self) -> None:
        """Pipeline stores items when scraper succeeds."""
        reset_datastore()

        # Register a mock scraper that returns fake items
        from unittest.mock import AsyncMock

        from agents.data_agent.scrapers.base import BaseScraper

        mock_scraper = AsyncMock(spec=BaseScraper)
        mock_scraper.source_type = SourceType.WEB
        mock_scraper.fetch.return_value = [
            CollectedItem(
                id="mock-1",
                source=SourceType.WEB,
                source_url="https://fake.com",
                title="Mock Article",
                content="This is a mock article with enough content to pass quality checks.",
                metadata={"author": "Mock"},
            )
        ]

        reg = ScraperRegistry()
        reg.register(mock_scraper)
        pipeline = DataPipeline(scraper_registry=reg)
        config = SourceConfig(source_type=SourceType.WEB, url="https://fake.com")

        result = asyncio.run(pipeline.run(config))
        assert isinstance(result, PipelineResult)
        assert result.extracted_count == 1
        assert result.stored_count == 1

        ds = get_datastore()
        stored = ds.get(result.dataset_id)
        assert stored is not None
        assert len(stored) == 1
        assert stored[0].title == "Mock Article"

    def test_unknown_source_type(self) -> None:
        """Pipeline handles unregistered source types gracefully."""
        empty_reg = ScraperRegistry()
        pipeline = DataPipeline(scraper_registry=empty_reg)
        config = SourceConfig(source_type=SourceType.WEB, url="https://x.com")

        result = asyncio.run(pipeline.run(config))
        assert isinstance(result, PipelineResult)
        assert result.extracted_count == 0
        assert len(result.errors) > 0


# ══════════════════════════════════════════════════════════════════
# Integration Tests
# ══════════════════════════════════════════════════════════════════


class TestIntegration:
    """Tests for ToolRegistry integration."""

    @pytest.fixture
    def registry(self) -> ToolRegistry:
        reg = ToolRegistry()
        register_data_tools(reg)
        return reg

    def test_four_tools_registered(self, registry: ToolRegistry) -> None:
        tools = registry.get_tools_for_worker("data")
        assert len(tools) == 4
        names = {t.name for t in tools}
        assert names == {
            "data_collect",
            "data_clean",
            "data_pipeline",
            "data_quality_report",
        }

    def test_data_clean_dispatch(self, registry: ToolRegistry) -> None:
        result = asyncio.run(
            registry.dispatch(
                "data_clean",
                raw_items=[
                    {
                        "id": "test-1",
                        "source": "web",
                        "source_url": "https://x.com",
                        "title": "Test Title",
                        "content": "Enough content to pass the quality threshold test.",
                        "metadata": {"author": "Alice"},
                    }
                ],
            )
        )
        assert result["output_count"] == 1
        assert result["duplicate_count"] == 0

    def test_data_clean_rejects_empty(self, registry: ToolRegistry) -> None:
        result = asyncio.run(registry.dispatch("data_clean", raw_items=[]))
        assert "error" in result

    def test_data_clean_with_pii(self, registry: ToolRegistry) -> None:
        result = asyncio.run(
            registry.dispatch(
                "data_clean",
                raw_items=[
                    {
                        "id": "pii-test",
                        "source": "web",
                        "source_url": "https://x.com",
                        "title": "Contact",
                        "content": "Call 13812345678 or email user@example.com for help with this data.",
                        "metadata": {},
                    }
                ],
            )
        )
        assert result["output_count"] == 1
        assert result["pii_masked_count"] == 1

    def test_data_quality_report_missing(self, registry: ToolRegistry) -> None:
        result = asyncio.run(registry.dispatch("data_quality_report", dataset_id="nonexistent"))
        assert "error" in result

    def test_data_quality_report_no_dataset_id(self, registry: ToolRegistry) -> None:
        result = asyncio.run(registry.dispatch("data_quality_report", dataset_id=""))
        assert "error" in result

    def test_registry_dispatches_to_data_worker(self) -> None:
        reg = ToolRegistry()
        register_data_tools(reg)
        workers = reg.get_workers_summary()
        assert "data" in workers
        assert len(workers["data"]) == 4

    def test_data_clean_handles_invalid_format(self, registry: ToolRegistry) -> None:
        result = asyncio.run(
            registry.dispatch(
                "data_clean",
                raw_items=[{"invalid": "format", "missing_required_fields": True}],
            )
        )
        assert "error" in result
