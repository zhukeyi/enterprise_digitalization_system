"""Tests for router agent — model adapters."""

from __future__ import annotations

import pytest

from agents.router_agent.adapters import (
    MockAdapter,
    ModelRegistry,
)
from agents.router_agent.models.request import ChatCompletionRequest, Message


class TestMockAdapter:
    @pytest.fixture
    def adapter(self) -> MockAdapter:
        return MockAdapter()

    @pytest.fixture
    def basic_request(self) -> ChatCompletionRequest:
        return ChatCompletionRequest(messages=[Message(role="user", content="你好")])

    async def test_mock_always_available(self, adapter: MockAdapter) -> None:
        assert adapter.health_check() is True

    async def test_mock_returns_valid_response(
        self, adapter: MockAdapter, basic_request: ChatCompletionRequest
    ) -> None:
        resp = await adapter.complete(basic_request)
        assert resp.object == "chat.completion"
        assert len(resp.choices) == 1
        assert resp.choices[0].message.role == "assistant"
        assert resp.choices[0].message.content

    async def test_mock_responds_to_hello(self, adapter: MockAdapter) -> None:
        req = ChatCompletionRequest(messages=[Message(role="user", content="hello")])
        resp = await adapter.complete(req)
        assert "Mock" in resp.choices[0].message.content

    async def test_mock_responds_to_help(self, adapter: MockAdapter) -> None:
        req = ChatCompletionRequest(messages=[Message(role="user", content="帮助")])
        resp = await adapter.complete(req)
        assert "FDE" in resp.choices[0].message.content

    async def test_mock_has_zero_cost(self, adapter: MockAdapter) -> None:
        assert adapter.cost_per_1k_tokens == 0.0

    async def test_mock_model_name(self, adapter: MockAdapter) -> None:
        assert adapter.full_name == "fde/mock-v1"

    async def test_mock_handles_empty_user_message(self, adapter: MockAdapter) -> None:
        req = ChatCompletionRequest(messages=[Message(role="system", content="你是一个助手")])
        resp = await adapter.complete(req)
        assert resp.choices[0].message.content  # should still return something

    async def test_mock_allows_streaming(self, adapter: MockAdapter) -> None:
        assert adapter.supports_streaming is True

    async def test_mock_usage_stats(self, adapter: MockAdapter) -> None:
        req = ChatCompletionRequest(messages=[Message(role="user", content="hello world test")])
        resp = await adapter.complete(req)
        assert resp.usage.prompt_tokens > 0
        assert resp.usage.completion_tokens > 0


class TestModelRegistry:
    @pytest.fixture
    def registry(self) -> ModelRegistry:
        r = ModelRegistry()
        r.discover_adapters()
        return r

    def test_registers_all_adapters(self, registry: ModelRegistry) -> None:
        models = registry.list_models()
        assert "fde/mock-v1" in models
        assert "deepseek/deepseek-chat" in models
        assert "qwen/qwen-turbo" in models
        assert "zhipu/glm-4-flash" in models

    def test_get_by_full_name(self, registry: ModelRegistry) -> None:
        adapter = registry.get("fde/mock-v1")
        assert adapter is not None
        assert adapter.model_name == "mock-v1"

    def test_get_by_model_name(self, registry: ModelRegistry) -> None:
        adapter = registry.get("mock-v1")
        assert adapter is not None
        assert adapter.provider == "fde"

    def test_get_unknown_model(self, registry: ModelRegistry) -> None:
        adapter = registry.get("nonexistent-model")
        assert adapter is None

    def test_available_filters_by_health(self, registry: ModelRegistry) -> None:
        available = registry.get_available()
        # Only mock should be available (others need API keys)
        names = [a.full_name for a in available]
        assert "fde/mock-v1" in names

    def test_register_custom_adapter(self, registry: ModelRegistry) -> None:
        from agents.router_agent.adapters.base import BaseAdapter

        class TestAdapter(BaseAdapter):
            model_name = "test-model"
            provider = "test"

            async def complete(self, request: ChatCompletionRequest) -> None:  # type: ignore[override]
                return None

        registry.register(TestAdapter())
        assert "test/test-model" in registry.list_models()


class TestStubAdapters:
    async def test_stubs_not_available_without_keys(self) -> None:
        from agents.router_agent.adapters.base import (
            DeepSeekStubAdapter,
            GlmStubAdapter,
            QwenStubAdapter,
        )

        assert DeepSeekStubAdapter().health_check() is False
        assert QwenStubAdapter().health_check() is False
        assert GlmStubAdapter().health_check() is False

    async def test_stubs_raise_not_implemented(self) -> None:
        from agents.router_agent.adapters.base import DeepSeekStubAdapter

        adapter = DeepSeekStubAdapter()
        req = ChatCompletionRequest(messages=[Message(role="user", content="test")])
        with pytest.raises(NotImplementedError):
            await adapter.complete(req)
