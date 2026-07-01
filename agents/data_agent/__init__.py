"""Data Agent — multi-source data collection, cleaning, and ETL pipeline (M3-T1).

Provides:
- Web/RSS/API scrapers for multi-source data collection
- Cleaning pipeline (dedup, normalization, PII masking, quality scoring)
- ETL pipeline orchestrator (extract → transform → load)
- ToolRegistry integration (data_collect, data_clean, data_pipeline, data_quality_report)
"""

from __future__ import annotations

from agents.data_agent.models import (
    CleanedItem,
    CollectedItem,
    DataQualityReport,
    PipelineResult,
    SourceConfig,
    SourceType,
)

__all__ = [
    "CleanedItem",
    "CollectedItem",
    "DataQualityReport",
    "PipelineResult",
    "SourceConfig",
    "SourceType",
]
