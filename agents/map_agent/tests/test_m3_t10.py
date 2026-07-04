"""MapAI M3-T10 tests — LangGraph nodes, interpreter, pipeline, and analysis API.

Tests cover:
- Interpreter: rule-based interpretation generation
- LangGraph nodes: fetch_entities, compute_correlation, generate_interpretation
- Pipeline: full 3-node sequential execution
- Routes: POST /map/analysis endpoint
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest
from fastapi.testclient import TestClient

from agents.map_agent.demo_data import BEIJING_ENTITIES
from agents.map_agent.interpreter import AnalysisInterpreter, get_interpreter
from agents.map_agent.langgraph_nodes import (
    NodeState,
    compute_correlation,
    fetch_entities,
    generate_interpretation,
    run_pipeline,
)
from agents.map_agent.models import (
    CorrelationMethod,
    CorrelationResponse,
    GeoEntity,
    GeoPoint,
)

# ══════════════════════════════════════════════════════════════════
# Helpers
# ══════════════════════════════════════════════════════════════════


def _run(coro: Any) -> Any:
    """Run an async coroutine synchronously, compatible with pytest-asyncio AUTO mode."""
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
    lng: float = 116.0,
    lat: float = 39.9,
    props: dict[str, Any] | None = None,
) -> GeoEntity:
    """Create a test GeoEntity."""
    return GeoEntity(
        entity_id=eid,
        name=name,
        location=GeoPoint(lng=lng, lat=lat, label=name),
        entity_type="test",
        properties=props or {"value": 100},
    )


# ══════════════════════════════════════════════════════════════════
# Interpreter Tests
# ══════════════════════════════════════════════════════════════════


class TestInterpreter:
    """Test the AnalysisInterpreter."""

    def test_interpret_with_results(self) -> None:
        """Interpreter should produce text when given valid correlation results."""
        entities = [
            _make_entity("e1", "Alpha", props={"pop": 100}),
            _make_entity("e2", "Beta", props={"pop": 200}),
        ]
        # Build a mock correlation response
        from agents.map_agent.models import (
            CorrelationMethod,
            CorrelationPairResult,
            CorrelationResponse,
        )

        response = CorrelationResponse(
            session_id="test",
            method=CorrelationMethod.PEARSON,
            entity_count=2,
            pair_count=1,
            results=[
                CorrelationPairResult(
                    entity_a="Alpha",
                    property_a="pop",
                    entity_b="Beta",
                    property_b="pop",
                    coefficient=0.85,
                    p_value=0.01,
                    strength="very_strong",
                    interpretation="test",
                )
            ],
            summary="Test summary",
        )

        interpreter = AnalysisInterpreter()
        text = interpreter.interpret(response, entities)
        assert len(text) > 50
        assert "Alpha" in text
        assert "Beta" in text
        assert "pop" in text

    def test_interpret_no_results(self) -> None:
        """Interpreter should handle empty results gracefully."""
        entities = [_make_entity("e1", "Alpha")]
        response = CorrelationResponse(
            session_id="test",
            method=CorrelationMethod.PEARSON,
            entity_count=1,
            pair_count=0,
            results=[],
            summary="No pairs",
        )
        interpreter = AnalysisInterpreter()
        text = interpreter.interpret(response, entities)
        assert "未找到可量化" in text or "不足" in text

    def test_interpret_with_user_query(self) -> None:
        """Interpreter should include user query context."""
        entities = [
            _make_entity("e1", "Alpha", props={"v": 10}),
            _make_entity("e2", "Beta", props={"v": 20}),
        ]
        from agents.map_agent.models import (
            CorrelationMethod,
            CorrelationPairResult,
            CorrelationResponse,
        )

        response = CorrelationResponse(
            session_id="t",
            method=CorrelationMethod.PEARSON,
            entity_count=2,
            pair_count=1,
            results=[
                CorrelationPairResult(
                    entity_a="Alpha",
                    property_a="v",
                    entity_b="Beta",
                    property_b="v",
                    coefficient=0.5,
                    p_value=0.1,
                    strength="moderate",
                )
            ],
        )
        interpreter = AnalysisInterpreter()
        text = interpreter.interpret(response, entities, user_query="Why is this happening?")
        assert "Why is this happening?" in text

    def test_build_llm_prompt(self) -> None:
        """LLM prompt builder should produce a structured prompt."""
        entities = [
            _make_entity("e1", "Alpha", props={"v": 10}),
            _make_entity("e2", "Beta", props={"v": 20}),
        ]
        from agents.map_agent.models import (
            CorrelationMethod,
            CorrelationPairResult,
            CorrelationResponse,
        )

        response = CorrelationResponse(
            session_id="t",
            method=CorrelationMethod.PEARSON,
            entity_count=2,
            pair_count=1,
            results=[
                CorrelationPairResult(
                    entity_a="Alpha",
                    property_a="v",
                    entity_b="Beta",
                    property_b="v",
                    coefficient=0.8,
                    p_value=0.01,
                    strength="strong",
                )
            ],
        )
        interpreter = AnalysisInterpreter()
        prompt = interpreter.build_llm_prompt(response, entities, "test query")
        assert "空间数据分析专家" in prompt
        assert "Alpha" in prompt
        assert "test query" in prompt

    def test_get_interpreter_singleton(self) -> None:
        """get_interpreter should return the same instance."""
        a = get_interpreter()
        b = get_interpreter()
        assert a is b


# ══════════════════════════════════════════════════════════════════
# LangGraph Node Tests
# ══════════════════════════════════════════════════════════════════


class TestFetchEntities:
    """Test the fetch_entities node."""

    def test_fetch_valid_ids(self) -> None:
        """Should fetch entities that exist in demo data."""
        state = NodeState(
            entity_ids=["bj-001", "bj-002"],
            errors=[],
            nodes_traced=[],
            timing_ms={},
        )
        result = fetch_entities(state)
        assert len(result["entities"]) == 2
        assert result["entities"][0].entity_id == "bj-001"
        assert "fetch_entities" in result["nodes_traced"]
        assert "fetch_entities" in result["timing_ms"]

    def test_fetch_with_missing_id(self) -> None:
        """Missing entity IDs should be logged as errors, not crash."""
        state = NodeState(
            entity_ids=["bj-001", "nonexistent"],
            errors=[],
            nodes_traced=[],
            timing_ms={},
        )
        result = fetch_entities(state)
        assert len(result["entities"]) == 1
        assert len(result["errors"]) == 1
        assert "nonexistent" in result["errors"][0]

    def test_fetch_empty_ids(self) -> None:
        """Empty entity_ids should produce empty entities list."""
        state = NodeState(
            entity_ids=[],
            errors=[],
            nodes_traced=[],
            timing_ms={},
        )
        result = fetch_entities(state)
        assert result["entities"] == []
        assert len(result["errors"]) == 0  # empty IDs just return empty, no error

    def test_fetch_shanghai_entities(self) -> None:
        """Should fetch Shanghai entities."""
        state = NodeState(
            entity_ids=["sh-001", "sh-002"],
            errors=[],
            nodes_traced=[],
            timing_ms={},
        )
        result = fetch_entities(state)
        assert len(result["entities"]) == 2
        assert result["entities"][0].name == "陆家嘴金融区"


class TestComputeCorrelation:
    """Test the compute_correlation node."""

    def test_compute_with_two_entities(self) -> None:
        """Should produce correlation results with 2+ entities."""
        entities = [
            _make_entity("e1", "A", props={"v": 100}),
            _make_entity("e2", "B", props={"v": 200}),
        ]
        state = NodeState(
            entities=entities,
            method="pearson",
            errors=[],
            nodes_traced=[],
            timing_ms={},
        )
        result = compute_correlation(state)
        assert result["correlation"] is not None
        assert result["correlation"].entity_count == 2
        assert "compute_correlation" in result["nodes_traced"]

    def test_compute_with_one_entity(self) -> None:
        """Should fail gracefully with < 2 entities."""
        entities = [_make_entity("e1", "A")]
        state = NodeState(
            entities=entities,
            method="pearson",
            errors=[],
            nodes_traced=[],
            timing_ms={},
        )
        result = compute_correlation(state)
        assert result["correlation"] is None
        assert len(result["errors"]) >= 1

    def test_compute_with_invalid_method(self) -> None:
        """Should default to pearson for unknown method."""
        entities = [
            _make_entity("e1", "A", props={"v": 1}),
            _make_entity("e2", "B", props={"v": 2}),
        ]
        state = NodeState(
            entities=entities,
            method="nonexistent_method",
            errors=[],
            nodes_traced=[],
            timing_ms={},
        )
        result = compute_correlation(state)
        assert result["correlation"] is not None

    def test_compute_with_demo_entities(self) -> None:
        """Should compute correlation on demo Beijing entities."""
        entities = [BEIJING_ENTITIES[0], BEIJING_ENTITIES[1]]
        state = NodeState(
            entities=entities,
            method="pearson",
            errors=[],
            nodes_traced=[],
            timing_ms={},
        )
        result = compute_correlation(state)
        assert result["correlation"] is not None
        assert result["correlation"].pair_count > 0


class TestGenerateInterpretation:
    """Test the generate_interpretation node."""

    def test_generate_with_valid_correlation(self) -> None:
        """Should produce interpretation text when correlation exists."""
        entities = [
            _make_entity("e1", "Alpha", props={"v": 100}),
            _make_entity("e2", "Beta", props={"v": 200}),
        ]
        # First compute correlation
        state = NodeState(
            entities=entities,
            method="pearson",
            errors=[],
            nodes_traced=[],
            timing_ms={},
        )
        state = compute_correlation(state)

        # Then generate interpretation
        result = generate_interpretation(state)
        assert len(result["interpretation"]) > 20
        assert "generate_interpretation" in result["nodes_traced"]

    def test_generate_with_no_correlation(self) -> None:
        """Should produce error message when correlation is None."""
        state = NodeState(
            entities=[],
            correlation=None,
            errors=["Some error"],
            nodes_traced=[],
            timing_ms={},
        )
        result = generate_interpretation(state)
        assert "分析未能完成" in result["interpretation"]

    def test_generate_with_query_context(self) -> None:
        """Should include user query in interpretation."""
        entities = [
            _make_entity("e1", "A", props={"v": 1}),
            _make_entity("e2", "B", props={"v": 2}),
        ]
        state = NodeState(
            entities=entities,
            method="pearson",
            query="What is the correlation?",
            errors=[],
            nodes_traced=[],
            timing_ms={},
        )
        state = compute_correlation(state)
        result = generate_interpretation(state)
        assert "What is the correlation?" in result["interpretation"]


# ══════════════════════════════════════════════════════════════════
# Pipeline Tests
# ══════════════════════════════════════════════════════════════════


class TestPipeline:
    """Test the full 3-node pipeline."""

    def test_pipeline_full_run(self) -> None:
        """Full pipeline should execute all 3 nodes and produce results."""
        result = run_pipeline(
            entity_ids=["bj-001", "bj-002", "bj-003"],
            method="pearson",
            query="Analyze Beijing CBD areas",
        )
        assert len(result["entities"]) == 3
        assert result["correlation"] is not None
        assert result["correlation"].pair_count > 0
        assert len(result["interpretation"]) > 50
        assert len(result["nodes_traced"]) == 4
        assert result["nodes_traced"][:3] == [
            "fetch_entities",
            "enrich_entity_data",
            "compute_correlation",
        ]
        assert len(result["timing_ms"]) >= 3

    def test_pipeline_insufficient_entities(self) -> None:
        """Pipeline should handle < 2 entities gracefully."""
        result = run_pipeline(
            entity_ids=["bj-001"],
            method="pearson",
        )
        assert len(result["entities"]) == 1
        assert result["correlation"] is None
        assert "不足" in result["interpretation"] or "未能完成" in result["interpretation"]

    def test_pipeline_with_missing_ids(self) -> None:
        """Pipeline should continue with available entities."""
        result = run_pipeline(
            entity_ids=["bj-001", "nonexistent", "bj-002"],
            method="pearson",
        )
        assert len(result["entities"]) == 2
        assert result["correlation"] is not None
        assert len(result["errors"]) == 1

    def test_pipeline_shanghai(self) -> None:
        """Pipeline should work with Shanghai entities."""
        result = run_pipeline(
            entity_ids=["sh-001", "sh-002", "sh-003"],
            query="Analyze Shanghai business districts",
        )
        assert len(result["entities"]) == 3
        assert result["correlation"] is not None
        assert "Analyze Shanghai business districts" in result["interpretation"]

    def test_pipeline_timing(self) -> None:
        """Pipeline should record timing for each node."""
        result = run_pipeline(entity_ids=["bj-001", "bj-002"])
        for node in ["fetch_entities", "compute_correlation", "generate_interpretation"]:
            assert node in result["timing_ms"]
            assert result["timing_ms"][node] >= 0


# ══════════════════════════════════════════════════════════════════
# API Route Tests
# ══════════════════════════════════════════════════════════════════


class TestAnalysisRoute:
    """Test the POST /map/analysis endpoint."""

    @pytest.fixture
    def client(self) -> TestClient:
        """Create a FastAPI test client with the map router."""
        from fastapi import FastAPI

        app = FastAPI()
        from agents.map_agent.routes import router

        app.include_router(router)
        return TestClient(app)

    def test_analysis_success(self, client: TestClient) -> None:
        """Should return 200 with full analysis results."""
        response = client.post(
            "/map/analysis",
            json={
                "entity_ids": ["bj-001", "bj-002", "bj-003"],
                "method": "pearson",
                "query": "Test analysis",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["entity_ids"]) == 3
        assert len(data["entities"]) == 3
        assert data["correlation"] is not None
        assert len(data["interpretation"]) > 20
        assert len(data["nodes_traced"]) == 4
        assert data["execution_time_ms"] >= 0

    def test_analysis_insufficient_entities(self, client: TestClient) -> None:
        """Should return 400 with < 2 entity IDs."""
        response = client.post(
            "/map/analysis",
            json={"entity_ids": ["bj-001"]},
        )
        assert response.status_code == 400
        assert "至少 2" in response.json()["detail"]

    def test_analysis_empty_entities(self, client: TestClient) -> None:
        """Should return 422 (validation error) with empty list."""
        response = client.post(
            "/map/analysis",
            json={"entity_ids": []},
        )
        assert response.status_code == 422

    def test_analysis_with_missing_ids(self, client: TestClient) -> None:
        """Should still succeed if some IDs are missing."""
        response = client.post(
            "/map/analysis",
            json={"entity_ids": ["bj-001", "nonexistent", "bj-002"]},
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["entities"]) == 2
        assert len(data["errors"]) == 1

    def test_analysis_default_method(self, client: TestClient) -> None:
        """Should use pearson as default method."""
        response = client.post(
            "/map/analysis",
            json={"entity_ids": ["bj-001", "bj-002"]},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["correlation"]["method"] == "pearson"

    def test_analysis_with_query(self, client: TestClient) -> None:
        """Should include user query in interpretation."""
        response = client.post(
            "/map/analysis",
            json={
                "entity_ids": ["bj-001", "bj-002"],
                "query": "Why are these areas different?",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert "Why are these areas different?" in data["interpretation"]

    def test_analysis_shanghai(self, client: TestClient) -> None:
        """Should work with Shanghai entities."""
        response = client.post(
            "/map/analysis",
            json={"entity_ids": ["sh-001", "sh-002", "sh-003", "sh-004"]},
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["entities"]) == 4
        assert data["correlation"]["pair_count"] > 0
