"""AuthMiddleware — ASGI middleware for authentication enforcement.

This middleware runs BEFORE request reaches the route handler,
validating credentials on all non-public paths.

Strategy:
- Public paths (health, auth endpoints, docs) pass through unchecked.
- All other paths require valid JWT or API-Key token.
- Unauthenticated requests receive 401 with WWW-Authenticate header.
"""

from __future__ import annotations

import logging
from typing import Any

from jose import JWTError
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from agents.governance_agent.auth.security import decode_token

logger = logging.getLogger("fde.governance.auth")

# Public endpoints that do not require authentication
DEFAULT_PUBLIC_PREFIXES: tuple[str, ...] = (
    "/health",
    "/docs",
    "/redoc",
    "/openapi.json",
    "/auth/login",
    "/auth/register",
    "/auth/refresh",
)

# Header name for API key authentication
API_KEY_HEADER = "X-API-Key"


class AuthMiddleware(BaseHTTPMiddleware):
    """ASGI middleware that enforces authentication on protected routes.

    Must be added to the FastAPI app BEFORE route handlers execute.

    Args:
        app: The ASGI application.
        public_paths: Additional paths that skip auth checks.
    """

    def __init__(
        self,
        app: Any,
        public_paths: list[str] | tuple[str, ...] | None = None,
    ) -> None:
        super().__init__(app)
        self.public_paths: list[str] = list(DEFAULT_PUBLIC_PREFIXES)
        if public_paths:
            self.public_paths.extend(public_paths)

    async def dispatch(self, request: Request, call_next: Any) -> Response:
        """Authenticate the request before passing to the route handler."""
        # Skip auth for public paths
        if self._is_public_path(request.url.path):
            return await call_next(request)  # type: ignore[no-any-return]

        # Allow OPTIONS (CORS preflight) through
        if request.method == "OPTIONS":
            return await call_next(request)  # type: ignore[no-any-return]

        # Attempt authentication
        user_info = await self._authenticate(request)

        if user_info is None:
            return JSONResponse(
                status_code=401,
                content={
                    "detail": "Authentication required",
                    "error_code": "UNAUTHORIZED",
                },
                headers={"WWW-Authenticate": "Bearer"},
            )

        # Inject user info into request scope for downstream use
        # FastAPI dependencies can access this via request.state
        request.state.user_id = user_info["user_id"]
        request.state.username = user_info["username"]
        request.state.roles = user_info.get("roles", [])

        return await call_next(request)  # type: ignore[no-any-return]

    def _is_public_path(self, path: str) -> bool:
        """Check if the path is in the public whitelist.

        Matching rules:
        - Exact match: ``normalized == pp`` (e.g., ``/auth`` matches ``/auth``)
        - Prefix segment match: ``normalized.startswith(pp + "/")``
          (e.g., ``/auth`` matches ``/auth/login`` but NOT ``/authxxx``)
        """
        # Normalize trailing slash
        normalized = path.rstrip("/") if path != "/" else path

        for public_path in self.public_paths:
            pp = public_path.rstrip("/")
            # Exact match or prefix segment match only.
            # Do NOT use bare startswith(pp) — it would let /auth match
            # /authxxx / /authentication and bypass auth on unrelated routes.
            if normalized == pp or normalized.startswith(pp + "/"):
                return True

        return False

    async def _authenticate(self, request: Request) -> dict[str, Any] | None:
        """Try to authenticate the request.

        Strategy:
        - JWT: Validated statelessly here (decode + type check).
        - API Key: Passed through to the dependency layer (needs DB lookup).
        - No auth: Returns None → 401.

        Returns user info dict or None if unauthenticated.
        """
        auth_header = request.headers.get("Authorization", "")

        # Method 1: JWT Bearer token (stateless validation)
        if auth_header.startswith("Bearer "):
            token = auth_header.removeprefix("Bearer ").strip()
            try:
                payload = decode_token(token)

                # Only access tokens can pass middleware auth
                if payload.get("type") != "access":
                    return None

                return {
                    "user_id": payload.get("sub", ""),
                    "username": payload.get("username", ""),
                    "roles": payload.get("roles", []),
                }
            except (JWTError, ValueError, TypeError):
                logger.debug("Invalid JWT token in AuthMiddleware")
                return None

        # Method 2: API Key header — deferred to dependency layer
        api_key = request.headers.get(API_KEY_HEADER, "").strip()
        if api_key:
            # API keys require a DB lookup which is done in the FastAPI
            # dependency layer (get_current_user). The middleware lets the
            # request through; the dependency will 401 if the key is invalid.
            # Mark state so downstream code knows auth is pending.
            return {
                "user_id": "",
                "username": "",
                "roles": [],
                "_auth_pending": "api_key",
            }

        # No auth credentials at all → deny
        return None


def create_auth_middleware(
    public_paths: list[str] | tuple[str, ...] | None = None,
) -> type[AuthMiddleware]:
    """Factory for creating pre-configured AuthMiddleware.

    Usage:
        from agents.governance_agent.middleware import create_auth_middleware
        app.add_middleware(create_auth_middleware(public_paths=["/custom/public"]))
    """

    # Return a subclass that injects custom public_paths
    class _ConfiguredAuthMiddleware(AuthMiddleware):
        def __init__(self, app: Any, _public_paths: Any = public_paths) -> None:
            super().__init__(app, public_paths=_public_paths)

    return _ConfiguredAuthMiddleware
