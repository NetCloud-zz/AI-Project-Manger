"""Durable request execution plans and per-item recovery."""

import sqlalchemy as sa
from alembic import op

revision = "20260910_1000_d6e7f8a9b0c1"
down_revision = "20260909_1900_c5d6e7f8a9b0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "agent_command_plans",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "request_id",
            sa.Integer(),
            sa.ForeignKey("agent_requests.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("policy", sa.String(20), nullable=False, server_default="independent"),
        sa.Column("status", sa.String(24), nullable=False, server_default="PLANNING"),
        sa.Column("expected_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error", sa.Text()),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("lease_token", sa.String(64)),
        sa.Column("lease_until", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_table(
        "agent_command_items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "plan_id",
            sa.Integer(),
            sa.ForeignKey("agent_command_plans.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("item_id", sa.String(64), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("tool", sa.String(100), nullable=False),
        sa.Column("source_text", sa.Text(), nullable=False),
        sa.Column("source_start", sa.Integer(), nullable=False),
        sa.Column("source_end", sa.Integer(), nullable=False),
        sa.Column("arguments", sa.JSON(), nullable=False),
        sa.Column("depends_on", sa.JSON(), nullable=False),
        sa.Column("state", sa.String(24), nullable=False, server_default="PENDING"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("result", sa.JSON()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint("plan_id", "item_id", name="uq_command_plan_item"),
    )
    op.create_index("ix_agent_command_items_plan_id", "agent_command_items", ["plan_id"])


def downgrade() -> None:
    op.drop_table("agent_command_items")
    op.drop_table("agent_command_plans")
