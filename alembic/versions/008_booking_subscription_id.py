"""Add subscription_id FK to bookings + backfill from notes.

Revision ID: 008_booking_sub_id
Revises: 007_payment_nullable
Create Date: 2026-05-04
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "008_booking_sub_id"
down_revision = "007_payment_nullable"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "bookings",
        sa.Column(
            "subscription_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey(
                "subscriptions.id",
                name="fk_bookings_subscription_id_subscriptions",
                ondelete="SET NULL",
            ),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_bookings_subscription_id",
        "bookings",
        ["subscription_id"],
    )

    # Backfill: extract subscription UUID from existing notes
    # ("Auto-created from subscription <uuid>") for rows that already exist.
    op.execute(
        """
        UPDATE bookings
        SET subscription_id = CAST(
            substring(notes from 'Auto-created from subscription ([0-9a-f-]{36})')
            AS uuid
        )
        WHERE booking_type = 'subscription'
          AND notes ~ 'Auto-created from subscription [0-9a-f-]{36}'
          AND subscription_id IS NULL
        """
    )


def downgrade() -> None:
    op.drop_index("ix_bookings_subscription_id", table_name="bookings")
    op.drop_column("bookings", "subscription_id")
