"""Observability backend registration."""

from __future__ import annotations

import logging
import os
from typing import Any

__all__ = [
    "_log_trace",
    "_registered_backends",
    "get_backend",
    "register_backend",
]

logger = logging.getLogger("fde.sdk.backends")


def _log_trace(name: str, status: str, latency_ms: float) -> None:
    """Log a trace span using structured logging. Replace with Langfuse in production."""
    trace_id = os.environ.get("TRACE_ID", "local")
    if "error" in status:
        logger.warning(
            "trace=%s span=%s status=%s latency=%.1fms", trace_id, name, status, latency_ms
        )
    else:
        logger.info("trace=%s span=%s status=%s latency=%.1fms", trace_id, name, status, latency_ms)


# ── Backend Registration (to be wired later) ──────────────────────

_registered_backends: dict[str, Any] = {}


def register_backend(name: str, backend: Any) -> None:
    """Register an observability backend (Langfuse, Braintrust, etc.)."""
    _registered_backends[name] = backend


def get_backend(name: str) -> Any | None:
    """Get a registered observability backend."""
    return _registered_backends.get(name)
