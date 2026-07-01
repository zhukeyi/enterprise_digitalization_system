"""Observability backend registration."""

from __future__ import annotations

import os
from typing import Any

__all__ = [
    "_log_trace",
    "_registered_backends",
    "get_backend",
    "register_backend",
]


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
