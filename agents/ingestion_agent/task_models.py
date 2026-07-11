"""P6a: Async ingestion tasks — ORM model + CRUD helpers.

Persists ingestion task state in the DB so the API handler can return
202 immediately and the background worker updates status as it progresses.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from agents.governance_agent.database.session import Base


def _utcnow() -> datetime:
    return datetime.now(tz=UTC)


class IngestTask(Base):
    """Persistent state for a single async ingestion job.

    Created by the API handler (202 Accepted) and updated by the
    background worker as the pipeline progresses.
    """

    __tablename__ = "ingest_tasks"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    status: Mapped[str] = mapped_column(
        String(20), default="pending", nullable=False, index=True
    )
    # pending → processing → completed | failed | partial

    filename: Mapped[str] = mapped_column(String(512), nullable=False)
    file_hash: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    doc_type: Mapped[str] = mapped_column(String(128), nullable=False)
    content_type: Mapped[str | None] = mapped_column(String(128), nullable=True)

    # Progress & result
    progress_pct: Mapped[int] = mapped_column(Integer, default=0)  # 0..100
    total_chunks: Mapped[int] = mapped_column(Integer, default=0)
    indexed_chunks: Mapped[int] = mapped_column(Integer, default=0)
    canonical_count: Mapped[int] = mapped_column(Integer, default=0)

    result: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Storage
    raw_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    storage_ref: Mapped[str | None] = mapped_column(String(512), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )

    def __repr__(self) -> str:
        return f"<IngestTask id={self.id!r} status={self.status!r} filename={self.filename!r}>"


# ══════════════════════════════════════════════════════════════════
# CRUD helpers
# ══════════════════════════════════════════════════════════════════

STATUS_PENDING = "pending"
STATUS_PROCESSING = "processing"
STATUS_COMPLETED = "completed"
STATUS_FAILED = "failed"
STATUS_PARTIAL = "partial"
