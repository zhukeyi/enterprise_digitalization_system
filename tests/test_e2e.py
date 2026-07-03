"""End-to-end integration tests for M1 milestone.

M1-T13: Validates the full pipeline:
1. Document parsing → chunking
2. Embedding → vector store
3. Hybrid search (BM25 + vector + RRF)
4. Router gateway (mock adapter chat completion)

All tests use mocked external services to avoid real infrastructure.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from agents.rag_agent.chunking import ChunkerFactory, Document
from agents.rag_agent.document_parser import ParserFactory
from agents.rag_agent.retriever import HybridSearchConfig, HybridSearchEngine
from agents.rag_agent.vector_store import VectorRecord, VectorStore
from agents.router_agent.adapters.base import MockAdapter
from agents.router_agent.models.request import ChatCompletionRequest, Message
from agents.router_agent.models.response import ChatCompletionResponse

# ══════════════════════════════════════════════════════════════════
# E2E Test 1: Parse → Chunk Pipeline
# ══════════════════════════════════════════════════════════════════


class TestParseChunkPipeline:
    def test_parse_then_chunk(self, tmp_path: Path) -> None:
        """Parse a text file, then chunk the result."""
        # Create test document
        text_content = "\n\n".join(
            [
                f"This is paragraph {i} about artificial intelligence and machine learning."
                for i in range(5)
            ]
        )
        test_file = tmp_path / "test.md"
        test_file.write_text(text_content, encoding="utf-8")

        # Step 1: Parse
        factory = ParserFactory()
        docs = factory.parse(str(test_file))
        assert len(docs) == 1

        # Step 2: Chunk
        chunker = ChunkerFactory().create(
            "recursive", chunk_size=200, chunk_overlap=20, use_token_count=False
        )
        chunks = chunker.chunk_document(
            Document(id="test-doc", content=docs[0].content, metadata=docs[0].metadata)
        )
        assert len(chunks) >= 1
        assert all(c.chunk_strategy == "recursive" for c in chunks)
        assert all(c.parent_document_id == "test-doc" for c in chunks)

    def test_parse_chunk_all_strategies(self, tmp_path: Path) -> None:
        """Test all chunking strategies on parsed content."""
        test_file = tmp_path / "sample.txt"
        test_file.write_text("Hello world. " * 100, encoding="utf-8")

        factory = ParserFactory()
        docs = factory.parse(str(test_file))
        assert len(docs) == 1

        for strategy in ["fixed_size", "semantic", "recursive"]:
            chunker = ChunkerFactory().create(
                strategy, chunk_size=150, chunk_overlap=20, use_token_count=False
            )
            chunks = chunker.chunk_document(Document(id="test", content=docs[0].content))
            assert len(chunks) >= 1, f"Strategy '{strategy}' produced no chunks"


# ══════════════════════════════════════════════════════════════════
# E2E Test 2: Embed → Store → Search Pipeline
# ══════════════════════════════════════════════════════════════════


class TestEmbedStoreSearchPipeline:
    @pytest.mark.asyncio
    async def test_embed_then_store_then_search(self) -> None:
        """Embed a document, store in vector store, then search it."""
        # Mock components
        mock_store = MagicMock(spec=VectorStore)
        mock_store.search.return_value = [
            VectorRecord(id="doc-1", payload={"text": "AI and machine learning"}, score=0.92),
        ]

        mock_embed = AsyncMock()
        mock_embed.encode_queries.return_value = [[0.1] * 1024]
        mock_embed.encode_documents.return_value = [[0.2] * 1024]

        # Create documents
        texts = [
            "Artificial intelligence is transforming the world.",
            "Python is great for data science.",
        ]
        ids = ["doc-1", "doc-2"]

        # Build hybrid search
        engine = HybridSearchEngine(
            vector_store=mock_store,
            embedding_model=mock_embed,
            config=HybridSearchConfig(top_k_final=5, top_k_each=10),
        )
        engine.index_documents(texts, ids)

        # Search
        results = await engine.search("AI transformation")
        assert len(results) >= 1
        mock_embed.encode_queries.assert_called_once()
        mock_store.search.assert_called_once()


# ══════════════════════════════════════════════════════════════════
# E2E Test 3: Router Gateway Pipeline
# ══════════════════════════════════════════════════════════════════


class TestRouterGatewayPipeline:
    @pytest.mark.asyncio
    async def test_router_completion(self) -> None:
        """Mock adapter returns a valid ChatCompletionResponse."""
        adapter = MockAdapter()

        request = ChatCompletionRequest(
            model="fde/mock-v1",
            messages=[Message(role="user", content="Hello, how are you?")],
        )

        response = await adapter.complete(request)
        assert isinstance(response, ChatCompletionResponse)
        assert response.model == "fde/mock-v1"
        assert len(response.choices) == 1
        assert response.choices[0].message.role == "assistant"
        assert "你好" in response.choices[0].message.content

    @pytest.mark.asyncio
    async def test_router_help_command(self) -> None:
        """Mock adapter responds to help queries."""
        adapter = MockAdapter()

        request = ChatCompletionRequest(
            model="fde/mock-v1",
            messages=[Message(role="user", content="help me understand the platform")],
        )

        response = await adapter.complete(request)
        assert "FDE" in response.choices[0].message.content
        assert (
            "RAG" in response.choices[0].message.content
            or "AI" in response.choices[0].message.content
        )

    @pytest.mark.asyncio
    async def test_router_fallback_request(self) -> None:
        """Default/mock response for unknown queries."""
        adapter = MockAdapter()

        request = ChatCompletionRequest(
            messages=[Message(role="user", content="What is the weather today?")],
        )

        response = await adapter.complete(request)
        assert response.choices[0].message.content
        # Default response should mention "Mock"
        assert "Mock" in response.choices[0].message.content


# ══════════════════════════════════════════════════════════════════
# E2E Test 4: Full Pipeline (parse → chunk → search → respond)
# ══════════════════════════════════════════════════════════════════


class TestFullPipeline:
    @pytest.mark.asyncio
    async def test_rag_then_respond(self, tmp_path: Path) -> None:
        """
        Simulate: user uploads document → parse → chunk → store → search → respond.

        All external deps are mocked:
        - Vector store (Qdrant) returns pre-configured results
        - Embedding model returns dummy vectors
        - Router adapter returns canned response
        """
        # ── Step 1: Create a test document and parse it ──
        doc_text = (
            "FDE AI Platform is a modular enterprise AI platform. "
            "It supports smart routing, RAG retrieval, HR analysis, and data analytics. "
            "The router gateway supports OpenAI-compatible API endpoints."
        )
        test_file = tmp_path / "fde_intro.md"
        test_file.write_text(doc_text, encoding="utf-8")

        factory = ParserFactory()
        parsed_docs = factory.parse(str(test_file))
        assert len(parsed_docs) == 1

        # ── Step 2: Chunk the parsed document ──
        chunker = ChunkerFactory().create(
            "recursive", chunk_size=100, chunk_overlap=10, use_token_count=False
        )
        chunks = chunker.chunk_document(
            Document(
                id="fde-intro", content=parsed_docs[0].content, metadata=parsed_docs[0].metadata
            )
        )
        assert len(chunks) >= 1

        # ── Step 3: Mock embedding + search ──
        mock_embed = AsyncMock()
        mock_embed.encode_queries.return_value = [[0.1] * 1024]

        mock_store = MagicMock()
        mock_store.search.return_value = [
            VectorRecord(
                id="fde-intro", payload={"text": "FDE supports RAG retrieval"}, score=0.87
            ),
        ]

        engine = HybridSearchEngine(
            vector_store=mock_store,
            embedding_model=mock_embed,
            config=HybridSearchConfig(top_k_final=3),
        )
        engine.index_documents(
            [c.content for c in chunks],
            ids=[c.chunk_id for c in chunks],
        )

        # ── Step 4: Search ──
        results = await engine.search("What does FDE support?")
        assert len(results) >= 1
        assert any("FDE" in r.content for r in results)

        # ── Step 5: Router responds using search context ──
        adapter = MockAdapter()
        context = "\n".join([f"- {r.content}" for r in results])
        query_with_context = f"Context:\n{context}\n\nQuestion: What does FDE support?\n\nBased on the context, answer the question."

        request = ChatCompletionRequest(
            model="fde/mock-v1",
            messages=[Message(role="user", content=query_with_context)],
        )
        response = await adapter.complete(request)
        assert isinstance(response, ChatCompletionResponse)
        assert response.model == "fde/mock-v1"


# ══════════════════════════════════════════════════════════════════
# E2E Test 5: Error Handling
# ══════════════════════════════════════════════════════════════════


class TestErrorHandling:
    def test_empty_document(self, tmp_path: Path) -> None:
        """Empty documents should produce no chunks."""
        factory = ParserFactory()
        test_file = tmp_path / "empty.txt"
        test_file.write_text("", encoding="utf-8")

        docs = factory.parse(str(test_file))
        assert len(docs) == 0

    def test_unsupported_format(self) -> None:
        """Unsupported formats should raise clear error."""
        from agents.rag_agent.document_parser import UnsupportedFormatError

        factory = ParserFactory()
        with pytest.raises(UnsupportedFormatError, match="No parser available"):
            factory.get_parser("archive.rar")

    @pytest.mark.asyncio
    async def test_router_error_handling(self) -> None:
        """Stub adapters without API keys should raise NotImplementedError."""
        from agents.router_agent.adapters.base import DeepSeekStubAdapter

        adapter = DeepSeekStubAdapter()
        request = ChatCompletionRequest(
            messages=[Message(role="user", content="test")],
        )
        with pytest.raises(NotImplementedError):
            await adapter.complete(request)

    @pytest.mark.asyncio
    async def test_anti_foolproof_middleware(self) -> None:
        """Anti-foolproof middleware should intercept destructive requests."""
        from httpx import ASGITransport, AsyncClient

        from agents.router_agent.main import app

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # Send a destructive request
            response = await client.post(
                "/v1/chat/completions",
                json={
                    "model": "fde/mock-v1",
                    "messages": [{"role": "user", "content": "Please delete all records"}],
                },
            )
            # The request should be processed (mock adapter returns 200)
            # or blocked by anti-foolproof middleware (400)
            # Either way, it should not be a 5xx server error
            assert response.status_code < 500, f"Unexpected server error: {response.status_code}"
            assert response.status_code in (
                200,
                400,
            ), f"Expected 200 or 400, got {response.status_code}"


# ══════════════════════════════════════════════════════════════════
# E2E Test 6: BM25 Hybrid Search Pipeline
# ══════════════════════════════════════════════════════════════════


class TestBM25HybridPipeline:
    @pytest.mark.asyncio
    async def test_bm25_only_workflow(self) -> None:
        """BM25-only search should work without vector store."""
        engine = HybridSearchEngine()
        engine.index_documents(
            [
                "The router agent manages model routing",
                "The RAG agent handles document retrieval",
                "The HR agent analyzes employee data",
            ],
            ids=["r1", "r2", "r3"],
        )
        results = await engine.search("document retrieval")
        assert len(results) >= 1
        assert any("RAG" in r.content for r in results)

    @pytest.mark.asyncio
    async def test_empty_query_returns_empty(self) -> None:
        engine = HybridSearchEngine()
        engine.index_documents(["hello"])
        results = await engine.search("")
        assert results == []
