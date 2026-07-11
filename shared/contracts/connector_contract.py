"""Connector contract models (F6: versioned, backward-compatible).

Defines the wire format used between FDE and external Java connectors:

* ``ConnectorManifest`` — self-describing metadata a connector publishes at
  ``GET /manifest``. Carries ``schema_version`` (semver) so FDE can apply
  forward/backward compatibility rules.
* ``CanonicalDocument`` — the normalized entity that lands in
  ``canonical_documents`` regardless of whether it came from a local file or a
  connector. This is the contract that decouples ingestion from source.
* ``FieldMapping`` / ``FieldMappingRule`` — declarative mapping from a
  connector's raw payload shape to ``CanonicalDocument.fields``.

Design rules (see docs/connector-contract.md):
- ``schema_version`` uses semver (MAJOR.MINOR.PATCH).
- Breaking changes bump MAJOR and require coordinated FDE + connector release.
- Unknown / unsupported MAJOR → FDE degrades gracefully + raises an alert.
"""

from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

# semver 2.0.0: MAJOR.MINOR.PATCH, each 0-999, no leading zeros except "0".
_SEMVER_RE = re.compile(
    r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)"
    r"(?:-((?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*)"
    r"(?:\.(?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*))*))?"
    r"(?:\+([0-9a-zA-Z-]+(?:\.[0-9a-zA-Z-]+)*))?$"
)


def is_valid_semver(value: str) -> bool:
    """Return True if ``value`` is a valid semantic version string."""
    return bool(_SEMVER_RE.match(value))


def major_version(value: str) -> int:
    """Extract the MAJOR component of a semver string (raises on invalid)."""
    if not is_valid_semver(value):
        raise ValueError(f"Invalid semver: {value!r}")
    return int(value.split(".", 1)[0])


class ConnectorManifest(BaseModel):
    """Self-describing metadata a connector exposes at ``GET /manifest``."""

    schema_version: str = Field(
        ...,
        description="semver of THIS manifest contract. FDE checks MAJOR for compatibility.",
        examples=["1.0.0"],
    )
    connector_id: str = Field(
        ...,
        description="Stable, unique connector identifier, e.g. 'logistics_yonyou'.",
        examples=["logistics_yonyou"],
    )
    name: str = Field(..., description="Human-readable connector name.")
    description: str | None = Field(default=None, description="Optional description.")
    protocol: Literal["rest", "grpc"] = Field(default="rest")
    base_url: str | None = Field(default=None, description="Root URL of the connector API.")
    auth_type: Literal["none", "api_key", "oauth2", "basic"] = Field(default="none")
    capabilities: list[str] = Field(
        default_factory=list,
        description="Declared abilities, e.g. ['query', 'list_entities', 'subscribe'].",
    )
    entity_types: list[str] = Field(
        default_factory=list,
        description="Canonical doc_types this connector can produce.",
    )
    field_mapping_ref: str | None = Field(
        default=None,
        description="Path or URL to the field_mapping.yaml for this connector.",
    )
    health_check_path: str | None = Field(
        default=None, description="Relative path FDE polls for health, e.g. '/actuator/health'."
    )

    @field_validator("schema_version")
    @classmethod
    def _check_semver(cls, v: str) -> str:
        if not is_valid_semver(v):
            raise ValueError(
                f"schema_version must be valid semver (got {v!r}); see https://semver.org"
            )
        return v


class FieldMappingRule(BaseModel):
    """A single mapping rule: extract ``source_path`` from raw → ``target_field``."""

    source_path: str = Field(
        ...,
        description="Dotted path into the raw payload, e.g. 'data.orderNo' or 'items.0.sku'.",
    )
    target_field: str = Field(
        ..., description="Canonical field name written into CanonicalDocument.fields."
    )
    transform: str | None = Field(
        default=None,
        description="Optional transform id, e.g. 'to_upper', 'to_iso_date', 'coalesce'.",
    )
    required: bool = Field(
        default=False, description="If True and missing, mapping fails loudly (or null + warning)."
    )


