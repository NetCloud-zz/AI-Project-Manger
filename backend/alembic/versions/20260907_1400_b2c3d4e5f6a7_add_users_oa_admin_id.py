"""add users.oa_admin_id for OA SSO mapping

Revision ID: 20260907_1400_b2c3d4e5f6a7
Revises: 20260907_1230_a1b2c3d4e5f6
Create Date: 2026-09-07 14:00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260907_1400_b2c3d4e5f6a7"
down_revision: str | None = "20260907_1230_a1b2c3d4e5f6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("users", sa.Column("oa_admin_id", sa.Integer(), nullable=True))
    op.create_unique_constraint("uq_users_oa_admin_id", "users", ["oa_admin_id"])


def downgrade() -> None:
    op.drop_constraint("uq_users_oa_admin_id", "users", type_="unique")
    op.drop_column("users", "oa_admin_id")
