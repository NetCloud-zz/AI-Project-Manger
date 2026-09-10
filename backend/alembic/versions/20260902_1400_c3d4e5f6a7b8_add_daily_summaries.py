"""add daily_project_summaries table

Revision ID: 20260902_1400_c3d4e5f6a7b8
Revises: 20260902_1300_b2c3d4e5f6a7
Create Date: 2026-09-02 14:00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260902_1400_c3d4e5f6a7b8"
down_revision: str | None = "20260902_1300_b2c3d4e5f6a7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "daily_project_summaries",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("summary_date", sa.Date(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("risk_summary", sa.Text(), nullable=False),
        sa.Column("next_action", sa.Text(), nullable=False),
        sa.Column("management_attention", sa.Text(), nullable=False),
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
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", "summary_date", name="uq_daily_summary_project_date"),
    )
    op.create_index(
        "ix_daily_project_summaries_project_id", "daily_project_summaries", ["project_id"]
    )
    op.create_index(
        "ix_daily_project_summaries_summary_date", "daily_project_summaries", ["summary_date"]
    )


def downgrade() -> None:
    op.drop_index("ix_daily_project_summaries_summary_date", table_name="daily_project_summaries")
    op.drop_index("ix_daily_project_summaries_project_id", table_name="daily_project_summaries")
    op.drop_table("daily_project_summaries")
