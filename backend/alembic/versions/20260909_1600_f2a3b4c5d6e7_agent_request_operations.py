"""Agent request/operation tables for OPT-03 idempotency.

Revision ID: 20260909_1600_f2a3b4c5d6e7
Revises: 20260909_1300_e1f2a3b4c5d6
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260909_1600_f2a3b4c5d6e7"
down_revision = "20260909_1300_e1f2a3b4c5d6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "agent_requests",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("conversation_id", sa.Integer(), nullable=False),
        sa.Column("client_request_id", sa.String(length=100), nullable=False),
        sa.Column("content_digest", sa.String(length=64), nullable=False),
        sa.Column("content_preview", sa.String(length=500), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("user_message_id", sa.Integer(), nullable=True),
        sa.Column("assistant_message_id", sa.Integer(), nullable=True),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["assistant_message_id"], ["agent_messages.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["conversation_id"], ["agent_conversations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_message_id"], ["agent_messages.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id",
            "conversation_id",
            "client_request_id",
            name="uq_agent_requests_user_conversation_client",
        ),
    )
    op.create_index("ix_agent_requests_user_id", "agent_requests", ["user_id"])
    op.create_index("ix_agent_requests_conversation_id", "agent_requests", ["conversation_id"])
    op.create_index(
        "ix_agent_requests_conversation_created",
        "agent_requests",
        ["conversation_id", "created_at"],
    )

    op.create_table(
        "agent_operations",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("operation_id", sa.String(length=64), nullable=False),
        sa.Column("request_id", sa.Integer(), nullable=False),
        sa.Column("tool_name", sa.String(length=100), nullable=False),
        sa.Column("args_digest", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("result_json", sa.JSON(), nullable=True),
        sa.Column("tool_call_id", sa.String(length=100), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["request_id"], ["agent_requests.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("operation_id", name="uq_agent_operations_operation_id"),
    )
    op.create_index("ix_agent_operations_request", "agent_operations", ["request_id"])


def downgrade() -> None:
    op.drop_index("ix_agent_operations_request", table_name="agent_operations")
    op.drop_table("agent_operations")
    op.drop_index("ix_agent_requests_conversation_created", table_name="agent_requests")
    op.drop_index("ix_agent_requests_conversation_id", table_name="agent_requests")
    op.drop_index("ix_agent_requests_user_id", table_name="agent_requests")
    op.drop_table("agent_requests")
