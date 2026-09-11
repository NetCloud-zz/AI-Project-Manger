"""Allow tasks without an assigned owner (L3 work registered first).

Revision ID: 20260911_1600_b2c3d4e5f6a7
Revises: 20260911_1400_a1b2c3d4e5f6
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260911_1600_b2c3d4e5f6a7"
down_revision = "20260911_1400_a1b2c3d4e5f6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("tasks") as batch:
        batch.alter_column("owner_id", existing_type=sa.Integer(), nullable=True)


def downgrade() -> None:
    # Restore NOT NULL only after every row has an owner (caller must fix data first).
    op.execute(
        """
        UPDATE tasks
        SET owner_id = (
            SELECT p.owner_id FROM projects p WHERE p.id = tasks.project_id
        )
        WHERE owner_id IS NULL
        """
    )
    with op.batch_alter_table("tasks") as batch:
        batch.alter_column("owner_id", existing_type=sa.Integer(), nullable=False)
