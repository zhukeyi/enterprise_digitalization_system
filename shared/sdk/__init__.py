"""FDE Platform — unified observability SDK adaptation layer.

All agents MUST use this module instead of directly depending
on Langfuse / Braintrust / OpenTelemetry SDKs.

This ensures:
- Consistent Trace ID propagation across all modules
- Easy swap of observability backends
- PII auto-masking before data leaves the VPC
"""

from __future__ import annotations

import functools
import os
import time
import uuid
from collections.abc import Callable
from typing import Any, TypeVar

F = TypeVar("F", bound=Callable[..., Any])

# ── Trace Context ──────────────────────────────────────────────────

_TRACE_ID_HEADER = "X-Trace-Id"
_PII_PATTERNS = {"email", "phone", "password", "secret", "token", "api_key", "ssn"}


class TraceContext:
    """Thread-local trace context with automatic span management."""

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


# ── Decorator ──────────────────────────────────────────────────────


def traced(name: str | None = None) -> Callable[[F], F]:
    """Decorator that creates a span around a function call.

    Args:
        name: Span name; defaults to function name.

    Usage:
        @traced("rag_retrieve")
        async def retrieve(query: str) -> list[Document]:
            ...
    """

    def decorator(func: F) -> F:
        @functools.wraps(func)
        async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
            span_name = name or func.__name__
            # Simplified: in production, use real Langfuse/OTel SDK
            start = time.time()
            try:
                result = await func(*args, **kwargs)
                elapsed = (time.time() - start) * 1000
                _log_trace(span_name, "success", elapsed)
                return result
            except Exception as e:
                elapsed = (time.time() - start) * 1000
                _log_trace(span_name, f"error: {e}", elapsed)
                raise

        @functools.wraps(func)
        def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
            span_name = name or func.__name__
            start = time.time()
            try:
                result = func(*args, **kwargs)
                elapsed = (time.time() - start) * 1000
                _log_trace(span_name, "success", elapsed)
                return result
            except Exception as e:
                elapsed = (time.time() - start) * 1000
                _log_trace(span_name, f"error: {e}", elapsed)
                raise

        import asyncio

        if asyncio.iscoroutinefunction(func):
            return async_wrapper  # type: ignore[return-value]
        return sync_wrapper  # type: ignore[return-value]

    return decorator


# ── Internal ───────────────────────────────────────────────────────


def _log_trace(name: str, status: str, latency_ms: float) -> None:
    """Stub: writes trace to stdout. Replace with Langfuse in production."""
    level = "WARN" if "error" in status else "INFO"
    trace_id = os.environ.get("TRACE_ID", "local")
    print(f"[{level}] trace={trace_id} span={name} status={status} latency={latency_ms:.1f}ms")


# ── Backend Registration (to be wired later) ──────────────────────

_registered_backends: dict[str, Any] = {}


def register_backend(name: str, backend: Any) -> None:
    """Register an observability backend (Langfuse, Braintrust, etc.)."""
    _registered_backends[name] = backend


def get_backend(name: str) -> Any | None:
    """Get a registered observability backend."""
    return _registered_backends.get(name)
