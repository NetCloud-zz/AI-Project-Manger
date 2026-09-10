"""S5 tracked risk events and versioned advice records.

Adds two history tables and one link column. Nothing existing is rewritten:
``Task.ai_status``, ``Project.risk_level`` and ``Issue.suggested_solution``
keep their current meaning, and the new tables record how those values came
about. Downgrade drops the history; the current-state fields survive.

Revision ID: 20260908_1800_c9d0e1f2a3b4
Revises: 20260908_1400_b8c9d0e1f2a3
"""

import sqlalchemy as sa
from alembic import op

revision = "20260908_1800_c9d0e1f2a3b4"
down_revision = "20260908_1400_b8c9d0e1f2a3"
branch_labels = None
depends_on = None


def timestamps() -> list[sa.Column]:
    return [
        sa.Column(name, sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now())
        for name in ("created_at", "updated_at")
    ]


def upgrade() -> None:
    op.create_table(
        "risk_events",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "project_id",
            sa.Integer(),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "task_id", sa.Integer(), sa.ForeignKey("tasks.id", ondelete="CASCADE"), nullable=True
        ),
        sa.Column(
            "issue_id", sa.Integer(), sa.ForeignKey("issues.id", ondelete="CASCADE"), nullable=True
        ),
        sa.Column("event_type", sa.String(24), nullable=False),
        sa.Column("dedupe_key", sa.String(120), nullable=False),
        sa.Column("level", sa.String(16), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="OPEN"),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("cause", sa.Text(), nullable=False),
        sa.Column("evidence", sa.JSON(), nullable=True),
        sa.Column("impact_date", sa.Date(), nullable=True),
        sa.Column("impact_days", sa.Integer(), nullable=True),
        sa.Column(
            "owner_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True
        ),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolution", sa.Text(), nullable=True),
        sa.Column(
            "resolved_by",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        *timestamps(),
        sa.UniqueConstraint("project_id", "dedupe_key", name="uq_risk_event_key"),
        sa.CheckConstraint("impact_days IS NULL OR impact_days >= 0", name="ck_risk_event_impact"),
    )
    op.create_index("ix_risk_events_project_id", "risk_events", ["project_id"])
    op.create_index("ix_risk_events_task_id", "risk_events", ["task_id"])
    op.create_index("ix_risk_events_status", "risk_events", ["status"])
    op.create_index("ix_risk_events_project_status", "risk_events", ["project_id", "status"])

    op.create_table(
        "advice_records",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "issue_id",
            sa.Integer(),
            sa.ForeignKey("issues.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "project_id",
            sa.Integer(),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("status", sa.String(16), nullable=False, server_default="PROPOSED"),
        sa.Column("content", sa.JSON(), nullable=False),
        sa.Column("evidence", sa.JSON(), nullable=True),
        sa.Column("coverage", sa.JSON(), nullable=True),
        sa.Column("context_digest", sa.String(64), nullable=True),
        sa.Column("model", sa.String(120), nullable=True),
        sa.Column(
            "generated_by",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "decided_by",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decision_note", sa.Text(), nullable=True),
        sa.Column(
            "proposal_id",
            sa.String(36),
            sa.ForeignKey("change_proposals.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("outcome", sa.String(16), nullable=True),
        sa.Column("issue_resolved", sa.Boolean(), nullable=True),
        sa.Column("outcome_note", sa.Text(), nullable=True),
        sa.Column(
            "evaluated_by",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("evaluated_at", sa.DateTime(timezone=True), nullable=True),
        *timestamps(),
        sa.UniqueConstraint("issue_id", "version", name="uq_advice_version"),
        sa.CheckConstraint("version >= 1", name="ck_advice_version"),
    )
    op.create_index("ix_advice_records_issue_id", "advice_records", ["issue_id"])
    op.create_index("ix_advice_records_project_id", "advice_records", ["project_id"])
    op.create_index("ix_advice_records_status", "advice_records", ["status"])
    op.create_index("ix_advice_records_issue_status", "advice_records", ["issue_id", "status"])

    with op.batch_alter_table("action_items") as batch:
        batch.add_column(sa.Column("advice_id", sa.Integer(), nullable=True))
        batch.create_foreign_key(
            "fk_action_items_advice_id",
            "advice_records",
            ["advice_id"],
            ["id"],
            ondelete="SET NULL",
        )
    op.create_index("ix_action_items_advice_id", "action_items", ["advice_id"])


def downgrade() -> None:
    op.drop_index("ix_action_items_advice_id", table_name="action_items")
    with op.batch_alter_table("action_items") as batch:
        batch.drop_constraint("fk_action_items_advice_id", type_="foreignkey")
        batch.drop_column("advice_id")

    op.drop_index("ix_advice_records_issue_status", table_name="advice_records")
    op.drop_index("ix_advice_records_status", table_name="advice_records")
    op.drop_index("ix_advice_records_project_id", table_name="advice_records")
    op.drop_index("ix_advice_records_issue_id", table_name="advice_records")
    op.drop_table("advice_records")

    op.drop_index("ix_risk_events_project_status", table_name="risk_events")
    op.drop_index("ix_risk_events_status", table_name="risk_events")
    op.drop_index("ix_risk_events_task_id", table_name="risk_events")
    op.drop_index("ix_risk_events_project_id", table_name="risk_events")
    op.drop_table("risk_events")
