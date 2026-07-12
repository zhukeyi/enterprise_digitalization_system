"""RAG Inspector — read, maintain, and replay RAG documents/chunks.

Provides:
- Document listing (from Postgres canonical_documents)
- Chunk browsing (from Postgres document_chunks)
- Chunk detail (content + parent + metadata + vector preview)
- Delete document (cascade Qdrant + Postgres + FTS)
- Reindex document (re-chunk + re-embed + re-upsert)
- Debug retrieve (HybridSearch + QueryRewrite + Reranker replay)

Uses the ingestion/rag agent's existing singletons and services.
"""

from __future__ import annotations

import logging
import os
import time
from typing import Any

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from agents.ingestion_agent.database.models import CanonicalDocument, DocumentChunk
from agents.ingestion_agent.store import get_embedding_model, get_vector_store

logger = logging.getLogger("fde.observability.rag_inspector")


async def list_documents(
    page: int = 1,
    page_size: int = 20,
    doc_type: str | None = None,
    source: str | None = None,
) -> dict[str, Any]:
    """List documents in the RAG store (Postgres canonical_documents).

    Gracefully degrades to an empty result set when the backing store is
    unavailable (e.g. Postgres connection refused) so the observability UI
    never hard-fails because of a transient DB outage.
    """
    from sqlalchemy.exc import SQLAlchemyError

    try:
        from agents.governance_agent.database.session import _get_session_factory

        factory = _get_session_factory()
        async with factory() as session:
            stmt = select(CanonicalDocument)
            count_stmt = select(func.count()).select_from(CanonicalDocument)
            if doc_type:
                stmt = stmt.where(CanonicalDocument.doc_type == doc_type)
                count_stmt = count_stmt.where(CanonicalDocument.doc_type == doc_type)
            if source:
                stmt = stmt.where(CanonicalDocument.source_connector == source)
                count_stmt = count_stmt.where(CanonicalDocument.source_connector == source)

            total = (await session.execute(count_stmt)).scalar() or 0
            stmt = stmt.order_by(CanonicalDocument.created_at.desc())
            stmt = stmt.offset((page - 1) * page_size).limit(page_size)
            rows = (await session.execute(stmt)).scalars().all()

            data = []
            for doc in rows:
                # Count chunks for this doc
                chunk_count = await _count_chunks(session, doc.id)
                data.append(
                    {
                        "doc_id": str(doc.id),
                        "title": doc.title,
                        "doc_type": doc.doc_type,
                        "source": doc.source_connector or "",
                        "language": doc.language or "",
                        "chunk_count": chunk_count,
                        "created_at": doc.created_at.isoformat() if doc.created_at else "",
                    }
                )

            return {
                "page": page,
                "page_size": page_size,
                "total": total,
                "total_pages": (total + page_size - 1) // page_size,
                "data": data,
                "db_available": True,
            }
    except (SQLAlchemyError, OSError) as e:
        logger.warning("list_documents: backing store unavailable, returning empty: %s", e)
        return {
            "page": page,
            "page_size": page_size,
            "total": 0,
            "total_pages": 0,
            "data": [],
            "db_available": False,
        }


async def _count_chunks(session: AsyncSession, canonical_document_id: str) -> int:
    """Count chunks for a document."""
    result = await session.execute(
        select(func.count())
        .select_from(DocumentChunk)
        .where(DocumentChunk.canonical_document_id == canonical_document_id)
    )
    return result.scalar() or 0


