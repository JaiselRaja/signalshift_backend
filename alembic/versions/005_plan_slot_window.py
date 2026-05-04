"""Add slot_window_start / slot_window_end to plans.

Revision ID: 005_plan_slot_window
Revises: 004_subscriptions
Create Date: 2026-05-03
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "005_plan_slot_window"
down_revision = "004_subscriptions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "plans",
        sa.Column("slot_window_start", sa.Time(), nullable=True),
    )
    op.add_column(
        "plans",
        sa.Column("slot_window_end", sa.Time(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("plans", "slot_window_end")
    op.drop_column("plans", "slot_window_start")
