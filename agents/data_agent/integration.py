"""Data Agent integration with LangGraph Orchestrator (M3-T1).

Bridges the data collection pipeline to the Supervisor-Worker framework
via ToolRegistry.

Registered tools:
- data_collect: Scrape data from a web/RSS/API source (EXTRACT only)
- data_clean: Clean and deduplicate a batch of raw items (TRANSFORM only)
- data_pipeline: Run the full ETL pipeline (EXTRACT → TRANSFORM → LOAD)
- data_quality_report: Get quality report for a stored dataset
"""

from __future__ import annotations

import logging
from typing import Any

from agents.data_agent.cleaning import CleaningPipeline
from agents.data_agent.models import (
    CollectedItem,
    PipelineResult,
    SourceConfig,
    SourceType,
)
from agents.data_agent.pipeline import DataPipeline, get_datastore
from agents.orchestrator.tools.registry import ToolDefinition, ToolRegistry

logger = logging.getLogger("fde.data.integration")

__all__ = ["register_data_tools"]


# ══════════════════════════════════════════════════════════════════
# Tool Handlers
# ══════════════════════════════════════════════════════════════════


async def _data_collect_handler(
    source_type: str = "web",
    query: str = "",
    max_items: int = 50,
) -> dict[str, Any]:
    """Collect data from a specified source (EXTRACT stage only).

    Args:
        source_type: Data source type (web, rss, api).
        query: URL or search keyword.
        max_items: Maximum items to return.
    """
    if not query:
        return {"error": "query is required", "source_type": source_type}

    try:
        st = SourceType(source_type)
    except ValueError:
        return {
            "error": f"Unknown source_type '{source_type}'. Valid: {[s.value for s in SourceType]}",
            "source_type": source_type,
        }

    config = SourceConfig(source_type=st, url=query, max_items=max_items)

    try:
        pipeline = DataPipeline()
        raw_items = await pipeline._extract(config)
    except (ValueError, RuntimeError, OSError) as e:
        logger.error("data_collect failed: %s", e)
        return {"error": str(e), "source_type": source_type, "query": query}

    return {
        "source_type": source_type,
        "query": query,
        "count": len(raw_items),
        "items": [
            {
                "id": item.id,
                "title": item.title,
                "content": item.content[:200],
                "source_url": item.source_url,
                "metadata": item.metadata,
            }
            for item in raw_items
        ],
    }


async def _data_clean_handler(
    raw_items: list[dict[str, Any]],
) -> dict[str, Any]:
    """Clean and deduplicate raw collected data (TRANSFORM stage only).

    Args:
        raw_items: List of raw item dicts with CollectedItem fields.
    """
    if not raw_items:
        return {"error": "raw_items is required", "count": 0}

    try:
        items = [CollectedItem(**ri) for ri in raw_items]
    except (ValueError, TypeError, KeyError) as e:
        return {"error": f"Invalid raw_items format: {e}", "count": 0}

    cleaning = CleaningPipeline()
    cleaned = cleaning.run(items)

    return {
        "input_count": len(raw_items),
        "output_count": len(cleaned),
        "duplicate_count": cleaning.duplicate_count,
        "pii_masked_count": cleaning.pii_masked_count,
        "items": [
            {
                "id": c.id,
                "title": c.title,
                "content": c.content[:200],
                "quality_score": c.quality_score,
                "pii_masked": c.pii_masked,
            }
            for c in cleaned
        ],
    }


async def _data_pipeline_handler(
    source_config: dict[str, Any],
) -> dict[str, Any]:
    """Run the full ETL pipeline (EXTRACT → TRANSFORM → LOAD).

    Args:
        source_config: Dict with keys matching SourceConfig fields.
    """
    try:
        config = SourceConfig(**source_config)
    except (ValueError, TypeError, KeyError) as e:
        return {"error": f"Invalid source_config: {e}"}

    pipeline = DataPipeline()
    try:
        result: PipelineResult = await pipeline.run(config)
    except (ValueError, RuntimeError, OSError) as e:
        logger.error("data_pipeline failed: %s", e)
        return {"error": str(e)}

    return {
        "dataset_id": result.dataset_id,
        "source": result.source.value,
        "extracted_count": result.extracted_count,
        "cleaned_count": result.cleaned_count,
        "stored_count": result.stored_count,
        "quality_report": {
            "total_items": result.quality_report.total_items,
            "valid_items": result.quality_report.valid_items,
            "duplicate_count": result.quality_report.duplicate_count,
            "completeness_avg": result.quality_report.completeness_avg,
            "uniqueness_avg": result.quality_report.uniqueness_avg,
            "validity_avg": result.quality_report.validity_avg,
        },
        "duration_ms": result.duration_ms,
        "errors": result.errors,
    }


