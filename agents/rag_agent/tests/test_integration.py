"""Tests for RAG Agent integration with LangGraph Orchestrator."""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock, patch

from agents.orchestrator.tools.registry import ToolRegistry
from agents.rag_agent.integration import (
    _rag_ingest_handler,
    _rag_search_handler,
    register_rag_tools,
)


class TestRAGIntegration:
    """Tests for RAG tool registration and handlers."""

    def test_register_rag_tools(self) -> None:
        """Register RAG tools should add rag_search and rag_ingest."""
        registry = ToolRegistry()
        register_rag_tools(registry)

        rag_tools = registry.get_tools_for_worker("rag")
        assert len(rag_tools) == 2

        names = [t.name for t in rag_tools]
        assert "rag_search" in names
        assert "rag_ingest" in names

    def test_rag_search_tool_metadata(self) -> None:
        """rag_search tool should have proper metadata."""
        registry = ToolRegistry()
        register_rag_tools(registry)

        tool = registry.get("rag_search")
        assert tool is not None
        assert tool.worker == "rag"
        assert tool.category == "retrieval"
        assert tool.is_dangerous is False
        assert "query" in tool.parameters
        assert tool.parameters["query"]["required"] is True

    def test_rag_ingest_tool_metadata(self) -> None:
        """rag_ingest tool should have proper metadata."""
        registry = ToolRegistry()
        register_rag_tools(registry)

        tool = registry.get("rag_ingest")
        assert tool is not None
        assert tool.worker == "rag"
        assert tool.category == "retrieval"
        assert "documents" in tool.parameters

    def test_rag_search_handler_mock(self) -> None:
        """rag_search handler should work with mocked engine."""
        mock_result = MagicMock()
        mock_result.content = "Test content"
        mock_result.score = 0.95
        mock_result.id = "chunk-1"
        mock_result.source = "test.pdf"
        mock_result.metadata = {"source": "test.pdf"}

        async def _async_search(*args: object, **kwargs: object) -> list[MagicMock]:
            return [mock_result]

        with patch("agents.rag_agent.integration.HybridSearchEngine") as mock_engine_cls:
            mock_engine = mock_engine_cls.return_value
            mock_engine.search = _async_search

            result = asyncio.run(_rag_search_handler(query="test query", top_k=5))
            assert result["query"] == "test query"
            assert result["total_results"] == 1
            assert len(result["results"]) == 1
            assert result["results"][0]["score"] == 0.95

    def test_rag_search_handler_error(self) -> None:
        """rag_search handler should return error dict on failure."""
        async def _async_search_error(*args: object, **kwargs: object) -> None:
            raise RuntimeError("Engine failed")

        with patch("agents.rag_agent.integration.HybridSearchEngine") as mock_engine_cls:
            mock_engine_cls.return_value.search = _async_search_error

            result = asyncio.run(_rag_search_handler(query="test"))
            assert "error" in result
            assert "Engine failed" in result["error"]

    def test_rag_ingest_handler_mock(self) -> None:
        """rag_ingest handler should work with mocked store."""
        with (
            patch("agents.rag_agent.integration.VectorStore") as mock_store_cls,
            patch("agents.rag_agent.integration.ParserFactory") as mock_parser_cls,
            patch("agents.rag_agent.integration.chunk_documents") as mock_chunk,
        ):

            mock_store = mock_store_cls.return_value
            mock_store.create_collection.return_value = None
            mock_store.upsert.return_value = None

            mock_parser = MagicMock()
            mock_parser = MagicMock()
            mock_parser_cls.return_value.get_parser.return_value = mock_parser
            mock_parsed = MagicMock()
            mock_parser.parse.return_value = mock_parsed

            mock_chunk.return_value = [MagicMock()]

            result = _rag_ingest_handler(
                documents=[{"path": "/test/doc.pdf", "format": "pdf"}],
                collection_name="test_collection",
            )
            assert result["collection"] == "test_collection"
            assert result["ingested"] == 1

    def test_rag_ingest_handler_error(self) -> None:
        """rag_ingest handler should return error dict on failure."""
        with patch("agents.rag_agent.integration.VectorStore") as mock_store_cls:
            mock_store_cls.return_value.create_collection.side_effect = RuntimeError("Store failed")

            result = _rag_ingest_handler(
                documents=[{"path": "/test/doc.pdf", "format": "pdf"}],
            )
            assert "error" in result

    def test_rag_tools_as_langchain_tools(self) -> None:
        """RAG tools should export correctly as LangChain tool format."""
        registry = ToolRegistry()
        register_rag_tools(registry)

        lc_tools = registry.as_langchain_tools()
        rag_lc = [t for t in lc_tools if t["name"].startswith("rag_")]
        assert len(rag_lc) >= 2

    def test_rag_tools_in_graph(self) -> None:
        """RAG tools should integrate with orchestrator graph."""
        from agents.orchestrator.langgraph.graph import build_orchestrator_graph

        registry = ToolRegistry()
        register_rag_tools(registry)

        graph = build_orchestrator_graph(tool_registry=registry)
        assert graph is not None

        # Verify RAG tools are available in the registry
        assert len(registry.get_tools_for_worker("rag")) == 2
