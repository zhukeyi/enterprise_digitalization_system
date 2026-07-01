"""Dify bridge — convert LangGraph tools to Dify-compatible format (M2-T7).

This is the core adapter that translates FDE's ToolRegistry tools into
Dify custom tool specifications. Dify calls FDE as external HTTP API tools.

Architecture constraint: Dify is admin-backend only, QPS limit = 5.
All production traffic goes through LangGraph directly.
"""

from __future__ import annotations

import logging
from typing import Any

from agents.dify_bridge.models import (
    DifyBridgeConfig,
    DifyParam,
    DifyParamType,
    DifyToolRequest,
    DifyToolResponse,
    DifyToolSpec,
    DifyWorkflowConfig,
)
from agents.orchestrator.tools.registry import ToolRegistry

logger = logging.getLogger("fde.dify.bridge")

# ── FDE type → Dify type mapping ──────────────────────────────────

_FDE_TO_DIFY_TYPE: dict[str, DifyParamType] = {
    "string": DifyParamType.STRING,
    "integer": DifyParamType.INTEGER,
    "number": DifyParamType.NUMBER,
    "boolean": DifyParamType.BOOLEAN,
    "array": DifyParamType.ARRAY_STRING,
    "object": DifyParamType.OBJECT,
}


# ══════════════════════════════════════════════════════════════════
# DifyBridge — core converter
# ══════════════════════════════════════════════════════════════════


class DifyBridge:
    """Converts FDE ToolRegistry tools to Dify-compatible tool specifications.

    Usage:
        bridge = DifyBridge(config)
        bridge.register_tools_from(registry)
        specs = bridge.export_tool_specs()  # → list[DifyToolSpec]
        yaml_str = bridge.export_yaml()      # → Dify import file
    """

    def __init__(self, config: DifyBridgeConfig | None = None) -> None:
        self.config = config or DifyBridgeConfig()
        self._tools: dict[str, DifyToolSpec] = {}

    def register_tools_from(self, registry: ToolRegistry) -> list[str]:
        """Convert all registered tools to Dify specs.

        Args:
            registry: The orchestrator's ToolRegistry with registered tools.

        Returns:
            List of tool names that were successfully registered.
        """
        registered: list[str] = []

        for tool_def in registry.list_all():
            try:
                spec = self._convert_tool(tool_def)
                self._tools[spec.name] = spec
                registered.append(spec.name)
            except Exception as e:
                logger.warning("Failed to convert tool '%s' to Dify: %s", tool_def.name, e)

        logger.info(
            "Registered %d/%d tools as Dify specs",
            len(registered),
            len(registry.list_all()),
        )
        return registered

    def export_tool_specs(self) -> list[DifyToolSpec]:
        """Export all registered Dify tool specifications."""
        return list(self._tools.values())

    def export_yaml(self) -> str:
        """Export tools as Dify-compatible YAML for import.

        Dify supports importing custom tools via YAML/OpenAPI format.
        """
        import yaml

        tools_data = []
        for tool in self._tools.values():
            tools_data.append(
                {
                    "identity": {
                        "name": tool.name,
                        "author": "FDE AI Platform",
                        "label": {"en_US": tool.name, "zh_Hans": tool.description[:50]},
                    },
                    "description": {
                        "en_US": tool.description,
                        "zh_Hans": tool.description,
                    },
                    "parameters": [
                        {
                            "name": p.name,
                            "type": p.type.value,
                            "required": p.required,
                            "description": {"en_US": p.description},
                            "default": p.default,
                        }
                        for p in tool.parameters
                    ],
                }
            )

        return yaml.dump({"tools": tools_data}, allow_unicode=True, sort_keys=False)

    def create_workflow(
        self, name: str, tool_names: list[str], description: str = ""
    ) -> DifyWorkflowConfig:
        """Create a Dify workflow configuration using FDE tools.

        Args:
            name: Workflow display name.
            tool_names: FDE tools to include in the workflow.
            description: Optional human-readable description.

        Returns:
            Workflow configuration for Dify import.
        """
        # Validate all tools exist
        missing = [t for t in tool_names if t not in self._tools]
        if missing:
            raise ValueError(f"Tools not registered: {missing}")

        workflow = DifyWorkflowConfig(
            name=name,
            description=description,
            tools=tool_names,
        )
        self.config.workflows.append(workflow)
        return workflow

    # ── Private: tool conversion ────────────────────────────────────

    def _convert_tool(self, tool_def: Any) -> DifyToolSpec:
        """Convert a ToolDefinition to a DifyToolSpec.

        Maps FDE parameter schemas to Dify-compatible OpenAPI parameters.
        """
        params = []
        for param_name, param_schema in tool_def.parameters.items():
            param_type = (
                param_schema.get("type", "string") if isinstance(param_schema, dict) else "string"
            )
            params.append(
                DifyParam(
                    name=param_name,
                    type=_FDE_TO_DIFY_TYPE.get(param_type, DifyParamType.STRING),
                    required=(
                        param_schema.get("required", False)
                        if isinstance(param_schema, dict)
                        else False
                    ),
                    description=(
                        param_schema.get("description", "")
                        if isinstance(param_schema, dict)
                        else ""
                    ),
                    default=param_schema.get("default") if isinstance(param_schema, dict) else None,
                )
            )

        return DifyToolSpec(
            name=f"fde_{tool_def.name}",
            description=tool_def.description,
            category=f"fde_{tool_def.category}",
            url=f"{self.config.fde_api_url}/dify/tools/{tool_def.name}",
            method="POST",
            headers={"Content-Type": "application/json"},
            parameters=params,
        )

    # ── Private: tool execution (called from FastAPI endpoint) ──────

    async def execute_tool(
        self, request: DifyToolRequest, registry: ToolRegistry
    ) -> DifyToolResponse:
        """Execute a FDE tool on behalf of Dify.

        This is the runtime bridge — Dify calls FDE's /dify/tools/{name}
        endpoint, which delegates to this method.

        Args:
            request: Dify-formatted tool request.
            registry: The ToolRegistry with registered handlers.

        Returns:
            Dify-compatible response.
        """
        try:
            import time

            start = time.monotonic()
            result = await registry.dispatch(request.tool_name, **request.parameters)
            latency_ms = int((time.monotonic() - start) * 1000)

            logger.info(
                "Dify tool '%s' executed in %dms (user=%s)",
                request.tool_name,
                latency_ms,
                request.user_id,
            )

            return DifyToolResponse(
                result=result,
                metadata={
                    "tool": request.tool_name,
                    "latency_ms": latency_ms,
                    "session_id": request.session_id,
                },
            )
        except KeyError:
            return DifyToolResponse(error=f"Tool '{request.tool_name}' not found in registry")
        except Exception as e:
            logger.error("Dify tool '%s' failed: %s", request.tool_name, e)
            return DifyToolResponse(error=str(e))
