"""Tests for metrics, logging, and OTel backend (M4-T4)."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from shared.sdk.metrics import (
    _render_all_metrics,
    http_request_duration_seconds,
    http_requests_total,
    record_rag_search,
    record_tool_call,
    record_worker_task,
    set_active_sessions,
    setup_metrics,
)


class TestMetricsCounter:
    def test_http_requests_counter(self) -> None:
        http_requests_total.inc({"method": "GET", "endpoint": "/test", "status": "200"})
        http_requests_total.inc({"method": "GET", "endpoint": "/test", "status": "200"})
        http_requests_total.inc({"method": "POST", "endpoint": "/test", "status": "201"})

        rendered = _render_all_metrics()
        assert 'fde_http_requests_total{method="GET",endpoint="/test",status="200"} 2' in rendered
        assert 'fde_http_requests_total{method="POST",endpoint="/test",status="201"} 1' in rendered

    def test_worker_tasks_counter(self) -> None:
        record_worker_task("rag_worker", "success")
        record_worker_task("rag_worker", "success")
        record_worker_task("rag_worker", "failed")

        rendered = _render_all_metrics()
        assert 'fde_worker_tasks_total{worker_name="rag_worker",status="success"} 2' in rendered
        assert 'fde_worker_tasks_total{worker_name="rag_worker",status="failed"} 1' in rendered

    def test_tool_calls_counter(self) -> None:
        record_tool_call("rag_search")
        record_tool_call("nl2sql")
        record_tool_call("rag_search")

        rendered = _render_all_metrics()
        assert 'fde_tool_calls_total{tool_name="rag_search"} 2' in rendered
        assert 'fde_tool_calls_total{tool_name="nl2sql"} 1' in rendered


class TestMetricsHistogram:
    def test_http_duration_histogram(self) -> None:
        http_request_duration_seconds.observe(0.05, {"method": "GET", "endpoint": "/test"})
        http_request_duration_seconds.observe(0.2, {"method": "GET", "endpoint": "/test"})

        rendered = _render_all_metrics()
        assert "fde_http_request_duration_seconds" in rendered
        # Should have bucket counts
        assert 'le="0.1"' in rendered

    def test_rag_search_histogram(self) -> None:
        record_rag_search(0.3, "hybrid")
        record_rag_search(0.8, "hybrid")
        record_rag_search(1.2, "vector")

        rendered = _render_all_metrics()
        assert "fde_rag_search_duration_seconds" in rendered
        assert 'strategy="hybrid"' in rendered
        assert 'strategy="vector"' in rendered


class TestMetricsGauge:
    def test_active_sessions_gauge(self) -> None:
        set_active_sessions(5)
        rendered = _render_all_metrics()
        assert "fde_active_sessions 5.0" in rendered

        set_active_sessions(0)
        rendered = _render_all_metrics()
        assert "fde_active_sessions 0.0" in rendered


class TestMetricsEndpoint:
    def test_metrics_endpoint_registered(self) -> None:
        app = FastAPI()
        setup_metrics(app)
        client = TestClient(app)

        response = client.get("/metrics")
        assert response.status_code == 200
        assert "text/plain" in response.headers["content-type"]
        assert "fde_http_requests_total" in response.text

    def test_metrics_endpoint_returns_uptime(self) -> None:
        app = FastAPI()
        setup_metrics(app)
        client = TestClient(app)

        response = client.get("/metrics")
        assert "fde_process_uptime_seconds" in response.text

    def test_metrics_middleware_records_request(self) -> None:
        app = FastAPI()
        setup_metrics(app)

        @app.get("/hello")
        async def hello() -> dict[str, str]:
            return {"message": "ok"}

        client = TestClient(app)
        client.get("/hello")
        client.get("/hello")

        response = client.get("/metrics")
        assert 'endpoint="/hello"' in response.text


class TestOTelBackend:
    def test_backend_disabled_by_default(self) -> None:
        from shared.sdk.otel_backend import OTelBackend

        backend = OTelBackend()
        assert backend.span_count == 0

        backend.emit_span("trace1", "span1", "test_op", 1000.0, 1000.1)
        # Disabled by default (FDE_OTEL_ENABLED=0), span_count unchanged
        assert backend.span_count == 0

    def test_backend_enabled(self) -> None:
        import os

        from shared.sdk.otel_backend import OTelBackend

        os.environ["FDE_OTEL_ENABLED"] = "1"
        try:
            backend = OTelBackend()
            backend.emit_span("trace2", "span2", "test_op2", 1000.0, 1000.1)
            assert backend.span_count == 1
        finally:
            os.environ["FDE_OTEL_ENABLED"] = "0"

    def test_llm_call_emission(self) -> None:
        import os

        from shared.sdk.otel_backend import OTelBackend

        os.environ["FDE_OTEL_ENABLED"] = "1"
        try:
            backend = OTelBackend()
            backend.emit_llm_call("trace3", "gpt-4", 100, 50, 1500.0, "Hello", "Hi there!")
            # Should not raise
        finally:
            os.environ["FDE_OTEL_ENABLED"] = "0"

    def test_singleton_pattern(self) -> None:
        from shared.sdk.otel_backend import get_default_backend

        b1 = get_default_backend()
        b2 = get_default_backend()
        assert b1 is b2

    def test_set_backend(self) -> None:
        from shared.sdk.otel_backend import OTelBackend, get_default_backend, set_default_backend

        custom = OTelBackend(service_name="custom")
        set_default_backend(custom)
        assert get_default_backend() is custom


class TestStructuredLogging:
    def test_json_formatter(self) -> None:
        import json
        import logging

        from shared.sdk.logging import JSONFormatter

        formatter = JSONFormatter()
        record = logging.LogRecord("test", logging.INFO, "path", 42, "test message", (), None)

        output = formatter.format(record)
        parsed = json.loads(output)

        assert parsed["level"] == "INFO"
        assert parsed["message"] == "test message"
        assert parsed["logger"] == "test"
        assert "timestamp" in parsed

    def test_json_formatter_with_exception(self) -> None:
        import json
        import logging

        from shared.sdk.logging import JSONFormatter

        formatter = JSONFormatter()
        try:
            raise ValueError("test error")
        except ValueError:
            record = logging.LogRecord(
                "test", logging.ERROR, "path", 42, "error occurred", (), None
            )
            record.exc_info = (ValueError, ValueError("test error"), None)

        output = formatter.format(record)
        parsed = json.loads(output)

        assert parsed["level"] == "ERROR"
        assert "test error" in parsed.get("exception", "")
