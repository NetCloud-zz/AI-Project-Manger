"""S4 notification delivery state, agent message cards, and plan drafts.

Existing PENDING outbox rows become QUEUED and keep their content. Because the
recipient unique key gains the channel column, SQLite is rebuilt via batch mode.

Revision ID: 20260908_1400_b8c9d0e1f2a3
Revises: 20260908_0900_a7b8c9d0e1f2
"""

import sqlalchemy as sa
from alembic import op

revision = "20260908_1400_b8c9d0e1f2a3"
down_revision = "20260908_0900_a7b8c9d0e1f2"
branch_labels = None
depends_on = None

_EVENT_STATUS_CHECK = "status IN ('QUEUED','SENT','FAILED','ACKNOWLEDGED')"


def timestamps() -> list[sa.Column]:
    return [
        sa.Column(name, sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now())
        for name in ("created_at", "updated_at")
    ]


def upgrade() -> None:
    # --- Notification delivery state -------------------------------------
    with op.batch_alter_table("plan_notification_events") as batch:
        batch.add_column(
            sa.Column("event_type", sa.String(32), nullable=False, server_default="PLAN_CHANGE")
        )
        batch.add_column(
            sa.Column("channel", sa.String(32), nullable=False, server_default="console")
        )
        batch.add_column(sa.Column("next_attempt_at", sa.DateTime(timezone=True)))
        batch.add_column(sa.Column("sent_at", sa.DateTime(timezone=True)))
        batch.add_column(
            sa.Column(
                "delivery_uncertain",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            )
        )
        batch.add_column(sa.Column("acknowledged_at", sa.DateTime(timezone=True)))

    # Queue existing intents before tightening the status domain.
    op.execute(
        "UPDATE plan_notification_events SET status = 'QUEUED', "
        "next_attempt_at = created_at WHERE status = 'PENDING'"
    )

    with op.batch_alter_table("plan_notification_events") as batch:
        batch.drop_constraint("uq_plan_event_recipient", type_="unique")
        batch.create_unique_constraint(
            "uq_plan_event_recipient", ["proposal_id", "recipient_id", "channel"]
        )
        batch.create_check_constraint("ck_plan_event_status", _EVENT_STATUS_CHECK)
        batch.alter_column("status", server_default="QUEUED")
    op.create_index(
        "ix_plan_notification_events_recipient_id", "plan_notification_events", ["recipient_id"]
    )
    op.create_index("ix_plan_notification_events_status", "plan_notification_events", ["status"])

    # --- Structured cards attached to assistant turns ---------------------
    op.add_column("agent_messages", sa.Column("cards", sa.JSON(), nullable=True))

    # --- Conversational project plan drafts -------------------------------
    op.create_table(
        "plan_drafts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "created_by",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="DRAFT"),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("content", sa.JSON(), nullable=False),
        sa.Column("review", sa.JSON()),
        sa.Column("digest", sa.String(64)),
        sa.Column("create_key", sa.String(100), nullable=False),
        sa.Column("publish_key", sa.String(100), unique=True),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id", ondelete="SET NULL")),
        sa.Column("published_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="RESTRICT")),
        sa.Column("published_at", sa.DateTime(timezone=True)),
        sa.Column("result", sa.JSON()),
        sa.Column("failure_reason", sa.Text()),
        sa.UniqueConstraint("created_by", "create_key", name="uq_plan_draft_create_key"),
        sa.CheckConstraint(
            "status IN ('DRAFT','REVIEWED','PUBLISHED','DISCARDED','FAILED')",
            name="ck_plan_draft_status",
        ),
        sa.CheckConstraint("revision >= 1", name="ck_plan_draft_revision"),
        *timestamps(),
    )
    op.create_index("ix_plan_drafts_created_by", "plan_drafts", ["created_by"])
    op.create_index("ix_plan_drafts_status", "plan_drafts", ["status"])


def downgrade() -> None:
    op.drop_index("ix_plan_drafts_status", table_name="plan_drafts")
    op.drop_index("ix_plan_drafts_created_by", table_name="plan_drafts")
    op.drop_table("plan_drafts")
    op.drop_column("agent_messages", "cards")

    op.drop_index("ix_plan_notification_events_status", table_name="plan_notification_events")
    op.drop_index("ix_plan_notification_events_recipient_id", table_name="plan_notification_events")
    # Only one channel row per recipient can survive the narrower key.
    op.execute(
        "DELETE FROM plan_notification_events WHERE id NOT IN ("
        "SELECT MIN(id) FROM plan_notification_events GROUP BY proposal_id, recipient_id)"
    )
    with op.batch_alter_table("plan_notification_events") as batch:
        batch.drop_constraint("ck_plan_event_status", type_="check")
        batch.drop_constraint("uq_plan_event_recipient", type_="unique")
        batch.create_unique_constraint("uq_plan_event_recipient", ["proposal_id", "recipient_id"])
        batch.alter_column("status", server_default="PENDING")
        batch.drop_column("acknowledged_at")
        batch.drop_column("delivery_uncertain")
        batch.drop_column("sent_at")
        batch.drop_column("next_attempt_at")
        batch.drop_column("channel")
        batch.drop_column("event_type")
    # Folding delivery state back into PENDING loses which rows were already sent.
    op.execute(
        "UPDATE plan_notification_events SET status = 'PENDING' WHERE status IN ('QUEUED','FAILED')"
    )
