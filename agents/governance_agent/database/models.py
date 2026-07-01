"""SQLAlchemy ORM models for Governance Agent.

Maps to the PostgreSQL schema defined in shared/models/schema.sql.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from agents.governance_agent.database.session import Base

# Cross-database JSON column: JSONB for PostgreSQL, JSON for SQLite
JsonColumn = JSONB().with_variant(JSON(), "sqlite")


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _new_uuid() -> str:
    return str(uuid.uuid4())


# ══════════════════════════════════════════════════════════════════
# User Model
# ══════════════════════════════════════════════════════════════════


class User(Base):
    """Application user with hashed password and RBAC roles.

    Maps to the `users` table plus `password_hash` (added for M2-T1).
    """

    __tablename__ = "users"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_new_uuid)
    username: Mapped[str] = mapped_column(String(128), unique=True, nullable=False, index=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    display_name: Mapped[str | None] = mapped_column(String(256), nullable=True)
    password_hash: Mapped[str] = mapped_column(String(256), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    roles: Mapped[list[str]] = mapped_column(JsonColumn, default=list, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )

    # Relationships
    api_keys: Mapped[list[ApiKey]] = relationship(
        "ApiKey", back_populates="user", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<User id={self.id} username={self.username!r}>"


# ══════════════════════════════════════════════════════════════════
# ApiKey Model
# ══════════════════════════════════════════════════════════════════


class ApiKey(Base):
    """API key for programmatic access (services, automations).

    Maps to the `api_keys` table. The raw key is only shown once
    at creation time; only key_hash is stored.
    """

    __tablename__ = "api_keys"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_new_uuid)
    user_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    key_hash: Mapped[str] = mapped_column(String(256), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    # Relationships
    user: Mapped[User] = relationship("User", back_populates="api_keys")

    def __repr__(self) -> str:
        return f"<ApiKey id={self.id} name={self.name!r}>"


# ══════════════════════════════════════════════════════════════════
# AuditLog Model
# ══════════════════════════════════════════════════════════════════


class AuditLog(Base):
    """Audit trail for all authenticated operations.

    Maps to the `audit_logs` table.
    """

    __tablename__ = "audit_logs"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_new_uuid)
    user_id: Mapped[str | None] = mapped_column(UUID(as_uuid=False), nullable=True)
    action: Mapped[str] = mapped_column(String(128), nullable=False)
    resource: Mapped[str] = mapped_column(String(256), nullable=False)
    detail: Mapped[dict[str, Any] | None] = mapped_column(JsonColumn, nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)  # Max IPv6 length
    trace_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    def __repr__(self) -> str:
        return f"<AuditLog id={self.id} action={self.action!r}>"


# ══════════════════════════════════════════════════════════════════
# Permission Model (for ABAC — knowledge-base / document / paragraph level)
# ══════════════════════════════════════════════════════════════════


class Permission(Base):
    """Attribute-based permission grants for fine-grained access control.

    Supports knowledge-base, document, and paragraph-level permissions.
    Each row grants a subject (user or group) an action on a resource.
    """

    __tablename__ = "permissions"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_new_uuid)
    subject_type: Mapped[str] = mapped_column(String(32), nullable=False)  # "user" | "role"
    subject_id: Mapped[str] = mapped_column(String(128), nullable=False)
    resource_type: Mapped[str] = mapped_column(
        String(64), nullable=False
    )  # "knowledge_base" | "document" | "paragraph" | "collection"
    resource_id: Mapped[str] = mapped_column(String(256), nullable=False)
    action: Mapped[str] = mapped_column(
        String(64), nullable=False
    )  # "read" | "write" | "delete" | "admin"
    granted_by: Mapped[str | None] = mapped_column(UUID(as_uuid=False), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    def __repr__(self) -> str:
        return f"<Permission subject={self.subject_type}:{self.subject_id} {self.action} {self.resource_type}:{self.resource_id}>"


# ══════════════════════════════════════════════════════════════════
# DecisionChainLog Model (M2-T2)
# ══════════════════════════════════════════════════════════════════


class DecisionChainLog(Base):
    """Audit trail for orchestrator decision chains.

    Maps to the `decision_chain_logs` table.
    Records supervisor plans, worker executions, and full decision context.
    """

    __tablename__ = "decision_chain_logs"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_new_uuid)
    user_id: Mapped[str | None] = mapped_column(UUID(as_uuid=False), nullable=True)
    session_id: Mapped[str] = mapped_column(UUID(as_uuid=False), nullable=False, index=True)
    query: Mapped[str] = mapped_column(Text, nullable=False)
    context: Mapped[dict[str, Any] | None] = mapped_column(JsonColumn, nullable=True)
    response: Mapped[str | None] = mapped_column(Text, nullable=True)
    model_used: Mapped[str | None] = mapped_column(String(128), nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    trace_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    def __repr__(self) -> str:
        return f"<DecisionChainLog id={self.id} session={self.session_id}>"
