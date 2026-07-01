"""Tracing decorator."""

from __future__ import annotations

import functools
import time
from collections.abc import Callable
from typing import Any, TypeVar

from shared.sdk.backends import _log_trace

__all__ = ["traced"]

F = TypeVar("F", bound=Callable[..., Any])


def traced(name: str | None = None) -> Callable[[F], F]:
    """Decorator that creates a span around a function call.

    Args:
        name: Span name; defaults to function name.

    Usage:
        @traced("rag_retrieve")
        async def retrieve(query: str) -> list[Document]:
            ...
    """

    def decorator(func: F) -> F:
        @functools.wraps(func)
        async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
            span_name = name or func.__name__
            # Simplified: in production, use real Langfuse/OTel SDK
            start = time.time()
            try:
                result = await func(*args, **kwargs)
                elapsed = (time.time() - start) * 1000
                _log_trace(span_name, "success", elapsed)
                return result
            except Exception as e:
                elapsed = (time.time() - start) * 1000
                _log_trace(span_name, f"error: {e}", elapsed)
                raise

        @functools.wraps(func)
        def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
            span_name = name or func.__name__
            start = time.time()
            try:
                result = func(*args, **kwargs)
                elapsed = (time.time() - start) * 1000
                _log_trace(span_name, "success", elapsed)
                return result
            except Exception as e:
                elapsed = (time.time() - start) * 1000
                _log_trace(span_name, f"error: {e}", elapsed)
                raise

        import asyncio

        if asyncio.iscoroutinefunction(func):
            return async_wrapper  # type: ignore[return-value]
        return sync_wrapper  # type: ignore[return-value]

    return decorator
