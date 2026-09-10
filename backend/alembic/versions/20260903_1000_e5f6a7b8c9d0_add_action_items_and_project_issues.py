"""add action_items and allow project-level issues

Revision ID: 20260903_1000_e5f6a7b8c9d0
Revises: 20260902_1500_d4e5f6a7b8c9
Create Date: 2026-09-03 10:00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260903_1000_e5f6a7b8c9d0"
down_revision: str | None = "20260902_1500_d4e5f6a7b8c9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Issues raised manually at project level have no owning task.
    op.alter_column("issues", "task_id", existing_type=sa.Integer(), nullable=True)

    op.create_table(
        "action_items",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("task_id", sa.Integer(), nullable=True),
        sa.Column("issue_id", sa.Integer(), nullable=True),
        sa.Column("owner_id", sa.Integer(), nullable=True),
        sa.Column("created_by", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("due_date", sa.Date(), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("priority", sa.String(length=16), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["issue_id"], ["issues.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_action_items_project_id", "action_items", ["project_id"])
    op.create_index("ix_action_items_task_id", "action_items", ["task_id"])
    op.create_index("ix_action_items_issue_id", "action_items", ["issue_id"])
    op.create_index("ix_action_items_owner_id", "action_items", ["owner_id"])
    op.create_index("ix_action_items_created_by", "action_items", ["created_by"])


def downgrade() -> None:
    op.drop_index("ix_action_items_created_by", table_name="action_items")
    op.drop_index("ix_action_items_owner_id", table_name="action_items")
    op.drop_index("ix_action_items_issue_id", table_name="action_items")
    op.drop_index("ix_action_items_task_id", table_name="action_items")
    op.drop_index("ix_action_items_project_id", table_name="action_items")
    op.drop_table("action_items")

    # Project-level issues cannot survive the NOT NULL restore.
    op.execute("DELETE FROM issues WHERE task_id IS NULL")
    op.alter_column("issues", "task_id", existing_type=sa.Integer(), nullable=False)
