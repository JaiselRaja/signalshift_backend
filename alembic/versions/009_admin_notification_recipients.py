"""admin_notification_recipients

Revision ID: 009_admin_recipients
Revises: 008_booking_sub_id
Create Date: 2026-06-07
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "009_admin_recipients"
down_revision = "008_booking_sub_id"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "admin_notification_recipients",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("label", sa.String(length=120), nullable=True),
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "email",
            name="uq_admin_recipient_tenant_email",
        ),
    )
    op.create_index(
        "ix_admin_notification_recipients_tenant_id",
        "admin_notification_recipients",
        ["tenant_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_admin_notification_recipients_tenant_id",
        table_name="admin_notification_recipients",
    )
    op.drop_table("admin_notification_recipients")
