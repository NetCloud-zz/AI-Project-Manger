"""add task start_date/progress_percent and task_links table

Revision ID: 20260902_1500_d4e5f6a7b8c9
Revises: 20260902_1400_c3d4e5f6a7b8
Create Date: 2026-09-02 15:00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260902_1500_d4e5f6a7b8c9"
down_revision: str | None = "20260902_1400_c3d4e5f6a7b8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("tasks", sa.Column("start_date", sa.Date(), nullable=True))
    op.add_column("tasks", sa.Column("progress_percent", sa.Integer(), nullable=True))
    op.create_check_constraint(
        "ck_tasks_progress_percent_range",
        "tasks",
        "progress_percent IS NULL OR (progress_percent >= 0 AND progress_percent <= 100)",
    )

    # Backfill so existing tasks render as bars instead of zero-length markers.
    op.execute(
        """
        UPDATE tasks
        SET start_date = LEAST(due_date, CAST(created_at AS DATE))
        WHERE start_date IS NULL
        """
    )

    op.create_table(
        "task_links",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("source_id", sa.Integer(), nullable=False),
        sa.Column("target_id", sa.Integer(), nullable=False),
        sa.Column("link_type", sa.String(length=20), nullable=False),
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
        sa.ForeignKeyConstraint(["source_id"], ["tasks.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["target_id"], ["tasks.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source_id", "target_id", name="uq_task_links_source_target"),
        sa.CheckConstraint("source_id <> target_id", name="ck_task_links_no_self_reference"),
    )
    op.create_index("ix_task_links_project_id", "task_links", ["project_id"])
    op.create_index("ix_task_links_source_id", "task_links", ["source_id"])
    op.create_index("ix_task_links_target_id", "task_links", ["target_id"])


def downgrade() -> None:
    op.drop_index("ix_task_links_target_id", table_name="task_links")
    op.drop_index("ix_task_links_source_id", table_name="task_links")
    op.drop_index("ix_task_links_project_id", table_name="task_links")
    op.drop_table("task_links")

    op.drop_constraint("ck_tasks_progress_percent_range", "tasks", type_="check")
    op.drop_column("tasks", "progress_percent")
    op.drop_column("tasks", "start_date")
