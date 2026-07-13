"""Customs trade data models — normalized schemas for the customs data base (P1-C).

This module defines the unified data contracts for the two tiers of customs data:

* **Tier-1** statistical customs data (UN Comtrade + national portals):
  ``TradeRecord`` carries HS category, partner country, port, value, quantity —
  **no buyer/importer name** (confidential by law).
* **Tier-2** bill-of-lading (BOL) data (US CBP/ImportYeti, India Zauba, …):
  ``BolShipment`` carries Shipper/Consignee/Notify/port/HS — the only source of
  buyer-level entities (``BuyerEntity``).

It also provides entity-resolution and HS/port normalization helpers shared by
the customs scraper, store, and marketing connector. No I/O here.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

from shared.utils.ids import new_uuid

__all__ = [
    "BolShipment",
    "BuyerEntity",
    "CustomsFetchResult",
    "DataSourceTier",
    "TradeFlow",
    "TradeRecord",
    "lookup_hs_section",
    "normalize_buyer_name",
    "normalize_hs_code",
    "normalize_port_name",
]


# ══════════════════════════════════════════════════════════════════
# Enums
# ══════════════════════════════════════════════════════════════════


class TradeFlow(StrEnum):
    """Trade flow direction."""

    IMPORT = "import"
    EXPORT = "export"


class DataSourceTier(StrEnum):
    """Customs data tier (P1-C feasibility split).

    * TIER1 — official statistical trade data (no buyer name, globally available).
    * TIER2 — bill-of-lading data (buyer name present, redistribution-restricted).
    """

    TIER1 = "tier1"
    TIER2 = "tier2"


# ══════════════════════════════════════════════════════════════════
# Tier-1: normalized statistical trade record
# ══════════════════════════════════════════════════════════════════


class TradeRecord(BaseModel):
    """Normalized statistical trade record (Tier-1) or aggregated BOL row (Tier-2).

    Attributes:
        hs_code: HS commodity code (digits only, e.g. ``8517``).
        hs_description: Human-readable commodity description.
        reporter_country: Reporting country (ISO-2 or name).
        partner_country: Partner / counterpart country.
        port: Port of loading or discharge.
        trade_flow: Import or export.
        value_usd: Trade value in USD.
        quantity: Net quantity (unit in ``quantity_unit``).
        quantity_unit: Quantity unit code / label.
        year: Reporting year.
        period: Reporting period string (year or ``YYYY-MM``).
        tier: Data source tier (Tier-1 / Tier-2).
        provider: Source provider id (e.g. ``un_comtrade``).
    """

    id: str = Field(default_factory=new_uuid, description="Unique record ID")
    hs_code: str = Field(default="", description="HS commodity code")
    hs_description: str = Field(default="", description="Commodity description")
    reporter_country: str = Field(default="", description="Reporting country")
    partner_country: str = Field(default="", description="Partner country")
    port: str = Field(default="", description="Port of loading/discharge")
    trade_flow: TradeFlow = Field(default=TradeFlow.IMPORT, description="Trade flow")
    value_usd: float = Field(default=0.0, description="Trade value (USD)")
    quantity: float | None = Field(default=None, description="Net quantity")
    quantity_unit: str | None = Field(default=None, description="Quantity unit")
    year: int = Field(default=0, description="Reporting year")
    period: str = Field(default="", description="Reporting period")
    tier: DataSourceTier = Field(default=DataSourceTier.TIER1, description="Data tier")
    provider: str = Field(default="", description="Source provider id")
    collected_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC), description="Collection time"
    )


# ══════════════════════════════════════════════════════════════════
# Tier-2: raw bill-of-lading shipment + resolved buyer entity
# ══════════════════════════════════════════════════════════════════


class BolShipment(BaseModel):
    """Raw bill-of-lading shipment (Tier-2).

    Attributes:
        shipper: Exporter / supplier name.
        consignee: Importer / buyer name (the actionable entity).
        notify: Notify party (often the buyer's agent).
        port_of_loading: Origin port.
        port_of_discharge: Destination port.
        hs_code: HS commodity code.
        hs_description: Commodity description.
        weight_kg: Gross weight in kg.
        quantity: Package / unit count.
        origin_country: Country of origin.
        arrival_date: Arrival date (ISO string).
        provider: Source provider id.
    """

    id: str = Field(default_factory=new_uuid, description="Unique shipment ID")
    shipper: str | None = Field(default=None, description="Exporter name")
    consignee: str | None = Field(default=None, description="Importer / buyer name")
    notify: str | None = Field(default=None, description="Notify party")
    port_of_loading: str | None = Field(default=None, description="Origin port")
    port_of_discharge: str | None = Field(default=None, description="Destination port")
    hs_code: str | None = Field(default=None, description="HS commodity code")
    hs_description: str | None = Field(default=None, description="Commodity description")
    weight_kg: float | None = Field(default=None, description="Gross weight (kg)")
    quantity: float | None = Field(default=None, description="Package/unit count")
    origin_country: str | None = Field(default=None, description="Country of origin")
    arrival_date: str | None = Field(default=None, description="Arrival date (ISO)")
    provider: str = Field(default="", description="Source provider id")
    raw: dict[str, Any] = Field(
        default_factory=dict, description="Original provider payload (audit only)"
    )


class BuyerEntity(BaseModel):
    """Resolved buyer / importer entity (Tier-2 derivative intelligence).

    This is the **derivative** artifact delivered to the GEO marketing layer —
    never the raw BOL. It aggregates a consignee's import footprint so the
    marketing module can segment audiences without redistributing source rows.
    """

    id: str = Field(default_factory=new_uuid, description="Unique buyer ID")
    raw_name: str = Field(description="Original consignee name")
    normalized_name: str = Field(description="Entity-resolved name key")
    country: str | None = Field(default=None, description="Buyer country")
    source_country: str | None = Field(default=None, description="Importing reporter country")
    import_count: int = Field(default=0, ge=0, description="Number of shipments")
    total_value_usd: float = Field(default=0.0, ge=0.0, description="Total import value (USD)")
    top_hs_codes: list[str] = Field(
        default_factory=list, description="Most frequent HS codes (derived profile)"
    )
    top_ports: list[str] = Field(
        default_factory=list, description="Most frequent ports (derived profile)"
    )
    first_seen: str | None = Field(default=None, description="First seen (ISO date)")
    last_seen: str | None = Field(default=None, description="Last seen (ISO date)")
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC), description="Last update time"
    )


class CustomsFetchResult(BaseModel):
    """Unified output of a customs fetch (Tier-1 and/or Tier-2)."""

    provider: str = Field(description="Source provider id")
    tier: DataSourceTier = Field(description="Data tier")
    trade_records: list[TradeRecord] = Field(default_factory=list)
    buyers: list[BuyerEntity] = Field(default_factory=list)
    fetched_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC), description="Fetch time"
    )


# ══════════════════════════════════════════════════════════════════
# Normalization helpers — entity resolution, HS, ports
# ══════════════════════════════════════════════════════════════════

# Corporate / legal-form tokens stripped during buyer entity resolution.
_LEGAL_SUFFIXES: frozenset[str] = frozenset(
    {
        "inc",
        "inc.",
        "co",
        "co.",
        "company",
        "corp",
        "corp.",
        "corporation",
        "ltd",
        "ltd.",
        "llc",
        "l.l.c.",
        "plc",
        "gmbh",
        "ag",
        "sa",
        "s.a.",
        "spa",
        "srl",
        "s.p.a.",
        "bv",
        "b.v.",
        "nv",
        "n.v.",
        "pte",
        "ltda",
        "oy",
        "ab",
        "as",
        "kft",
        "zao",
        "ooo",
        "pjsc",
        "llp",
        "kg",
    }
)

# HS chapter (2-digit) → section label. Used for category surfacing in the portal.
_HS_SECTIONS: tuple[tuple[int, str], ...] = (
    (5, "Section I — Live animals & animal products"),
    (14, "Section II — Vegetable products"),
    (15, "Section III — Animal/vegetable fats & oils"),
    (24, "Section IV — Prepared food, beverages, tobacco"),
    (27, "Section V — Mineral products"),
    (38, "Section VI — Chemicals & allied industries"),
    (40, "Section VII — Plastics & rubber"),
    (43, "Section VIII — Raw hides, leather, furs"),
    (46, "Section IX — Wood & articles"),
    (49, "Section X — Pulp, paper"),
    (63, "Section XI — Textiles & textile articles"),
    (67, "Section XII — Footwear, headgear, umbrellas"),
    (70, "Section XIII — Stone, plaster, glass, ceramics"),
    (71, "Section XIV — Pearls, precious stones & metals"),
    (83, "Section XV — Base metals & articles"),
    (85, "Section XVI — Machinery & electrical equipment"),
    (89, "Section XVII — Vehicles, aircraft, vessels"),
    (92, "Section XVIII — Optical, photographic, medical, clocks"),
    (93, "Section XIX — Arms & ammunition"),
    (96, "Section XX — Misc manufactured articles"),
    (97, "Section XXI — Works of art & antiques"),
)


def normalize_hs_code(code: str | None) -> str:
    """Normalize an HS code to digits-only uppercase (e.g. ``85 . 17`` → ``8517``).

    Args:
        code: Raw HS code from a source (may contain dots/spaces).

    Returns:
        Normalized HS code, or empty string if input is empty.
    """
    if not code:
        return ""
    digits = re.sub(r"[^0-9]", "", str(code))
    return digits.upper()


def lookup_hs_section(hs_code: str | None) -> str:
    """Resolve the HS section label for a (normalized) HS code.

    Args:
        hs_code: Normalized HS code (digits).

    Returns:
        Section label, or ``"Unknown section"`` when not resolvable.
    """
    code = normalize_hs_code(hs_code)
    if len(code) < 2:
        return "Unknown section"
    try:
        chapter = int(code[:2])
    except ValueError:
        return "Unknown section"
    for max_chapter, label in _HS_SECTIONS:
        if chapter <= max_chapter:
            return label
    return "Unknown section"


def normalize_buyer_name(name: str | None) -> str:
    """Resolve a buyer/consignee name to a comparison key for entity resolution.

    Lowercases, collapses punctuation/whitespace, and strips common corporate
    legal-form tokens so that ``"ACME Inc."`` and ``"ACME, INC"`` map to ``acme``.

    Args:
        name: Raw consignee / importer name.

    Returns:
        Normalized comparison key (empty string if input is empty).
    """
    if not name:
        return ""
    s = str(name).lower()
    s = re.sub(r"[.,&/()]", " ", s)
    tokens = [t for t in re.split(r"\s+", s) if t and t not in _LEGAL_SUFFIXES]
    return " ".join(tokens).strip()


def normalize_port_name(port: str | None) -> str:
    """Normalize a port name for consistent grouping (e.g. ``"Shanghai, CN"`` → ``shanghai cn``).

    Args:
        port: Raw port name.

    Returns:
        Normalized port name key.
    """
    if not port:
        return ""
    s = str(port).lower()
    s = re.sub(r"[.,&/()]", " ", s)
    return re.sub(r"\s+", " ", s).strip()
