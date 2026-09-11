"""Preserve planning attempts, coverage and required user input."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20260911_1000_f8a9b0c1d2e3"
down_revision = "20260910_1100_e7f8a9b0c1d2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "agent_command_plans",
        sa.Column(
            "planning_details",
            sa.JSON().with_variant(postgresql.JSONB(), "postgresql"),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("agent_command_plans", "planning_details")
