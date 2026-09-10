"""Track task risk evidence invalidation after business changes.

Revision ID: 20260907_1700_e5f6a7b8c9d0
Revises: 20260907_1600_d4e5f6a7b8c9
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260907_1700_e5f6a7b8c9d0"
down_revision: str | None = "20260907_1600_d4e5f6a7b8c9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "tasks", sa.Column("risk_context_changed_at", sa.DateTime(timezone=True), nullable=True)
    )
    # Existing merged statuses cannot prove when their underlying evidence was valid.
    op.execute("UPDATE tasks SET risk_context_changed_at = CURRENT_TIMESTAMP")


def downgrade() -> None:
    op.drop_column("tasks", "risk_context_changed_at")
