"""Customs-derived audience connector for GEO marketing (P1-C, C-8).

Consumes the customs data base (``BuyerEntity`` derivatives + ``TradeRecord``
trends from ``CustomsStore``) and produces ``CustomsAudienceSegment`` objects
segmented along four axes required by the GEO campaign layer:

* **品类 (category)** — HS section derived from the buyer's top HS codes.
* **港口 (port)** — the buyer's most frequent discharge port.
* **频次 (frequency)** — import-count tier (high / mid / low).
* **增长 (growth)** — recency tier derived from ``last_seen`` (rising / stable /
  declining / unknown).

Every buyer is screened against sanctions lists (R3 red line) before it is added
to a segment's *deliverable* audience. Blocked buyers are excluded from outreach
but recorded for audit. No raw BOL rows ever leave the data_agent layer — only
``BuyerEntity`` derivative profiles flow in.

This module deliberately imports nothing from the marketing *content* layer so it
can be unit-tested without numpy (C-9/C-11 content math is downstream).
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel, Field

from agents.data_agent.compliance_guard import OutreachComplianceGate, SanctionsGuard
from agents.data_agent.customs_models import (
    BuyerEntity,
    lookup_hs_section,
    normalize_port_name,
)
from agents.data_agent.customs_store import CustomsStore

__all__ = [
    "CustomsAudienceConnector",
    "CustomsAudienceSegment",
    "DeliverableBuyer",
    "FrequencyTier",
    "GrowthTier",
    "SegmentComplianceStatus",
]


class FrequencyTier(StrEnum):
    """Import-frequency tier derived from ``BuyerEntity.import_count``."""

    HIGH = "high"
    MID = "mid"
    LOW = "low"
    UNKNOWN = "unknown"


class GrowthTier(StrEnum):
    """Import-growth / recency tier derived from ``BuyerEntity.last_seen``."""

    RISING = "rising"
    STABLE = "stable"
    DECLINING = "declining"
    UNKNOWN = "unknown"


class SegmentComplianceStatus(StrEnum):
    """Sanctions screening outcome for a segment's deliverable audience."""

    PASSED = "passed"  # no blocked buyers
    PARTIAL = "partial"  # some buyers blocked, rest deliverable
    BLOCKED = "blocked"  # all buyers blocked
    UNKNOWN = "unknown"  # no buyers (empty segment)


class DeliverableBuyer(BaseModel):
    """A single buyer cleared for outbound GEO marketing (derivative only)."""

    name: str = Field(description="Normalized/raw buyer name (derivative, never raw BOL)")
    country: str | None = Field(default=None, description="Buyer country")
    source_country: str | None = Field(default=None, description="Importing reporter country")
    total_value_usd: float = Field(default=0.0, ge=0.0, description="Aggregate import value")
    import_count: int = Field(default=0, ge=0, description="Shipment count")
    top_hs_codes: list[str] = Field(default_factory=list)
    top_ports: list[str] = Field(default_factory=list)


class CustomsAudienceSegment(BaseModel):
    """A homogeneous audience cell: one (category × port × frequency × growth) combo."""

    segment_id: str = Field(description="Stable id = hash of the 4-tuple key")
    name: str = Field(description="Human-readable segment label")
    category: str = Field(description="HS section label (品类)")
    hs_codes: list[str] = Field(default_factory=list, description="HS codes covered by the segment")
    port: str = Field(description="Discharge port (港口)")
    frequency_tier: FrequencyTier = Field(description="频次 tier")
    growth_tier: GrowthTier = Field(description="增长 tier")

    buyer_count: int = Field(default=0, ge=0, description="Total buyers in the cell")
    deliverable_count: int = Field(default=0, ge=0, description="Buyers cleared for outreach")
    blocked_count: int = Field(default=0, ge=0, description="Buyers blocked by sanctions")
    total_value_usd: float = Field(default=0.0, ge=0.0, description="Aggregate value (deliverable)")

    deliverable_buyers: list[DeliverableBuyer] = Field(default_factory=list)
    blocked_sample: list[str] = Field(default_factory=list, description="Sample blocked names (audit)")
    compliance_status: SegmentComplianceStatus = Field(default=SegmentComplianceStatus.UNKNOWN)

    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @property
    def outreach_ready(self) -> bool:
        """True when at least one buyer is cleared for outreach."""
        return self.deliverable_count > 0


