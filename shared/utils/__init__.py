"""FDE Platform — shared utility functions.

Common helpers used across agents: config loading, ID generation,
data validation, rate limiting, retry logic.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any

# ── Config ─────────────────────────────────────────────────────────


def load_config(path: str | Path, env_prefix: str = "FDE_") -> dict[str, Any]:
    """Load configuration from JSON/YAML file, overridden by env vars.

    Args:
        path: Path to config file.
        env_prefix: Environment variables with this prefix override file values.

    Returns:
        Merged configuration dictionary.
    """
    config: dict[str, Any] = {}
    path_obj = Path(path)

    if path_obj.suffix in (".json",) and path_obj.exists():
        config = json.loads(path_obj.read_text(encoding="utf-8"))

    # Override with env vars
    for key, value in os.environ.items():
        if key.startswith(env_prefix):
            config_key = key[len(env_prefix) :].lower()
            config[config_key] = value

    return config


# ── ID Generation ──────────────────────────────────────────────────


def new_uuid() -> str:
    """Generate a UUID v4 string."""
    return str(uuid.uuid4())


def short_id(length: int = 8) -> str:
    """Generate a short random ID (URL-safe)."""
    import base64
    import secrets

    raw = secrets.token_bytes(length)
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


# ── Hashing ────────────────────────────────────────────────────────


def hash_content(content: str, algorithm: str = "sha256") -> str:
    """Hash a string for deduplication."""
    h = hashlib.new(algorithm)
    h.update(content.encode("utf-8"))
    return h.hexdigest()


# ── Retry ──────────────────────────────────────────────────────────


async def retry_async(
    func: Callable[..., Any],
    *args: Any,
    max_retries: int = 3,
    base_delay: float = 1.0,
    backoff_factor: float = 2.0,
    **kwargs: Any,
) -> Any:
    """Retry an async function with exponential backoff.

    Args:
        func: Async callable to retry.
        max_retries: Maximum retry attempts.
        base_delay: Initial delay in seconds.
        backoff_factor: Multiplier for successive delays.

    Returns:
        Result of the successful call.

    Raises:
        Last exception if all retries fail.
    """
    last_exc: Exception | None = None
    for attempt in range(max_retries + 1):
        try:
            return await func(*args, **kwargs)
        except Exception as e:
            last_exc = e
            if attempt < max_retries:
                delay = base_delay * (backoff_factor**attempt)
                await asyncio.sleep(delay)
    raise last_exc  # type: ignore[misc]


# ── Validation ─────────────────────────────────────────────────────


def ensure_dir(path: str | Path) -> Path:
    """Ensure a directory exists, creating it if necessary."""
    p = Path(path)
    p.mkdir(parents=True, exist_ok=True)
    return p


def safe_filename(name: str) -> str:
    """Sanitize a string for use as a filename."""
    import re

    name = re.sub(r"[^\w\s-]", "", name).strip()
    name = re.sub(r"[-\s]+", "_", name)
    return name[:255]
