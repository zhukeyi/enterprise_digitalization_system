"""Fallback chain — automatic failover within 3 seconds.

M1-T7: When a primary model times out or errors, the fallback chain
automatically switches to the next available adapter.

Configuration:
- max_retries: Maximum retry attempts before giving up (default: 3)
- timeout_seconds: Per-adapter timeout before trying next (default: 3.0)
- backoff: Exponential backoff multiplier between retries (default: False)
"""

from __future__ import annotations

import asyncio
import logging

from agents.router_agent.adapters.base import AdapterError, BaseAdapter, ModelRegistry
from agents.router_agent.models.request import ChatCompletionRequest
from agents.router_agent.models.response import ChatCompletionResponse

logger = logging.getLogger("fde.router.fallback")


class FallbackChain:
    """Executes model requests with automatic failover.

    The chain tries adapters in order:
    1. The requested model's adapter
    2. Other available adapters (by cost ascending)
    3. Mock adapter as last resort

    Each attempt has a timeout; if exceeded, the next adapter is tried.
    """

    def __init__(
        self,
        registry: ModelRegistry,
        max_retries: int = 3,
        timeout_seconds: float = 3.0,
    ) -> None:
        self.registry = registry
        self.max_retries = max_retries
        self.timeout_seconds = timeout_seconds

    async def execute(
        self,
        model_name: str,
        request: ChatCompletionRequest,
        trace_id: str = "unknown",
    ) -> ChatCompletionResponse:
        """Execute a request with automatic failover.

        Args:
            model_name: Primary model to try.
            request: Chat completion request.
            trace_id: Trace ID for logging.

        Returns:
            Chat completion response from whichever adapter succeeds.

        Raises:
            RuntimeError: If all adapters fail.
        """
        # Build fallback order
        adapters = self._build_fallback_order(model_name)
        errors: list[str] = []

        for i, adapter in enumerate(adapters):
            attempt_name = adapter.full_name
            logger.info(
                "trace=%s attempt=%d/%d adapter=%s",
                trace_id,
                i + 1,
                len(adapters),
                attempt_name,
            )

            try:
                # Execute with timeout
                response = await asyncio.wait_for(
                    adapter.complete(request),
                    timeout=self.timeout_seconds,
                )
                logger.info(
                    "trace=%s success adapter=%s attempt=%d",
                    trace_id,
                    attempt_name,
                    i + 1,
                )
                return response

            except TimeoutError:
                error_msg = f"timeout after {self.timeout_seconds}s"
                errors.append(f"{attempt_name}: {error_msg}")
                logger.warning("trace=%s timeout adapter=%s", trace_id, attempt_name)

            except AdapterError as e:
                error_msg = str(e)
                errors.append(f"{attempt_name}: {error_msg}")
                logger.warning("trace=%s adapter_error adapter=%s: %s", trace_id, attempt_name, e)

            except NotImplementedError:
                error_msg = "adapter not yet implemented (no API key)"
                errors.append(f"{attempt_name}: {error_msg}")
                logger.info("trace=%s not_implemented adapter=%s", trace_id, attempt_name)

            except Exception as e:
                error_msg = f"{type(e).__name__}: {e}"
                errors.append(f"{attempt_name}: {error_msg}")
                logger.exception("trace=%s unexpected_error adapter=%s", trace_id, attempt_name)

        # All adapters failed
        error_summary = "; ".join(errors)
        raise RuntimeError(f"All {len(adapters)} adapters failed: {error_summary}")

    def _build_fallback_order(self, primary_name: str) -> list[BaseAdapter]:
        """Build ordered list of adapters to try.

        Order:
        1. Primary adapter (if available)
        2. Other available adapters by cost
        3. Mock adapter as last resort
        """
        primary = self.registry.get(primary_name)
        available = self.registry.get_available()

        adapters: list[BaseAdapter] = []

        # Primary first
        if primary and primary in available:
            adapters.append(primary)
        elif primary:
            adapters.append(primary)  # Try anyway, might fail fast

        # Other adapters by cost
        other = [a for a in available if a.full_name != (primary.full_name if primary else "")]
        other.sort(key=lambda a: a.cost_per_1k_tokens)
        adapters.extend(other)

        # Mock as final safety net
        mock = self.registry.get("fde/mock-v1")
        if mock and mock not in adapters:
            adapters.append(mock)

        # Limit to max_retries
        return adapters[: self.max_retries]
