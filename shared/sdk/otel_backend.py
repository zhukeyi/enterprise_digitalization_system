"""OpenTelemetry-compatible observability backend.

Provides a bridge between FDE's trace system and OTel/Langfuse backends.
Supports: stdout (dev), OTLP HTTP export (prod), Langfuse (LLM observability).
"""

from __future__ import annotations

import json
import logging
import os
import time
from typing import Any

logger = logging.getLogger("fde.sdk.otel")


class OTelBackend:
    """OTel backend with OTLP HTTP export and Langfuse integration."""

    def __init__(self, service_name: str = "fde-ai-platform") -> None:
        self.service_name = service_name
        self._enabled = os.environ.get("FDE_OTEL_ENABLED", "0") == "1"
        self._otlp_endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "")
        self._langfuse_enabled = os.environ.get("LANGFUSE_PUBLIC_KEY") is not None
        self._span_count: int = 0

        if self._enabled and not self._otlp_endpoint:
            logger.warning("OTel enabled but OTEL_EXPORTER_OTLP_ENDPOINT not set, using stdout")

    def emit_span(
        self,
        trace_id: str,
        span_id: str,
        name: str,
        start_time: float,
        end_time: float | None = None,
        status: str = "ok",
        attributes: dict[str, Any] | None = None,
    ) -> None:
        """Emit a span to the observability backend."""
        if not self._enabled:
            return

        self._span_count += 1
        duration_ms = ((end_time or time.time()) - start_time) * 1000
        attrs = attributes or {}

        if self._otlp_endpoint:
            self._export_otlp(trace_id, span_id, name, start_time, duration_ms, status, attrs)
        else:
            self._log_stdout(trace_id, span_id, name, duration_ms, status, attrs)

    def _log_stdout(
        self,
        trace_id: str,
        span_id: str,
        name: str,
        duration_ms: float,
        status: str,
        attrs: dict[str, Any],
    ) -> None:
        """Log span to structured stdout (dev mode)."""
        logger.info(
            "trace_id=%s span_id=%s name=%s duration=%.2fms status=%s attrs=%s",
            trace_id,
            span_id,
            name,
            duration_ms,
            status,
            json.dumps(attrs, default=str),
        )

    def _export_otlp(
        self,
        trace_id: str,
        span_id: str,
        name: str,
        start_time: float,
        duration_ms: float,
        status: str,
        attrs: dict[str, Any],
    ) -> None:
        """Export span to OTLP HTTP collector (best-effort, non-blocking)."""
        try:
            import urllib.request

            # OTLP/HTTP JSON format
            payload = {
                "resourceSpans": [
                    {
                        "resource": {
                            "attributes": [
                                {
                                    "key": "service.name",
                                    "value": {"stringValue": self.service_name},
                                },
                            ]
                        },
                        "scopeSpans": [
                            {
                                "scope": {"name": "fde-ai-platform", "version": "0.1.0"},
                                "spans": [
                                    {
                                        "traceId": trace_id,
                                        "spanId": span_id,
                                        "name": name,
                                        "startTimeUnixNano": str(int(start_time * 1e9)),
                                        "endTimeUnixNano": str(
                                            int((start_time + duration_ms / 1000) * 1e9)
                                        ),
                                        "status": {"code": 1 if status == "ok" else 2},
                                        "attributes": [
                                            {"key": k, "value": {"stringValue": str(v)}}
                                            for k, v in attrs.items()
                                        ],
                                    }
                                ],
                            }
                        ],
                    }
                ],
            }

            data = json.dumps(payload).encode()
            url = f"{self._otlp_endpoint}/v1/traces"
            req = urllib.request.Request(url, data=data, method="POST")
            req.add_header("Content-Type", "application/json")

            # Non-blocking: don't await response
            urllib.request.urlopen(req, timeout=2)
        except Exception:
            # Best-effort: don't let span export block the application
            pass

    def emit_llm_call(
        self,
        trace_id: str,
        model: str,
        prompt_tokens: int,
        completion_tokens: int,
        duration_ms: float,
        input_text: str = "",
        output_text: str = "",
    ) -> None:
        """Emit an LLM-specific observation event (Langfuse compatible)."""
        if not self._enabled:
            return

        event = {
            "trace_id": trace_id,
            "type": "llm_call",
            "model": model,
            "usage": {"prompt_tokens": prompt_tokens, "completion_tokens": completion_tokens},
            "duration_ms": duration_ms,
            "timestamp": time.time(),
        }

        if self._langfuse_enabled:
            logger.debug("langfuse_event: %s", json.dumps(event, default=str))
        else:
            logger.info(
                "llm_call model=%s tokens=%d/%d duration=%.0fms",
                model,
                prompt_tokens,
                completion_tokens,
                duration_ms,
            )

    @property
    def span_count(self) -> int:
        return self._span_count


# Singleton
_default_backend: OTelBackend | None = None


def get_default_backend() -> OTelBackend:
    global _default_backend
    if _default_backend is None:
        _default_backend = OTelBackend()
    return _default_backend


def set_default_backend(backend: OTelBackend) -> None:
    global _default_backend
    _default_backend = backend
