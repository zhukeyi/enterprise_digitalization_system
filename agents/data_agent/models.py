"""Data Agent models — Pydantic data contracts for the ETL pipeline.

Defines:
- SourceConfig: 采集源配置
- CollectedItem: EXTRACT 阶段输出(原始数据)
- CleanedItem: TRANSFORM 阶段输出(清洗后数据)
- DataQualityReport: 数据质量报告
- PipelineResult: 流水线最终输出
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

from shared.utils.ids import new_uuid

__all__ = [
    "CleanedItem",
    "CollectedItem",
    "DataQualityReport",
    "GEORiskReport",
    "GeoFlag",
    "PipelineResult",
    "SourceConfig",
    "SourceType",
]


# ══════════════════════════════════════════════════════════════════
# Enums
# ══════════════════════════════════════════════════════════════════


class SourceType(StrEnum):
    """Supported data source types."""

    WEB = "web"
    RSS = "rss"
    API = "api"
    CUSTOMS = "customs"
    RSSHUB = "rsshub"
    CRAWL4AI = "crawl4ai"


# ══════════════════════════════════════════════════════════════════
# EXTRACT Stage Models
# ══════════════════════════════════════════════════════════════════


class SourceConfig(BaseModel):
    """采集源配置 — 描述从哪里采集、如何采集.

    Attributes:
        source_type: 数据源类型 (web/rss/api).
        url: 目标 URL(网页地址、RSS feed、REST API endpoint).
        auth_config: 认证配置(bearer_token / api_key / basic_auth).
        max_items: 最大采集条数.
        headers: 自定义 HTTP 请求头.
    """

    source_type: SourceType = Field(description="Data source type")
    url: str = Field(description="Target URL")
    auth_config: dict[str, Any] | None = Field(
        default=None,
        description="Auth config (bearer_token, api_key, basic_auth)",
    )
    max_items: int = Field(default=50, ge=1, le=500, description="Max items to collect")
    headers: dict[str, str] = Field(default_factory=dict, description="Custom HTTP headers")
    metadata: dict[str, Any] | None = Field(
        default=None,
        description="Provider/adapter metadata (e.g. provider, reporter, year, hsCode)",
    )


class CollectedItem(BaseModel):
    """采集原始数据 — EXTRACT 阶段输出.

    统一模型,不论数据源是 web/rss/api,采集结果都包装为 CollectedItem.

    Attributes:
        id: 唯一标识.
        source: 数据源类型.
        source_url: 采集来源 URL.
        title: 标题.
        content: 正文/摘要.
        raw_html: 原始 HTML(仅 web 采集器有值).
        metadata: 采集附加信息(作者、发布时间、标签等).
        collected_at: 采集时间.
    """

    id: str = Field(default_factory=new_uuid, description="Unique item ID")
    source: SourceType = Field(description="Data source type")
    source_url: str = Field(description="Source URL")
    title: str = Field(default="", description="Item title")
    content: str = Field(default="", description="Main content or summary")
    raw_html: str | None = Field(default=None, description="Raw HTML (web scraper only)")
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Additional metadata (author, date, tags, etc.)",
    )
    collected_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="Collection timestamp",
    )


# ══════════════════════════════════════════════════════════════════
# TRANSFORM Stage Models
# ══════════════════════════════════════════════════════════════════


class CleanedItem(BaseModel):
    """清洗后数据 — TRANSFORM 阶段输出.

    经过去重、标准化、PII 脱敏后的数据.

    Attributes:
        id: 保留原始 CollectedItem 的 ID.
        source: 数据源类型.
        source_url: 采集来源 URL.
        title: 标准化后的标题.
        content: 纯文本内容(HTML 已剥离).
        metadata: 标准化后的元数据.
        quality_score: 质量评分 (0.0-1.0).
        pii_masked: 是否进行了 PII 脱敏.
        cleaned_at: 清洗时间.
    """

    id: str = Field(description="Original CollectedItem ID")
    source: SourceType = Field(description="Data source type")
    source_url: str = Field(description="Source URL")
    title: str = Field(description="Normalized title")
    content: str = Field(description="Plain text content (HTML stripped)")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Normalized metadata")
    quality_score: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Quality score (0.0-1.0)",
    )
    pii_masked: bool = Field(default=False, description="Whether PII was masked")
    cleaned_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="Cleaning timestamp",
    )


# ══════════════════════════════════════════════════════════════════
# Quality Report Model
# ══════════════════════════════════════════════════════════════════


class GEORiskReport(BaseModel):
    """GEO 污染风险评估 — 检测 AI 生成内容、信源不可信、提示注入等.

    Attributes:
        geo_score: 综合 GEO 污染风险 (0.0=真实, 1.0=高风险).
        ai_generated_score: AI 生成文本可能性 (0.0-1.0).
        credibility_score: 信源可信度 (1.0=高可信, 0.0=不可信).
        prompt_injection_detected: 是否检测到隐藏提示注入.
        cross_source_verified: 是否通过多源交叉验证.
        flags: 触发标记列表 (e.g. "ai_pattern", "keyword_stuffing", "fake_citation").
    """

    geo_score: float = Field(default=0.0, ge=0.0, le=1.0)
    ai_generated_score: float = Field(default=0.0, ge=0.0, le=1.0)
    credibility_score: float = Field(default=1.0, ge=0.0, le=1.0)
    prompt_injection_detected: bool = False
    cross_source_verified: bool = False
    flags: list[str] = Field(default_factory=list)


class GeoFlag(StrEnum):
    """GEO 污染标记类型."""

    AI_PATTERN = "ai_pattern"
    SENTENCE_UNIFORMITY = "sentence_uniformity"
    FAKE_CITATION = "fake_citation"
    KEYWORD_STUFFING = "keyword_stuffing"
    PROMPT_INJECTION = "prompt_injection"
    CONTENT_FARM = "content_farm"
    LOW_CREDIBILITY = "low_credibility"
    CITATION_LAUNDERING = "citation_laundering"
    AUTO_TRANSLATED = "auto_translated"
    SYNCHRONIZED_CONTENT = "synchronized_content"


class DataQualityReport(BaseModel):
    """数据质量报告 — LOAD 阶段副产物.

    Attributes:
        total_items: 采集总数(EXTRACT 输出).
        valid_items: 有效数据数(TRANSFORM 后).
        duplicate_count: 去重数量.
        completeness_avg: 完整性平均分 (0.0-1.0).
        uniqueness_avg: 唯一性平均分 (0.0-1.0).
        validity_avg: 有效性平均分 (0.0-1.0).
        pii_masked_count: PII 脱敏条数.
        geo_risk_items: GEO 高风险条目数.
        avg_geo_score: 平均 GEO 污染风险 (0.0-1.0).
        geo_flagged_count: 被标记的条目数.
    """

    total_items: int = Field(default=0, ge=0, description="Total items collected")
    valid_items: int = Field(default=0, ge=0, description="Valid items after cleaning")
    duplicate_count: int = Field(default=0, ge=0, description="Duplicates removed")
    completeness_avg: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Average completeness score",
    )
    uniqueness_avg: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Average uniqueness score",
    )
    validity_avg: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Average validity score",
    )
    pii_masked_count: int = Field(default=0, ge=0, description="Items with PII masked")
    geo_risk_items: int = Field(default=0, ge=0, description="Items with high GEO risk")
    avg_geo_score: float = Field(default=0.0, ge=0.0, le=1.0, description="Average GEO risk score")
    geo_flagged_count: int = Field(default=0, ge=0, description="Items flagged for GEO concerns")


# ══════════════════════════════════════════════════════════════════
# Pipeline Result Model
# ══════════════════════════════════════════════════════════════════


class PipelineResult(BaseModel):
    """ETL 流水线最终输出.

    Attributes:
        dataset_id: 数据集唯一标识(用于后续查询).
        source: 数据源类型.
        extracted_count: EXTRACT 阶段采集数量.
        cleaned_count: TRANSFORM 阶段清洗后数量.
        stored_count: LOAD 阶段存储数量.
        quality_report: 数据质量报告.
        duration_ms: 总耗时(毫秒).
        errors: 错误信息列表.
    """

    dataset_id: str = Field(default_factory=new_uuid, description="Dataset identifier")
    source: SourceType = Field(description="Data source type")
    extracted_count: int = Field(default=0, ge=0, description="Items extracted")
    cleaned_count: int = Field(default=0, ge=0, description="Items after cleaning")
    stored_count: int = Field(default=0, ge=0, description="Items stored")
    quality_report: DataQualityReport = Field(
        default_factory=DataQualityReport,
        description="Data quality report",
    )
    duration_ms: int = Field(default=0, ge=0, description="Total duration in ms")
    errors: list[str] = Field(default_factory=list, description="Error messages")
