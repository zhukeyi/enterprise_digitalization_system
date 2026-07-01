"""Tests for MapAI — Module L."""

from __future__ import annotations


class TestMapModels:
    def test_geo_point_create(self) -> None:
        from agents.map_agent.models import GeoPoint

        p = GeoPoint(lng=116.4, lat=39.9, label="Beijing")
        assert p.lng == 116.4
        assert p.label == "Beijing"

    def test_geo_entity_create(self) -> None:
        from agents.map_agent.models import GeoEntity, GeoPoint

        e = GeoEntity(
            entity_id="e1",
            name="CBD",
            location=GeoPoint(lng=116.46, lat=39.92),
            properties={"pop": 180000},
        )
        assert e.properties["pop"] == 180000

    def test_analysis_context_add(self) -> None:
        from agents.map_agent.models import AnalysisContext, GeoEntity, GeoPoint

        ctx = AnalysisContext(session_id="s1")
        ctx.add_entity(
            GeoEntity(
                entity_id="e1",
                name="A",
                location=GeoPoint(lng=0, lat=0),
            )
        )
        assert ctx.entity_count == 1
        ctx.add_entity(
            GeoEntity(
                entity_id="e1",
                name="A2",
                location=GeoPoint(lng=1, lat=1),
            )
        )
        assert ctx.entity_count == 1  # Dedup

    def test_analysis_context_remove(self) -> None:
        from agents.map_agent.models import AnalysisContext, GeoEntity, GeoPoint

        ctx = AnalysisContext(session_id="s1")
        ctx.add_entity(GeoEntity(entity_id="e1", name="A", location=GeoPoint(lng=0, lat=0)))
        assert ctx.remove_entity("e1") is True
        assert ctx.remove_entity("e1") is False


class TestDemoData:
    def test_beijing_entities_exist(self) -> None:
        from agents.map_agent.demo_data import BEIJING_ENTITIES

        assert len(BEIJING_ENTITIES) == 6

    def test_get_region(self) -> None:
        from agents.map_agent.demo_data import get_demo_region

        r = get_demo_region("beijing")
        assert r is not None
        assert r.name == "北京"
        assert len(r.entities) == 6

    def test_get_unknown_region(self) -> None:
        from agents.map_agent.demo_data import get_demo_region

        assert get_demo_region("paris") is None

    def test_entities_in_bounds(self) -> None:
        from agents.map_agent.demo_data import get_entities_in_bounds

        results = get_entities_in_bounds(116.0, 39.5, 117.0, 40.5)
        assert len(results) > 0

    def test_entities_in_empty_bounds(self) -> None:
        from agents.map_agent.demo_data import get_entities_in_bounds

        results = get_entities_in_bounds(0, 0, 1, 1)
        assert results == []


class TestCorrelationEngine:
    def test_engine_singleton(self) -> None:
        from agents.map_agent.engine import get_correlation_engine

        e1 = get_correlation_engine()
        e2 = get_correlation_engine()
        assert e1 is e2

    def test_insufficient_entities(self) -> None:
        from agents.map_agent.engine import get_correlation_engine
        from agents.map_agent.models import AnalysisContext, CorrelationRequest

        engine = get_correlation_engine()
        ctx = AnalysisContext(session_id="s1")
        resp = engine.compute(CorrelationRequest(context=ctx))
        assert resp.entity_count == 0
        assert resp.pair_count == 0

    def test_auto_pair_beijing(self) -> None:
        from agents.map_agent.demo_data import BEIJING_ENTITIES
        from agents.map_agent.engine import get_correlation_engine
        from agents.map_agent.models import AnalysisContext, CorrelationRequest

        engine = get_correlation_engine()
        ctx = AnalysisContext(session_id="s1", entities=list(BEIJING_ENTITIES))
        resp = engine.compute(CorrelationRequest(context=ctx))
        assert resp.entity_count == 6
        assert resp.pair_count > 0
        assert resp.summary != "<PASSWORD>"

    def test_coefficient_range(self) -> None:
        from agents.map_agent.engine import SpatialCorrelationEngine

        engine = SpatialCorrelationEngine()
        coef, pval = engine._compute_coefficient(100, 50)
        assert -1 <= coef <= 1
        assert 0 <= pval <= 1


class TestMapWorker:
    def test_worker_instantiation(self) -> None:
        from agents.orchestrator.langgraph.workers import MapWorker
        from agents.orchestrator.tools.registry import ToolRegistry

        w = MapWorker(ToolRegistry())
        assert w.name == "map"

    def test_register_tools(self) -> None:
        from agents.map_agent.worker import register_map_tools
        from agents.orchestrator.tools.registry import ToolRegistry

        registry = ToolRegistry()
        register_map_tools(registry)
        tools = registry.get_tools_for_worker("map")
        assert len(tools) == 2
        names = {t.name for t in tools}
        assert "map_spatial_query" in names
        assert "map_correlate" in names