def _current_year() -> int:
    return datetime.now(UTC).year


def _classify_frequency(import_count: int, *, high: int, mid: int) -> FrequencyTier:
    if import_count <= 0:
        return FrequencyTier.UNKNOWN
    if import_count >= high:
        return FrequencyTier.HIGH
    if import_count >= mid:
        return FrequencyTier.MID
    return FrequencyTier.LOW


def _classify_growth(last_seen: str | None, ref_year: int) -> GrowthTier:
    if not last_seen:
        return GrowthTier.UNKNOWN
    digits = "".join(ch for ch in last_seen[:4] if ch.isdigit())
    if len(digits) != 4:
        return GrowthTier.UNKNOWN
    try:
        yr = int(digits)
    except ValueError:
        return GrowthTier.UNKNOWN
    years_since = ref_year - yr
    if years_since <= 1:
        return GrowthTier.RISING
    if years_since <= 3:
        return GrowthTier.STABLE
    return GrowthTier.DECLINING


def _primary_hs_section(buyer: BuyerEntity) -> str:
    if buyer.top_hs_codes:
        return lookup_hs_section(buyer.top_hs_codes[0])
    return "Unknown section"


def _primary_port(buyer: BuyerEntity) -> str:
    if buyer.top_ports:
        return normalize_port_name(buyer.top_ports[0]) or buyer.top_ports[0]
    return "unknown"


