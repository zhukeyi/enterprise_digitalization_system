"""Tool Registry — centralized tool discovery & dispatch.

Workers register their tools here; the supervisor uses the registry
to understand available capabilities and route tasks accordingly.

M1-T6: Core tool registration mechanism
"""

from __future__ import annotations

import inspect
import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger("fde.orchestrator.tools")


# ══════════════════════════════════════════════════════════════════
# Tool Definition
# ══════════════════════════════════════════════════════════════════


@dataclass
class ToolDefinition:
    """A registered tool's metadata and handler."""

    name: str
    description: str
    worker: str  # Which worker agent owns this tool
    handler: Callable[..., Any]  # The actual tool function
    parameters: dict[str, Any] = field(default_factory=dict)  # JSON Schema-like params
    is_dangerous: bool = False  # Whether this tool needs foolproof confirmation
    category: str = "general"  # Tool category for grouping


# ══════════════════════════════════════════════════════════════════
# Tool Registry
# ══════════════════════════════════════════════════════════════════


class ToolRegistry:
    """Central registry for all worker tools.

    The supervisor queries this registry to understand what tools
    are available, and workers register their tools during initialization.

    Usage:
        registry = ToolRegistry()
        registry.register(ToolDefinition(
            name="rag_search",
            description="Search the knowledge base",
            worker="rag",
            handler=rag_engine.search,
            parameters={"query": {"type": "string", "required": True}},
        ))
        tools = registry.get_tools_for_worker("rag")
    """

    def __init__(self) -> None:
        self._tools: dict[str, ToolDefinition] = {}

    def register(self, tool: ToolDefinition) -> None:
        """Register a tool definition."""
        if tool.name in self._tools:
            logger.warning("Tool '%s' already registered, overwriting", tool.name)
        self._tools[tool.name] = tool
        logger.debug(
            "Registered tool: %s (worker=%s, category=%s)", tool.name, tool.worker, tool.category
        )

    def unregister(self, name: str) -> None:
        """Remove a tool from the registry."""
        if name in self._tools:
            del self._tools[name]
            logger.debug("Unregistered tool: %s", name)

    def get(self, name: str) -> ToolDefinition | None:
        """Get a tool definition by name."""
        return self._tools.get(name)

    def get_tools_for_worker(self, worker: str) -> list[ToolDefinition]:
        """Get all tools belonging to a specific worker."""
        return [t for t in self._tools.values() if t.worker == worker]

    def get_dangerous_tools(self) -> list[ToolDefinition]:
        """Get all tools that require foolproof confirmation."""
        return [t for t in self._tools.values() if t.is_dangerous]

    def list_all(self) -> list[ToolDefinition]:
        """List all registered tools."""
        return list(self._tools.values())

    def list_by_category(self, category: str) -> list[ToolDefinition]:
        """List tools in a specific category."""
        return [t for t in self._tools.values() if t.category == category]

    async def dispatch(self, tool_name: str, **kwargs: Any) -> Any:
        """Execute a tool by name with given arguments.

        Supports both sync and async handlers. If the handler is async,
        the coroutine is properly awaited.

        Args:
            tool_name: Name of the tool to execute.
            **kwargs: Arguments to pass to the tool handler.

        Returns:
            Tool execution result.

        Raises:
            KeyError: If tool is not found in registry.
            Exception: If tool execution fails.
        """
        tool = self._tools.get(tool_name)
        if tool is None:
            raise KeyError(f"Tool '{tool_name}' not found in registry")

        logger.info("Dispatching tool: %s (worker=%s)", tool_name, tool.worker)
        try:
            result = tool.handler(**kwargs)
            if inspect.iscoroutine(result):
                result = await result
            logger.info("Tool '%s' completed successfully", tool_name)
            return result
        except Exception as e:
            logger.error("Tool '%s' failed: %s", tool_name, e)
            raise

    def as_langchain_tools(self) -> list[dict[str, Any]]:
        """Export tool definitions in LangChain tool format.

        This format is used by the supervisor LLM to understand
        available tools and their parameters.
        """
        tools = []
        for t in self._tools.values():
            tools.append(
                {
                    "name": t.name,
                    "description": t.description,
                    "parameters": t.parameters,
                }
            )
        return tools

    def get_workers_summary(self) -> dict[str, list[str]]:
        """Get a summary of which workers have which tools."""
        summary: dict[str, list[str]] = {}
        for t in self._tools.values():
            if t.worker not in summary:
                summary[t.worker] = []
            summary[t.worker].append(t.name)
        return summary
