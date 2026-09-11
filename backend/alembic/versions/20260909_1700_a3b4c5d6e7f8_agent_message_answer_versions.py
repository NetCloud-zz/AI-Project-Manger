"""OPT-04: answer version association fields on agent_messages.

Revision ID: 20260909_1700_a3b4c5d6e7f8
Revises: 20260909_1600_f2a3b4c5d6e7
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260909_1700_a3b4c5d6e7f8"
down_revision = "20260909_1600_f2a3b4c5d6e7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("agent_messages") as batch:
        batch.add_column(sa.Column("parent_user_message_id", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("regenerated_from_id", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("answer_version", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("selected_answer_id", sa.Integer(), nullable=True))
        batch.add_column(
            sa.Column(
                "association_status",
                sa.String(length=16),
                nullable=False,
                server_default="NORMAL",
            )
        )
        batch.create_foreign_key(
            "fk_agent_messages_parent_user",
            "agent_messages",
            ["parent_user_message_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch.create_foreign_key(
            "fk_agent_messages_regenerated_from",
            "agent_messages",
            ["regenerated_from_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch.create_foreign_key(
            "fk_agent_messages_selected_answer",
            "agent_messages",
            ["selected_answer_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch.create_index("ix_agent_messages_parent_user", ["parent_user_message_id"])

    # Best-effort backfill: pair each USER with the next ASSISTANT as version 1.
    # Ambiguous multi-regenerate histories stay unbound (association_status kept NORMAL
    # only when a single clear pair exists; otherwise leave parent null as LEGACY).
    op.execute(
        """
        UPDATE agent_messages AS a
        SET
            parent_user_message_id = u.id,
            answer_version = 1,
            association_status = 'NORMAL'
        FROM agent_messages AS u
        WHERE a.role = 'ASSISTANT'
          AND u.role = 'USER'
          AND a.conversation_id = u.conversation_id
          AND a.parent_user_message_id IS NULL
          AND a.id = (
              SELECT MIN(a2.id)
              FROM agent_messages AS a2
              WHERE a2.conversation_id = u.conversation_id
                AND a2.role = 'ASSISTANT'
                AND a2.id > u.id
                AND NOT EXISTS (
                    SELECT 1 FROM agent_messages AS mid
                    WHERE mid.conversation_id = u.conversation_id
                      AND mid.role = 'USER'
                      AND mid.id > u.id
                      AND mid.id < a2.id
                )
          )
        """
    )
    op.execute(
        """
        UPDATE agent_messages AS u
        SET selected_answer_id = a.id
        FROM agent_messages AS a
        WHERE u.role = 'USER'
          AND a.parent_user_message_id = u.id
          AND a.answer_version = 1
          AND u.selected_answer_id IS NULL
        """
    )
    op.execute(
        """
        UPDATE agent_messages
        SET association_status = 'LEGACY'
        WHERE role = 'ASSISTANT'
          AND parent_user_message_id IS NULL
        """
    )


def downgrade() -> None:
    with op.batch_alter_table("agent_messages") as batch:
        batch.drop_index("ix_agent_messages_parent_user")
        batch.drop_constraint("fk_agent_messages_selected_answer", type_="foreignkey")
        batch.drop_constraint("fk_agent_messages_regenerated_from", type_="foreignkey")
        batch.drop_constraint("fk_agent_messages_parent_user", type_="foreignkey")
        batch.drop_column("association_status")
        batch.drop_column("selected_answer_id")
        batch.drop_column("answer_version")
        batch.drop_column("regenerated_from_id")
        batch.drop_column("parent_user_message_id")
