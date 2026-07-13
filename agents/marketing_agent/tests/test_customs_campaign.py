"""End-to-end integration test for the customs → GEO campaign pipeline (P1-C, C-12).

Exercises the full chain adapters → C-8 segments → C-9 content → C-10 push
(+ compliance gates) → C-11 ROI over the FastAPI router, using an in-memory
customs store (no disk, no network).
"""

from __future__ import annotations

import asyncio

from fastapi.testclient import TestClient

from agents.data_agent.customs_models import BuyerEntity
from agents.data_agent.customs_store import CustomsStore
from agents.marketing_agent.customs_campaign_router import set_store
from agents.router_agent.main import app

_UNSUB = "https://fde.local/unsubscribe"


def _seed_store() -> CustomsStore:
    store = CustomsStore(":memory:")
    asyncio.run(store.init())
    buyers = [
        BuyerEntity(
            raw_name="Globex Corp", normalized_name="globex corp",
            country="US", source_country="CN",
            import_count=30, total_value_usd=500_000.0,
            top_hs_codes=["8517", "8471"], top_ports=["Shanghai"],
            first_seen="2023-01-01", last_seen="2026-03-01",
        ),
        BuyerEntity(
            raw_name="Initech LLC", normalized_name="initech llc",
            country="US", source_country="CN",
            import_count=8, total_value_usd=120_000.0,
            top_hs_codes=["8517"], top_ports=["Shanghai"],
            first_seen="2023-01-01", last_seen="2025-06-01",
        ),
        BuyerEntity(
            raw_name="Stark Industries", normalized_name="stark industries",
            country="US", source_country="CN",
            import_count=12, total_value_usd=300_000.0,
            top_hs_codes=["8708"], top_ports=["Los Angeles"],
            first_seen="2022-01-01", last_seen="2024-01-01",
        ),
        # sanctioned → must be blocked from outreach (R3)
        BuyerEntity(
            raw_name="SANCTIONED SAMPLE CORP", normalized_name="sanctioned sample corp",
            country="RU", source_country="CN",
            import_count=50, total_value_usd=900_000.0,
            top_hs_codes=["8517"], top_ports=["Shanghai"],
            first_seen="2023-01-01", last_seen="2026-01-01",
        ),
        # second sanctioned buyer in its own cell → fully BLOCKED segment (R3)
        BuyerEntity(
            raw_name="BLOCKED EXAMPLE HOLDINGS", normalized_name="blocked example holdings",
            country="RU", source_country="CN",
            import_count=3, total_value_usd=40_000.0,
            top_hs_codes=["6109"], top_ports=["Ningbo"],
            first_seen="2020-01-01", last_seen="2021-01-01",
        ),
    ]
    asyncio.run(store.upsert_buyers(buyers))
    return store


client = TestClient(app)


def setup_module(_):
    set_store(_seed_store())


def teardown_module(_):
    set_store(None)


def _clean_segment_id():
    resp = client.get("/api/customs-campaign/segments")
    assert resp.status_code == 200
    for s in resp.json():
        if s["compliance_status"] == "passed" and s["deliverable_count"] > 0:
            return s["segment_id"]
    raise AssertionError("no clean segment found")


def test_segments_built_with_compliance_split():
    resp = client.get("/api/customs-campaign/segments")
    assert resp.status_code == 200
    segs = resp.json()
    assert segs
    # the sanctioned buyer forms a blocked segment
    assert any(s["compliance_status"] == "blocked" for s in segs)
    # sanctioned buyer excluded from any deliverable set
    for s in segs:
        assert "SANCTIONED SAMPLE CORP" not in [b["name"] for b in s["deliverable_buyers"]]


def test_overview_summary():
    resp = client.get("/api/customs-campaign/overview")
    assert resp.status_code == 200
    ov = resp.json()
    assert ov["outreach_ready"] >= 1
    assert ov["blocked_segments"] >= 1
    assert ov["total_deliverable_buyers"] >= 3
    assert ov["total_blocked_buyers"] >= 1


def test_content_generation():
    sid = _clean_segment_id()
    resp = client.post(
        "/api/customs-campaign/content",
        json={"segment_id": sid, "brand": "云栖智能", "target_langs": ["en", "ja"]},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["geo_piece"]["geo_optimized"] is True
    assert "en" in data["multilingual"]["pieces"]
    assert data["keywords"]


def test_push_email_corporate_allowed():
    sid = _clean_segment_id()
    resp = client.post(
        "/api/customs-campaign/push",
        json={
            "segment_id": sid,
            "channel": "email",
            "address": "marketing@acme-corp.com",
            "brand": "云栖智能",
            "email": "marketing@acme-corp.com",
            "consent": True,
            "unsubscribe_url": _UNSUB,
        },
    )
    assert resp.status_code == 200
    assert resp.json()["success"] is True


def test_push_blocked_segment_refused():
    # find the blocked segment
    segs = client.get("/api/customs-campaign/segments").json()
    blocked = next(s for s in segs if s["compliance_status"] == "blocked")
    resp = client.post(
        "/api/customs-campaign/push",
        json={
            "segment_id": blocked["segment_id"],
            "channel": "webhook",
            "address": "https://hook.example.com",
            "brand": "云栖智能",
        },
    )
    assert resp.status_code == 200
    assert resp.json()["success"] is False


def test_roi_attribution_with_prediction():
    resp = client.post(
        "/api/customs-campaign/roi",
        json={"total_budget": 80_000.0},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["blended_roas"] > 0
    # ≥2 deliverable segments → OLS prediction fires
    assert data["roi_prediction"] is not None
    assert data["roi_prediction"]["spend"] == 80_000.0


def test_unknown_segment_404():
    resp = client.post(
        "/api/customs-campaign/content",
        json={"segment_id": "does-not-exist", "brand": "X"},
    )
    assert resp.status_code == 404


def test_push_im_channel_allowed():
    """IM channel (enterprise IM) is a valid push channel — no PII required."""
    sid = _clean_segment_id()
    resp = client.post(
        "/api/customs-campaign/push",
        json={
            "segment_id": sid,
            "channel": "im",
            "address": "https://im.example.com/webhook",
            "brand": "云栖智能",
        },
    )
    assert resp.status_code == 200
    # IM channel should succeed (no email/consent gate needed)
    assert resp.json()["success"] is True


def test_content_with_brand_id():
    """Content generation with brand_id fuses brand keyword plan (C-9)."""
    sid = _clean_segment_id()
    resp = client.post(
        "/api/customs-campaign/content",
        json={
            "segment_id": sid,
            "brand": "云栖智能",
            "brand_id": "BRAND-001",
            "target_langs": ["en"],
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["geo_piece"]["geo_optimized"] is True
    assert data["keywords"]


def test_segment_id_format_is_url_safe():
    """F1 regression: segment_id must not contain pipe characters."""
    resp = client.get("/api/customs-campaign/segments")
    assert resp.status_code == 200
    for s in resp.json():
        assert "|" not in s["segment_id"], (
            f"segment_id contains pipe: {s['segment_id']}"
        )
        assert "--" in s["segment_id"], (
            f"segment_id should use -- delimiter: {s['segment_id']}"
        )
