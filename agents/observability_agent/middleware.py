"""API metrics middleware — records per-request details for API management.

Stores last 10,000 requests in a ring buffer for API stats queries.
Does NOT duplicate Prometheus metrics (handled by shared/sdk/metrics.py).
"""

from __future__ import annotations

import time
from collections import deque
from typing import Any

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

# Ring buffer: (timestamp, method, path, status_code, latency_ms, user_id)
_api_call_buffer: deque[tuple[float, str, str, int, float, str]] = deque(maxlen=10000)


def get_api_calls() -> list[tuple[float, str, str, int, float, str]]:
    """Return a snapshot of recent API calls."""
    return list(_api_call_buffer)


def get_api_stats_summary() -> dict[str, Any]:
    """Compute aggregate stats from the ring buffer."""
    calls = list(_api_call_buffer)
    if not calls:
        return {"total_calls": 0, "avg_latency_ms": 0.0, "error_rate": 0.0}

    total = len(calls)
    errors = sum(1 for c in calls if c[3] >= 400)
    avg_latency = sum(c[4] for c in calls) / total
    now = time.time()
    recent_60s = [c for c in calls if now - c[0] < 60]
    qps = len(recent_60s) / 60.0 if recent_60s else 0.0

    return {
        "total_calls": total,
        "avg_latency_ms": round(avg_latency, 1),
        "error_rate": round(errors / total, 4),
        "qps": round(qps, 2),
    }


class APIMetricsMiddleware(BaseHTTPMiddleware):
    """Record per-request API metrics to ring buffer."""

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        start = time.monotonic()
        response = await call_next(request)
        latency = (time.monotonic() - start) * 1000

        # Extract user_id if auth is enabled
        user_id = ""
        try:
            if hasattr(request.state, "user"):
                user_id = str(getattr(request.state, "user", ""))
        except Exception:
            pass

        _api_call_buffer.append(
            (
                time.time(),
                request.method,
                request.url.path,
                response.status_code,
                round(latency, 1),
                user_id,
            )
        )

        return response
