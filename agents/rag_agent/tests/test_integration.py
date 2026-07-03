"""Tests for RAG Agent integration with LangGraph Orchestrator."""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock, patch

from agents.orchestrator.tools.registry import ToolRegistry
from agents.rag_agent.integration import (
    _rag_answer_handler,
    _rag_ingest_handler,
    _rag_search_handler,
    _reset_vector_store,
    register_rag_tools,
)


class TestRAGIntegration:
    """Tests for RAG tool registration and handlers."""

    def setup_method(self) -> None:
        """Reset VectorStore singleton before each test."""
        _reset_vector_store()

    def test_register_rag_tools(self) -> None:
        """Register RAG tools should add rag_search, rag_ingest, and rag_answer."""
        registry = ToolRegistry()
        register_rag_tools(registry)

        rag_tools = registry.get_tools_for_worker("rag")
        assert len(rag_tools) == 3

        names = [t.name for t in rag_tools]
        assert "rag_search" in names
        assert "rag_ingest" in names
        assert "rag_answer" in names

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

            result = asyncio.run(
                _rag_ingest_handler(
                    documents=[{"path": "/test/doc.pdf", "format": "pdf"}],
                    collection_name="test_collection",
                )
            )
            assert result["collection"] == "test_collection"
            assert result["ingested"] == 1

    def test_rag_ingest_handler_error(self) -> None:
        """rag_ingest handler should return error dict on failure."""
        with patch("agents.rag_agent.integration.VectorStore") as mock_store_cls:
            mock_store_cls.return_value.create_collection.side_effect = RuntimeError("Store failed")

            result = asyncio.run(
                _rag_ingest_handler(
                    documents=[{"path": "/test/doc.pdf", "format": "pdf"}],
                )
            )
            assert "error" in result

    def test_rag_tools_as_langchain_tools(self) -> None:
        """RAG tools should export correctly as LangChain tool format."""
        registry = ToolRegistry()
        register_rag_tools(registry)

        lc_tools = registry.as_langchain_tools()
        rag_lc = [t for t in lc_tools if t["name"].startswith("rag_")]
        assert len(rag_lc) >= 3

    def test_rag_tools_in_graph(self) -> None:
        """RAG tools should integrate with orchestrator graph."""
        from agents.orchestrator.langgraph.graph import build_orchestrator_graph

        registry = ToolRegistry()
        register_rag_tools(registry)

        graph = build_orchestrator_graph(tool_registry=registry)
        assert graph is not None

        # Verify RAG tools are available in the registry
        assert len(registry.get_tools_for_worker("rag")) == 3

    def test_register_rag_tools_with_auth(self) -> None:
        """register_rag_tools_with_auth should register permission-filtered tools."""
        from agents.rag_agent.integration import register_rag_tools_with_auth

        registry = ToolRegistry()

        # Create a throwaway async session factory
        import asyncio

        from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

        async def _test_register() -> None:
            engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
            try:
                factory = async_sessionmaker(engine, expire_on_commit=False)

                register_rag_tools_with_auth(
                    registry=registry,
                    user_id="user-1",
                    session_factory=factory,
                )

                tools = registry.get_tools_for_worker("rag")
                assert len(tools) == 3
                assert tools[0].name == "rag_search"
                assert tools[1].name == "rag_ingest"
                assert tools[2].name == "rag_answer"
            finally:
                await engine.dispose()

        asyncio.run(_test_register())


class TestRagAnswerHandler:
    """Tests for the rag_answer zero-hallucination synthesis handler."""

    def test_rag_answer_with_provided_context(self) -> None:
        """rag_answer should synthesize from provided context_chunks."""
        chunks = [
            {
                "content": "FastAPI is a modern Python web framework for building APIs.",
                "score": 0.92,
                "source": "tech_doc.pdf",
                "chunk_id": "chunk-1",
            },
            {
                "content": "FastAPI supports async endpoints and automatic OpenAPI docs.",
                "score": 0.78,
                "source": "tech_doc.pdf",
                "chunk_id": "chunk-2",
            },
        ]

        result = asyncio.run(_rag_answer_handler(query="What is FastAPI?", context_chunks=chunks))
        assert "answer" in result
        assert "FastAPI" in result["answer"]
        assert result["confidence"] == 0.92
        assert result["total_sources"] == 2
        assert len(result["sources"]) == 2
        assert result["sources"][0]["source"] == "tech_doc.pdf"

    def test_rag_answer_empty_results(self) -> None:
        """rag_answer with no chunks should return 'not found' message."""
        result = asyncio.run(_rag_answer_handler(query="unknown topic", context_chunks=[]))
        assert "未找到相关文档" in result["answer"]
        assert result["confidence"] == 0.0
        assert result["total_sources"] == 0
        assert result["sources"] == []

    def test_rag_answer_low_confidence(self) -> None:
        """rag_answer with score < 0.3 should emit low-confidence warning."""
        chunks = [
            {
                "content": "Some barely relevant content.",
                "score": 0.15,
                "source": "low_relevance.pdf",
                "chunk_id": "chunk-x",
            },
        ]

        result = asyncio.run(_rag_answer_handler(query="obscure query", context_chunks=chunks))
        assert "置信度较低" in result["answer"]
        assert result["confidence"] == 0.15

    def test_rag_answer_high_confidence(self) -> None:
        """rag_answer with high score should not include low-confidence warning."""
        chunks = [
            {
                "content": "Directly relevant answer content.",
                "score": 0.95,
                "source": "authoritative.pdf",
                "chunk_id": "chunk-hi",
            },
        ]

        result = asyncio.run(_rag_answer_handler(query="relevant query", context_chunks=chunks))
        assert "置信度较低" not in result["answer"]
        assert "根据知识库文档" in result["answer"]
        assert result["confidence"] == 0.95

    def test_rag_answer_tool_registered(self) -> None:
        """rag_answer tool should have proper metadata in registry."""
        registry = ToolRegistry()
        register_rag_tools(registry)

        tool = registry.get("rag_answer")
        assert tool is not None
        assert tool.worker == "rag"
        assert tool.category == "retrieval"
        assert "query" in tool.parameters
        assert tool.parameters["query"]["required"] is True
        assert "context_chunks" in tool.parameters
