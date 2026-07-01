"""Desktop client authentication manager (M2-T4).

Handles token acquisition, caching, and refresh for the desktop app.
Uses JWT access + refresh tokens from the Governance Agent's /auth endpoints.
Token persistence via file-based cache (Tauri production: keychain/os keyring).
"""

from __future__ import annotations

import json
import logging
import os
import time
from contextlib import suppress
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx

logger = logging.getLogger("fde.client.auth")


@dataclass
class TokenCache:
    """In-memory token cache with file persistence.

    In production (Tauri), this would use the OS keychain via
    the Tauri secure storage API instead of a plain file.
    """

    access_token: str = ""
    refresh_token: str = ""
    expires_at: float = 0.0  # Unix timestamp
    user_id: str = ""
    username: str = ""
    roles: list[str] = field(default_factory=list)

    @property
    def is_valid(self) -> bool:
        """Check if the cached access token is still valid (>30s buffer)."""
        return bool(self.access_token) and time.time() < (self.expires_at - 30)

    @property
    def is_authenticated(self) -> bool:
        """Check if we have any valid token (access or refresh)."""
        return bool(self.access_token) or bool(self.refresh_token)


class DesktopAuthManager:
    """Manages authentication lifecycle for the desktop client.

    Flow:
    1. login() → get JWT access + refresh tokens
    2. Tokens cached to file (dev) or keychain (prod)
    3. Auto-refresh when access token expires
    4. logout() → clear tokens

    Dependency: Governance Agent's /auth endpoints must be available.
    """

    def __init__(
        self,
        backend_url: str = "http://localhost:8000",
        cache_dir: str | None = None,
    ) -> None:
        self.backend_url = backend_url.rstrip("/")
        self._cache = TokenCache()
        self._cache_path = Path(cache_dir or os.path.expanduser("~/.fde")) / "desktop_auth.json"
        self._client = httpx.AsyncClient(timeout=30.0)
        self._load_cache()

    async def close(self) -> None:
        """Clean up HTTP client."""
        await self._client.aclose()

    async def login(self, username: str, password: str) -> dict[str, Any]:
        """Authenticate and cache tokens.

        Args:
            username: User login name.
            password: Plaintext password.

        Returns:
            Dict with user info and token status.

        Raises:
            httpx.HTTPStatusError: On authentication failure.
        """
        resp = await self._client.post(
            f"{self.backend_url}/auth/login",
            json={"username": username, "password": password},
        )
        resp.raise_for_status()
        data = resp.json()

        if not isinstance(data, dict):
            raise ValueError(f"Unexpected login response: {type(data)}")
        if "access_token" not in data or "refresh_token" not in data:
            raise ValueError(f"Missing tokens in login response: {list(data.keys())}")

        self._cache.access_token = data["access_token"]
        self._cache.refresh_token = data["refresh_token"]
        self._cache.expires_at = time.time() + data.get("expires_in", 1800)

        # Decode user info from token payload
        user_info = self._decode_token_payload(data["access_token"])
        self._cache.user_id = user_info.get("sub", "")
        self._cache.username = user_info.get("username", "")
        self._cache.roles = user_info.get("roles", [])

        self._save_cache()
        logger.info("Desktop user '%s' authenticated", username)

        return {
            "success": True,
            "username": self._cache.username,
            "roles": self._cache.roles,
            "expires_in": data.get("expires_in", 1800),
        }

    async def refresh(self) -> bool:
        """Attempt to refresh the access token.

        Returns:
            True if refresh succeeded, False otherwise.
        """
        if not self._cache.refresh_token:
            return False

        try:
            resp = await self._client.post(
                f"{self.backend_url}/auth/refresh",
                json={"refresh_token": self._cache.refresh_token},
            )
            resp.raise_for_status()
            data = resp.json()

            self._cache.access_token = data["access_token"]
            self._cache.refresh_token = data["refresh_token"]
            self._cache.expires_at = time.time() + data.get("expires_in", 1800)
            self._save_cache()
            logger.info("Token refreshed successfully")
            return True
        except Exception as e:
            logger.warning("Token refresh failed: %s", e)
            return False

    async def ensure_authenticated(self) -> str | None:
        """Return a valid access token, refreshing if needed.

        Returns:
            Valid access token string, or None if re-authentication is required.
        """
        if self._cache.is_valid:
            return self._cache.access_token

        if self._cache.refresh_token:
            success = await self.refresh()
            if success and self._cache.is_valid:
                return self._cache.access_token  # type: ignore[unreachable]

        return None

    def logout(self) -> None:
        """Clear all tokens and remove cache file."""
        self._cache = TokenCache()
        with suppress(OSError):
            self._cache_path.unlink(missing_ok=True)
        logger.info("Desktop user logged out")

    def get_auth_headers(self) -> dict[str, str]:
        """Get HTTP Authorization header value.

        Returns:
            Bearer token header dict if authenticated, empty dict otherwise.
        """
        if self._cache.is_valid:
            return {"Authorization": f"Bearer {self._cache.access_token}"}
        return {}

    # ── Private helpers ──────────────────────────────────────────────

    def _save_cache(self) -> None:
        """Persist tokens to local file with atomic write.

        Writes to a temp file first, then renames to target to avoid
        corruption on partial write (crash, disk full, etc.).
        """
        try:
            self._cache_path.parent.mkdir(parents=True, exist_ok=True)
            data = {
                "access_token": self._cache.access_token,
                "refresh_token": self._cache.refresh_token,
                "expires_at": self._cache.expires_at,
                "user_id": self._cache.user_id,
                "username": self._cache.username,
                "roles": self._cache.roles,
            }
            tmp_path = self._cache_path.with_suffix(".tmp")
            tmp_path.write_text(json.dumps(data), encoding="utf-8")
            tmp_path.replace(self._cache_path)
        except (OSError, json.JSONDecodeError) as e:
            logger.warning("Failed to save auth cache: %s", e)

    def _load_cache(self) -> None:
        """Load persisted tokens from file."""
        try:
            if not self._cache_path.exists():
                return
            data = json.loads(self._cache_path.read_text(encoding="utf-8"))
            self._cache.access_token = data.get("access_token", "")
            self._cache.refresh_token = data.get("refresh_token", "")
            self._cache.expires_at = data.get("expires_at", 0.0)
            self._cache.user_id = data.get("user_id", "")
            self._cache.username = data.get("username", "")
            self._cache.roles = data.get("roles", [])
        except (OSError, json.JSONDecodeError, KeyError) as e:
            logger.warning("Failed to load auth cache: %s", e)

    @staticmethod
    def _decode_token_payload(token: str) -> dict[str, Any]:
        """Decode JWT payload without verification (for display only).

        Real verification is done server-side by AuthMiddleware.
        Catches specific exceptions: malformed token, base64 errors,
        JSON decode errors — all fall back to empty dict.
        """
        import base64

        try:
            parts = token.split(".")
            if len(parts) < 2:
                return {}
            payload_b64 = parts[1]
            padding = 4 - len(payload_b64) % 4
            if padding != 4:
                payload_b64 += "=" * padding
            decoded = base64.urlsafe_b64decode(payload_b64)
            return json.loads(decoded)  # type: ignore[no-any-return]
        except (IndexError, ValueError, json.JSONDecodeError, base64.binascii.Error):  # type: ignore[attr-defined]
            return {}
