"""LiteLLM adapter — unified model gateway via LiteLLM proxy (OpenAI-compatible).

This adapter delegates model execution to a running **LiteLLM proxy**
(default :4000), which centralizes 100+ provider integrations, virtual-key
auth, per-tenant budgets, cost tracking and fallback.

P0-A design goals (risk R1 mitigation — gray rollout, fallback-safe):
- Conforms *exactly* to :class:`BaseAdapter`, so it slots into the existing
  ``ModelRegistry`` / ``RoutingEngine`` / ``FallbackChain`` with zero changes
  to the gateway core.
- **Graceful**: reports healthy only when ``LITELLM_PROXY_URL`` is configured.
  Until LiteLLM is deployed + enabled, this adapter is invisible to
  ``/v1/models`` and excluded from the fallback chain — the legacy
  Mock/Stub adapters remain the active path untouched.
- **Lean**: talks plain HTTP (httpx) to the proxy's OpenAI-compatible endpoint.
  No hard dependency on the ``litellm`` Python package, keeping the dependency
  surface small (consistent with the project's numpy-only / single-host posture).

Multi-tenancy: the gateway may pass a caller's LiteLLM *virtual key* via
``request.extra["litellm_key"]``; the adapter forwards it as the ``Authorization``
bearer token so the proxy enforces that tenant's model allowlist + budget.
When no virtual key is supplied, the adapter's configured ``api_key`` (master
key, single-tenant dev mode) is used.
"""

from __future__ import annotations

import logging
import os
import time
import uuid

import httpx

from agents.router_agent.models.request import ChatCompletionRequest
from agents.router_agent.models.response import (
    ChatCompletionResponse,
    Choice,
    Message,
    Usage,
)

logger = logging.getLogger("fde.router.adapters.litellm")


class LiteLLMAdapterError(Exception):
    """Raised when the LiteLLM proxy call fails."""


def _env_flag(name: str, default: bool = False) -> bool:
    val = os.getenv(name)
    if val is None:
        return default
    return val.strip().lower() in ("1", "true", "yes", "on")


