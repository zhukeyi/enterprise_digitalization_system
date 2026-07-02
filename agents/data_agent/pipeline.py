"""ETL pipeline orchestrator — extract → transform → load (M3-T1).

Orchestrates the full data pipeline:
  STAGE 1: EXTRACT — route to the correct scraper by SourceType
  STAGE 2: TRANSFORM — run CleaningPipeline (dedup/normalize/PII/quality)
  STAGE 3: LOAD — store into in-memory datastore, build quality report

Usage:
    pipeline = DataPipeline()
    result = await pipeline.run(config)
    print(result.dataset_id)
"""

from __future__ import annotations

import logging
import time

from agents.data_agent.cleaning import CleaningPipeline
from agents.data_agent.models import (
    CleanedItem,
    CollectedItem,
    DataQualityReport,
    PipelineResult,
    SourceConfig,
)
from agents.data_agent.scrapers.base import ScraperRegistry, ScrapingError

logger = logging.getLogger("fde.data.pipeline")

__all__ = ["DataPipeline", "get_datastore", "reset_datastore"]

# ══════════════════════════════════════════════════════════════════
# In-memory Datastore (M3: dict; M4: PostgreSQL)
# ══════════════════════════════════════════════════════════════════

_datastore: dict[str, list[CleanedItem]] = {}


def get_datastore() -> dict[str, list[CleanedItem]]:
    """Get the in-memory datastore (for testing and tool handlers)."""
    return _datastore


def reset_datastore() -> None:
    """Reset the in-memory datastore (for testing)."""
    _datastore.clear()


# ══════════════════════════════════════════════════════════════════
# DataPipeline
# ══════════════════════════════════════════════════════════════════


class DataPipeline:
    """Complete ETL pipeline orchestrator.

    Responsibilities:
    1. Route to the correct scraper based on config.source_type
    2. Run the CleaningPipeline on scraped items
    3. Store cleaned items and generate a quality report

    The pipeline handles errors gracefully: if EXTRACT fails, the
    result contains the error; TRANSFORM and LOAD are skipped.
    """

    def __init__(self, scraper_registry: ScraperRegistry | None = None) -> None:
        self._scrapers = scraper_registry or ScraperRegistry().create_default()

    async def run(self, config: SourceConfig) -> PipelineResult:
        """Execute the full ETL pipeline.

        Args:
            config: Source configuration (url, type, auth, max_items).

        Returns:
            PipelineResult with dataset_id, counts, quality report.
        """
        start = time.monotonic()
        errors: list[str] = []

        # ── STAGE 1: EXTRACT ──────────────────────────────
        try:
            raw_items = await self._extract(config)
        except (ValueError, RuntimeError, OSError, ScrapingError) as e:
            logger.error("EXTRACT failed: %s", e)
            return PipelineResult(
                source=config.source_type,
                extracted_count=0,
                cleaned_count=0,
                stored_count=0,
                quality_report=DataQualityReport(),
                duration_ms=int((time.monotonic() - start) * 1000),
                errors=[f"Extract failed: {e}"],
            )

        if not raw_items:
            logger.info("EXTRACT: 0 items from %s", config.url)
            return PipelineResult(
                source=config.source_type,
                extracted_count=0,
                cleaned_count=0,
                stored_count=0,
                quality_report=DataQualityReport(),
                duration_ms=int((time.monotonic() - start) * 1000),
            )

        logger.info("EXTRACT: %d items from %s", len(raw_items), config.url)

        # ── STAGE 2: TRANSFORM ────────────────────────────
        cleaning = CleaningPipeline()
        cleaned_items = cleaning.run(raw_items)
        logger.info(
            "TRANSFORM: %d → %d (duplicates: %d)",
            len(raw_items),
            len(cleaned_items),
            cleaning.duplicate_count,
        )

        # ── STAGE 3: LOAD ─────────────────────────────────
        from shared.utils.ids import new_uuid

        dataset_id = new_uuid()
        _datastore[dataset_id] = cleaned_items
        logger.info("LOAD: stored %d items as dataset %s", len(cleaned_items), dataset_id)

        # ── Quality Report ────────────────────────────────
        quality = self._build_quality_report(raw_items, cleaned_items, cleaning)

        return PipelineResult(
            dataset_id=dataset_id,
            source=config.source_type,
            extracted_count=len(raw_items),
            cleaned_count=len(cleaned_items),
            stored_count=len(cleaned_items),
            quality_report=quality,
            duration_ms=int((time.monotonic() - start) * 1000),
            errors=errors,
        )

    async def _extract(self, config: SourceConfig) -> list[CollectedItem]:
        """Route to the correct scraper and fetch data.

        Args:
            config: Source configuration.

        Returns:
            List of collected items.

        Raises:
            ValueError: If no scraper is registered for the source type.
        """
        scraper = self._scrapers.get_or_raise(config.source_type)
        return await scraper.fetch(config)

    def _build_quality_report(
        self,
        raw_items: list[CollectedItem],
        cleaned_items: list[CleanedItem],
        cleaning: CleaningPipeline,
    ) -> DataQualityReport:
        """Build a DataQualityReport from pipeline results.

        Args:
            raw_items: Items from EXTRACT stage.
            cleaned_items: Items after TRANSFORM stage.
            cleaning: The CleaningPipeline instance (for stats).

        Returns:
            DataQualityReport with completeness, uniqueness, validity scores.
        """
        if not cleaned_items:
            return DataQualityReport(
                total_items=len(raw_items),
                valid_items=0,
                duplicate_count=cleaning.duplicate_count,
                completeness_avg=0.0,
                uniqueness_avg=0.0,
                validity_avg=0.0,
                pii_masked_count=0,
            )

        total = len(raw_items) if raw_items else 1

        # Completeness: fraction of cleaned items with non-empty title and content
        completeness_avg = round(
            sum(1 for c in cleaned_items if c.title and c.content) / len(cleaned_items), 4
        )

        # Uniqueness: cleaned / raw ratio
        uniqueness_avg = round(len(cleaned_items) / max(total, 1), 4)

        # Validity: average quality score
        validity_avg = round(sum(c.quality_score for c in cleaned_items) / len(cleaned_items), 4)

        return DataQualityReport(
            total_items=len(raw_items),
            valid_items=len(cleaned_items),
            duplicate_count=cleaning.duplicate_count,
            completeness_avg=completeness_avg,
            uniqueness_avg=uniqueness_avg,
            validity_avg=validity_avg,
            pii_masked_count=cleaning.pii_masked_count,
        )
