"""Tests for router agent — FastAPI gateway endpoints."""

from __future__ import annotations

from collections.abc import AsyncGenerator

import pytest
from httpx import ASGITransport, AsyncClient

from agents.router_agent.main import app


@pytest.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


class TestHealthEndpoint:
    async def test_health_returns_ok(self, client: AsyncClient) -> None:
        resp = await client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert "components" in data

    async def test_health_includes_mock_component(self, client: AsyncClient) -> None:
        resp = await client.get("/health")
        data = resp.json()
        assert "fde/mock-v1" in data["components"]


class TestModelsEndpoint:
    async def test_list_models(self, client: AsyncClient) -> None:
        resp = await client.get("/v1/models")
        assert resp.status_code == 200
        data = resp.json()
        assert data["object"] == "list"
        assert len(data["data"]) >= 1
        model_ids = [m["id"] for m in data["data"]]
        assert "fde/mock-v1" in model_ids

    async def test_models_have_correct_structure(self, client: AsyncClient) -> None:
        resp = await client.get("/v1/models")
        data = resp.json()
        for model in data["data"]:
            assert "id" in model
            assert "object" in model
            assert model["object"] == "model"


class TestChatCompletionsEndpoint:
    async def test_basic_chat_completion(self, client: AsyncClient) -> None:
        payload = {
            "messages": [{"role": "user", "content": "你好"}],
        }
        resp = await client.post("/v1/chat/completions", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["object"] == "chat.completion"
        assert len(data["choices"]) == 1
        assert data["choices"][0]["message"]["role"] == "assistant"
        assert data["choices"][0]["message"]["content"]

    async def test_help_query_returns_help_response(self, client: AsyncClient) -> None:
        payload = {
            "messages": [{"role": "user", "content": "help"}],
        }
        resp = await client.post("/v1/chat/completions", json=payload)
        data = resp.json()
        content = data["choices"][0]["message"]["content"]
        assert "FDE" in content

    async def test_empty_messages_rejected(self, client: AsyncClient) -> None:
        resp = await client.post("/v1/chat/completions", json={"messages": []})
        assert resp.status_code == 422

    async def test_missing_messages_rejected(self, client: AsyncClient) -> None:
        resp = await client.post("/v1/chat/completions", json={})
        assert resp.status_code == 422

    async def test_explicit_model_selection(self, client: AsyncClient) -> None:
        payload = {
            "model": "fde/mock-v1",
            "messages": [{"role": "user", "content": "test"}],
        }
        resp = await client.post("/v1/chat/completions", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert "fde/mock-v1" in data["model"]

    async def test_trace_header_propagation(self, client: AsyncClient) -> None:
        payload = {
            "messages": [{"role": "user", "content": "test"}],
        }
        resp = await client.post(
            "/v1/chat/completions", json=payload, headers={"X-Trace-Id": "custom-trace-123"}
        )
        assert resp.headers.get("X-Trace-Id") == "custom-trace-123"

    async def test_response_time_header(self, client: AsyncClient) -> None:
        payload = {
            "messages": [{"role": "user", "content": "test"}],
        }
        resp = await client.post("/v1/chat/completions", json=payload)
        assert "X-Response-Time-ms" in resp.headers

    async def test_multi_turn_conversation(self, client: AsyncClient) -> None:
        payload = {
            "messages": [
                {"role": "system", "content": "你是一个助手。"},
                {"role": "user", "content": "告诉我今天的天气"},
                {"role": "assistant", "content": "今天天气很好。"},
                {"role": "user", "content": "为什么？"},
            ],
        }
        resp = await client.post("/v1/chat/completions", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["choices"][0]["message"]["content"]
        assert data["usage"]["prompt_tokens"] > 0

    async def test_anti_foolproof_blocks_destructive_keyword(self, client: AsyncClient) -> None:
        payload = {
            "messages": [{"role": "user", "content": "delete the entire database"}],
        }
        resp = await client.post("/v1/chat/completions", json=payload)
        assert resp.status_code == 400
        data = resp.json()
        assert data["error"]["code"] == "DESTRUCTIVE_OPERATION"

    async def test_anti_foolproof_bypass_with_header(self, client: AsyncClient) -> None:
        payload = {
            "messages": [{"role": "user", "content": "delete the entire database"}],
        }
        resp = await client.post(
            "/v1/chat/completions",
            json=payload,
            headers={"X-Foolproof-Confirm": "yes"},
        )
        assert resp.status_code == 200  # bypass works, proceeds to mock reply

    async def test_anti_foolproof_blocks_chinese_keyword(self, client: AsyncClient) -> None:
        """防呆机制应拦截中文危险关键词."""
        payload = {
            "messages": [{"role": "user", "content": "请帮我删除所有数据库记录"}],
        }
        resp = await client.post("/v1/chat/completions", json=payload)
        assert resp.status_code == 400
        data = resp.json()
        assert data["error"]["code"] == "DESTRUCTIVE_OPERATION"

    async def test_anti_foolproof_blocks_chinese_destroy(self, client: AsyncClient) -> None:
        """防呆机制应拦截'销毁'关键词."""
        payload = {
            "messages": [{"role": "user", "content": "请销毁所有敏感数据"}],
        }
        resp = await client.post("/v1/chat/completions", json=payload)
        assert resp.status_code == 400

    async def test_anti_foolproof_blocks_chinese_HR_keywords(self, client: AsyncClient) -> None:
        """防呆机制应拦截 HR 相关危险操作（裁掉/解雇/开除）."""
        for word in ["裁掉", "解雇", "开除"]:
            payload = {
                "messages": [{"role": "user", "content": f"请{word}张三"}],
            }
            resp = await client.post("/v1/chat/completions", json=payload)
            assert resp.status_code == 400, f"Keyword '{word}' not blocked"

    async def test_anti_foolproof_chinese_bypass(self, client: AsyncClient) -> None:
        """带确认头时，中文关键词也应被放行."""
        payload = {
            "messages": [{"role": "user", "content": "确认删除所有过期记录"}],
        }
        resp = await client.post(
            "/v1/chat/completions",
            json=payload,
            headers={"X-Foolproof-Confirm": "yes"},
        )
        assert resp.status_code == 200
