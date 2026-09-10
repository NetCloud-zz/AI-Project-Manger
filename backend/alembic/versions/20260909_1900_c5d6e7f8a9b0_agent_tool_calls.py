"""Add agent_tool_calls for Phase-1 Management Agent audit.

Revision ID: 20260909_1900_c5d6e7f8a9b0
Revises: 20260909_1800_b4c5d6e7f8a9
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20260909_1900_c5d6e7f8a9b0"
down_revision = "20260909_1800_b4c5d6e7f8a9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    json_type = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")
    op.create_table(
        "agent_tool_calls",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("request_id", sa.Integer(), nullable=True),
        sa.Column("conversation_id", sa.Integer(), nullable=True),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("tool_name", sa.String(length=100), nullable=False),
        sa.Column("risk_level", sa.String(length=32), nullable=False),
        sa.Column("tool_call_id", sa.String(length=100), nullable=True),
        sa.Column("arguments_json", json_type, nullable=True),
        sa.Column("result_summary", json_type, nullable=True),
        sa.Column("success", sa.Boolean(), nullable=False),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["conversation_id"], ["agent_conversations.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["request_id"], ["agent_requests.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_agent_tool_calls_request", "agent_tool_calls", ["request_id"])
    op.create_index("ix_agent_tool_calls_created", "agent_tool_calls", ["created_at"])
    op.create_index(
        op.f("ix_agent_tool_calls_conversation_id"),
        "agent_tool_calls",
        ["conversation_id"],
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_agent_tool_calls_conversation_id"), table_name="agent_tool_calls")
    op.drop_index("ix_agent_tool_calls_created", table_name="agent_tool_calls")
    op.drop_index("ix_agent_tool_calls_request", table_name="agent_tool_calls")
    op.drop_table("agent_tool_calls")
