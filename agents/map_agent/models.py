"""MapAI spatial analysis models (Module L).

Defines the data contracts for geographic entity marking, spatial correlation,
and analysis context. Voice/ASR features suspended per user request.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

# ══════════════════════════════════════════════════════════════════
# Geographic Entity Models
# ══════════════════════════════════════════════════════════════════


class GeoPoint(BaseModel):
    """A geographic point (lng, lat)."""

    lng: float = Field(description="Longitude")
    lat: float = Field(description="Latitude")
    label: str = Field(default="", description="Point label")


class GeoEntity(BaseModel):
    """A marked geographic entity for analysis."""

    entity_id: str = Field(description="Unique entity identifier")
    name: str = Field(description="Entity display name")
    location: GeoPoint = Field(description="Geographic location")
    entity_type: str = Field(
        default="point",
        description="point, polygon, building, region, route",
    )
    properties: dict[str, Any] = Field(
        default_factory=dict,
        description="Entity attributes (population, revenue, risk_score, etc.)",
    )
    data_source: str = Field(default="manual", description="manual, api, db_query")
    marked_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
    )


class AnalysisContext(BaseModel):
    """Global analysis context — the '分析收纳盒'.

    Aggregates marked entities for cross-entity spatial analysis.
    """

    session_id: str = Field(description="Analysis session identifier")
    entities: list[GeoEntity] = Field(default_factory=list, description="Marked entities")
    query: str = Field(default="", description="Current analysis query")
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
    )

    @property
    def entity_count(self) -> int:
        return len(self.entities)

    @property
    def entity_types(self) -> list[str]:
        return list({e.entity_type for e in self.entities})

    def add_entity(self, entity: GeoEntity) -> None:
        """Add an entity to the context (dedup by entity_id)."""
        existing_ids = {e.entity_id for e in self.entities}
        if entity.entity_id not in existing_ids:
            self.entities.append(entity)

    def remove_entity(self, entity_id: str) -> bool:
        """Remove an entity by ID. Returns True if found and removed."""
        before = len(self.entities)
        self.entities = [e for e in self.entities if e.entity_id != entity_id]
        return len(self.entities) < before


# ══════════════════════════════════════════════════════════════════
# Spatial Analysis Models
# ══════════════════════════════════════════════════════════════════


class CorrelationMethod(StrEnum):
    """Supported correlation methods."""

    PEARSON = "pearson"
    SPEARMAN = "spearman"
    SPATIAL_AUTOCORRELATION = "spatial_autocorr"
    DISTANCE_WEIGHTED = "distance_weighted"


class CorrelationPair(BaseModel):
    """A pair of entity properties being correlated."""

    entity_a_id: str
    property_a: str
    entity_b_id: str
    property_b: str


class CorrelationRequest(BaseModel):
    """Request for spatial correlation analysis."""

    context: AnalysisContext = Field(description="Analysis context with entities")
    pairs: list[CorrelationPair] = Field(
        default_factory=list,
        description="Entity-property pairs to correlate (empty = auto-pair all)",
    )
    method: CorrelationMethod = Field(default=CorrelationMethod.PEARSON)


class CorrelationPairResult(BaseModel):
    """Result for a single correlation pair."""

    entity_a: str
    property_a: str
    entity_b: str
    property_b: str
    coefficient: float = Field(description="Correlation coefficient (-1 to 1)")
    p_value: float = Field(description="Statistical significance")
    strength: str = Field(description="weak, moderate, strong, very_strong")
    interpretation: str = Field(default="")


class CorrelationResponse(BaseModel):
    """Full correlation analysis response."""

    session_id: str
    method: CorrelationMethod
    entity_count: int
    pair_count: int
    results: list[CorrelationPairResult] = Field(default_factory=list)
    summary: str = Field(default="")
    execution_time_ms: int = Field(default=0)


class SpatialQueryRequest(BaseModel):
    """Spatial query — find entities within a region."""

    bounds: list[float] = Field(
        description="[west, south, east, north] bounding box",
        min_length=4,
        max_length=4,
    )
    entity_types: list[str] = Field(default_factory=list, description="Filter by type")
    limit: int = Field(default=50, ge=1, le=500)


class SpatialQueryResponse(BaseModel):
    """Spatial query result."""

    bounds: list[float]
    total: int
    entities: list[GeoEntity] = Field(default_factory=list)


# ══════════════════════════════════════════════════════════════════
# Map Region Data (Mock / Demo)
# ══════════════════════════════════════════════════════════════════


class MapRegion(BaseModel):
    """A predefined map region with demo entities."""

    region_id: str
    name: str
    center: GeoPoint
    zoom: int = Field(default=10, ge=1, le=20)
    entities: list[GeoEntity] = Field(default_factory=list)
