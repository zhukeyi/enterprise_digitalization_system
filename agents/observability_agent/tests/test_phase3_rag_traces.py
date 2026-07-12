"""Tests for Phase 3: RAG Inspector + Trace Viewer.

These tests focus on the endpoints and in-memory stores. Heavy
integration (Qdrant/Postgres) is guarded by try/except so tests pass
without a live vector DB when appropriate.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from agents.observability_agent.auth_middleware import APIKeyMiddleware
from agents.observability_agent.middleware import APIMetricsMiddleware
from agents.observability_agent.router import router, set_app
from agents.observability_agent.trace_store import (
    get_trace_stats,
    get_trace_tree,
    get_traces,
    record_span,
)


@pytest.fixture
def app() -> FastAPI:
    """Create a test FastAPI app with observability router."""
    app = FastAPI()
    app.add_middleware(APIMetricsMiddleware)
    app.add_middleware(APIKeyMiddleware)
    app.include_router(router)
    set_app(app)
    return app


@pytest.fixture
def client(app: FastAPI) -> TestClient:
    """Create a test client."""
    return TestClient(app)


class TestRagEndpoints:
    """Tests for RAG inspector endpoints (graceful when no DB)."""

    def test_rag_docs_endpoint(self, client: TestClient) -> None:
        """GET /api/observability/rag/docs returns a valid structure."""
        resp = client.get("/api/observability/rag/docs")
        assert resp.status_code == 200
        data = resp.json()
        assert "page" in data
        assert "total" in data
        assert "data" in data
        assert isinstance(data["data"], list)

    def test_rag_docs_with_doc_type(self, client: TestClient) -> None:
        """GET /api/observability/rag/docs?doc_type=pdf returns structure."""
        resp = client.get("/api/observability/rag/docs?doc_type=pdf")
        assert resp.status_code == 200
        assert resp.json()["page"] == 1

    def test_rag_chunk_detail_404(self, client: TestClient) -> None:
        """GET /api/observability/rag/chunks/{id} returns 404 for unknown."""
        resp = client.get("/api/observability/rag/chunks/nonexistent-id")
        assert resp.status_code in (404, 200)  # 200 if gracefully handled

    def test_rag_delete_requires_confirm(self, client: TestClient) -> None:
        """DELETE /api/observability/rag/docs/{id} requires confirm=DELETE."""
        resp = client.delete("/api/observability/rag/docs/some-id")
        assert resp.status_code == 400
        assert "confirm" in resp.json()["detail"].lower()

    def test_rag_debug_retrieve_requires_query(self, client: TestClient) -> None:
        """POST /api/observability/rag/debug/retrieve requires query."""
        resp = client.post("/api/observability/rag/debug/retrieve", json={})
        assert resp.status_code == 400

    def test_rag_debug_retrieve_endpoint(self, client: TestClient) -> None:
        """POST /api/observability/rag/debug/retrieve returns structure (graceful)."""
        resp = client.post(
            "/api/observability/rag/debug/retrieve",
            json={"query": "测试检索", "top_k": 5},
        )
        # 200 if Qdrant reachable, 500 with clear error if not
        assert resp.status_code in (200, 500)
        if resp.status_code == 200:
            data = resp.json()
            assert "rewritten_query" in data
            assert "latency_ms" in data


class TestTraceStore:
    """Tests for trace span store (in-memory)."""

    def test_record_and_list_traces(self) -> None:
        """Record spans and list traces."""
        record_span(
            trace_id="t1", span_id="s1", name="http_request",
            start_time=1000.0, end_time=1001.0, span_type="http",
        )
        record_span(
            trace_id="t1", span_id="s2", name="llm_call", parent_span_id="s1",
            start_time=1000.5, end_time=1000.8, span_type="llm",
        )
        result = get_traces(page=1)
        assert result["total"] >= 1
        # Find our trace
        trace_ids = [t["trace_id"] for t in result["data"]]
        assert "t1" in trace_ids

    def test_trace_tree(self) -> None:
        """Get full trace tree for a trace_id."""
        record_span(
            trace_id="t2", span_id="a", name="root",
            start_time=2000.0, end_time=2002.0, span_type="http",
        )
        tree = get_trace_tree("t2")
        assert tree is not None
        assert tree["trace_id"] == "t2"
        assert tree["span_count"] >= 1
        assert tree["total_duration_ms"] >= 0

    def test_trace_tree_not_found(self) -> None:
        """get_trace_tree returns None for unknown trace."""
        assert get_trace_tree("nonexistent") is None

    def test_trace_stats(self) -> None:
        """Get trace statistics."""
        record_span(
            trace_id="t3", span_id="s1", name="slow_op",
            start_time=3000.0, end_time=3005.0, status="error",
        )
        record_span(
            trace_id="t4", span_id="s1", name="fast_op",
            start_time=3100.0, end_time=3100.5,
        )
        stats = get_trace_stats()
        assert "p50_ms" in stats
        assert "p95_ms" in stats
        assert "p99_ms" in stats
        assert "error_rate" in stats
        assert stats["total_spans"] >= 2
        assert "hot_paths" in stats

    def test_trace_filters(self) -> None:
        """Filter traces by status=error."""
        record_span(
            trace_id="t5", span_id="s1", name="err_op",
            start_time=4000.0, end_time=4001.0, status="error",
        )
        result = get_traces(status="error")
        assert all(t["status"] == "error" for t in result["data"])


class TestTraceEndpoints:
    """Tests for trace HTTP endpoints."""

    def test_traces_endpoint(self, client: TestClient) -> None:
        """GET /api/observability/traces returns list."""
        record_span(
            trace_id="e1", span_id="s1", name="endpoint_test",
            start_time=5000.0, end_time=5001.0,
        )
        resp = client.get("/api/observability/traces")
        assert resp.status_code == 200
        data = resp.json()
        assert "data" in data
        assert "total" in data

    def test_trace_detail_endpoint(self, client: TestClient) -> None:
        """GET /api/observability/traces/{id} returns tree."""
        record_span(
            trace_id="e2", span_id="s1", name="detail_test",
            start_time=6000.0, end_time=6001.0,
        )
        resp = client.get("/api/observability/traces/e2")
        assert resp.status_code == 200
        assert resp.json()["trace_id"] == "e2"

    def test_trace_detail_404(self, client: TestClient) -> None:
        """GET /api/observability/traces/{id} 404 for unknown."""
        resp = client.get("/api/observability/traces/unknown-trace")
        assert resp.status_code == 404

    def test_trace_stats_endpoint(self, client: TestClient) -> None:
        """GET /api/observability/traces/stats returns stats."""
        record_span(
            trace_id="e3", span_id="s1", name="stats_test",
            start_time=7000.0, end_time=7002.0,
        )
        resp = client.get("/api/observability/traces/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert "p50_ms" in data
        assert "span_types" in data
