"""Dify Bridge — LangGraph to Dify tool adapter (M2-T7).

Dify is used as admin-backend low-QPS visualization layer only.
Does NOT enter the core high-concurrency orchestration path.

Capabilities:
- Convert ToolRegistry tools to Dify-compatible OpenAPI specs
- Export YAML for Dify custom tool import
- FastAPI router for Dify to call FDE tools as external API
"""

from agents.dify_bridge.bridge import DifyBridge
from agents.dify_bridge.models import (
    DifyBridgeConfig,
    DifyParam,
    DifyParamType,
    DifyToolRequest,
    DifyToolResponse,
    DifyToolSpec,
    DifyWorkflowConfig,
)
from agents.dify_bridge.router import create_dify_router

__all__ = [
    "DifyBridge",
    "DifyBridgeConfig",
    "DifyParam",
    "DifyParamType",
    "DifyToolRequest",
    "DifyToolResponse",
    "DifyToolSpec",
    "DifyWorkflowConfig",
    "create_dify_router",
]
