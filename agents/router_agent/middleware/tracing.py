"""Tracing middleware — injects Trace ID into every request.

All requests get a unique X-Trace-Id header that propagates
through the entire call chain (gateway → adapter → model).
"""

from __future__ import annotations

import time
import uuid

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response
from starlette.types import ASGIApp


class TracingMiddleware(BaseHTTPMiddleware):
    """Adds X-Trace-Id header and logs request duration."""

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        trace_id = request.headers.get("X-Trace-Id", str(uuid.uuid4()))
        request.state.trace_id = trace_id
        start = time.monotonic()

        response = await call_next(request)

        elapsed = (time.monotonic() - start) * 1000
        response.headers["X-Trace-Id"] = trace_id
        response.headers["X-Response-Time-ms"] = f"{elapsed:.1f}"
        return response