class FieldMapping(BaseModel):
    """Declarative field mapping for one canonical doc_type of one connector."""

    schema_version: str = Field(..., description="semver of the mapping file format.")
    connector_id: str = Field(..., description="Which connector this mapping applies to.")
    doc_type: str = Field(..., description="Target canonical doc_type, e.g. 'sales_order'.")
    rules: list[FieldMappingRule] = Field(
        default_factory=list, description="Ordered extraction rules."
    )

    @field_validator("schema_version")
    @classmethod
    def _check_semver(cls, v: str) -> str:
        if not is_valid_semver(v):
            raise ValueError(f"schema_version must be valid semver (got {v!r})")
        return v


class CanonicalDocument(BaseModel):
    """Normalized entity stored in ``canonical_documents`` (source-agnostic)."""

    doc_type: str = Field(..., description="Canonical entity type, e.g. 'sales_order'.")
    title: str = Field(..., description="Human-readable title used in previews and search.")
    fields: dict[str, Any] = Field(default_factory=dict, description="Normalized canonical fields.")
    doc_id: str | None = Field(
        default=None, description="Stable id within the source system (for idempotent upsert)."
    )
    source_ref: str | None = Field(
        default=None,
        description="Provenance, e.g. 'connector://logistics_yonyou/order/123' or 'local://<hash>'.",
    )
    language: str | None = Field(default=None, description="ISO 639-1 language code, if known.")
    content_hash: str | None = Field(
        default=None, description="Hash of canonical payload for de-duplication."
    )
    metadata: dict[str, Any] | None = Field(
        default=None, description="Non-canonical extras kept for debugging / audit."
    )


def _get_by_path(raw: Any, path: str) -> Any:
    """Resolve a dotted path against a nested dict/list structure."""
    cur: Any = raw
    for part in path.split("."):
        if cur is None:
            return None
        if isinstance(cur, dict):
            cur = cur.get(part)
        elif isinstance(cur, list):
            try:
                cur = cur[int(part)]
            except (ValueError, IndexError):
                return None
        else:
            return None
    return cur


def _apply_transform(value: Any, transform: str | None) -> Any:
    """Apply a named transform to a single extracted value.

    Supported: ``to_upper``, ``to_lower``, ``to_iso_date`` (best-effort
    passthrough, downstream validators normalize), ``coalesce:<default>``.
    Unknown transforms are ignored (value returned unchanged) so a connector
    can introduce new transforms without breaking older FDE versions.
    """
    if not transform:
        return value
    name, _, arg = transform.partition(":")
    if name == "to_upper":
        return str(value).upper()
    if name == "to_lower":
        return str(value).lower()
    if name == "to_iso_date":
        return value
    if name == "coalesce":
        return value or arg
    return value


def apply_field_mapping(raw: dict[str, Any], mapping: FieldMapping) -> CanonicalDocument:
    """Apply a ``FieldMapping`` to a raw connector payload → ``CanonicalDocument``.

    Missing optional paths are skipped; missing *required* paths are reported in
    ``metadata['mapping_warnings']`` rather than raising, so one bad field never
    drops the whole document (defensive per ingestion design).
    """
    fields: dict[str, Any] = {}
    warnings: list[str] = []
    for rule in mapping.rules:
        value = _get_by_path(raw, rule.source_path)
        if value is None:
            if rule.required:
                warnings.append(f"required field missing: {rule.source_path}")
            continue
        fields[rule.target_field] = _apply_transform(value, rule.transform)

    return CanonicalDocument(
        doc_type=mapping.doc_type,
        title=str(fields.get("title") or fields.get("name") or mapping.doc_type),
        fields=fields,
        metadata=({"mapping_warnings": warnings} if warnings else None),
    )


__all__ = [
    "CanonicalDocument",
    "ConnectorManifest",
    "FieldMapping",
    "FieldMappingRule",
    "apply_field_mapping",
    "is_valid_semver",
    "major_version",
]
