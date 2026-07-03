"""JWT token creation/verification, password hashing, and API key management.

Security strategy:
- JWT (HS256) for human users (short-lived access + long-lived refresh)
- API Key (SHA256 hash) for services and automations
- Passwords hashed with bcrypt via passlib
"""

from __future__ import annotations

import hashlib
import os
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any

from jose import jwt
from passlib.context import CryptContext

# ══════════════════════════════════════════════════════════════════
# Configuration
# ══════════════════════════════════════════════════════════════════

_INSECURE_DEFAULT = "change-me-in-production"
JWT_SECRET_KEY: str = os.getenv("JWT_SECRET_KEY", _INSECURE_DEFAULT)
JWT_ALGORITHM: str = os.getenv("JWT_ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES: int = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "30"))
REFRESH_TOKEN_EXPIRE_DAYS: int = int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", "7"))

# Fail-fast: refuse to run with the insecure default in production
if JWT_SECRET_KEY == _INSECURE_DEFAULT and os.getenv("FDE_ENABLE_AUTH", "0") == "1":
    import sys

    sys.stderr.write(
        "FATAL: JWT_SECRET_KEY is not set (using insecure default). "
        "Set JWT_SECRET_KEY environment variable before enabling auth.\n"
    )
    sys.exit(1)

# ══════════════════════════════════════════════════════════════════
# Password hashing (bcrypt)
# ══════════════════════════════════════════════════════════════════

_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    """Hash a plain-text password using bcrypt."""
    return _pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plain-text password against a bcrypt hash."""
    return _pwd_context.verify(plain_password, hashed_password)


# ══════════════════════════════════════════════════════════════════
# JWT Token Operations
# ══════════════════════════════════════════════════════════════════


def create_access_token(
    user_id: str,
    username: str,
    roles: list[str] | None = None,
    expires_delta: timedelta | None = None,
) -> str:
    """Create a short-lived JWT access token.

    Args:
        user_id: The user's UUID.
        username: The user's username.
        roles: RBAC roles for the user.
        expires_delta: Custom expiration. Defaults to ACCESS_TOKEN_EXPIRE_MINUTES.

    Returns:
        Encoded JWT string.
    """
    now = datetime.now(UTC)
    expire = now + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))

    payload = {
        "sub": user_id,
        "username": username,
        "roles": roles or [],
        "type": "access",
        "iat": now,
        "exp": expire,
    }
    return jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)


def create_refresh_token(user_id: str, username: str) -> str:
    """Create a long-lived JWT refresh token.

    Args:
        user_id: The user's UUID.
        username: The user's username.

    Returns:
        Encoded JWT string.
    """
    now = datetime.now(UTC)
    expire = now + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)

    payload = {
        "sub": user_id,
        "username": username,
        "type": "refresh",
        "iat": now,
        "exp": expire,
    }
    return jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)


def decode_token(token: str) -> dict[str, Any]:
    """Decode and verify a JWT token.

    Args:
        token: The JWT string to decode.

    Returns:
        Decoded payload as dict.

    Raises:
        JWTError: If the token is invalid, expired, or tampered with.
    """
    return jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])


# ══════════════════════════════════════════════════════════════════
# API Key Operations
# ══════════════════════════════════════════════════════════════════


def create_api_key() -> tuple[str, str, str]:
    """Generate a new API key pair.

    Returns:
        Tuple of (raw_key, key_hash, prefix).
        - raw_key: The full key to give to the user (shown once).
        - key_hash: SHA256 hash for secure storage.
        - prefix: First 8 chars for identification in logs/UI.
    """
    raw_key = f"fde_{secrets.token_urlsafe(32)}"
    key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
    prefix = raw_key[:12]  # "fde_" + first 8 of random part
    return raw_key, key_hash, prefix


def hash_api_key(raw_key: str) -> str:
    """Hash an API key for storage/comparison."""
    return hashlib.sha256(raw_key.encode()).hexdigest()


def verify_api_key(raw_key: str, stored_hash: str) -> bool:
    """Verify a raw API key against a stored hash.

    Uses constant-time comparison via secrets.compare_digest.
    """
    computed = hash_api_key(raw_key)
    return secrets.compare_digest(computed, stored_hash)
