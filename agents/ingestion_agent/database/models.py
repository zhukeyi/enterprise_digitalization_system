"""SQLAlchemy ORM models for the 4 shared ingestion tables.

Mirrors the conventions in ``agents/governance_agent/database/models.py`` and
registers on the same shared ``Base`` so a single ``alembic upgrade head``
migrates the whole schema.

Tables (see docs/master-delivery-plan.md §2.1):

* ``raw_documents``        — 原始抽取 (raw extracted payload)
* ``canonical_documents``  — 归一后标准实体 (connector data uses storage_ref)
* ``document_chunks``      — 切片, 含父子关系 (parent_chunk_id self-FK)
* ``connector_registry``   — 连接器注册 / 健康 / 字段映射引用

NOTE on naming: the *persisted* canonical entity is ``CanonicalDocument`` (ORM).
The wire/contract model of the same name lives in
``shared.contracts.connector_contract.CanonicalDocument`` — import it aliased
(e.g. ``from shared.contracts.connector_contract import CanonicalDocument as ContractCanonicalDocument``)
when both are needed in one module.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from agents.governance_agent.database.session import Base

# Cross-database JSON column: JSONB on PostgreSQL, JSON on SQLite (mirrors governance models).
JsonColumn = JSONB().with_variant(JSON(), "sqlite")


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _new_uuid() -> str:
    return str(uuid.uuid4())


class RawDocument(Base):
    """Raw extracted payload before normalization (table ``raw_documents``)."""

    __tablename__ = "raw_documents"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_new_uuid)
    source_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    source_ref: Mapped[str | None] = mapped_column(String(512), nullable=True, index=True)
    content_type: Mapped[str | None] = mapped_column(String(128), nullable=True)
    # 文件级内容哈希（P3b 幂等）：相同原始字节永不产生重复 RawDocument / 幽灵文档。
    content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    # 原始字节在对象存储中的引用（P3b）：minio://bucket/key | local://key | memory://key。
    # 为 None 时表示原始字节未外置（旧库 / 仅元数据）。
    storage_ref: Mapped[str | None] = mapped_column(String(512), nullable=True)
    raw_payload: Mapped[dict[str, Any] | None] = mapped_column(JsonColumn, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )

    canonical: Mapped[list[CanonicalDocument]] = relationship(back_populates="raw")


class CanonicalDocument(Base):
    """Normalized, source-agnostic entity (table ``canonical_documents``).

    Both local files and connectors land here as the same shape; connector rows
    carry ``storage_ref`` like ``connector://<id>/<type>/<pk>``.
    """

    __tablename__ = "canonical_documents"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_new_uuid)
    raw_document_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False), ForeignKey("raw_documents.id", ondelete="SET NULL"), nullable=True
    )
    doc_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    canonical_payload: Mapped[dict[str, Any] | None] = mapped_column(JsonColumn, nullable=True)
    storage_ref: Mapped[str | None] = mapped_column(String(512), nullable=True)
    source_connector: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    language: Mapped[str | None] = mapped_column(String(16), nullable=True)
    content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )

    raw: Mapped[RawDocument | None] = relationship(back_populates="canonical")
    chunks: Mapped[list[DocumentChunk]] = relationship(
        back_populates="canonical", cascade="all, delete-orphan"
    )


class DocumentChunk(Base):
    """A chunk of a canonical document (table ``document_chunks``).

    Supports parent/child chunking (e.g. a table block with row children) via the
    self-referential ``parent_chunk_id`` foreign key.
    """

    __tablename__ = "document_chunks"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_new_uuid)
    canonical_document_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("canonical_documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    parent_chunk_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("document_chunks.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    token_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    embedding_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(JsonColumn, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    canonical: Mapped[CanonicalDocument] = relationship(back_populates="chunks")


class ConnectorRegistry(Base):
    """Registered connector metadata, health, and mapping reference.

    ``manifest`` stores the ConnectorManifest JSONB; ``credentials_encrypted``
    stores **only ciphertext** (pgcrypto) — never plaintext secrets (F13).
    """

    __tablename__ = "connector_registry"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_new_uuid)
    connector_id: Mapped[str] = mapped_column(String(128), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    manifest: Mapped[dict[str, Any] | None] = mapped_column(JsonColumn, nullable=True)
    field_mapping_ref: Mapped[str | None] = mapped_column(String(512), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="inactive")
    health: Mapped[str] = mapped_column(String(32), nullable=False, default="unknown")
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    base_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    credentials_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )


__all__ = [
    "CanonicalDocument",
    "ConnectorRegistry",
    "DocumentChunk",
    "RawDocument",
]
