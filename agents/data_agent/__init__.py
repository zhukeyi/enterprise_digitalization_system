"""Data Agent — multi-source data collection, cleaning, and ETL pipeline (M3-T1 + M3-T2).

M3-T1:
- Web/RSS/API scrapers for multi-source data collection
- Cleaning pipeline (dedup, normalization, PII masking, quality scoring)
- ETL pipeline orchestrator (extract -> transform -> load)
- ToolRegistry integration (data_collect, data_clean, data_pipeline, data_quality_report)

M3-T2:
- Report template engine (Jinja2 + matplotlib chart generation)
- Multi-channel push service (email, IM, webhook)
- APScheduler-based periodic report scheduling
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
from agents.data_agent.report_models import (
    ChartSpec,
    ChartType,
    PushChannel,
    PushResult,
    PushTarget,
    ReportFormat,
    ReportInstance,
    ReportSection,
    ReportTemplate,
    TemplateVariable,
)

__all__ = [
    "ChartSpec",
    "ChartType",
    "CleanedItem",
    "CollectedItem",
    "DataQualityReport",
    "PipelineResult",
    "PushChannel",
    "PushResult",
    "PushTarget",
    "ReportFormat",
    "ReportInstance",
    "ReportSection",
    "ReportTemplate",
    "SourceConfig",
    "SourceType",
    "TemplateVariable",
]
