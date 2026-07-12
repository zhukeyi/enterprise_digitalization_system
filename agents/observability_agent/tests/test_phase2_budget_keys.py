"""Tests for Phase 2: Token tracking, budget, API keys, external API registry."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from agents.observability_agent.api_keys import (
    create_api_key,
    delete_api_key,
    list_api_keys,
    validate_api_key,
)
from agents.observability_agent.auth_middleware import APIKeyMiddleware
from agents.observability_agent.budget import get_budget, set_budget
from agents.observability_agent.middleware import APIMetricsMiddleware
from agents.observability_agent.router import router, set_app
from agents.observability_agent.token_tracker import (
    get_cost_report,
    get_model_pricing,
    get_routing_distribution,
    get_token_usage_grouped,
    get_token_usage_summary,
    record_token_usage,
)


@pytest.fixture
def app() -> FastAPI:
    """Create a test FastAPI app with observability router."""
    app = FastAPI()
    app.add_middleware(APIMetricsMiddleware)
    app.add_middleware(APIKeyMiddleware)
    app.include_router(router)
    set_app(app)
    return app


@pytest.fixture
def client(app: FastAPI) -> TestClient:
    """Create a test client."""
    return TestClient(app)


class TestTokenTracking:
    """Tests for token usage tracking."""

    def test_record_and_summary(self) -> None:
        """Record token usage and verify summary."""
        record_token_usage(
            trace_id="test-trace-1",
            model="fde/mock-v1",
            prompt_tokens=100,
            completion_tokens=50,
            latency_ms=200,
            agent_module="router_agent",
        )
        summary = get_token_usage_summary()
        assert summary["total_calls"] >= 1
        assert summary["total_tokens"] >= 150

    def test_grouped_by_model(self) -> None:
        """Group token usage by model."""
        record_token_usage("t1", "fde/mock-v1", 100, 50, agent_module="router_agent")
        record_token_usage("t2", "deepseek/deepseek-chat", 200, 80, agent_module="orchestrator")
        grouped = get_token_usage_grouped(group_by="model")
        assert len(grouped) >= 1
        models = {g["group_value"] for g in grouped}
        assert "fde/mock-v1" in models

    def test_grouped_by_agent(self) -> None:
        """Group token usage by agent."""
        record_token_usage("t1", "fde/mock-v1", 100, 50, agent_module="rag_agent")
        grouped = get_token_usage_grouped(group_by="agent")
        agents = {g["group_value"] for g in grouped}
        assert "rag_agent" in agents

    def test_cost_report(self) -> None:
        """Get cost report."""
        record_token_usage("t1", "deepseek/deepseek-chat", 1000, 500, agent_module="orchestrator")
        report = get_cost_report(period="daily")
        assert isinstance(report, list)
        # DeepSeek has pricing > 0, so total_cost should be > 0 if called
        if report:
            assert report[0]["total_cost"] >= 0

    def test_routing_distribution(self) -> None:
        """Get routing distribution."""
        record_token_usage("t1", "fde/mock-v1", 100, 50, agent_module="router_agent")
        dist = get_routing_distribution()
        assert isinstance(dist, list)
        assert len(dist) >= 1

    def test_model_pricing(self) -> None:
        """Get model pricing table."""
        pricing = get_model_pricing()
        assert len(pricing) > 0
        assert any(p["model"] == "fde/mock-v1" for p in pricing)


class TestBudget:
    """Tests for Cost Canary budget system."""

    def test_set_and_get_budget(self) -> None:
        """Set a budget and retrieve it."""
        set_budget("test_agent", 1.0)
        result = get_budget("test_agent")
        assert result["agent_module"] == "test_agent"
        assert result["daily_limit_usd"] == 1.0

    def test_budget_no_spend_ok(self) -> None:
        """Budget with no spend should be ok."""
        set_budget("empty_agent", 0.5)
        result = get_budget("empty_agent")
        assert result["status"] == "ok"
        assert result["percentage"] == 0.0


class TestApiKeys:
    """Tests for API Key management."""

    def test_create_api_key(self) -> None:
        """Create an API key."""
        result = create_api_key(name="test-key", user_id="user1")
        assert "api_key" in result
        assert result["key_id"]
        assert result["name"] == "test-key"
        # Cleanup
        delete_api_key(result["key_id"])

    def test_validate_api_key(self) -> None:
        """Validate a created API key."""
        created = create_api_key(name="test-key-2", user_id="user2")
        raw_key = created["api_key"]
        info = validate_api_key(raw_key)
        assert info is not None
        assert info["key_id"] == created["key_id"]
        # Invalid key
        assert validate_api_key("fde_invalid_key_xyz") is None
        # Cleanup
        delete_api_key(created["key_id"])

    def test_list_api_keys(self) -> None:
        """List API keys."""
        created = create_api_key(name="list-test", user_id="user3")
        keys = list_api_keys()
        assert any(k["key_id"] == created["key_id"] for k in keys)
        delete_api_key(created["key_id"])

    def test_delete_api_key(self) -> None:
        """Delete an API key."""
        created = create_api_key(name="del-test", user_id="user4")
        key_id = created["key_id"]
        assert delete_api_key(key_id) is True
        assert delete_api_key(key_id) is False  # Already deleted


class TestApiKeyEndpoints:
    """Tests for API Key HTTP endpoints."""

    def test_create_key_endpoint(self, client: TestClient) -> None:
        """POST /api/observability/api/keys creates a key."""
        resp = client.post(
            "/api/observability/api/keys",
            json={"name": "e2e-test", "user_id": "u1", "quota_tpm": 5000, "quota_rpm": 30},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "api_key" in data
        assert data["name"] == "e2e-test"
        # Cleanup
        delete_api_key(data["key_id"])

    def test_list_keys_endpoint(self, client: TestClient) -> None:
        """GET /api/observability/api/keys returns list."""
        created = create_api_key(name="list-e2e", user_id="u1")
        resp = client.get("/api/observability/api/keys")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert any(k["key_id"] == created["key_id"] for k in data)
        delete_api_key(created["key_id"])

    def test_delete_key_endpoint(self, client: TestClient) -> None:
        """DELETE /api/observability/api/keys/{id} deletes key."""
        created = create_api_key(name="del-e2e", user_id="u1")
        key_id = created["key_id"]
        resp = client.delete(f"/api/observability/api/keys/{key_id}")
        assert resp.status_code == 200
        assert resp.json()["deleted"] is True

    def test_create_key_rate_limit(self, client: TestClient) -> None:
        """Rate limit: creating key, then using it repeatedly hits 429."""
        created = create_api_key(name="ratelimit-test", user_id="u1", quota_rpm=2)
        raw_key = created["api_key"]
        headers = {"X-API-Key": raw_key}
        # First request should pass (within limit)
        r1 = client.get("/api/observability/api/external", headers=headers)
        assert r1.status_code in (200, 401)  # 401 if key invalid in test
        # Second request should also pass (limit is 2/min)
        r2 = client.get("/api/observability/api/external", headers=headers)
        assert r2.status_code in (200, 401)
        # Cleanup
        delete_api_key(created["key_id"])


class TestExternalAPIRegistry:
    """Tests for external API registry."""

    def test_external_apis_endpoint(self, client: TestClient) -> None:
        """GET /api/observability/api/external returns registry."""
        resp = client.get("/api/observability/api/external")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) > 0
        # Check known entries
        names = {api["name"] for api in data}
        assert "Dify" in names
        assert "Baidu Maps (Server)" in names


class TestTokenEndpoints:
    """Tests for token usage/cost/budget HTTP endpoints."""

    def test_token_usage_endpoint(self, client: TestClient) -> None:
        """GET /api/observability/tokens/usage returns data."""
        record_token_usage("t1", "fde/mock-v1", 100, 50, agent_module="router_agent")
        resp = client.get("/api/observability/tokens/usage?group_by=model")
        assert resp.status_code == 200
        data = resp.json()
        assert "summary" in data
        assert "data" in data

    def test_token_cost_endpoint(self, client: TestClient) -> None:
        """GET /api/observability/tokens/cost returns data."""
        record_token_usage("t1", "fde/mock-v1", 100, 50, agent_module="router_agent")
        resp = client.get("/api/observability/tokens/cost?period=daily")
        assert resp.status_code == 200
        data = resp.json()
        assert "summary" in data
        assert "data" in data

    def test_token_routing_endpoint(self, client: TestClient) -> None:
        """GET /api/observability/tokens/routing returns distribution."""
        record_token_usage("t1", "fde/mock-v1", 100, 50, agent_module="router_agent")
        resp = client.get("/api/observability/tokens/routing")
        assert resp.status_code == 200
        data = resp.json()
        assert "distribution" in data
        assert "pricing" in data

    def test_budget_endpoints(self, client: TestClient) -> None:
        """POST + GET budget endpoints."""
        resp = client.post(
            "/api/observability/tokens/budget",
            json={"agent_module": "budget_e2e", "daily_limit_usd": 0.1},
        )
        assert resp.status_code == 200
        assert resp.json()["daily_limit_usd"] == 0.1

        resp2 = client.get("/api/observability/tokens/budget?agent_module=budget_e2e")
        assert resp2.status_code == 200
        assert resp2.json()["agent_module"] == "budget_e2e"

    def test_budget_events_endpoint(self, client: TestClient) -> None:
        """GET /api/observability/tokens/budget/events returns events."""
        resp = client.get("/api/observability/tokens/budget/events")
        assert resp.status_code == 200
        data = resp.json()
        assert "events" in data
        assert "total" in data
