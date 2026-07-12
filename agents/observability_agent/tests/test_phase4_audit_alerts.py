"""Tests for Phase 4: Audit Trail + Alerting & Drift Detection."""

from __future__ import annotations

import csv
import io

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from agents.observability_agent.alerting import (
    _BASELINE,
    _compute_drift,
    delete_alert_rule,
    evaluate_alerts,
    get_alert_rules,
    set_alert_rule,
)
from agents.observability_agent.audit_store import (
    clear_audit_logs,
    export_audit_logs,
    get_audit_logs,
    record_audit_event,
)
from agents.observability_agent.auth_middleware import APIKeyMiddleware
from agents.observability_agent.middleware import APIMetricsMiddleware
from agents.observability_agent.router import router, set_app


@pytest.fixture
def app() -> FastAPI:
    a = FastAPI()
    a.add_middleware(APIMetricsMiddleware)
    a.add_middleware(APIKeyMiddleware)
    a.include_router(router)
    set_app(a)
    return a


@pytest.fixture
def client(app: FastAPI) -> TestClient:
    return TestClient(app)


# ── Audit store (unit) ──────────────────────────────────────────


class TestAuditStore:
    def setup_method(self) -> None:
        clear_audit_logs()

    def test_record_and_query(self) -> None:
        record_audit_event("admin", "api_key.create", "api_key", "k1", status="ok")
        record_audit_event("admin", "rag.document.delete", "document", "d1", status="failed")
        logs = get_audit_logs()
        assert logs["total"] == 2
        # newest first
        assert logs["data"][0]["action"] == "rag.document.delete"

    def test_filter_by_action(self) -> None:
        record_audit_event("admin", "api_key.create", "api_key", "k1")
        record_audit_event("admin", "rag.document.delete", "document", "d1")
        logs = get_audit_logs(action="api_key.create")
        assert logs["total"] == 1
        assert logs["data"][0]["action"] == "api_key.create"

    def test_filter_by_status(self) -> None:
        record_audit_event("admin", "x", "y", "1", status="ok")
        record_audit_event("admin", "x", "y", "2", status="failed")
        logs = get_audit_logs(status="failed")
        assert logs["total"] == 1

    def test_export_csv(self) -> None:
        record_audit_event("admin", "api_key.create", "api_key", "k1", detail="name=test")
        csv_text = export_audit_logs("csv")
        reader = csv.DictReader(io.StringIO(csv_text))
        rows = list(reader)
        assert len(rows) == 1
        assert rows[0]["action"] == "api_key.create"
        assert rows[0]["actor"] == "admin"

    def test_export_unsupported_format(self) -> None:
        raised = False
        try:
            export_audit_logs("pdf")
        except ValueError:
            raised = True
        assert raised, "expected ValueError for unsupported format"


# ── Alerting (unit) ─────────────────────────────────────────────


class TestAlerting:
    def test_default_rules_present(self) -> None:
        rules = get_alert_rules()
        ids = {r["id"] for r in rules}
        assert "error_rate_high" in ids
        assert "latency_p95_high" in ids
        assert "daily_cost_spike" in ids
        assert "budget_exceeded" in ids

    def test_set_and_delete_rule(self) -> None:
        set_alert_rule("test_rule", "error_rate", "gt", 0.5, severity="info")
        rules = {r["id"]: r for r in get_alert_rules()}
        assert "test_rule" in rules
        assert rules["test_rule"]["threshold"] == 0.5
        assert delete_alert_rule("test_rule") is True
        assert delete_alert_rule("test_rule") is False

    def test_evaluate_returns_structure(self) -> None:
        result = evaluate_alerts()
        assert "metrics" in result
        assert "triggered" in result
        assert "drift" in result
        assert "active_alerts" in result
        # triggered is always a list (may be non-empty if other tests
        # recorded error spans, raising the live error_rate above threshold)
        assert isinstance(result["triggered"], list)

    def test_drift_insufficient_data(self) -> None:
        _BASELINE.clear()
        report = _compute_drift()
        assert report["status"] == "insufficient_data"

    def test_drift_detection(self) -> None:
        _BASELINE.clear()
        # Seed a stable baseline
        for _ in range(31):
            _BASELINE.append({
                "ts_epoch": 1.0,
                "error_rate": 0.01,
                "p95_ms": 100.0,
                "daily_cost_usd": 1.0,
                "total_spans": 10,
            })
        # Push a drifted snapshot
        _BASELINE.append({
            "ts_epoch": 2.0,
            "error_rate": 0.5,
            "p95_ms": 100.0,
            "daily_cost_usd": 1.0,
            "total_spans": 10,
        })
        report = _compute_drift()
        assert report["status"] == "drift_detected"
        assert "error_rate" in report["drifted_metrics"]


# ── Endpoints (integration via TestClient) ──────────────────────


class TestAuditEndpoints:
    def test_audit_logs_endpoint(self, client: TestClient) -> None:
        record_audit_event("admin", "api_key.create", "api_key", "k1")
        resp = client.get("/api/observability/audit/logs")
        assert resp.status_code == 200
        assert "data" in resp.json()
        assert resp.json()["total"] >= 1

    def test_audit_export_endpoint(self, client: TestClient) -> None:
        record_audit_event("admin", "api_key.create", "api_key", "k1")
        resp = client.get("/api/observability/audit/export?format=csv")
        assert resp.status_code == 200
        assert "text/csv" in resp.headers.get("content-type", "")
        assert "api_key.create" in resp.text

    def test_alerts_endpoint(self, client: TestClient) -> None:
        resp = client.get("/api/observability/alerts")
        assert resp.status_code == 200
        assert "data" in resp.json()

    def test_alert_rules_endpoint(self, client: TestClient) -> None:
        resp = client.get("/api/observability/alerts/rules")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)
        assert len(resp.json()) >= 4

    def test_alert_rule_create_and_delete(self, client: TestClient) -> None:
        resp = client.post(
            "/api/observability/alerts/rules",
            json={"metric": "error_rate", "operator": "gt", "threshold": 0.9, "severity": "info"},
        )
        assert resp.status_code == 200
        rule_id = resp.json()["id"]
        del_resp = client.delete(f"/api/observability/alerts/rules/{rule_id}")
        assert del_resp.status_code == 200
        assert del_resp.json()["deleted"] is True

    def test_alert_evaluate_endpoint(self, client: TestClient) -> None:
        resp = client.post("/api/observability/alerts/evaluate")
        assert resp.status_code == 200
        data = resp.json()
        assert "metrics" in data
        assert "drift" in data

    def test_drift_endpoint(self, client: TestClient) -> None:
        resp = client.get("/api/observability/drift")
        assert resp.status_code == 200
        assert "status" in resp.json()

    def test_mutation_records_audit(self, client: TestClient) -> None:
        """Creating an API key should produce an audit event."""
        resp = client.post(
            "/api/observability/api/keys",
            json={"name": "audit-test-key", "user_id": "u1", "quota_tpm": 1000, "quota_rpm": 10},
        )
        assert resp.status_code == 200
        key_id = resp.json()["key_id"]
        # The creation must have produced exactly one matching audit event
        logs = get_audit_logs(action="api_key.create")
        matching = [e for e in logs["data"] if e["resource_id"] == key_id]
        assert len(matching) == 1
        assert matching[0]["resource_type"] == "api_key"
