"""S7: widen the plan-change outbox into a general notification outbox.

The table only ever carried applied change proposals. Risk events now queue
messages through the same reliable path, so the source column becomes one of
two and the recipient uniqueness key moves onto an explicit dedupe key.

Existing rows keep their content and get the key they would have been written
with today (``PLAN_CHANGE:<proposal_id>``), so nothing is resent or lost.

Revision ID: 20260908_2100_d0e1f2a3b4c5
Revises: 20260908_1800_c9d0e1f2a3b4
"""

import sqlalchemy as sa
from alembic import op

revision = "20260908_2100_d0e1f2a3b4c5"
down_revision = "20260908_1800_c9d0e1f2a3b4"
branch_labels = None
depends_on = None

OLD = "plan_notification_events"
NEW = "notification_events"


def upgrade() -> None:
    op.execute(f"UPDATE {OLD} SET status = 'QUEUED' WHERE status IS NULL")
    op.rename_table(OLD, NEW)

    with op.batch_alter_table(NEW) as batch:
        batch.add_column(sa.Column("dedupe_key", sa.String(160)))
        batch.add_column(
            sa.Column(
                "risk_event_id",
                sa.Integer(),
                sa.ForeignKey("risk_events.id", ondelete="CASCADE", name="fk_notification_risk"),
            )
        )
    op.execute(f"UPDATE {NEW} SET dedupe_key = 'PLAN_CHANGE:' || proposal_id")

    with op.batch_alter_table(NEW) as batch:
        batch.alter_column("dedupe_key", existing_type=sa.String(160), nullable=False)
        batch.alter_column("proposal_id", existing_type=sa.String(36), nullable=True)
        batch.drop_constraint("uq_plan_event_recipient", type_="unique")
        batch.drop_constraint("ck_plan_event_status", type_="check")
        batch.create_unique_constraint(
            "uq_notification_recipient", ["dedupe_key", "recipient_id", "channel"]
        )
        batch.create_check_constraint(
            "ck_notification_status", "status IN ('QUEUED','SENT','FAILED','ACKNOWLEDGED')"
        )
        batch.create_check_constraint(
            "ck_notification_one_source", "(proposal_id IS NULL) <> (risk_event_id IS NULL)"
        )

    for old_name, columns in (
        ("ix_plan_notification_events_proposal_id", ["proposal_id"]),
        ("ix_plan_notification_events_project_id", ["project_id"]),
        ("ix_plan_notification_events_recipient_id", ["recipient_id"]),
        ("ix_plan_notification_events_status", ["status"]),
    ):
        _drop_index(old_name, NEW)
        op.create_index(f"ix_{NEW}_{columns[0]}", NEW, columns)
    op.create_index(f"ix_{NEW}_dedupe_key", NEW, ["dedupe_key"])
    op.create_index(f"ix_{NEW}_risk_event_id", NEW, ["risk_event_id"])

    # Keep the audit trail queryable under the name the code now uses.
    op.execute(
        "UPDATE audit_logs SET resource_type = 'notification_event' "
        "WHERE resource_type = 'plan_notification_event'"
    )


def downgrade() -> None:
    op.execute(
        "UPDATE audit_logs SET resource_type = 'plan_notification_event' "
        "WHERE resource_type = 'notification_event'"
    )
    # Risk notices have no home in the narrower shape.
    op.execute(f"DELETE FROM {NEW} WHERE risk_event_id IS NOT NULL")
    for name in ("dedupe_key", "risk_event_id", "proposal_id", "project_id", "recipient_id"):
        _drop_index(f"ix_{NEW}_{name}", NEW)
    _drop_index(f"ix_{NEW}_status", NEW)

    with op.batch_alter_table(NEW) as batch:
        batch.drop_constraint("ck_notification_one_source", type_="check")
        batch.drop_constraint("ck_notification_status", type_="check")
        batch.drop_constraint("uq_notification_recipient", type_="unique")
        batch.alter_column("proposal_id", existing_type=sa.String(36), nullable=False)
        batch.drop_column("risk_event_id")
        batch.drop_column("dedupe_key")
        batch.create_unique_constraint(
            "uq_plan_event_recipient", ["proposal_id", "recipient_id", "channel"]
        )
        batch.create_check_constraint(
            "ck_plan_event_status", "status IN ('QUEUED','SENT','FAILED','ACKNOWLEDGED')"
        )

    op.rename_table(NEW, OLD)
    op.create_index(f"ix_{OLD}_proposal_id", OLD, ["proposal_id"])
    op.create_index(f"ix_{OLD}_project_id", OLD, ["project_id"])
    op.create_index(f"ix_{OLD}_recipient_id", OLD, ["recipient_id"])
    op.create_index(f"ix_{OLD}_status", OLD, ["status"])


def _drop_index(name: str, table: str) -> None:
    """Index names differ between databases created by migration and by metadata."""
    inspector = sa.inspect(op.get_bind())
    if any(index["name"] == name for index in inspector.get_indexes(table)):
        op.drop_index(name, table_name=table)
