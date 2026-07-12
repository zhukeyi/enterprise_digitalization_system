"""Tests for observability agent health checks and endpoints."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from agents.observability_agent.health_checker import check_liveness
from agents.observability_agent.middleware import APIMetricsMiddleware, get_api_stats_summary
from agents.observability_agent.router import router, set_app


@pytest.fixture
def app() -> FastAPI:
    """Create a test FastAPI app with observability router."""
    app = FastAPI()
    app.add_middleware(APIMetricsMiddleware)
    app.include_router(router)
    set_app(app)
    return app


@pytest.fixture
def client(app: FastAPI) -> TestClient:
    """Create a test client."""
    return TestClient(app)


class TestHealthProbes:
    """Tests for three-tier health probes."""

    def test_healthz_returns_200(self, client: TestClient) -> None:
        """GET /api/observability/healthz returns 200 with healthy status."""
        resp = client.get("/api/observability/healthz")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "healthy"

    def test_livez_returns_status(self, client: TestClient) -> None:
        """GET /api/observability/livez returns alive status."""
        resp = client.get("/api/observability/livez")
        assert resp.status_code == 200
        data = resp.json()
        assert "status" in data
        assert "error_rate" in data

    def test_readyz_returns_components(self, client: TestClient) -> None:
        """GET /api/observability/readyz returns component list."""
        resp = client.get("/api/observability/readyz")
        assert resp.status_code == 200
        data = resp.json()
        assert "status" in data
        assert "components" in data
        assert isinstance(data["components"], list)

    def test_check_liveness_low_error_rate(self) -> None:
        """Liveness check passes with low error rate."""
        assert check_liveness(0.0) is True
        assert check_liveness(0.1) is True

    def test_check_liveness_high_error_rate(self) -> None:
        """Liveness check fails with high error rate."""
        assert check_liveness(0.6) is False
        assert check_liveness(1.0) is False


class TestOverview:
    """Tests for overview endpoint."""

    def test_overview_returns_health_score(self, client: TestClient) -> None:
        """GET /api/observability/overview returns health score and KPIs."""
        resp = client.get("/api/observability/overview")
        assert resp.status_code == 200
        data = resp.json()
        assert "health_score" in data
        assert 0 <= data["health_score"] <= 100
        assert "kpis" in data
        assert "modules" in data
        assert len(data["modules"]) > 0

    def test_overview_kpis_have_labels(self, client: TestClient) -> None:
        """KPI cards have proper labels."""
        resp = client.get("/api/observability/overview")
        data = resp.json()
        labels = [kpi["label"] for kpi in data["kpis"]]
        assert "QPS" in labels
        assert "Error Rate" in labels


class TestServiceMap:
    """Tests for service map endpoint."""

    def test_service_map_returns_nodes_and_edges(self, client: TestClient) -> None:
        """GET /api/observability/health/service-map returns nodes and edges."""
        resp = client.get("/api/observability/health/service-map")
        assert resp.status_code == 200
        data = resp.json()
        assert "nodes" in data
        assert "edges" in data
        assert len(data["nodes"]) > 10
        for node in data["nodes"]:
            assert "id" in node
            assert "status" in node


class TestAPIEndpointScan:
    """Tests for API endpoint auto-scan."""

    def test_list_endpoints_returns_list(self, client: TestClient) -> None:
        """GET /api/observability/api/endpoints returns list of endpoints."""
        resp = client.get("/api/observability/api/endpoints")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        # Should contain the observability endpoints themselves
        assert len(data) > 0
        paths = [e["path"] for e in data]
        # At least one endpoint should be from observability
        assert any("healthz" in p or "overview" in p or "endpoints" in p for p in paths)

    def test_api_stats_returns_summary(self, client: TestClient) -> None:
        """GET /api/observability/api/stats returns call statistics."""
        resp = client.get("/api/observability/api/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert "total_calls" in data
        assert "avg_latency_ms" in data
        assert "error_rate" in data


class TestAPIMetricsMiddleware:
    """Tests for API metrics middleware."""

    def test_middleware_records_calls(self, client: TestClient) -> None:
        """Middleware records API calls in ring buffer."""
        client.get("/api/observability/healthz")
        client.get("/api/observability/overview")
        stats = get_api_stats_summary()
        assert stats["total_calls"] > 0

    def test_middleware_records_latency(self, client: TestClient) -> None:
        """Middleware records latency for requests."""
        client.get("/api/observability/healthz")
        stats = get_api_stats_summary()
        assert stats["avg_latency_ms"] >= 0.0


class TestStubs:
    """Tests for stub endpoints (Phase 2/3/4 will implement fully)."""

    def test_token_usage_stub(self, client: TestClient) -> None:
        """Token usage endpoint returns stub response."""
        resp = client.get("/api/observability/tokens/usage")
        assert resp.status_code == 200
        data = resp.json()
        assert "data" in data

    def test_rag_docs_stub(self, client: TestClient) -> None:
        """RAG docs endpoint returns stub response."""
        resp = client.get("/api/observability/rag/docs")
        assert resp.status_code == 200
        data = resp.json()
        assert "total" in data

    def test_traces_stub(self, client: TestClient) -> None:
        """Traces endpoint returns stub response."""
        resp = client.get("/api/observability/traces")
        assert resp.status_code == 200
        data = resp.json()
        assert "total" in data

    def test_audit_logs_stub(self, client: TestClient) -> None:
        """Audit logs endpoint returns stub response."""
        resp = client.get("/api/observability/audit/logs")
        assert resp.status_code == 200
        data = resp.json()
        assert "total" in data
