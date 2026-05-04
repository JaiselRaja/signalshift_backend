"""Allow payment_transactions.booking_id to be NULL — subscription
payments don't have a single booking, they pay for a recurring subscription.

Revision ID: 007_payment_nullable
Revises: 006_sub_slots
Create Date: 2026-05-03
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "007_payment_nullable"
down_revision = "006_sub_slots"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "payment_transactions",
        "booking_id",
        existing_type=sa.dialects.postgresql.UUID(as_uuid=True),
        nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        "payment_transactions",
        "booking_id",
        existing_type=sa.dialects.postgresql.UUID(as_uuid=True),
        nullable=False,
    )
