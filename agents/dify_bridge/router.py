"""Dify bridge — FastAPI router for Dify tool execution (M2-T7).

Registers /dify/tools/* endpoints that Dify calls as external API tools.
This is the runtime integration point between Dify workflows and FDE tools.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Request

from agents.dify_bridge.bridge import DifyBridge
from agents.dify_bridge.models import DifyBridgeConfig, DifyToolRequest, DifyToolResponse
from agents.orchestrator.tools.registry import ToolRegistry

logger = logging.getLogger("fde.dify.router")


def create_dify_router(
    registry: ToolRegistry,
    config: DifyBridgeConfig | None = None,
) -> APIRouter:
    """Create a FastAPI router with Dify tool execution endpoints.

    Args:
        registry: The orchestrator's ToolRegistry (shared instance).
        config: Dify bridge configuration.

    Returns:
        FastAPI APIRouter with /dify/tools/* routes.
    """
    bridge = DifyBridge(config)
    bridge.register_tools_from(registry)

    router = APIRouter(prefix="/dify", tags=["dify"])

    # ── Tool execution endpoint ─────────────────────────────────────
    @router.post("/tools/{tool_name}", response_model=DifyToolResponse)
    async def execute_tool(
        tool_name: str,
        body: DifyToolRequest,
        request: Request,
    ) -> DifyToolResponse:
        """Execute a FDE tool on behalf of Dify.

        This endpoint is called by Dify's HTTP Request / API tool node.
        Dify passes the tool parameters as a JSON body.
        """
        logger.info("Dify calling tool '%s' (session=%s)", tool_name, body.session_id)

        # Ensure tool_name matches the request
        body.tool_name = tool_name

        response = await bridge.execute_tool(body, registry)

        if response.error:
            logger.warning("Dify tool '%s' failed: %s", tool_name, response.error)
            # Don't raise HTTPException — Dify expects the error in the response body

        return response

    # ── Tool listing endpoint ───────────────────────────────────────
    @router.get("/tools", response_model=list[dict[str, Any]])
    async def list_tools() -> list[dict[str, Any]]:
        """List all registered Dify tools with their specifications.

        Called by Dify admin UI to populate the tool list.
        """
        specs = bridge.export_tool_specs()
        return [
            {
                "name": s.name,
                "description": s.description,
                "category": s.category,
                "url": s.url,
                "method": s.method,
                "parameters": [
                    {
                        "name": p.name,
                        "type": p.type.value,
                        "required": p.required,
                        "description": p.description,
                    }
                    for p in s.parameters
                ],
            }
            for s in specs
        ]

    # ── YAML export endpoint ────────────────────────────────────────
    @router.get("/tools/export")
    async def export_yaml() -> dict[str, str]:
        """Export tools as Dify-compatible YAML for import into Dify.

        Admin users can download this YAML and import it into Dify's
        custom tool management page.
        """
        return {"yaml": bridge.export_yaml()}

    # ── Health check ────────────────────────────────────────────────
    @router.get("/health")
    async def health() -> dict[str, str]:
        """Health check for Dify bridge availability."""

        return {
            "status": "ok",
            "tools_count": str(len(bridge.export_tool_specs())),
            "dify_url": bridge.config.dify_api_url,
        }

    # ── OpenAPI spec serving (P7: for Dify Custom Tool import) ─────
    @router.get("/openapi.yaml")
    async def openapi_spec() -> Any:
        """Serve the FDE OpenAPI 3.0 spec for Dify custom tool import.

        In Dify: 工具 → 创建自定义工具 → OpenAPI → 输入此 URL:
        https://host:8443/fde-api/dify/openapi.yaml
        """
        import yaml
        from pathlib import Path

        spec_path = Path(__file__).parent.parent.parent / "docs" / "fde-dify-openapi.yaml"
        with open(spec_path) as f:
            return yaml.safe_load(f)

    logger.info(
        "Dify bridge router created with %d tools at /dify/*",
        len(bridge.export_tool_specs()),
    )
    return router
