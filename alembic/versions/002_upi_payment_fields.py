"""Add UPI manual-verification fields to payment_transactions.

Revision ID: 002_upi_fields
Revises: 001_initial
Create Date: 2026-04-19
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "002_upi_fields"
down_revision = "001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("payment_transactions", sa.Column("utr", sa.String(length=32), nullable=True))
    op.add_column(
        "payment_transactions",
        sa.Column("verified_by", sa.dialects.postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "payment_transactions",
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column("payment_transactions", sa.Column("reject_reason", sa.Text(), nullable=True))
    op.create_foreign_key(
        "fk_payment_transactions_verified_by_users",
        "payment_transactions",
        "users",
        ["verified_by"],
        ["id"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_payment_transactions_verified_by_users",
        "payment_transactions",
        type_="foreignkey",
    )
    op.drop_column("payment_transactions", "reject_reason")
    op.drop_column("payment_transactions", "verified_at")
    op.drop_column("payment_transactions", "verified_by")
    op.drop_column("payment_transactions", "utr")