class LiteLLMAdapter:
    """OpenAI-compatible adapter that proxies to a LiteLLM gateway.

    Note: intentionally does NOT subclass ``BaseAdapter`` via ABC metaclass
    conflicts; it implements the *same structural interface* (``complete``,
    ``health_check``, ``full_name``, ``model_name``, ``provider``,
    ``cost_per_1k_tokens``, ``supports_streaming``, ``max_tokens``) so the
    registry / fallback chain accept it duck-typed. Using ABC would force
    ``@abstractmethod`` re-declaration; duck typing keeps the legacy
    ``BaseAdapter`` contract intact and avoids import churn.
    """

    # Interface fields expected by ModelRegistry / FallbackChain / Response shape
    model_name: str = "litellm-default"
    provider: str = "litellm"
    cost_per_1k_tokens: float = 0.0
    supports_streaming: bool = False
    max_tokens: int = 8192

    def __init__(
        self,
        proxy_url: str | None = None,
        api_key: str | None = None,
        default_model: str = "fde-default",
        timeout_seconds: float = 30.0,
        name: str = "litellm/default",
    ) -> None:
        self.proxy_url = (proxy_url or os.getenv("LITELLM_PROXY_URL", "")).rstrip("/")
        self.api_key = api_key or os.getenv("LITELLM_MASTER_KEY", "")
        self.default_model = default_model or os.getenv("LITELLM_DEFAULT_MODEL", "fde-default")
        self.timeout = timeout_seconds
        self._name = name
        self._client: httpx.AsyncClient | None = None
        # Effective health is determined lazily; config presence gates it.
        self._configured = bool(self.proxy_url)

    # ── Registry / fallback contract ────────────────────────────

    @property
    def full_name(self) -> str:
        return self._name

    def health_check(self) -> bool:
        """Healthy only when a proxy URL is configured.

        Call-time connectivity is not probed here (avoids network cost on
        every routing decision); the fallback chain already wraps
        :meth:`complete` in a timeout + exception handler, so a down proxy is
        handled gracefully at execution time.
        """
        return self._configured

    # ── Client lifecycle ─────────────────────────────────────────

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(self.timeout),
                headers={"User-Agent": "fde-router/1.0"},
            )
        return self._client

    async def aclose(self) -> None:
        if self._client is not None and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    # ── Completion ───────────────────────────────────────────────

    async def complete(self, request: ChatCompletionRequest) -> ChatCompletionResponse:
        """Forward a chat completion to the LiteLLM proxy."""
        if not self._configured:
            raise LiteLLMAdapterError("LiteLLM proxy URL not configured")

        model = request.model or self.default_model
        payload = self._build_payload(request, model)
        auth_token = self._auth_for(request)

        url = f"{self.proxy_url}/chat/completions"
        headers = {"Content-Type": "application/json"}
        if auth_token:
            headers["Authorization"] = f"Bearer {auth_token}"

        try:
            client = self._get_client()
            resp = await client.post(url, json=payload, headers=headers)
        except httpx.TimeoutException as e:
            raise LiteLLMAdapterError(f"LiteLLM proxy timeout: {e}") from e
        except httpx.HTTPError as e:
            raise LiteLLMAdapterError(f"LiteLLM proxy unreachable: {e}") from e

        if resp.status_code != 200:
            body = resp.text[:500]
            raise LiteLLMAdapterError(
                f"LiteLLM proxy returned {resp.status_code}: {body}"
            )

        try:
            data = resp.json()
        except ValueError as e:
            raise LiteLLMAdapterError(f"Invalid JSON from LiteLLM proxy: {e}") from e

        return self._parse_response(data, model)

    # ── Helpers ──────────────────────────────────────────────────

    @staticmethod
    def _build_payload(request: ChatCompletionRequest, model: str) -> dict:
        payload: dict = {
            "model": model,
            "messages": [{"role": m.role, "content": m.content} for m in request.messages],
            "temperature": request.temperature,
            "top_p": request.top_p,
            "n": request.n,
        }
        if request.max_tokens is not None:
            payload["max_tokens"] = request.max_tokens
        if request.stop:
            payload["stop"] = request.stop
        # Forward any LiteLLM-specific passthrough params (e.g. drop_params,
        # mock_response, fallbacks) supplied by upstream callers.
        extra = getattr(request, "extra", None) or {}
        for k, v in extra.items():
            if k.startswith("litellm_") and k not in ("litellm_key",):
                payload[k] = v
        return payload

    @staticmethod
    def _resolve_key(request: ChatCompletionRequest) -> str | None:
        """Resolve the virtual key to forward to the proxy.

        Priority: explicit virtual key in ``request.extra["litellm_key"]``
        (set by the gateway from the caller's Authorization header) → adapter
        master key (dev mode).
        """
        extra = getattr(request, "extra", None) or {}
        vk = extra.get("litellm_key")
        if vk:
            return vk
        return None  # fall back to adapter.api_key at call site

    def _auth_for(self, request: ChatCompletionRequest) -> str | None:
        vk = self._resolve_key(request)
        return vk or self.api_key or None

    @staticmethod
    def _parse_response(data: dict, requested_model: str) -> ChatCompletionResponse:
        choices_raw = data.get("choices", [])
        choices = [
            Choice(
                index=c.get("index", 0),
                message=Message(
                    role=(c.get("message", {}) or {}).get("role", "assistant"),
                    content=(c.get("message", {}) or {}).get("content", ""),
                ),
                finish_reason=c.get("finish_reason", "stop"),
            )
            for c in choices_raw
        ]
        usage_raw = data.get("usage", {}) or {}
        usage = Usage(
            prompt_tokens=int(usage_raw.get("prompt_tokens", 0)),
            completion_tokens=int(usage_raw.get("completion_tokens", 0)),
            total_tokens=int(usage_raw.get("total_tokens", 0)),
        )
        return ChatCompletionResponse(
            id=data.get("id", f"litellm-{uuid.uuid4().hex[:8]}"),
            created=int(data.get("created", time.time())),
            model=data.get("model", requested_model),
            choices=choices,
            usage=usage,
        )


def build_litellm_adapter(name: str = "litellm/default") -> LiteLLMAdapter | None:
    """Factory: return a configured adapter, or ``None`` if not enabled.

    Enabling is controlled by ``LITELLM_PROXY_URL`` (set in env / compose).
    Returns ``None`` when unset so callers can skip registration safely —
    this is the gray-rollout safeguard that keeps the legacy adapters active.
    """
    proxy_url = os.getenv("LITELLM_PROXY_URL", "").strip()
    if not proxy_url:
        logger.info("LiteLLM adapter disabled (LITELLM_PROXY_URL not set)")
        return None
    adapter = LiteLLMAdapter(name=name)
    logger.info("LiteLLM adapter enabled → %s (model=%s)", adapter.proxy_url, adapter.default_model)
    return adapter
