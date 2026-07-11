"""Unit tests for the connector contract models (P0 deliverable, F6 versioning)."""

from __future__ import annotations

import pytest

from shared.contracts.connector_contract import (
    CanonicalDocument,
    ConnectorManifest,
    FieldMapping,
    FieldMappingRule,
    apply_field_mapping,
    is_valid_semver,
    major_version,
)


# -- semver helpers ----------------------------------------------------------
def test_is_valid_semver() -> None:
    assert is_valid_semver("1.0.0")
    assert is_valid_semver("1.2.3")
    assert is_valid_semver("10.0.0-rc.1")
    assert is_valid_semver("1.0.0+build.5")
    assert not is_valid_semver("v1")
    assert not is_valid_semver("1.0")
    assert not is_valid_semver("01.0.0")  # no leading zeros


def test_major_version() -> None:
    assert major_version("2.3.4") == 2
    assert major_version("10.0.0") == 10
    with pytest.raises(ValueError):
        major_version("not-semver")


# -- ConnectorManifest -------------------------------------------------------
def test_manifest_requires_valid_schema_version() -> None:
    with pytest.raises(ValueError):
        ConnectorManifest(schema_version="v1", connector_id="x", name="x")
    # valid
    m = ConnectorManifest(schema_version="1.0.0", connector_id="x", name="x")
    assert m.schema_version == "1.0.0"


def test_manifest_defaults() -> None:
    m = ConnectorManifest(schema_version="1.0.0", connector_id="logi", name="Logi")
    assert m.protocol == "rest"
    assert m.auth_type == "none"
    assert m.capabilities == []
    assert m.entity_types == []


# -- FieldMapping + apply ----------------------------------------------------
def test_apply_field_mapping_happy_path() -> None:
    raw = {
        "data": {
            "orderNo": "SO1",
            "customerName": "acme",
            "totalAmount": 100,
            "items": [{"sku": "A"}, {"sku": "B"}],
        }
    }
    mapping = FieldMapping(
        schema_version="1.0.0",
        connector_id="logi",
        doc_type="sales_order",
        rules=[
            FieldMappingRule(source_path="data.orderNo", target_field="order_no", required=True),
            FieldMappingRule(
                source_path="data.customerName", target_field="customer_name", transform="to_upper"
            ),
            FieldMappingRule(source_path="data.totalAmount", target_field="total_amount"),
            FieldMappingRule(source_path="items", target_field="items"),
        ],
    )
    doc = apply_field_mapping(raw, mapping)
    assert doc.doc_type == "sales_order"
    assert doc.fields["order_no"] == "SO1"
    assert doc.fields["customer_name"] == "ACME"  # transform applied? (noop here, kept)
    assert doc.fields["total_amount"] == 100
    assert doc.metadata is None  # no warnings


def test_apply_field_mapping_missing_required_warns_not_raises() -> None:
    raw = {"data": {"orderNo": "SO1"}}  # totalAmount (required) missing
    mapping = FieldMapping(
        schema_version="1.0.0",
        connector_id="logi",
        doc_type="sales_order",
        rules=[
            FieldMappingRule(source_path="data.orderNo", target_field="order_no", required=True),
            FieldMappingRule(
                source_path="data.totalAmount", target_field="total_amount", required=True
            ),
        ],
    )
    doc = apply_field_mapping(raw, mapping)
    assert doc.fields["order_no"] == "SO1"
    assert "total_amount" not in doc.fields
    assert doc.metadata is not None
    assert "mapping_warnings" in doc.metadata  # defensive: whole doc not dropped


def test_apply_field_mapping_list_index_path() -> None:
    raw = {"items": [{"sku": "X"}, {"sku": "Y"}]}
    mapping = FieldMapping(
        schema_version="1.0.0",
        connector_id="logi",
        doc_type="sales_order",
        rules=[FieldMappingRule(source_path="items.1.sku", target_field="second_sku")],
    )
    doc = apply_field_mapping(raw, mapping)
    assert doc.fields["second_sku"] == "Y"


def test_canonical_document_roundtrip_fields() -> None:
    cd = CanonicalDocument(
        doc_type="sales_order",
        title="SO1",
        fields={"a": 1},
        source_ref="connector://logi/sales_order/SO1",
    )
    assert cd.doc_type == "sales_order"
    assert cd.source_ref.startswith("connector://")
