"""Tests for Dify Bridge — M2-T7."""

from __future__ import annotations

import pytest

from agents.dify_bridge.models import (
    DifyBridgeConfig,
    DifyParam,
    DifyParamType,
    DifyToolRequest,
    DifyToolResponse,
    DifyToolSpec,
    DifyWorkflowConfig,
)
from agents.orchestrator.tools.registry import ToolDefinition, ToolRegistry

# ══════════════════════════════════════════════════════════════════
# Model Tests
# ══════════════════════════════════════════════════════════════════


class TestDifyModels:
    def test_dify_param_create(self) -> None:
        """DifyParam should hold parameter metadata."""
        p = DifyParam(
            name="query", type=DifyParamType.STRING, required=True, description="Search query"
        )
        assert p.name == "query"
        assert p.required is True
        assert p.type == DifyParamType.STRING

    def test_dify_tool_spec_create(self) -> None:
        """DifyToolSpec should represent a complete tool."""
        spec = DifyToolSpec(
            name="fde_rag_search",
            description="Search knowledge base",
            url="http://localhost:8000/dify/tools/rag_search",
            method="POST",
            parameters=[
                DifyParam(
                    name="query", type=DifyParamType.STRING, required=True, description="Query"
                ),
                DifyParam(name="top_k", type=DifyParamType.INTEGER, required=False, default=5),
            ],
        )
        assert spec.name == "fde_rag_search"
        assert len(spec.parameters) == 2
        assert spec.method == "POST"

    def test_dify_tool_request_create(self) -> None:
        """DifyToolRequest should carry tool name and parameters."""
        req = DifyToolRequest(tool_name="rag_search", parameters={"query": "test"})
        assert req.tool_name == "rag_search"
        assert req.parameters["query"] == "test"

    def test_dify_tool_response_success(self) -> None:
        """Success response should have no error."""
        resp = DifyToolResponse(result={"count": 5})
        assert resp.success is True
        assert resp.error is None

    def test_dify_tool_response_error(self) -> None:
        """Error response should have error message."""
        resp = DifyToolResponse(error="Tool not found")
        assert resp.success is False
        assert resp.error == "Tool not found"

    def test_dify_workflow_config(self) -> None:
        """Workflow config should reference FDE tools."""
        wf = DifyWorkflowConfig(
            name="Compliance Check",
            description="Check compliance on documents",
            tools=["audit_log_query", "risk_check"],
        )
        assert len(wf.tools) == 2
        assert wf.trigger == "manual"

    def test_dify_bridge_config_defaults(self) -> None:
        """Bridge config should have safety limits."""
        cfg = DifyBridgeConfig()
        assert cfg.max_concurrent_workflows == 3
        assert cfg.rate_limit_per_minute == 10
        assert cfg.dify_api_url == "http://217.142.246.70"

    def test_param_type_values(self) -> None:
        """DifyParamType should cover all expected types."""
        values = {t.value for t in DifyParamType}
        assert "string" in values
        assert "number" in values
        assert "array[string]" in values


# ══════════════════════════════════════════════════════════════════
# DifyBridge Tests
# ══════════════════════════════════════════════════════════════════


class TestDifyBridge:
    def test_register_tools_from_registry(self) -> None:
        """Should convert ToolRegistry tools to Dify specs."""
        from agents.dify_bridge.bridge import DifyBridge

        registry = ToolRegistry()
        registry.register(
            ToolDefinition(
                name="test_search",
                description="Test search tool",
                worker="test",
                handler=lambda query="", **kw: {"results": 3},
                parameters={
                    "query": {"type": "string", "required": True, "description": "Query text"}
                },
                category="test",
            )
        )

        bridge = DifyBridge()
        registered = bridge.register_tools_from(registry)
        assert "fde_test_search" in registered

        specs = bridge.export_tool_specs()
        assert len(specs) == 1
        assert specs[0].name == "fde_test_search"

    def test_export_yaml(self) -> None:
        """YAML export should be parseable."""
        from agents.dify_bridge.bridge import DifyBridge

        registry = ToolRegistry()
        registry.register(
            ToolDefinition(
                name="test_search",
                description="Test search tool",
                worker="test",
                handler=lambda query="", **kw: {"results": 3},
                parameters={"query": {"type": "string", "required": True}},
                category="test",
            )
        )

        bridge = DifyBridge()
        bridge.register_tools_from(registry)
        yaml_str = bridge.export_yaml()

        assert "tools:" in yaml_str
        assert "fde_test_search" in yaml_str
        assert "query" in yaml_str

    def test_create_workflow(self) -> None:
        """Should create a Dify workflow with registered tools."""
        from agents.dify_bridge.bridge import DifyBridge

        registry = ToolRegistry()
        registry.register(
            ToolDefinition(
                name="audit",
                description="Audit tool",
                worker="compliance",
                handler=lambda: {"ok": True},
                parameters={},
                category="compliance",
            )
        )

        bridge = DifyBridge()
        bridge.register_tools_from(registry)

        wf = bridge.create_workflow(
            name="Compliance Check", tool_names=["fde_audit"], description="Check compliance"
        )
        assert wf.name == "Compliance Check"
        assert len(bridge.config.workflows) == 1

    def test_create_workflow_missing_tool_raises(self) -> None:
        """Should raise ValueError for unknown tools."""
        from agents.dify_bridge.bridge import DifyBridge

        bridge = DifyBridge()
        with pytest.raises(ValueError, match="not registered"):
            bridge.create_workflow("Bad WF", tool_names=["nonexistent"])

    @pytest.mark.asyncio
    async def test_execute_tool_success(self) -> None:
        """Should execute a tool via Dify bridge."""
        from agents.dify_bridge.bridge import DifyBridge

        registry = ToolRegistry()
        registry.register(
            ToolDefinition(
                name="test_tool",
                description="Test",
                worker="test",
                handler=lambda query="", **kw: {"results": 5, "query": query},
                parameters={"query": {"type": "string", "required": False}},
                category="test",
            )
        )

        bridge = DifyBridge()
        bridge.register_tools_from(registry)

        req = DifyToolRequest(tool_name="test_tool", parameters={"query": "hello"})
        resp = await bridge.execute_tool(req, registry)

        assert resp.success is True
        assert resp.result["results"] == 5

    @pytest.mark.asyncio
    async def test_execute_tool_not_found(self) -> None:
        """Should return error for unknown tool."""
        from agents.dify_bridge.bridge import DifyBridge

        bridge = DifyBridge()
        registry = ToolRegistry()

        req = DifyToolRequest(tool_name="nonexistent", parameters={})
        resp = await bridge.execute_tool(req, registry)

        assert resp.success is False
        assert "not found" in resp.error.lower()

    def test_dify_bridge_empty_registry(self) -> None:
        """Empty registry should produce empty specs."""
        from agents.dify_bridge.bridge import DifyBridge

        bridge = DifyBridge()
        registry = ToolRegistry()
        registered = bridge.register_tools_from(registry)
        assert registered == []
        assert bridge.export_tool_specs() == []
