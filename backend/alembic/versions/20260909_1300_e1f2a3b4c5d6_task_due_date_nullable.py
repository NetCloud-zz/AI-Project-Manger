"""Allow tasks without planned start/due dates (L3 undated work items).

Revision ID: 20260909_1300_e1f2a3b4c5d6
Revises: 20260908_2100_d0e1f2a3b4c5
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260909_1300_e1f2a3b4c5d6"
down_revision = "20260908_2100_d0e1f2a3b4c5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("tasks") as batch:
        batch.alter_column("due_date", existing_type=sa.Date(), nullable=True)


def downgrade() -> None:
    # Fill blanks so the NOT NULL restore cannot fail on existing rows.
    op.execute("UPDATE tasks SET due_date = CURRENT_DATE WHERE due_date IS NULL")
    with op.batch_alter_table("tasks") as batch:
        batch.alter_column("due_date", existing_type=sa.Date(), nullable=False)
