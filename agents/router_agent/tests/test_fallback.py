"""Tests for router agent — fallback chain."""

from __future__ import annotations

import pytest

from agents.router_agent.adapters import BaseAdapter, ModelRegistry
from agents.router_agent.models.request import ChatCompletionRequest, Message
from agents.router_agent.routing.fallback import FallbackChain


class TestFallbackChain:
    @pytest.fixture
    def registry(self) -> ModelRegistry:
        r = ModelRegistry()
        r.discover_adapters()
        return r

    @pytest.fixture(name="chat_request")
    def chat_request_fixture(self) -> ChatCompletionRequest:
        return ChatCompletionRequest(messages=[Message(role="user", content="你好")])

    async def test_successful_execution_with_mock(
        self, registry: ModelRegistry, chat_request: ChatCompletionRequest
    ) -> None:
        chain = FallbackChain(registry)
        resp = await chain.execute("fde/mock-v1", chat_request, "test_trace")
        assert resp.object == "chat.completion"
        assert resp.choices[0].message.content

    async def test_fallback_to_next_adapter_when_primary_fails(
        self, registry: ModelRegistry, chat_request: ChatCompletionRequest
    ) -> None:
        chain = FallbackChain(registry, timeout_seconds=1.0)
        # Request a stub adapter that raises NotImplementedError -> should fallback to mock
        resp = await chain.execute("deepseek/deepseek-chat", chat_request, "test_trace_fallback")
        assert resp.object == "chat.completion"
        assert "fde/mock-v1" in resp.model

    async def test_all_adapters_fail_raises_error(
        self, registry: ModelRegistry, chat_request: ChatCompletionRequest
    ) -> None:
        """If even mock fails, should raise a clear error."""
        # Create a registry with only a failing adapter
        reg_empty = ModelRegistry()

        class FailingAdapter(BaseAdapter):
            model_name = "fails"
            provider = "fail"

            async def complete(self, request: ChatCompletionRequest) -> None:  # type: ignore[override]
                raise RuntimeError("always fails")

        reg_empty.register(FailingAdapter())
        chain_empty = FallbackChain(reg_empty, max_retries=1, timeout_seconds=1.0)

        with pytest.raises(RuntimeError, match=r"All.*adapters failed"):
            await chain_empty.execute("fail/fails", chat_request, "test_trace_fail")

    async def test_fallback_order_respects_primary_first(
        self, registry: ModelRegistry, chat_request: ChatCompletionRequest
    ) -> None:
        chain = FallbackChain(registry)
        adapters = chain._build_fallback_order("fde/mock-v1")
        assert adapters[0].full_name == "fde/mock-v1"

    async def test_timeout_handling(self, registry: ModelRegistry) -> None:
        """Very short timeout should still fallback gracefully."""
        chain = FallbackChain(registry, timeout_seconds=0.001, max_retries=1)
        req = ChatCompletionRequest(messages=[Message(role="user", content="a" * 1000)])

        # Even with very tight timeout should eventually land on mock
        resp = await chain.execute("fde/mock-v1", req, "test_timeout")
        assert resp.object == "chat.completion"