async def _data_quality_report_handler(
    dataset_id: str = "",
) -> dict[str, Any]:
    """Get the data quality report for a stored dataset.

    Args:
        dataset_id: The dataset identifier from a previous data_pipeline run.
    """
    if not dataset_id:
        return {"error": "dataset_id is required"}

    datastore = get_datastore()
    items = datastore.get(dataset_id)

    if items is None:
        return {
            "error": f"Dataset '{dataset_id}' not found",
            "available_datasets": list(datastore.keys()),
        }

    if not items:
        return {
            "dataset_id": dataset_id,
            "total_items": 0,
            "completeness_avg": 0.0,
            "validity_avg": 0.0,
            "pii_masked_count": 0,
        }

    return {
        "dataset_id": dataset_id,
        "total_items": len(items),
        "completeness_avg": round(sum(1 for c in items if c.title and c.content) / len(items), 4),
        "validity_avg": round(sum(c.quality_score for c in items) / len(items), 4),
        "pii_masked_count": sum(1 for c in items if c.pii_masked),
        "sources": list({c.source.value for c in items}),
    }


# ══════════════════════════════════════════════════════════════════
# Registration
# ══════════════════════════════════════════════════════════════════


def register_data_tools(registry: ToolRegistry) -> None:
    """Register all data agent tools with the orchestrator ToolRegistry.

    Four tools are registered:
    - data_collect: EXTRACT stage only
    - data_clean: TRANSFORM stage only
    - data_pipeline: Full ETL pipeline
    - data_quality_report: Query stored dataset quality

    Args:
        registry: The orchestrator's ToolRegistry instance.
    """
    registry.register(
        ToolDefinition(
            name="data_collect",
            description="从指定数据源采集数据 (web/RSS/API),返回原始采集结果",
            worker="data",
            handler=_data_collect_handler,
            parameters={
                "source_type": {
                    "type": "string",
                    "required": True,
                    "description": "Data source type: web, rss, api",
                },
                "query": {
                    "type": "string",
                    "required": True,
                    "description": "URL or search query",
                },
                "max_items": {
                    "type": "integer",
                    "required": False,
                    "default": 50,
                    "description": "Maximum items to collect (1-500)",
                },
            },
            category="data",
        )
    )

    registry.register(
        ToolDefinition(
            name="data_clean",
            description="清洗原始采集数据(去重/标准化/PII脱敏)",
            worker="data",
            handler=_data_clean_handler,
            parameters={
                "raw_items": {
                    "type": "array",
                    "required": True,
                    "description": "List of raw item dicts with CollectedItem fields",
                },
            },
            category="data",
        )
    )

    registry.register(
        ToolDefinition(
            name="data_pipeline",
            description="执行完整 ETL 流水线(采集→清洗→存储),返回数据集 ID 和质量报告",
            worker="data",
            handler=_data_pipeline_handler,
            parameters={
                "source_config": {
                    "type": "object",
                    "required": True,
                    "description": (
                        "SourceConfig dict: source_type, url, "
                        "auth_config (optional), max_items (optional)"
                    ),
                },
            },
            category="data",
        )
    )

    registry.register(
        ToolDefinition(
            name="data_quality_report",
            description="查询已存储数据集的质量报告",
            worker="data",
            handler=_data_quality_report_handler,
            parameters={
                "dataset_id": {
                    "type": "string",
                    "required": True,
                    "description": "Dataset identifier from a previous pipeline run",
                },
            },
            category="data",
        )
    )

    logger.info(
        "Registered %d data tools",
        len(registry.get_tools_for_worker("data")),
    )
