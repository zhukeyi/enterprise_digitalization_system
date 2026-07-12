"""Pydantic models for observability agent."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field


class ComponentStatus(BaseModel):
    """Status of a single platform component."""

    name: str
    type: str  # qdrant, postgres, sqlite, dify, embedding, nginx
    status: str = "unknown"  # healthy, degraded, unhealthy, unknown
    latency_ms: float = 0.0
    version: str = ""
    details: dict[str, Any] = Field(default_factory=dict)


class HealthCheckResult(BaseModel):
    """Result of a health check probe."""

    status: str = "healthy"  # healthy, degraded, unhealthy
    components: list[ComponentStatus] = Field(default_factory=list)
    checked_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class KPICard(BaseModel):
    """Single KPI metric card."""

    label: str
    value: float
    unit: str = ""
    trend: str = "stable"  # up, down, stable
    trend_value: float = 0.0


class ModuleStatusCard(BaseModel):
    """Status card for a single agent module."""

    name: str
    status: str = "online"  # online, offline, degraded
    last_called: str = ""
    error_rate: float = 0.0
    endpoint_count: int = 0


class TimelineEvent(BaseModel):
    """Event in the 24h timeline."""

    timestamp: datetime
    type: str  # deploy, alert, degrade, info
    message: str


class OverviewStats(BaseModel):
    """Aggregated overview statistics."""

    health_score: float = 100.0
    kpis: list[KPICard] = Field(default_factory=list)
    modules: list[ModuleStatusCard] = Field(default_factory=list)
    events: list[TimelineEvent] = Field(default_factory=list)
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class APIEndpointInfo(BaseModel):
    """Auto-scanned API endpoint information."""

    path: str
    method: str
    summary: str = ""
    module: str = ""
    tags: list[str] = Field(default_factory=list)


class APIEndpointStats(BaseModel):
    """Statistics for a single API endpoint."""

    path: str
    method: str
    qps: float = 0.0
    p95_latency_ms: float = 0.0
    error_rate: float = 0.0
    total_calls: int = 0


class TokenUsageRecord(BaseModel):
    """Single token usage log record."""

    timestamp: datetime
    trace_id: str = ""
    model: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    cost_usd: float = 0.0
    agent_module: str = ""
    user_id: str = ""
    latency_ms: float = 0.0


class TokenUsageAggregation(BaseModel):
    """Aggregated token usage by a dimension."""

    group_key: str
    group_value: str
    total_tokens: int
    total_cost: float
    call_count: int


class RAGDocSummary(BaseModel):
    """Summary of a document in the RAG inspector."""

    doc_id: str
    title: str = ""
    doc_type: str = ""
    source: str = ""
    chunk_count: int = 0
    embedding_model: str = ""
    status: str = "indexed"
    created_at: str = ""


class RAGChunkDetail(BaseModel):
    """Detail of a single RAG chunk."""

    chunk_id: str
    doc_id: str
    text: str
    parent_text: str = ""
    block_kind: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)
    vector_preview: list[float] = Field(default_factory=list)


class TraceSpan(BaseModel):
    """A single trace span."""

    trace_id: str
    span_id: str
    parent_span_id: str = ""
    name: str
    start_time: datetime
    end_time: datetime | None = None
    duration_ms: float = 0.0
    status: str = "ok"
    span_type: str = "http"  # http, llm, rag, tool
    attributes: dict[str, Any] = Field(default_factory=dict)


class TraceTree(BaseModel):
    """A trace tree (collection of spans for one trace)."""

    trace_id: str
    spans: list[TraceSpan] = Field(default_factory=list)
    total_duration_ms: float = 0.0
    span_count: int = 0
    status: str = "ok"


class AuditLogEntry(BaseModel):
    """Single audit log entry."""

    id: int = 0
    timestamp: datetime
    user_id: str = ""
    action: str
    target_type: str = ""
    target_id: str = ""
    detail: dict[str, Any] = Field(default_factory=dict)
    ip_address: str = ""
    trace_id: str = ""
