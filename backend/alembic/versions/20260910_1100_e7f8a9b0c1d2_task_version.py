"""Add optimistic lock version on tasks for Agent/REST concurrent edits."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260910_1100_e7f8a9b0c1d2"
down_revision = "20260910_1000_d6e7f8a9b0c1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "tasks",
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
    )


def downgrade() -> None:
    op.drop_column("tasks", "version")