class CustomsAudienceConnector:
    """Builds GEO-marketing audience segments from the customs data base.

    Usage::

        store = await get_customs_store()
        connector = CustomsAudienceConnector(store)
        segments = await connector.build_segments(min_value_usd=10_000)
        for seg in segments:
            if seg.outreach_ready:
                ...  # hand seg off to C-9 content generation / C-10 push
    """

    def __init__(
        self,
        store: CustomsStore | None = None,
        *,
        gate: OutreachComplianceGate | None = None,
        high_frequency: int = 20,
        mid_frequency: int = 5,
        max_buyers_per_segment: int = 500,
    ) -> None:
        """Initialize.

        Args:
            store: A ``CustomsStore`` to read buyer entities from (optional if you
                call :meth:`build_from_buyers` with an explicit list).
            gate: Sanctions/outreach compliance gate (default: fresh ``SanctionsGuard``).
            high_frequency: import_count threshold for ``HIGH`` tier.
            mid_frequency: import_count threshold for ``MID`` tier.
            max_buyers_per_segment: cap stored deliverable buyers per segment (memory).
        """
        self._store = store
        self._gate = gate or OutreachComplianceGate(SanctionsGuard())
        self._high = high_frequency
        self._mid = mid_frequency
        self._max = max_buyers_per_segment

    # ── public API ──────────────────────────────────────────────────

    async def build_segments(
        self,
        *,
        category: str | None = None,
        port: str | None = None,
        frequency_tier: FrequencyTier | None = None,
        growth_tier: GrowthTier | None = None,
        min_value_usd: float = 0.0,
        min_import_count: int = 0,
        limit: int = 200,
        country: str | None = None,
    ) -> list[CustomsAudienceSegment]:
        """Read buyers from the store and return filtered, screened segments.

        Args:
            category: Filter to an HS section label substring.
            port: Filter to a (normalized) port name.
            frequency_tier: Filter to a frequency tier.
            growth_tier: Filter to a growth tier.
            min_value_usd: Drop buyers below this aggregate import value.
            min_import_count: Drop buyers below this shipment count.
            limit: Max buyers fetched from the store.
            country: Restrict to a buyer country.

        Returns:
            Segments (one per non-empty 4-tuple cell), sorted by deliverable value.
        """
        if self._store is None:
            raise ValueError("CustomsAudienceConnector requires a CustomsStore for build_segments")
        buyers = await self._store.top_buyers(country=country, limit=limit)
        return self.build_from_buyers(
            buyers,
            category=category,
            port=port,
            frequency_tier=frequency_tier,
            growth_tier=growth_tier,
            min_value_usd=min_value_usd,
            min_import_count=min_import_count,
        )

    def build_from_buyers(
        self,
        buyers: list[BuyerEntity],
        *,
        category: str | None = None,
        port: str | None = None,
        frequency_tier: FrequencyTier | None = None,
        growth_tier: GrowthTier | None = None,
        min_value_usd: float = 0.0,
        min_import_count: int = 0,
    ) -> list[CustomsAudienceSegment]:
        """Synchronous variant: segment an explicit buyer list (test-friendly)."""
        ref_year = _current_year()
        # Bucket buyers into (category, port, freq, growth) cells.
        cells: dict[tuple[str, str, FrequencyTier, GrowthTier], list[BuyerEntity]] = {}
        for b in buyers:
            if b.total_value_usd < min_value_usd or b.import_count < min_import_count:
                continue
            cat = _primary_hs_section(b)
            p = _primary_port(b)
            freq = _classify_frequency(b.import_count, high=self._high, mid=self._mid)
            grow = _classify_growth(b.last_seen, ref_year)
            if category and category.lower() not in cat.lower():
                continue
            if port and port.lower() not in p.lower():
                continue
            if frequency_tier and freq != frequency_tier:
                continue
            if growth_tier and grow != growth_tier:
                continue
            cells.setdefault((cat, p, freq, grow), []).append(b)

        segments: list[CustomsAudienceSegment] = []
        for (cat, p, freq, grow), group in cells.items():
            seg = self._make_segment(cat, p, freq, grow, group)
            segments.append(seg)

        segments.sort(key=lambda s: s.total_value_usd, reverse=True)
        return segments

    # ── internals ───────────────────────────────────────────────────

    def _make_segment(
        self,
        category: str,
        port: str,
        freq: FrequencyTier,
        grow: GrowthTier,
        buyers: list[BuyerEntity],
    ) -> CustomsAudienceSegment:
        hs_set: dict[str, int] = {}
        deliverable: list[DeliverableBuyer] = []
        blocked_sample: list[str] = []
        blocked_count = 0
        deliverable_value = 0.0

        for b in buyers:
            # R3: sanctions screen every buyer before outreach eligibility.
            decision = self._gate.evaluate(buyer_name=b.raw_name, country=b.country)
            for code in b.top_hs_codes:
                hs_set[code] = hs_set.get(code, 0) + 1
            if decision.allowed:
                deliverable.append(
                    DeliverableBuyer(
                        name=b.raw_name,
                        country=b.country,
                        source_country=b.source_country,
                        total_value_usd=b.total_value_usd,
                        import_count=b.import_count,
                        top_hs_codes=list(b.top_hs_codes),
                        top_ports=list(b.top_ports),
                    )
                )
                deliverable_value += b.total_value_usd
            else:
                blocked_count += 1
                if len(blocked_sample) < 5:
                    blocked_sample.append(b.raw_name)

        # Keep memory bounded: store only the top-N deliverable buyers by value.
        deliverable.sort(key=lambda x: x.total_value_usd, reverse=True)
        capped = deliverable[: self._max]

        if not buyers:
            status = SegmentComplianceStatus.UNKNOWN
        elif blocked_count == 0:
            status = SegmentComplianceStatus.PASSED
        elif len(deliverable) == 0:
            status = SegmentComplianceStatus.BLOCKED
        else:
            status = SegmentComplianceStatus.PARTIAL

        seg_id = f"{category}|{port}|{freq.value}|{grow.value}"
        name = (
            f"{category} · {port or 'any'} · "
            f"{freq.value}频次 · {grow.value}增长"
        )
        return CustomsAudienceSegment(
            segment_id=seg_id,
            name=name,
            category=category,
            hs_codes=sorted(hs_set, key=lambda k: hs_set[k], reverse=True)[:10],
            port=port,
            frequency_tier=freq,
            growth_tier=grow,
            buyer_count=len(buyers),
            deliverable_count=len(deliverable),
            blocked_count=blocked_count,
            total_value_usd=deliverable_value,
            deliverable_buyers=capped,
            blocked_sample=blocked_sample,
            compliance_status=status,
        )
