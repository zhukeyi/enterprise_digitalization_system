"""API Key authentication & rate-limiting middleware.

Checks for X-API-Key header, validates the key, and enforces
per-key rate limits (TPM/RPM). Falls back gracefully: if no key
is provided, request proceeds as anonymous (for public endpoints).

This is for the observability API management feature — it does NOT
replace the governance_agent AuthMiddleware (JWT + RBAC).
"""

from __future__ import annotations

import logging

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import JSONResponse

from agents.observability_agent.api_keys import (
    check_rate_limit,
    validate_api_key,
)

logger = logging.getLogger("fde.observability.auth")

# Paths that never require an API key (public health/monitoring)
_PUBLIC_PREFIXES = (
    "/health",
    "/healthz",
    "/readyz",
    "/livez",
    "/docs",
    "/redoc",
    "/openapi.json",
    "/metrics",
    "/api/observability/overview",
    "/api/observability/health",
)


class APIKeyMiddleware(BaseHTTPMiddleware):
    """Validate API key and enforce rate limits."""

    async def dispatch(
        self, request, call_next: RequestResponseEndpoint
    ):
        # Check if path is public (no key required)
        path = request.url.path
        is_public = any(path.startswith(p) for p in _PUBLIC_PREFIXES)

        api_key = request.headers.get("X-API-Key", "")
        key_info = None

        if api_key:
            key_info = validate_api_key(api_key)
            if key_info is None:
                return JSONResponse(
                    status_code=401,
                    content={"error": "Invalid or disabled API key"},
                )
        elif not is_public:
            # No key on a protected path — allow but mark anonymous
            # (Real auth is handled by governance_auth when FDE_ENABLE_AUTH=1)
            pass

        # Rate limit check (only if key provided)
        if key_info:
            _raw_tokens = request.headers.get("X-Token-Estimate", "0") or "0"
            try:
                est_tokens = int(_raw_tokens)
            except (ValueError, TypeError):
                est_tokens = 0
            allowed, reason = check_rate_limit(
                key_id=key_info["key_id"],
                tokens=est_tokens,
            )
            if not allowed:
                return JSONResponse(
                    status_code=429,
                    content={"error": reason, "retry_after": 60},
                    headers={"Retry-After": "60"},
                )

        # Store key info for downstream use
        if key_info:
            request.state.api_key_id = key_info["key_id"]
            request.state.api_key_name = key_info["name"]
            request.state.api_user_id = key_info["user_id"]

        response = await call_next(request)
        return response
