"""Add plans table + seed default Daily / Starter / Pro plans per tenant.

Revision ID: 003_plans
Revises: 002_upi_fields
Create Date: 2026-05-01
"""

from __future__ import annotations

import json
import uuid

import sqlalchemy as sa
from alembic import op

revision = "003_plans"
down_revision = "002_upi_fields"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "plans",
        sa.Column(
            "id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "tenant_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", name="fk_plans_tenant_id_tenants"),
            nullable=False,
            index=True,
        ),
        sa.Column("code", sa.String(length=50), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("tagline", sa.Text(), nullable=True),
        sa.Column("plan_type", sa.String(length=20), nullable=False, server_default="monthly"),
        sa.Column("price", sa.Numeric(10, 2), nullable=False),
        sa.Column("price_unit", sa.String(length=20), nullable=False, server_default="/month"),
        sa.Column("hours_per_month", sa.Integer(), nullable=True),
        sa.Column("discount_pct", sa.Integer(), nullable=True),
        sa.Column("advance_window_days", sa.Integer(), nullable=True),
        sa.Column(
            "perks",
            sa.dialects.postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("featured", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("display_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("tenant_id", "code", name="uq_plans_tenant_code"),
    )

    # Seed default plans for every existing tenant so the UI has data.
    bind = op.get_bind()
    tenants = bind.execute(sa.text("SELECT id FROM tenants")).fetchall()
    if not tenants:
        return

    defaults = [
        {
            "code": "daily",
            "name": "Daily Pass",
            "tagline": "Pay-per-slot. No commitment.",
            "plan_type": "daily",
            "price": 1200,
            "price_unit": "/hour",
            "hours_per_month": None,
            "discount_pct": None,
            "advance_window_days": 1,
            "perks": [
                "Pay only for what you play",
                "Real-time slot availability",
                "Instant booking confirmation",
                "No subscription, no lock-in",
                "Standard equipment rental",
            ],
            "featured": False,
            "display_order": 0,
        },
        {
            "code": "starter",
            "name": "Starter",
            "tagline": "Perfect for casual weekend players",
            "plan_type": "monthly",
            "price": 2999,
            "price_unit": "/month",
            "hours_per_month": 4,
            "discount_pct": 5,
            "advance_window_days": 3,
            "perks": [
                "4 hours of fixed recurring turf time",
                "5% off any extra bookings",
                "Book up to 3 days in advance",
                "Free cancellation up to 24h before",
                "Standard equipment rental",
            ],
            "featured": False,
            "display_order": 10,
        },
        {
            "code": "pro",
            "name": "Pro",
            "tagline": "For serious teams who play every week",
            "plan_type": "monthly",
            "price": 4999,
            "price_unit": "/month",
            "hours_per_month": 8,
            "discount_pct": 15,
            "advance_window_days": 7,
            "perks": [
                "8 hours of fixed recurring turf time",
                "15% off any extra bookings",
                "Book up to 7 days in advance",
                "Free cancellation up to 12h before",
                "Free equipment rental + bibs",
                "Priority support on WhatsApp",
            ],
            "featured": True,
            "display_order": 20,
        },
    ]

    for (tenant_id,) in tenants:
        for p in defaults:
            bind.execute(
                sa.text(
                    """
                    INSERT INTO plans (
                      id, tenant_id, code, name, tagline, plan_type,
                      price, price_unit, hours_per_month, discount_pct,
                      advance_window_days, perks, featured, display_order, is_active
                    ) VALUES (
                      :id, :tenant_id, :code, :name, :tagline, :plan_type,
                      :price, :price_unit, :hours_per_month, :discount_pct,
                      :advance_window_days, CAST(:perks AS jsonb), :featured, :display_order, true
                    )
                    """
                ),
                {
                    "id": str(uuid.uuid4()),
                    "tenant_id": tenant_id,
                    "perks": json.dumps(p["perks"]),
                    **{k: v for k, v in p.items() if k != "perks"},
                },
            )


def downgrade() -> None:
    op.drop_table("plans")
