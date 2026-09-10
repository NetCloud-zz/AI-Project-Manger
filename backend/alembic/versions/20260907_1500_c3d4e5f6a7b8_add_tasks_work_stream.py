"""add tasks.work_stream for Gantt grouping

Revision ID: 20260907_1500_c3d4e5f6a7b8
Revises: 20260907_1400_b2c3d4e5f6a7
Create Date: 2026-09-07 15:00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260907_1500_c3d4e5f6a7b8"
down_revision: str | None = "20260907_1400_b2c3d4e5f6a7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("tasks", sa.Column("work_stream", sa.String(length=120), nullable=True))
    op.create_index("ix_tasks_work_stream", "tasks", ["project_id", "work_stream"])


def downgrade() -> None:
    op.drop_index("ix_tasks_work_stream", table_name="tasks")
    op.drop_column("tasks", "work_stream")
