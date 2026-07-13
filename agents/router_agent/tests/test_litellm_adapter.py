"""Tests for the LiteLLM adapter (P0-A / L-2).

Uses httpx.MockTransport so no real network / proxy is required.
"""

from __future__ import annotations

import httpx
import pytest

from agents.router_agent.adapters.litellm_adapter import (
    LiteLLMAdapter,
    LiteLLMAdapterError,
    build_litellm_adapter,
)
from agents.router_agent.models.request import ChatCompletionRequest, Message


def _req(content: str = "hello", model: str | None = None, extra: dict | None = None) -> ChatCompletionRequest:
    return ChatCompletionRequest(
        messages=[Message(role="user", content=content)],
        model=model,
        extra=extra or {},
    )


def _mock_adapter(handler) -> LiteLLMAdapter:
    a = LiteLLMAdapter(proxy_url="http://litellm:4000", api_key="master", default_model="fde-default")
    a._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return a


# ── Factory / health gating (gray rollout) ──────────────────────


def test_factory_disabled_without_proxy_url(monkeypatch):
    monkeypatch.delenv("LITELLM_PROXY_URL", raising=False)
    assert build_litellm_adapter() is None


def test_factory_enabled_with_proxy_url(monkeypatch):
    monkeypatch.setenv("LITELLM_PROXY_URL", "http://litellm:4000")
    a = build_litellm_adapter()
    assert a is not None
    assert a.health_check() is True
    assert a.full_name == "litellm/default"


def test_health_false_when_unconfigured():
    a = LiteLLMAdapter(proxy_url="")
    assert a.health_check() is False


# ── Completion mapping / parsing ────────────────────────────────


async def test_complete_maps_payload_and_parses_response():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["auth"] = request.headers.get("Authorization")
        captured["body"] = request.content
        return httpx.Response(
            200,
            json={
                "id": "chatcmpl-1",
                "object": "chat.completion",
                "created": 123,
                "model": "fde-default",
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": "hi there"},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {"prompt_tokens": 5, "completion_tokens": 2, "total_tokens": 7},
            },
        )

    a = _mock_adapter(handler)
    resp = await a.complete(_req(content="hello", model="fde-default"))

    assert str(captured["url"]).endswith("/chat/completions")
    assert captured["auth"] == "Bearer master"
    assert b"fde-default" in captured["body"]
    assert resp.model == "fde-default"
    assert resp.choices[0].message.content == "hi there"
    assert resp.usage.total_tokens == 7
    await a.aclose()


async def test_complete_forwards_virtual_key_from_extra():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["auth"] = request.headers.get("Authorization")
        return httpx.Response(
            200,
            json={
                "id": "x",
                "model": "fde-default",
                "choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
            },
        )

    a = _mock_adapter(handler)
    resp = await a.complete(_req(extra={"litellm_key": "vk-tenant-123"}))
    assert captured["auth"] == "Bearer vk-tenant-123"
    assert resp.choices[0].message.content == "ok"
    await a.aclose()


async def test_complete_uses_default_model_when_none():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = request.content
        return httpx.Response(
            200,
            json={
                "id": "x",
                "model": "fde-default",
                "choices": [{"message": {"content": "d"}, "finish_reason": "stop"}],
                "usage": {},
            },
        )

    a = _mock_adapter(handler)
    await a.complete(_req(model=None))  # no explicit model
    assert b"fde-default" in captured["body"]
    await a.aclose()


# ── Error handling ──────────────────────────────────────────────


async def test_complete_raises_on_proxy_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="boom")

    a = _mock_adapter(handler)
    with pytest.raises(LiteLLMAdapterError):
        await a.complete(_req())
    await a.aclose()


async def test_complete_raises_on_unconfigured():
    a = LiteLLMAdapter(proxy_url="")
    with pytest.raises(LiteLLMAdapterError):
        await a.complete(_req())


# ── Structural conformance to BaseAdapter contract (D5) ──────────
# The adapter is duck-typed (does NOT subclass BaseAdapter) to avoid import
# churn. This test guards against silent contract drift: if BaseAdapter's
# interface changes, this must fail loudly.


def test_adapter_conforms_to_base_adapter_contract():

    a = LiteLLMAdapter(proxy_url="http://litellm:4000", api_key="m")

    # Required attributes present (class-level interface fields)
    for attr in ("model_name", "provider", "cost_per_1k_tokens", "supports_streaming", "max_tokens"):
        assert hasattr(a, attr), f"missing interface attr: {attr}"

    # Required methods present and with correct shape
    assert callable(a.complete)
    import asyncio

    assert asyncio.iscoroutinefunction(a.complete)
    assert callable(a.health_check)
    assert isinstance(a.full_name, str) and a.full_name

    # Must satisfy BaseAdapter.register (duck-typed acceptance): register
    # accepts any object exposing full_name + complete, and aliases resolve.
    from agents.router_agent.adapters.base import ModelRegistry

    reg2 = ModelRegistry()
    reg2.register(a, aliases=["fde-default"])
    assert reg2.get("fde-default") is a
    assert reg2.get(a.full_name) is a


async def test_auth_for_prefers_virtual_key_over_master():
    a = LiteLLMAdapter(proxy_url="http://litellm:4000", api_key="master-key")
    # virtual key present -> wins
    assert a._auth_for(_req(extra={"litellm_key": "vk-123"})) == "vk-123"
    # no virtual key -> falls back to configured master key
    assert a._auth_for(_req()) == "master-key"
