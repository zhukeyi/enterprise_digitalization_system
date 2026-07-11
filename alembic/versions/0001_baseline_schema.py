"""Baseline schema — reproduces shared/models/schema.sql.

This is the initial Alembic revision for an existing database that was
previously created from ``shared/models/schema.sql``. All statements are
idempotent (``IF NOT EXISTS``) so the migration is safe to run against the
already-existing production schema.

Revision ID: 0001_baseline
Revises:
Create Date: 2026-07-11
"""

from collections.abc import Sequence

from sqlalchemy import text as sa_text

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0001_baseline"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_STATEMENTS: list[str] = [
    "CREATE EXTENSION IF NOT EXISTS pgcrypto",
    """
    CREATE TABLE IF NOT EXISTS users (
        id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        username    VARCHAR(128) NOT NULL UNIQUE,
        email       VARCHAR(255) NOT NULL UNIQUE,
        display_name VARCHAR(256),
        is_active   BOOLEAN NOT NULL DEFAULT TRUE,
        roles       JSONB NOT NULL DEFAULT '[]',
        created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
        updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS api_keys (
        id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        user_id     UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        key_hash    VARCHAR(256) NOT NULL UNIQUE,
        name        VARCHAR(128) NOT NULL,
        is_active   BOOLEAN NOT NULL DEFAULT TRUE,
        expires_at  TIMESTAMPTZ,
        created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS audit_logs (
        id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        user_id     UUID REFERENCES users(id),
        action      VARCHAR(256) NOT NULL,
        resource    VARCHAR(256) NOT NULL,
        detail      JSONB,
        ip_address  INET,
        trace_id    UUID,
        created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS decision_chain_logs (
        id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        user_id     UUID REFERENCES users(id),
        session_id  UUID NOT NULL,
        query       TEXT NOT NULL,
        context     JSONB,
        response    TEXT,
        model_used  VARCHAR(128),
        latency_ms  INTEGER,
        trace_id    UUID,
        created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS knowledge_bases (
        id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        name        VARCHAR(256) NOT NULL,
        description TEXT,
        permissions JSONB NOT NULL DEFAULT '{}',
        created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
        updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_audit_user ON audit_logs(user_id)",
    "CREATE INDEX IF NOT EXISTS idx_audit_action ON audit_logs(action)",
    "CREATE INDEX IF NOT EXISTS idx_audit_created ON audit_logs(created_at DESC)",
    "CREATE INDEX IF NOT EXISTS idx_decision_user ON decision_chain_logs(user_id)",
    "CREATE INDEX IF NOT EXISTS idx_decision_session ON decision_chain_logs(session_id)",
    "CREATE INDEX IF NOT EXISTS idx_decision_created ON decision_chain_logs(created_at DESC)",
]


def upgrade() -> None:
    for stmt in _STATEMENTS:
        op.execute(sa_text(stmt))


def downgrade() -> None:
    # Drop in FK-safe order (children before parents).
    op.execute(sa_text("DROP TABLE IF EXISTS decision_chain_logs CASCADE"))
    op.execute(sa_text("DROP TABLE IF EXISTS audit_logs CASCADE"))
    op.execute(sa_text("DROP TABLE IF EXISTS api_keys CASCADE"))
    op.execute(sa_text("DROP TABLE IF EXISTS knowledge_bases CASCADE"))
    op.execute(sa_text("DROP TABLE IF EXISTS users CASCADE"))
