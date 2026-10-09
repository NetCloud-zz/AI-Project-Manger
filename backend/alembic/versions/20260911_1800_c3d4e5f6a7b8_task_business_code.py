"""Add tasks.task_code with daily T{YYYYMMDD}-NNN business ids.

Revision ID: 20260911_1800_c3d4e5f6a7b8
Revises: 20260911_1600_b2c3d4e5f6a7
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260911_1800_c3d4e5f6a7b8"
down_revision = "20260911_1600_b2c3d4e5f6a7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("tasks") as batch:
        batch.add_column(sa.Column("task_code", sa.String(length=64), nullable=True))
    # Backfill existing rows using created_at in Asia/Shanghai, sequenced per calendar day.
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute(
            """
            WITH numbered AS (
                SELECT
                    id,
                    'T' || to_char(
                        (created_at AT TIME ZONE 'UTC') AT TIME ZONE 'Asia/Shanghai',
                        'YYYYMMDD'
                    ) || '-' || lpad(
                        CAST(
                            row_number() OVER (
                                PARTITION BY (
                                    ((created_at AT TIME ZONE 'UTC') AT TIME ZONE 'Asia/Shanghai')::date
                                )
                                ORDER BY id
                            ) AS text
                        ),
                        3,
                        '0'
                    ) AS code
                FROM tasks
                WHERE task_code IS NULL
            )
            UPDATE tasks AS t
            SET task_code = numbered.code
            FROM numbered
            WHERE t.id = numbered.id
            """
        )
    else:
        op.execute(
            """
            UPDATE tasks
            SET task_code = 'Tlegacy-' || printf('%06d', id)
            WHERE task_code IS NULL
            """
        )
    with op.batch_alter_table("tasks") as batch:
        batch.create_unique_constraint("uq_tasks_task_code", ["task_code"])


def downgrade() -> None:
    with op.batch_alter_table("tasks") as batch:
        batch.drop_constraint("uq_tasks_task_code", type_="unique")
        batch.drop_column("task_code")