async def get_document_chunks(
    doc_id: str,
    page: int = 1,
    page_size: int = 50,
) -> dict[str, Any]:
    """Get all chunks for a document (paginated)."""
    from sqlalchemy.exc import SQLAlchemyError

    try:
        from agents.governance_agent.database.session import _get_session_factory

        factory = _get_session_factory()
        async with factory() as session:
            count_stmt = (
                select(func.count())
                .select_from(DocumentChunk)
                .where(DocumentChunk.canonical_document_id == doc_id)
            )
            total = (await session.execute(count_stmt)).scalar() or 0

            stmt = (
                select(DocumentChunk)
                .where(DocumentChunk.canonical_document_id == doc_id)
                .order_by(DocumentChunk.chunk_index.asc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
            rows = (await session.execute(stmt)).scalars().all()

            data = []
            for chunk in rows:
                meta = chunk.metadata_json or {}
                data.append(
                    {
                        "chunk_id": str(chunk.id),
                        "chunk_index": chunk.chunk_index,
                        "content": chunk.content,
                        "token_count": chunk.token_count or 0,
                        "parent_chunk_id": str(chunk.parent_chunk_id) if chunk.parent_chunk_id else None,
                        "embedding_id": chunk.embedding_id or "",
                        "metadata": meta,
                    }
                )

            return {
                "doc_id": doc_id,
                "page": page,
                "page_size": page_size,
                "total": total,
                "total_pages": (total + page_size - 1) // page_size,
                "data": data,
                "db_available": True,
            }
    except (SQLAlchemyError, OSError) as e:
        logger.warning("get_document_chunks: backing store unavailable: %s", e)
        return {
            "doc_id": doc_id,
            "page": page,
            "page_size": page_size,
            "total": 0,
            "total_pages": 0,
            "data": [],
            "db_available": False,
        }


async def get_chunk_detail(chunk_id: str) -> dict[str, Any] | None:
    """Get detailed chunk info including parent text and vector preview."""
    from sqlalchemy.exc import SQLAlchemyError

    try:
        from agents.governance_agent.database.session import _get_session_factory

        factory = _get_session_factory()
        async with factory() as session:
            stmt = select(DocumentChunk).where(DocumentChunk.id == chunk_id)
            chunk = (await session.execute(stmt)).scalars().first()
            if chunk is None:
                return None

            meta = chunk.metadata_json or {}
            parent_text = meta.get("parent_text") or ""

            # Try to get vector preview from Qdrant
            vector_preview = await _get_vector_preview(chunk.embedding_id or str(chunk.id))

            return {
                "chunk_id": str(chunk.id),
                "doc_id": str(chunk.canonical_document_id),
                "chunk_index": chunk.chunk_index,
                "content": chunk.content,
                "parent_text": parent_text,
                "token_count": chunk.token_count or 0,
                "parent_chunk_id": str(chunk.parent_chunk_id) if chunk.parent_chunk_id else None,
                "embedding_id": chunk.embedding_id or "",
                "metadata": meta,
                "vector_preview": vector_preview,
                "db_available": True,
            }
    except (SQLAlchemyError, OSError) as e:
        logger.warning("get_chunk_detail: backing store unavailable: %s", e)
        return None


async def _get_vector_preview(point_id: str) -> list[float]:
    """Get first 10 dims of a vector from Qdrant (best-effort)."""
    try:
        vs = get_vector_store()
        if hasattr(vs.async_client, "retrieve"):
            points = await vs.async_client.retrieve(
                collection_name=vs.config.collection_name,
                ids=[point_id],
                with_vectors=True,
            )
        else:
            points = await vs.async_client.get_points(
                collection_name=vs.config.collection_name,
                ids=[point_id],
                with_vectors=True,
            )
        if points:
            vec = getattr(points[0], "vector", None)
            if vec:
                return [round(float(v), 4) for v in vec[:10]]
    except Exception as e:
        logger.debug("vector preview failed for %s: %s", point_id, e)
    return []


async def delete_document(doc_id: str) -> dict[str, Any]:
    """Delete a document: cascade Qdrant points + Postgres rows + FTS.

    Returns affected counts. Caller must have done confirmation upstream.
    """
    from agents.governance_agent.database.session import _get_session_factory

    factory = _get_session_factory()
    async with factory() as session:
        # 1. Get all chunk IDs for this doc
        chunk_ids = (
            await session.execute(
                select(DocumentChunk.id).where(DocumentChunk.canonical_document_id == doc_id)
            )
        ).scalars().all()
        chunk_id_strs = [str(c) for c in chunk_ids]

        # 2. Delete from Qdrant
        deleted_qdrant = 0
        if chunk_id_strs:
            try:
                vs = get_vector_store()
                await vs.async_delete_points(chunk_id_strs)
                deleted_qdrant = len(chunk_id_strs)
            except Exception as e:
                logger.warning("Qdrant delete failed (non-fatal): %s", e)

        # 3. Delete Postgres chunks
        await session.execute(
            text("DELETE FROM document_chunks WHERE canonical_document_id = :did"),
            {"did": doc_id},
        )

        # 4. Delete canonical document
        await session.execute(
            text("DELETE FROM canonical_documents WHERE id = :did"),
            {"did": doc_id},
        )

        await session.commit()

        return {
            "deleted": True,
            "doc_id": doc_id,
            "qdrant_points": deleted_qdrant,
            "postgres_chunks": len(chunk_id_strs),
        }


async def reindex_document(doc_id: str) -> dict[str, Any]:
    """Re-chunk + re-embed + re-upsert a document.

    Reads the canonical document's payload, re-renders text, re-chunks
    with the current chunking strategy, re-embeds, and re-upserts to
    Qdrant + Postgres (document_chunks).
    """
    from agents.governance_agent.database.session import _get_session_factory
    from agents.ingestion_agent.chunking import build_text_chunks
    from agents.rag_agent.vector_store import VectorRecord

    factory = _get_session_factory()
    start = time.monotonic()

    async with factory() as session:
        # Load canonical document
        doc = (
            await session.execute(
                select(CanonicalDocument).where(CanonicalDocument.id == doc_id)
            )
        ).scalars().first()

        if doc is None:
            return {"doc_id": doc_id, "reindexed": False, "error": "document not found"}

        # Render canonical text the same way the pipeline does
        from agents.ingestion_agent.pipeline import render_canonical_text

        text = render_canonical_text(doc)

        # Delete existing chunks + Qdrant points
        chunk_ids = (
            await session.execute(
                select(DocumentChunk.id).where(DocumentChunk.canonical_document_id == doc_id)
            )
        ).scalars().all()
        chunk_id_strs = [str(c) for c in chunk_ids]
        if chunk_id_strs:
            try:
                vs = get_vector_store()
                await vs.async_delete_points(chunk_id_strs)
            except Exception as e:
                logger.warning("Qdrant delete failed (non-fatal): %s", e)
            await session.execute(
                text("DELETE FROM document_chunks WHERE canonical_document_id = :did"),
                {"did": doc_id},
            )
            await session.commit()

        # Re-chunk
        specs = build_text_chunks(
            text,
            doc_type=doc.doc_type,
            source_ref=doc.storage_ref or doc.source_connector or "",
            raw_id=str(doc.id),
        )

        if not specs:
            return {
                "doc_id": doc_id,
                "reindexed": False,
                "error": "no text content to reindex",
                "elapsed_ms": round((time.monotonic() - start) * 1000, 1),
            }

        # Re-embed
        texts = [s.child_text for s in specs]
        embedding_model = get_embedding_model()
        vectors = await embedding_model.encode_documents(texts)

        # Re-upsert to Qdrant + insert Postgres chunks
        vs = get_vector_store()
        new_chunk_ids: list[str] = []
        records_to_upsert: list[VectorRecord] = []
        from uuid import uuid4

        for spec, vec in zip(specs, vectors, strict=True):
            cid = str(uuid4())
            new_chunk_ids.append(cid)
            records_to_upsert.append(
                VectorRecord(
                    id=cid,
                    vector=vec,
                    payload={
                        "text": spec.child_text,
                        "parent_text": spec.parent_text,
                        "title": doc.title,
                        "source": doc.source_connector or "",
                        "doc_type": doc.doc_type,
                        "canonical_document_id": str(doc.id),
                    },
                )
            )
            # Insert Postgres chunk
            chunk = DocumentChunk(
                id=cid,
                canonical_document_id=str(doc.id),
                chunk_index=len(new_chunk_ids) - 1,
                content=spec.child_text,
                token_count=len(spec.child_text) // 4,
                embedding_id=cid,
                metadata_json={
                    "parent_text": spec.parent_text,
                    "block_kind": spec.metadata.get("block_kind", "text"),
                    "chunking_strategy": "parent_child",
                    "embedding_model": os.getenv("FDE_RAG_EMBEDDING_MODEL", "BAAI/bge-m3"),
                },
            )
            session.add(chunk)

        await vs.async_upsert(records_to_upsert)
        await session.commit()

    elapsed = (time.monotonic() - start) * 1000

    return {
        "doc_id": doc_id,
        "reindexed": True,
        "elapsed_ms": round(elapsed, 1),
        "new_chunk_count": len(new_chunk_ids),
    }


async def debug_retrieve(
    query: str,
    top_k: int = 10,
    doc_type: str | None = None,
) -> dict[str, Any]:
    """Replay a retrieval: QueryRewrite + HybridSearch + Reranker.

    Returns rewritten query, retrieved chunks with scores, latency.
    """
    from agents.rag_agent.query_rewrite import get_default_rewriter
    from agents.rag_agent.reranker import get_default_reranker

    start = time.monotonic()

    # Query rewrite
    rewriter = get_default_rewriter()
    rewritten = rewriter.rewrite(query)

    # Embed query
    embedding_model = get_embedding_model()
    q_vecs = await embedding_model.encode_queries([rewritten])
    q_vec = q_vecs[0]

    # Vector search
    vs = get_vector_store()
    candidate_k = min(max(top_k * 4, top_k + 8), 20)
    candidates = await vs.async_search(
        vector=q_vec,
        top_k=candidate_k,
        filter_conditions={"doc_type": doc_type} if doc_type else None,
    )

    # Rerank
    rk = get_default_reranker()
    records = rk.rerank(rewritten, candidates, top_k)

    elapsed = (time.monotonic() - start) * 1000

    chunks = []
    for idx, r in enumerate(records):
        payload = r.payload
        chunks.append(
            {
                "id": str(r.id),
                "rank": idx + 1,
                "score": round(r.score or 0.0, 4),
                "text": (payload.get("text") or "")[:500],
                "title": payload.get("title") or "",
                "source": payload.get("source") or "",
                "doc_type": payload.get("doc_type") or "",
            }
        )

    return {
        "query": query,
        "rewritten_query": rewritten,
        "latency_ms": round(elapsed, 1),
        "candidate_count": len(candidates),
        "chunks": chunks,
    }


def get_rag_stats() -> dict[str, Any]:
    """Get overall RAG store stats (document/chunk counts, collection info)."""
    try:
        vs = get_vector_store()
        collection_info = vs.get_collection_info()
        points = getattr(collection_info, "points_count", 0)
    except Exception as e:
        logger.debug("rag stats qdrant failed: %s", e)
        points = 0

    return {
        "qdrant_points": points,
        "status": "ok" if points > 0 else "empty",
    }
