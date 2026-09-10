"""add project co-owners, start_date, and task branches

Revision ID: 20260907_1600_d4e5f6a7b8c9
Revises: 20260907_1500_c3d4e5f6a7b8
Create Date: 2026-09-07 16:00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260907_1600_d4e5f6a7b8c9"
down_revision: str | None = "20260907_1500_c3d4e5f6a7b8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("projects", sa.Column("start_date", sa.Date(), nullable=True))

    op.create_table(
        "project_owners",
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("project_id", "user_id", name="pk_project_owners"),
    )
    op.create_index("ix_project_owners_user_id", "project_owners", ["user_id"])

    # Backfill: every project already has a primary owner_id.
    op.execute(
        """
        INSERT INTO project_owners (project_id, user_id)
        SELECT id, owner_id FROM projects
        ON CONFLICT DO NOTHING
        """
    )

    op.add_column("tasks", sa.Column("branch_root_id", sa.Integer(), nullable=True))
    op.add_column("tasks", sa.Column("branch_label", sa.String(length=80), nullable=True))
    op.add_column(
        "tasks",
        sa.Column(
            "is_active_branch",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
    )
    op.create_foreign_key(
        "fk_tasks_branch_root_id",
        "tasks",
        "tasks",
        ["branch_root_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_tasks_branch_root_id", "tasks", ["branch_root_id"])


def downgrade() -> None:
    op.drop_index("ix_tasks_branch_root_id", table_name="tasks")
    op.drop_constraint("fk_tasks_branch_root_id", "tasks", type_="foreignkey")
    op.drop_column("tasks", "is_active_branch")
    op.drop_column("tasks", "branch_label")
    op.drop_column("tasks", "branch_root_id")

    op.drop_index("ix_project_owners_user_id", table_name="project_owners")
    op.drop_table("project_owners")
    op.drop_column("projects", "start_date")
