"""Add the ``permissions`` table (ABAC grants).

The ``Permission`` ORM model exists but was never created by the legacy
``schema.sql`` flow. This additive, forward-only migration brings the
database in line with the modeled metadata.

Revision ID: 0002_add_permissions
Revises: 0001_baseline
Create Date: 2026-07-11
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0002_add_permissions"
down_revision: str | None = "0001_baseline"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "permissions",
        sa.Column(
            "id",
            sa.UUID(as_uuid=False),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
            nullable=False,
        ),
        sa.Column("subject_type", sa.String(32), nullable=False),
        sa.Column("subject_id", sa.String(128), nullable=False),
        sa.Column("resource_type", sa.String(64), nullable=False),
        sa.Column("resource_id", sa.String(256), nullable=False),
        sa.Column("action", sa.String(64), nullable=False),
        sa.Column("granted_by", sa.UUID(as_uuid=False), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index("idx_permissions_subject", "permissions", ["subject_type", "subject_id"])
    op.create_index("idx_permissions_resource", "permissions", ["resource_type", "resource_id"])


def downgrade() -> None:
    op.drop_index("idx_permissions_resource", table_name="permissions")
    op.drop_index("idx_permissions_subject", table_name="permissions")
    op.drop_table("permissions")
