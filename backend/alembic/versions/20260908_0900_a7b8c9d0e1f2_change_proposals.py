"""S3 reviewed change proposals and transactional notification events.

Revision ID: 20260908_0900_a7b8c9d0e1f2
Revises: 20260907_1800_f6a7b8c9d0e1
"""

import sqlalchemy as sa
from alembic import op

revision = "20260908_0900_a7b8c9d0e1f2"
down_revision = "20260907_1800_f6a7b8c9d0e1"
branch_labels = None
depends_on = None


def timestamps() -> list[sa.Column]:
    return [
        sa.Column(name, sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now())
        for name in ("created_at", "updated_at")
    ]


def upgrade() -> None:
    op.create_table(
        "change_proposals",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "project_id",
            sa.Integer(),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "created_by",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("status", sa.String(16), nullable=False, server_default="DRAFT"),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("request", sa.JSON(), nullable=False),
        sa.Column("source", sa.JSON()),
        sa.Column("create_key", sa.String(100), nullable=False),
        sa.Column("create_hash", sa.String(64), nullable=False),
        sa.Column("preview", sa.JSON()),
        sa.Column("diff", sa.JSON()),
        sa.Column("snapshot_token", sa.String(64)),
        sa.Column("digest", sa.String(64)),
        sa.Column("base_plan_version", sa.Integer()),
        sa.Column("confirmed_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="RESTRICT")),
        sa.Column("confirmed_at", sa.DateTime(timezone=True)),
        sa.Column("expires_at", sa.DateTime(timezone=True)),
        sa.Column("applied_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="RESTRICT")),
        sa.Column("applied_at", sa.DateTime(timezone=True)),
        sa.Column(
            "applied_version_id",
            sa.Integer(),
            sa.ForeignKey("plan_versions.id", ondelete="RESTRICT"),
        ),
        sa.Column("apply_key", sa.String(100), unique=True),
        sa.Column("result", sa.JSON()),
        sa.Column("failure_reason", sa.Text()),
        sa.UniqueConstraint(
            "project_id", "created_by", "create_key", name="uq_proposal_create_key"
        ),
        sa.CheckConstraint(
            "status IN ('DRAFT','VALIDATED','CONFIRMED','APPLIED','REJECTED','EXPIRED','FAILED')",
            name="ck_proposal_status",
        ),
        sa.CheckConstraint("revision >= 1", name="ck_proposal_revision"),
        *timestamps(),
    )
    op.create_index("ix_change_proposals_project_id", "change_proposals", ["project_id"])
    op.create_table(
        "plan_notification_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "proposal_id",
            sa.String(36),
            sa.ForeignKey("change_proposals.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "project_id",
            sa.Integer(),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "recipient_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="PENDING"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_error", sa.Text()),
        sa.UniqueConstraint("proposal_id", "recipient_id", name="uq_plan_event_recipient"),
        *timestamps(),
    )
    for column in ("proposal_id", "project_id"):
        op.create_index(
            f"ix_plan_notification_events_{column}", "plan_notification_events", [column]
        )


def downgrade() -> None:
    op.drop_table("plan_notification_events")
    op.drop_table("change_proposals")
