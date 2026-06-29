"""Tests for Tool Registry."""

from __future__ import annotations

import pytest

from agents.orchestrator.tools.registry import ToolDefinition, ToolRegistry

# ══════════════════════════════════════════════════════════════════
# ToolDefinition Tests
# ══════════════════════════════════════════════════════════════════


class TestToolDefinition:
    """Tests for ToolDefinition dataclass."""

    def test_create_basic_tool(self) -> None:
        def mock_handler(query: str) -> str:
            return f"Result for: {query}"

        tool = ToolDefinition(
            name="mock_search",
            description="Mock search tool",
            worker="rag",
            handler=mock_handler,
        )
        assert tool.name == "mock_search"
        assert tool.worker == "rag"
        assert tool.is_dangerous is False
        assert tool.category == "general"

    def test_create_dangerous_tool(self) -> None:
        def dangerous_handler(action: str) -> str:
            return f"Executed: {action}"

        tool = ToolDefinition(
            name="delete_data",
            description="Delete data (dangerous)",
            worker="data",
            handler=dangerous_handler,
            is_dangerous=True,
            category="destructive",
        )
        assert tool.is_dangerous is True
        assert tool.category == "destructive"

    def test_tool_with_parameters(self) -> None:
        def param_handler(query: str, limit: int = 10) -> list[str]:
            return [f"result_{i}" for i in range(limit)]

        tool = ToolDefinition(
            name="search_with_limit",
            description="Search with result limit",
            worker="rag",
            handler=param_handler,
            parameters={
                "query": {"type": "string", "required": True},
                "limit": {"type": "integer", "required": False, "default": 10},
            },
        )
        assert "query" in tool.parameters
        assert tool.parameters["limit"]["default"] == 10


# ══════════════════════════════════════════════════════════════════
# ToolRegistry Tests
# ══════════════════════════════════════════════════════════════════


class TestToolRegistry:
    """Tests for ToolRegistry."""

    def _make_tool(self, name: str, worker: str = "rag", dangerous: bool = False) -> ToolDefinition:
        def handler(**kwargs: object) -> str:
            return f"Result from {name}"

        return ToolDefinition(
            name=name,
            description=f"Tool {name}",
            worker=worker,
            handler=handler,
            is_dangerous=dangerous,
        )

    def test_register_and_get(self) -> None:
        registry = ToolRegistry()
        tool = self._make_tool("rag_search")
        registry.register(tool)
        assert registry.get("rag_search") is not None
        assert registry.get("rag_search").name == "rag_search"

    def test_get_nonexistent(self) -> None:
        registry = ToolRegistry()
        assert registry.get("nonexistent") is None

    def test_unregister(self) -> None:
        registry = ToolRegistry()
        tool = self._make_tool("rag_search")
        registry.register(tool)
        registry.unregister("rag_search")
        assert registry.get("rag_search") is None

    def test_register_overwrites(self) -> None:
        registry = ToolRegistry()
        tool1 = self._make_tool("rag_search")
        tool2 = self._make_tool("rag_search")
        registry.register(tool1)
        registry.register(tool2)
        assert len(registry.list_all()) == 1

    def test_get_tools_for_worker(self) -> None:
        registry = ToolRegistry()
        registry.register(self._make_tool("rag_search", worker="rag"))
        registry.register(self._make_tool("rag_ingest", worker="rag"))
        registry.register(self._make_tool("hr_profile", worker="hr"))

        rag_tools = registry.get_tools_for_worker("rag")
        assert len(rag_tools) == 2
        assert all(t.worker == "rag" for t in rag_tools)

    def test_get_dangerous_tools(self) -> None:
        registry = ToolRegistry()
        registry.register(self._make_tool("rag_search", dangerous=False))
        registry.register(self._make_tool("delete_data", worker="data", dangerous=True))

        dangerous = registry.get_dangerous_tools()
        assert len(dangerous) == 1
        assert dangerous[0].name == "delete_data"

    def test_list_all(self) -> None:
        registry = ToolRegistry()
        registry.register(self._make_tool("rag_search"))
        registry.register(self._make_tool("hr_profile", worker="hr"))
        assert len(registry.list_all()) == 2

    def test_list_by_category(self) -> None:
        registry = ToolRegistry()
        registry.register(
            ToolDefinition(
                name="search",
                description="Search",
                worker="rag",
                handler=lambda: "",
                category="retrieval",
            )
        )
        registry.register(
            ToolDefinition(
                name="delete",
                description="Delete",
                worker="data",
                handler=lambda: "",
                category="destructive",
            )
        )

        retrieval_tools = registry.list_by_category("retrieval")
        assert len(retrieval_tools) == 1
        assert retrieval_tools[0].name == "search"

    def test_dispatch_success(self) -> None:
        registry = ToolRegistry()

        def search_handler(query: str) -> str:
            return f"Found: {query}"

        tool = ToolDefinition(
            name="rag_search",
            description="Search",
            worker="rag",
            handler=search_handler,
        )
        registry.register(tool)

        result = registry.dispatch("rag_search", query="test")
        assert result == "Found: test"

    def test_dispatch_nonexistent_raises(self) -> None:
        registry = ToolRegistry()
        with pytest.raises(KeyError, match="not found"):
            registry.dispatch("nonexistent")

    def test_dispatch_handler_error(self) -> None:
        registry = ToolRegistry()

        def failing_handler(**kwargs: object) -> str:
            raise ValueError("Handler failed")

        tool = ToolDefinition(
            name="failing_tool",
            description="Fails",
            worker="rag",
            handler=failing_handler,
        )
        registry.register(tool)

        with pytest.raises(ValueError, match="Handler failed"):
            registry.dispatch("failing_tool")

    def test_as_langchain_tools(self) -> None:
        registry = ToolRegistry()
        registry.register(
            ToolDefinition(
                name="rag_search",
                description="Search knowledge base",
                worker="rag",
                handler=lambda: "",
                parameters={"query": {"type": "string", "required": True}},
            )
        )

        lc_tools = registry.as_langchain_tools()
        assert len(lc_tools) == 1
        assert lc_tools[0]["name"] == "rag_search"
        assert lc_tools[0]["parameters"]["query"]["required"] is True

    def test_get_workers_summary(self) -> None:
        registry = ToolRegistry()
        registry.register(self._make_tool("rag_search", worker="rag"))
        registry.register(self._make_tool("rag_ingest", worker="rag"))
        registry.register(self._make_tool("hr_profile", worker="hr"))

        summary = registry.get_workers_summary()
        assert "rag" in summary
        assert "hr" in summary
        assert len(summary["rag"]) == 2
        assert len(summary["hr"]) == 1
