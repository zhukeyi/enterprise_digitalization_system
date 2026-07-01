"""Thread-safe trace context using contextvars.

Provides per-request/per-task trace isolation without thread-local issues.
"""

from __future__ import annotations

import contextvars
import time
import uuid
from typing import Any

from shared.sdk import sanitize_pii

# Context variable for the current trace
_current_trace: contextvars.ContextVar[TraceContext | None] = contextvars.ContextVar(
    "fde_trace", default=None
)


class TraceContext:
    """Thread-safe trace context using contextvars."""

    def __init__(self, trace_id: str | None = None) -> None:
        self.trace_id: str = trace_id or str(uuid.uuid4())
        self._spans: list[dict[str, Any]] = []

    def start_span(self, name: str, metadata: dict[str, Any] | None = None) -> str:
        span_id = str(uuid.uuid4())[:8]
        self._spans.append(
            {
                "span_id": span_id,
                "name": name,
                "start": time.time(),
                "metadata": sanitize_pii(metadata or {}),
            }
        )
        return span_id

    def end_span(self, span_id: str, metadata: dict[str, Any] | None = None) -> None:
        for span in self._spans:
            if span["span_id"] == span_id:
                span["end"] = time.time()
                span["duration_ms"] = (span["end"] - span["start"]) * 1000
                if metadata:
                    span["output"] = sanitize_pii(metadata)
                break


def get_current_trace() -> TraceContext | None:
    """Get the current trace context for this async/thread context."""
    return _current_trace.get()


def set_current_trace(ctx: TraceContext) -> contextvars.ContextVar.Token[TraceContext | None]:
    """Set the current trace context. Returns a token for reset."""
    return _current_trace.set(ctx)


def reset_current_trace(
    token: contextvars.ContextVar.Token[TraceContext | None],
) -> None:
    """Reset the trace context to its previous value."""
    _current_trace.reset(token)
