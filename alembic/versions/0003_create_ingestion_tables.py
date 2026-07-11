"""create ingestion shared tables (raw/canonical/chunks/connector_registry)

Revision ID: 0003_create_ingestion_tables
Revises: 0002_add_permissions
Create Date: 2026-07-11
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0003_create_ingestion_tables"
down_revision: str | None = "0002_add_permissions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "raw_documents",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True, nullable=False),
        sa.Column("source_type", sa.String(32), nullable=False),
        sa.Column("source_ref", sa.String(512), nullable=True),
        sa.Column("content_type", sa.String(128), nullable=True),
        sa.Column("raw_payload", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_raw_documents_source_type", "raw_documents", ["source_type"])
    op.create_index("ix_raw_documents_source_ref", "raw_documents", ["source_ref"])

    op.create_table(
        "canonical_documents",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True, nullable=False),
        sa.Column("raw_document_id", postgresql.UUID(as_uuid=False), nullable=True),
        sa.Column("doc_type", sa.String(64), nullable=False),
        sa.Column("title", sa.String(512), nullable=False),
        sa.Column("canonical_payload", postgresql.JSONB(), nullable=True),
        sa.Column("storage_ref", sa.String(512), nullable=True),
        sa.Column("source_connector", sa.String(128), nullable=True),
        sa.Column("language", sa.String(16), nullable=True),
        sa.Column("content_hash", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["raw_document_id"], ["raw_documents.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_canonical_documents_doc_type", "canonical_documents", ["doc_type"])
    op.create_index(
        "ix_canonical_documents_source_connector", "canonical_documents", ["source_connector"]
    )
    op.create_index("ix_canonical_documents_content_hash", "canonical_documents", ["content_hash"])

    op.create_table(
        "document_chunks",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True, nullable=False),
        sa.Column("canonical_document_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("parent_chunk_id", postgresql.UUID(as_uuid=False), nullable=True),
        sa.Column("chunk_index", sa.Integer, nullable=False, server_default=sa.text("0")),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("token_count", sa.Integer, nullable=True),
        sa.Column("embedding_id", sa.String(128), nullable=True),
        sa.Column("metadata_json", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["canonical_document_id"], ["canonical_documents.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["parent_chunk_id"], ["document_chunks.id"], ondelete="CASCADE"),
    )
    op.create_index(
        "ix_document_chunks_canonical_document_id",
        "document_chunks",
        ["canonical_document_id"],
    )
    op.create_index("ix_document_chunks_parent_chunk_id", "document_chunks", ["parent_chunk_id"])

    op.create_table(
        "connector_registry",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True, nullable=False),
        sa.Column("connector_id", sa.String(128), nullable=False),
        sa.Column("name", sa.String(256), nullable=False),
        sa.Column("manifest", postgresql.JSONB(), nullable=True),
        sa.Column("field_mapping_ref", sa.String(512), nullable=True),
        sa.Column("status", sa.String(32), nullable=False, server_default=sa.text("'inactive'")),
        sa.Column("health", sa.String(32), nullable=False, server_default=sa.text("'unknown'")),
        sa.Column("last_checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("base_url", sa.String(512), nullable=True),
        sa.Column("credentials_encrypted", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "uq_connector_registry_connector_id",
        "connector_registry",
        ["connector_id"],
        unique=True,
    )
    op.create_index("ix_connector_registry_status", "connector_registry", ["status"])


def downgrade() -> None:
    # Drop children first to respect foreign keys.
    op.drop_table("document_chunks")
    op.drop_table("canonical_documents")
    op.drop_table("connector_registry")
    op.drop_table("raw_documents")
