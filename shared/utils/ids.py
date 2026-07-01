"""ID generation helpers."""

from __future__ import annotations

import uuid

__all__ = ["new_uuid", "short_id"]


def new_uuid() -> str:
    """Generate a UUID v4 string."""
    return str(uuid.uuid4())


def short_id(length: int = 8) -> str:
    """Generate a short random ID (URL-safe)."""
    import base64
    import secrets

    raw = secrets.token_bytes(length)
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")
