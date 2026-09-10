"""add progress_updates table

Revision ID: 20260902_1200_a1b2c3d4e5f6
Revises: 638d77372830
Create Date: 2026-09-02 12:00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260902_1200_a1b2c3d4e5f6"
down_revision: str | None = "638d77372830"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "progress_updates",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("task_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("raw_content", sa.Text(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("progress_percent", sa.Integer(), nullable=True),
        sa.Column(
            "ai_status",
            sa.Enum(
                "ON_TRACK",
                "AT_RISK",
                "DELAYED",
                name="progress_ai_status",
                native_enum=False,
                length=16,
            ),
            nullable=True,
        ),
        sa.Column("risk_detected", sa.Boolean(), nullable=True),
        sa.Column(
            "ai_analysis_failed", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_progress_updates_task_id", "progress_updates", ["task_id"])
    op.create_index("ix_progress_updates_user_id", "progress_updates", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_progress_updates_user_id", table_name="progress_updates")
    op.drop_index("ix_progress_updates_task_id", table_name="progress_updates")
    op.drop_table("progress_updates")
