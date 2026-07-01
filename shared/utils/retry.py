"""Async retry helpers."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any

__all__ = ["retry_async"]


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
