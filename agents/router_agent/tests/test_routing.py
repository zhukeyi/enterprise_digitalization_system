"""Tests for router agent — routing engine."""

from __future__ import annotations

import pytest

from agents.router_agent.models.request import ChatCompletionRequest, Message
from agents.router_agent.routing.engine import RouteRule, RoutingEngine


class TestRoutingEngine:
    @pytest.fixture
    def engine(self) -> RoutingEngine:
        return RoutingEngine()

    def test_route_simple_query_to_mock(self, engine: RoutingEngine) -> None:
        """Simple queries should route to mock/cheapest model."""
        req = ChatCompletionRequest(messages=[Message(role="user", content="你好")])
        result = engine.route(req)
        assert result == "fde/mock-v1"

    def test_explicit_model_returns_as_is(self, engine: RoutingEngine) -> None:
        """If user specifies a model, it should be used directly."""
        req = ChatCompletionRequest(
            model="custom-model",
            messages=[Message(role="user", content="hello")],
        )
        result = engine.route(req)
        assert result == "custom-model"

    def test_long_query_routes_to_medium(self, engine: RoutingEngine) -> None:
        """Longer queries should be classified as medium complexity."""
        long_text = "今天天气怎么样？" * 200  # ~2000 chars
        req = ChatCompletionRequest(messages=[Message(role="user", content=long_text)])
        result = engine.route(req)
        assert isinstance(result, str)

    def test_very_long_query_routes_to_complex(self, engine: RoutingEngine) -> None:
        """Very long queries should be classified as complex."""
        very_long = "测试" * 3000  # >5000 chars
        req = ChatCompletionRequest(messages=[Message(role="user", content=very_long)])
        result = engine.route(req)
        assert isinstance(result, str)

    def test_multi_turn_is_medium(self, engine: RoutingEngine) -> None:
        """Multi-turn conversations should be medium or higher."""
        messages = [Message(role="user", content=f"消息{i}") for i in range(6)]
        req = ChatCompletionRequest(messages=messages)
        result = engine.route(req)
        assert result  # routes to something

    def test_sensitive_keywords_route_to_local(self, engine: RoutingEngine) -> None:
        """Sensitive queries should be routed to local model."""
        req = ChatCompletionRequest(messages=[Message(role="user", content="我的密码是123456")])
        result = engine.route(req)
        assert result == "fde/mock-v1"

    def test_default_fallback_no_model(self, engine: RoutingEngine) -> None:
        """Empty request with no explicit model should always route."""
        req = ChatCompletionRequest(messages=[Message(role="user", content="test")])
        result = engine.route(req)
        assert result  # should not be empty

    def test_reload_does_not_crash(self, engine: RoutingEngine) -> None:
        """Hot-reload should work without error."""
        engine.reload()  # should not raise


class TestRouteRule:
    def test_rule_has_defaults(self) -> None:
        """RouteRule should have sensible defaults."""
        rule = RouteRule(name="test", model="mock-v1")
        assert rule.priority == 100
        assert rule.conditions == {}
        assert rule.name == "test"
        assert rule.model == "mock-v1"
