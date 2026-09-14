"""Allow OWNER role on task_participants for multi-owner tasks.

Revision ID: 20260914_1200_d4e5f6a7b8c9
Revises: 20260911_1800_c3d4e5f6a7b8
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260914_1200_d4e5f6a7b8c9"
down_revision = "20260911_1800_c3d4e5f6a7b8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("task_participants") as batch:
        batch.drop_constraint("ck_participant_role", type_="check")
        batch.create_check_constraint(
            "ck_participant_role",
            "role IN ('COLLABORATOR', 'WATCHER', 'OWNER')",
        )


def downgrade() -> None:
    op.execute(
        sa.text("UPDATE task_participants SET role = 'COLLABORATOR' WHERE role = 'OWNER'")
    )
    with op.batch_alter_table("task_participants") as batch:
        batch.drop_constraint("ck_participant_role", type_="check")
        batch.create_check_constraint(
            "ck_participant_role",
            "role IN ('COLLABORATOR', 'WATCHER')",
        )
