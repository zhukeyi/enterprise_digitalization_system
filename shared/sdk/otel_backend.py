"""OpenTelemetry-compatible observability backend.

Provides a bridge between FDE's trace system and OTel/Langfuse backends.
In production, register a real backend; in dev, uses stdout.
"""

from __future__ import annotations

import logging
import os
import time
from typing import Any

logger = logging.getLogger("fde.sdk.otel")


class OTelBackend:
    """Stub OTel backend that logs spans to stdout/structured logger.

    In production, replace with real OTel exporter or Langfuse integration.
    """

    def __init__(self, service_name: str = "fde-ai-platform") -> None:
        self.service_name = service_name
        self._enabled = os.environ.get("FDE_OTEL_ENABLED", "0") == "1"

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
            logger.debug("OTel disabled, skipping span: %s", name)
            return

        duration_ms = ((end_time or time.time()) - start_time) * 1000
        logger.info(
            "trace=%s span=%s status=%s duration=%.1fms attrs=%s",
            trace_id,
            name,
            status,
            duration_ms,
            attributes or {},
        )


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
