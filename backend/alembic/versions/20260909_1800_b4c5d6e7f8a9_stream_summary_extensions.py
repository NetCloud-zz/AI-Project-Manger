"""OPT-05—09 schema extensions: stream states, summary range, request heartbeat.

Revision ID: 20260909_1800_b4c5d6e7f8a9
Revises: 20260909_1700_a3b4c5d6e7f8
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260909_1800_b4c5d6e7f8a9"
down_revision = "20260909_1700_a3b4c5d6e7f8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("agent_conversations") as batch:
        batch.add_column(sa.Column("summary_through_message_id", sa.Integer(), nullable=True))

    with op.batch_alter_table("agent_requests") as batch:
        batch.add_column(
            sa.Column(
                "cancel_requested",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("false"),
            )
        )
        batch.add_column(sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("agent_requests") as batch:
        batch.drop_column("heartbeat_at")
        batch.drop_column("cancel_requested")
    with op.batch_alter_table("agent_conversations") as batch:
        batch.drop_column("summary_through_message_id")
