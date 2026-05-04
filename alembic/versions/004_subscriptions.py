"""Add subscriptions table for monthly recurring slot plans.

Revision ID: 004_subscriptions
Revises: 003_plans
Create Date: 2026-05-03
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "004_subscriptions"
down_revision = "003_plans"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "subscriptions",
        sa.Column(
            "id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "tenant_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", name="fk_subscriptions_tenant_id_tenants"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "user_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", name="fk_subscriptions_user_id_users"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "plan_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("plans.id", name="fk_subscriptions_plan_id_plans"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "turf_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("turfs.id", name="fk_subscriptions_turf_id_turfs"),
            nullable=False,
            index=True,
        ),
        sa.Column("day_of_week", sa.Integer(), nullable=False),
        sa.Column("start_time", sa.Time(), nullable=False),
        sa.Column("end_time", sa.Time(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="pending"),
        sa.Column("starts_on", sa.Date(), nullable=True),
        sa.Column("expires_on", sa.Date(), nullable=True),
        sa.Column(
            "payment_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey(
                "payment_transactions.id",
                name="fk_subscriptions_payment_id_payment_transactions",
            ),
            nullable=True,
            index=True,
        ),
        sa.Column("cancelled_at", sa.DateTime(), nullable=True),
        sa.Column("cancel_reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index(
        "ix_subscriptions_turf_dow_status",
        "subscriptions",
        ["turf_id", "day_of_week", "status"],
    )


def downgrade() -> None:
    op.drop_index("ix_subscriptions_turf_dow_status", table_name="subscriptions")
    op.drop_table("subscriptions")
