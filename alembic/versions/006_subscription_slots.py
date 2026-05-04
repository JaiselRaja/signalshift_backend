"""Multi-slot subscriptions: split slot fields into a child table.

Revision ID: 006_sub_slots
Revises: 005_plan_slot_window
Create Date: 2026-05-03
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "006_sub_slots"
down_revision = "005_plan_slot_window"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "subscription_slots",
        sa.Column(
            "id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "subscription_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey(
                "subscriptions.id",
                name="fk_subscription_slots_subscription_id",
                ondelete="CASCADE",
            ),
            nullable=False,
            index=True,
        ),
        sa.Column("day_of_week", sa.Integer(), nullable=False),
        sa.Column("start_time", sa.Time(), nullable=False),
        sa.Column("end_time", sa.Time(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index(
        "ix_subscription_slots_dow_time",
        "subscription_slots",
        ["day_of_week", "start_time"],
    )

    # No production data exists yet — drop the legacy single-slot columns.
    op.drop_index("ix_subscriptions_turf_dow_status", table_name="subscriptions")
    op.drop_column("subscriptions", "day_of_week")
    op.drop_column("subscriptions", "start_time")
    op.drop_column("subscriptions", "end_time")


def downgrade() -> None:
    op.add_column("subscriptions", sa.Column("end_time", sa.Time(), nullable=True))
    op.add_column("subscriptions", sa.Column("start_time", sa.Time(), nullable=True))
    op.add_column("subscriptions", sa.Column("day_of_week", sa.Integer(), nullable=True))
    op.create_index(
        "ix_subscriptions_turf_dow_status",
        "subscriptions",
        ["turf_id", "day_of_week", "status"],
    )
    op.drop_index("ix_subscription_slots_dow_time", table_name="subscription_slots")
    op.drop_table("subscription_slots")
