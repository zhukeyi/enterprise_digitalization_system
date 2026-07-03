"""Trace context and PII sanitization."""

from __future__ import annotations

import contextvars
import time
import uuid
from typing import Any

__all__ = ["TraceContext", "get_current_trace", "get_trace_id", "sanitize_pii"]

_TRACE_ID_HEADER = "X-Trace-Id"
_PII_PATTERNS = {"email", "phone", "password", "secret", "token", "api_key", "ssn"}

# ContextVar for async-safe trace context propagation
_current_trace: contextvars.ContextVar[TraceContext | None] = contextvars.ContextVar(
    "_current_trace", default=None
)


class TraceContext:
    """Async-safe trace context using contextvars for propagation across tasks."""

    def __init__(self, trace_id: str | None = None) -> None:
        self.trace_id: str = trace_id or str(uuid.uuid4())
        self.spans: list[dict[str, Any]] = []

    def start_span(self, name: str, metadata: dict[str, Any] | None = None) -> str:
        span_id = str(uuid.uuid4())[:8]
        self.spans.append(
            {
                "span_id": span_id,
                "name": name,
                "start": time.time(),
                "metadata": sanitize_pii(metadata or {}),
            }
        )
        return span_id

    def end_span(self, span_id: str, metadata: dict[str, Any] | None = None) -> None:
        for span in self.spans:
            if span["span_id"] == span_id:
                span["end"] = time.time()
                span["duration_ms"] = (span["end"] - span["start"]) * 1000
                if metadata:
                    span["output"] = sanitize_pii(metadata)
                break

    def __enter__(self) -> TraceContext:
        _current_trace.set(self)
        return self

    def __exit__(self, *exc: Any) -> None:
        _current_trace.set(None)


def get_current_trace() -> TraceContext | None:
    """Get the current trace context from contextvars."""
    return _current_trace.get()


def get_trace_id(headers: dict[str, str] | None = None) -> str:
    """Extract or generate a trace ID from request headers."""
    if headers and _TRACE_ID_HEADER in headers:
        return headers[_TRACE_ID_HEADER]
    return str(uuid.uuid4())


def sanitize_pii(data: dict[str, Any]) -> dict[str, Any]:
    """Recursively mask PII keys in a dictionary."""
    result: dict[str, Any] = {}
    for key, value in data.items():
        key_lower = key.lower()
        if any(pattern in key_lower for pattern in _PII_PATTERNS):
            result[key] = "[MASKED]"
        elif isinstance(value, dict):
            result[key] = sanitize_pii(value)
        elif isinstance(value, list):
            result[key] = [sanitize_pii(item) if isinstance(item, dict) else item for item in value]
        else:
            result[key] = value
    return result
