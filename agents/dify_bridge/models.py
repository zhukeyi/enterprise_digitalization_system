"""Dify integration bridge — converts LangGraph tools to Dify custom tools (M2-T7).

Dify is used as an admin-backend low-QPS visualization layer only.
It does NOT enter the core high-concurrency orchestration path.

This module provides:
1. DifyToolSpec — OpenAPI-compatible tool specification for Dify import
2. DifyBridge — converts ToolRegistry tools to Dify-compatible format
3. FastAPI endpoint registration for Dify to call FDE as external API tools
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

# ══════════════════════════════════════════════════════════════════
# Dify Tool Specification Models
# ══════════════════════════════════════════════════════════════════


class DifyParamType(StrEnum):
    """Dify-supported parameter types."""

    STRING = "string"
    NUMBER = "number"
    INTEGER = "integer"
    BOOLEAN = "boolean"
    OBJECT = "object"
    ARRAY_NUMBER = "array[number]"
    ARRAY_STRING = "array[string]"
    ARRAY_OBJECT = "array[object]"


class DifyParam(BaseModel):
    """A single parameter in a Dify tool definition."""

    name: str = Field(description="Parameter name")
    type: DifyParamType = Field(description="Dify type")
    required: bool = Field(default=False)
    description: str = Field(default="")
    default: Any = Field(default=None)
    options: list[dict[str, str]] | None = Field(default=None, description="Enum options")


class DifyToolSpec(BaseModel):
    """Complete Dify custom tool specification.

    This is the format Dify expects when importing external API tools.
    Compatible with Dify's OpenAPI/Swagger tool import format.
    """

    name: str = Field(description="Unique tool identifier")
    description: str = Field(description="Human-readable tool description")
    category: str = Field(default="fde", description="Tool category in Dify UI")
    url: str = Field(description="Endpoint URL for this tool")
    method: str = Field(default="POST", description="HTTP method")
    headers: dict[str, str] = Field(
        default_factory=dict, description="Fixed headers (e.g., Authorization)"
    )
    parameters: list[DifyParam] = Field(default_factory=list, description="Tool parameters")
    output_schema: dict[str, Any] = Field(
        default_factory=dict, description="Expected response schema"
    )


# ══════════════════════════════════════════════════════════════════
# Dify API Bridge Models
# ══════════════════════════════════════════════════════════════════


class DifyToolRequest(BaseModel):
    """Request from Dify to FDE backend.

    Dify calls FDE endpoints as external API tools.
    This is the standardized request format.
    """

    tool_name: str = Field(description="FDE tool name to invoke")
    parameters: dict[str, Any] = Field(
        default_factory=dict, description="Tool parameters as key-value pairs"
    )
    user_id: str = Field(default="", description="Dify user identifier for audit")
    session_id: str = Field(default="", description="Dify workflow session ID")


class DifyToolResponse(BaseModel):
    """Response from FDE back to Dify.

    Dify expects a specific format for tool responses.
    """

    result: Any = Field(default=None, description="Tool execution result")
    error: str | None = Field(default=None, description="Error message if failed")
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Additional context (latency, worker, etc.)",
    )

    @property
    def success(self) -> bool:
        return self.error is None


# ══════════════════════════════════════════════════════════════════
# Dify Workflow Configuration
# ══════════════════════════════════════════════════════════════════


class DifyWorkflowConfig(BaseModel):
    """Configuration for a Dify workflow that calls FDE tools.

    This is for documentation and configuration management,
    not for runtime execution (Dify handles that internally).
    """

    name: str = Field(description="Workflow name")
    description: str = Field(default="")
    tools: list[str] = Field(default_factory=list, description="FDE tool names used")
    trigger: str = Field(default="manual", description="manual, webhook, scheduled")
    environment: str = Field(default="production")
    enabled: bool = Field(default=True)


class DifyBridgeConfig(BaseModel):
    """Top-level Dify bridge configuration."""

    dify_api_url: str = Field(default="http://217.142.246.70", description="Dify instance URL")
    fde_api_url: str = Field(
        default="http://217.142.246.70:8000", description="FDE backend API URL"
    )
    api_key: str = Field(default="", description="Dify API key (admin)")
    default_category: str = Field(default="fde_enterprise")
    workflows: list[DifyWorkflowConfig] = Field(default_factory=list)
    tools: list[DifyToolSpec] = Field(default_factory=list)

    # Safety limits (Dify QPS=5 → enforce low concurrency)
    max_concurrent_workflows: int = Field(default=3, ge=1, le=5)
    rate_limit_per_minute: int = Field(default=10, ge=1, le=60)
