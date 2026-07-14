"""Tests for MapAI interpreter LLM integration (Ollama/LiteLLM).

Tests cover:
- interpret_with_llm falls back to rule templates when env vars unset
- interpret_with_llm calls LLM and returns its text when configured
- interpret_with_llm falls back on LLM error
- generate_interpretation node uses LLM path when configured
"""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from agents.map_agent.interpreter import AnalysisInterpreter
from agents.map_agent.langgraph_nodes import NodeState, generate_interpretation
from agents.map_agent.models import (
    CorrelationMethod,
    CorrelationPairResult,
    CorrelationResponse,
    GeoEntity,
    GeoPoint,
)


def _run(coro: Any) -> Any:
    """Run an async coroutine synchronously."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_closed():
            raise RuntimeError("loop closed")
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    return loop.run_until_complete(coro)


def _make_entity(
    eid: str,
    name: str,
    props: dict[str, Any] | None = None,
) -> GeoEntity:
    return GeoEntity(
        entity_id=eid,
        name=name,
        location=GeoPoint(lng=116.0, lat=39.9, label=name),
        entity_type="test",
        properties=props or {"value": 100},
    )


def _make_response() -> CorrelationResponse:
    return CorrelationResponse(
        session_id="test",
        method=CorrelationMethod.PEARSON,
        entity_count=2,
        pair_count=1,
        results=[
            CorrelationPairResult(
                entity_a="Alpha",
                property_a="v",
                entity_b="Beta",
                property_b="v",
                coefficient=0.85,
                p_value=0.01,
                strength="very_strong",
            )
        ],
    )


class TestInterpretWithLLM:
    """Test the interpret_with_llm method."""

    def test_falls_back_when_env_unset(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """When FDE_MAP_LLM_MODEL or LITELLM_PROXY_URL is unset, use rule templates."""
        monkeypatch.setattr("agents.map_agent.interpreter._MAP_LLM_MODEL", "")
        monkeypatch.setattr("agents.map_agent.interpreter._LITELLM_PROXY_URL", "")

        entities = [_make_entity("e1", "Alpha"), _make_entity("e2", "Beta")]
        response = _make_response()
        interpreter = AnalysisInterpreter()

        text = _run(interpreter.interpret_with_llm(response, entities))
        # Should contain rule-based content, not an LLM call
        assert "Alpha" in text
        assert "极强" in text or "强" in text

    def test_calls_llm_when_configured(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """When env vars are set, call the LLM and return its text."""
        monkeypatch.setattr("agents.map_agent.interpreter._MAP_LLM_MODEL", "fde-local")
        monkeypatch.setattr("agents.map_agent.interpreter._LITELLM_PROXY_URL", "http://localhost:11434/v1")

        entities = [_make_entity("e1", "Alpha"), _make_entity("e2", "Beta")]
        response = _make_response()
        interpreter = AnalysisInterpreter()

        mock_llm_text = "LLM 生成的专业解读：Alpha 和 Beta 存在显著正相关。"
        with patch(
            "agents.map_agent.interpreter._call_llm",
            new_callable=AsyncMock,
            return_value=mock_llm_text,
        ):
            text = _run(interpreter.interpret_with_llm(response, entities))

        assert text == mock_llm_text
        assert "LLM" in text

    def test_falls_back_on_llm_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """When the LLM call raises, fall back to rule templates."""
        monkeypatch.setattr("agents.map_agent.interpreter._MAP_LLM_MODEL", "fde-local")
        monkeypatch.setattr("agents.map_agent.interpreter._LITELLM_PROXY_URL", "http://localhost:11434/v1")

        entities = [_make_entity("e1", "Alpha"), _make_entity("e2", "Beta")]
        response = _make_response()
        interpreter = AnalysisInterpreter()

        with patch(
            "agents.map_agent.interpreter._call_llm",
            new_callable=AsyncMock,
            side_effect=RuntimeError("connection refused"),
        ):
            text = _run(interpreter.interpret_with_llm(response, entities))

        # Should contain rule-based fallback
        assert "Alpha" in text
        assert "极强" in text or "强" in text

    def test_falls_back_on_empty_llm_response(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """When the LLM returns empty text, fall back to rule templates."""
        monkeypatch.setattr("agents.map_agent.interpreter._MAP_LLM_MODEL", "fde-local")
        monkeypatch.setattr("agents.map_agent.interpreter._LITELLM_PROXY_URL", "http://localhost:11434/v1")

        entities = [_make_entity("e1", "Alpha"), _make_entity("e2", "Beta")]
        response = _make_response()
        interpreter = AnalysisInterpreter()

        with patch(
            "agents.map_agent.interpreter._call_llm",
            new_callable=AsyncMock,
            return_value="",
        ):
            text = _run(interpreter.interpret_with_llm(response, entities))

        assert "Alpha" in text
        assert "极强" in text or "强" in text


class TestGenerateInterpretationWithLLM:
    """Test the generate_interpretation node with LLM enabled."""

    def test_node_uses_llm_when_configured(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """generate_interpretation should call LLM when FDE_MAP_LLM_MODEL is set."""
        monkeypatch.setattr("agents.map_agent.interpreter._MAP_LLM_MODEL", "fde-local")
        monkeypatch.setattr("agents.map_agent.interpreter._LITELLM_PROXY_URL", "http://localhost:11434/v1")

        entities = [
            _make_entity("e1", "Alpha", props={"v": 100}),
            _make_entity("e2", "Beta", props={"v": 200}),
        ]
        from agents.map_agent.langgraph_nodes import compute_correlation

        state = NodeState(
            entities=entities,
            method="pearson",
            errors=[],
            nodes_traced=[],
            timing_ms={},
        )
        state = compute_correlation(state)

        mock_text = "这是来自 LLM 的专业空间分析解读。"
        with patch(
            "agents.map_agent.interpreter._call_llm",
            new_callable=AsyncMock,
            return_value=mock_text,
        ):
            result = generate_interpretation(state)

        assert result["interpretation"] == mock_text
        assert "generate_interpretation" in result["nodes_traced"]

    def test_node_falls_back_to_rules_when_unset(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """generate_interpretation should use rules when FDE_MAP_LLM_MODEL is unset."""
        monkeypatch.setattr("agents.map_agent.interpreter._MAP_LLM_MODEL", "")
        monkeypatch.setattr("agents.map_agent.interpreter._LITELLM_PROXY_URL", "")

        entities = [
            _make_entity("e1", "Alpha", props={"v": 100}),
            _make_entity("e2", "Beta", props={"v": 200}),
        ]
        from agents.map_agent.langgraph_nodes import compute_correlation

        state = NodeState(
            entities=entities,
            method="pearson",
            errors=[],
            nodes_traced=[],
            timing_ms={},
        )
        state = compute_correlation(state)
        result = generate_interpretation(state)

        # Rule-based content
        assert "Alpha" in result["interpretation"]
        assert "相关性" in result["interpretation"] or "相关" in result["interpretation"]
