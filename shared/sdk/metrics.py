"""FastAPI Prometheus metrics endpoint.

Provides standard HTTP metrics + FDE-specific business metrics.
Exposed at GET /metrics (Prometheus scrape target).

Usage:
    from shared.sdk.metrics import setup_metrics
    app = FastAPI()
    setup_metrics(app)
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable

from fastapi import FastAPI, Request, Response

logger = logging.getLogger("fde.sdk.metrics")

# Inline metrics implementation (no prometheus-client dependency)
# Uses Prometheus text format 0.0.4

_metrics_registry: dict[str, _Metric] = {}
_start_time = time.time()


class _Counter:
    """Simple counter metric."""

    def __init__(self, name: str, help_text: str, labels: list[str]) -> None:
        self.name = name
        self.help = help_text
        self.labels = labels
        self._data: dict[tuple[str, ...], int] = {}
        _metrics_registry[name] = self

    def inc(self, label_values: dict[str, str] | None = None) -> None:
        key = self._make_key(label_values)
        self._data[key] = self._data.get(key, 0) + 1

    def _make_key(self, label_values: dict[str, str] | None) -> tuple[str, ...]:
        if not label_values:
            return ()
        return tuple(label_values.get(l, "") for l in self.labels)

    def _render(self) -> str:
        lines = [f"# HELP {self.name} {self.help}", f"# TYPE {self.name} counter"]
        for key, val in self._data.items():
            if key:
                labels_str = ",".join(f'{self.labels[i]}="{key[i]}"' for i in range(len(key)))
                lines.append(f"{self.name}{{{labels_str}}} {val}")
            else:
                lines.append(f"{self.name} {val}")
        return "\n".join(lines)


class _Histogram:
    """Simple histogram metric."""

    def __init__(self, name: str, help_text: str, labels: list[str], buckets: list[float]) -> None:
        self.name = name
        self.help = help_text
        self.labels = labels
        self.buckets = buckets
        self._data: dict[tuple[str, ...], list[float]] = {}
        _metrics_registry[name] = self

    def observe(self, value: float, label_values: dict[str, str] | None = None) -> None:
        key = self._make_key(label_values)
        if key not in self._data:
            self._data[key] = []
        self._data[key].append(value)

    def _make_key(self, label_values: dict[str, str] | None) -> tuple[str, ...]:
        if not label_values:
            return ()
        return tuple(label_values.get(l, "") for l in self.labels)

    def _render(self) -> str:
        name = self.name
        lines = [f"# HELP {name} {self.help}", f"# TYPE {name} histogram"]
        for key, values in self._data.items():
            if not values:
                continue
            labels_str = ",".join(f'{self.labels[i]}="{key[i]}"' for i in range(len(key))) if key else ""
            total = len(values)
            total_sum = sum(values)
            bucket_counts: dict[float, int] = {b: sum(1 for v in values if v <= b) for b in self.buckets}

            label_prefix = f"{name}_bucket{{{labels_str},le=" if labels_str else f"{name}_bucket{{le="

            for bucket in self.buckets:
                lines.append(f'{label_prefix}"{bucket}"}} {bucket_counts[bucket]}')
            lines.append(f'{label_prefix}"+Inf"}} {total}')
            lines.append(f"{name}_sum{{{labels_str}}} {total_sum}" if labels_str else f"{name}_sum {total_sum}")
            lines.append(f"{name}_count{{{labels_str}}} {total}" if labels_str else f"{name}_count {total}")
        return "\n".join(lines)


class _Gauge:
    """Simple gauge metric."""

    def __init__(self, name: str, help_text: str, labels: list[str]) -> None:
        self.name = name
        self.help = help_text
        self.labels = labels
        self._data: dict[tuple[str, ...], float] = {}
        _metrics_registry[name] = self

    def set(self, value: float, label_values: dict[str, str] | None = None) -> None:
        key = self._make_key(label_values)
        self._data[key] = value

    def _make_key(self, label_values: dict[str, str] | None) -> tuple[str, ...]:
        if not label_values:
            return ()
        return tuple(label_values.get(l, "") for l in self.labels)

    def _render(self) -> str:
        lines = [f"# HELP {self.name} {self.help}", f"# TYPE {self.name} gauge"]
        for key, val in self._data.items():
            if key:
                labels_str = ",".join(f'{self.labels[i]}="{key[i]}"' for i in range(len(key)))
                lines.append(f"{self.name}{{{labels_str}}} {val}")
            else:
                lines.append(f"{self.name} {val}")
        return "\n".join(lines)


# Alias for type hinting
_Metric = _Counter | _Histogram | _Gauge


# ══════════════════════════════════════════════════════════════════
# FDE Business Metrics
# ══════════════════════════════════════════════════════════════════

http_requests_total = _Counter(
    "fde_http_requests_total",
    "Total HTTP requests",
    ["method", "endpoint", "status"],
)

http_request_duration_seconds = _Histogram(
    "fde_http_request_duration_seconds",
    "HTTP request duration in seconds",
    ["method", "endpoint"],
    [0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 5.0, 10.0],
)

worker_tasks_total = _Counter(
    "fde_worker_tasks_total",
    "Total worker task executions",
    ["worker_name", "status"],
)

tool_calls_total = _Counter(
    "fde_tool_calls_total",
    "Total tool invocations",
    ["tool_name"],
)

rag_search_duration_seconds = _Histogram(
    "fde_rag_search_duration_seconds",
    "RAG search duration in seconds",
    ["strategy"],
    [0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 5.0],
)

active_sessions = _Gauge(
    "fde_active_sessions",
    "Currently active sessions",
    [],
)

# ══════════════════════════════════════════════════════════════════
# Middleware
# ══════════════════════════════════════════════════════════════════


async def _metrics_middleware(request: Request, call_next: Callable) -> Response:
    """Record HTTP metrics for every request."""
    start = time.time()
    response = await call_next(request)
    duration = time.time() - start

    # Extract endpoint for aggregation (truncate IDs)
    path = request.url.path
    # Normalize dynamic segments: /im/webhook/wecom -> /im/webhook/{platform}
    parts = path.split("/")
    normalized = "/".join(parts[:3]) if len(parts) > 3 else path

    http_requests_total.inc({"method": request.method, "endpoint": normalized, "status": str(response.status_code)})
    http_request_duration_seconds.observe(duration, {"method": request.method, "endpoint": normalized})

    return response


def setup_metrics(app: FastAPI) -> None:
    """Register metrics middleware and /metrics endpoint on a FastAPI app."""

    @app.middleware("http")
    async def metrics_middleware(request: Request, call_next: Callable) -> Response:
        return await _metrics_middleware(request, call_next)

    @app.get("/metrics")
    async def metrics_endpoint() -> Response:
        """Prometheus metrics endpoint."""
        lines = [_render_all_metrics()]
        # Add process uptime
        uptime = time.time() - _start_time
        lines.append(f"# HELP fde_process_uptime_seconds Process uptime in seconds")
        lines.append(f"# TYPE fde_process_uptime_seconds gauge")
        lines.append(f"fde_process_uptime_seconds {uptime:.0f}")

        return Response(content="\n".join(lines) + "\n", media_type="text/plain; version=0.0.4")

    logger.info("Prometheus metrics endpoint registered at /metrics")


def _render_all_metrics() -> str:
    """Render all registered metrics in Prometheus text format."""
    parts: list[str] = []
    for name, metric in _metrics_registry.items():
        parts.append(metric._render())
    return "\n".join(parts)


# ══════════════════════════════════════════════════════════════════
# Convenience Functions
# ══════════════════════════════════════════════════════════════════


def record_worker_task(worker_name: str, status: str) -> None:
    """Record a worker task execution."""
    worker_tasks_total.inc({"worker_name": worker_name, "status": status})


def record_tool_call(tool_name: str) -> None:
    """Record a tool invocation."""
    tool_calls_total.inc({"tool_name": tool_name})


def record_rag_search(duration: float, strategy: str = "hybrid") -> None:
    """Record RAG search duration."""
    rag_search_duration_seconds.observe(duration, {"strategy": strategy})


def set_active_sessions(count: int) -> None:
    """Set the current active session count."""
    active_sessions.set(float(count))