"""Initial schema — all core tables.

Revision ID: 001_initial
Revises:
Create Date: 2026-04-16
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ─── Tenants ───
    op.create_table(
        "tenants",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("slug", sa.String(100), nullable=False, unique=True),
        sa.Column("config", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb")),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id"),
    )

    # ─── Users ───
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("phone", sa.String(20), nullable=True),
        sa.Column("full_name", sa.String(255), nullable=True),
        sa.Column("avatar_url", sa.Text(), nullable=True),
        sa.Column("role", sa.String(50), server_default="player", nullable=False),
        sa.Column("preferences", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb")),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true")),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_users_tenant_email", "users", ["tenant_id", "email"], unique=True)

    # ─── Turfs ───
    op.create_table(
        "turfs",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("slug", sa.String(100), nullable=False),
        sa.Column("sport_types", postgresql.ARRAY(sa.String()), server_default=sa.text("ARRAY[]::varchar[]")),
        sa.Column("address", sa.Text(), nullable=True),
        sa.Column("city", sa.String(100), nullable=True),
        sa.Column("lat", sa.Numeric(10, 7), nullable=True),
        sa.Column("lng", sa.Numeric(10, 7), nullable=True),
        sa.Column("amenities", postgresql.JSONB(), server_default=sa.text("'[]'::jsonb")),
        sa.Column("operating_hours", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb")),
        sa.Column("metadata", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb")),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "slug", name="uq_turf_tenant_slug"),
    )

    # ─── Turf Slot Rules ───
    op.create_table(
        "turf_slot_rules",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("turf_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("turfs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("day_of_week", sa.Integer(), nullable=False),
        sa.Column("start_time", sa.Time(), nullable=False),
        sa.Column("end_time", sa.Time(), nullable=False),
        sa.Column("duration_mins", sa.Integer(), server_default="60"),
        sa.Column("slot_type", sa.String(20), server_default="regular"),
        sa.Column("base_price", sa.Numeric(10, 2), nullable=False),
        sa.Column("currency", sa.String(3), server_default="INR"),
        sa.Column("max_capacity", sa.Integer(), server_default="1"),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true")),
        sa.Column("valid_from", sa.Date(), nullable=True),
        sa.Column("valid_until", sa.Date(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id"),
    )

    # ─── Slot Overrides ───
    op.create_table(
        "slot_overrides",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("turf_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("turfs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("override_date", sa.Date(), nullable=False),
        sa.Column("start_time", sa.Time(), nullable=True),
        sa.Column("end_time", sa.Time(), nullable=True),
        sa.Column("override_type", sa.String(20), nullable=False),
        sa.Column("override_price", sa.Numeric(10, 2), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("turf_id", "override_date", "start_time", name="uq_override_turf_date_start"),
    )

    # ─── Bookings ───
    op.create_table(
        "bookings",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("turf_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("turfs.id"), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("team_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("booking_date", sa.Date(), nullable=False),
        sa.Column("start_time", sa.Time(), nullable=False),
        sa.Column("end_time", sa.Time(), nullable=False),
        sa.Column("duration_mins", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(20), server_default="pending", nullable=False),
        sa.Column("booking_type", sa.String(20), server_default="regular"),
        sa.Column("base_price", sa.Numeric(10, 2), server_default="0"),
        sa.Column("discount_amount", sa.Numeric(10, 2), server_default="0"),
        sa.Column("tax_amount", sa.Numeric(10, 2), server_default="0"),
        sa.Column("final_price", sa.Numeric(10, 2), server_default="0"),
        sa.Column("currency", sa.String(3), server_default="INR"),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancel_reason", sa.Text(), nullable=True),
        sa.Column("refund_amount", sa.Numeric(10, 2), nullable=True),
        sa.Column("version", sa.Integer(), server_default="1"),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("metadata", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_bookings_conflict", "bookings", ["turf_id", "booking_date", "start_time", "end_time", "status"])
    op.create_index("ix_bookings_user", "bookings", ["user_id", "booking_date"])
    op.create_index("ix_bookings_turf_date", "bookings", ["turf_id", "booking_date"])

    # ─── Pricing Rules ───
    op.create_table(
        "pricing_rules",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("turf_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("turfs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("rule_type", sa.String(50), nullable=False),
        sa.Column("priority", sa.Integer(), server_default="10"),
        sa.Column("conditions", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb")),
        sa.Column("adjustment_type", sa.String(20), nullable=False),
        sa.Column("adjustment_value", sa.Numeric(10, 2), nullable=False),
        sa.Column("stackable", sa.Boolean(), server_default=sa.text("false")),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true")),
        sa.Column("valid_from", sa.Date(), nullable=True),
        sa.Column("valid_until", sa.Date(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id"),
    )

    # ─── Cancellation Policies ───
    op.create_table(
        "cancellation_policies",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("turf_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("turfs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("rules", postgresql.JSONB(), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true")),
        sa.Column("is_default", sa.Boolean(), server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id"),
    )

    # ─── Teams ───
    op.create_table(
        "teams",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("slug", sa.String(100), nullable=False),
        sa.Column("sport_type", sa.String(50), nullable=False),
        sa.Column("logo_url", sa.Text(), nullable=True),
        sa.Column("captain_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("metadata", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb")),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "slug", name="uq_team_tenant_slug"),
    )

    # ─── Team Memberships ───
    op.create_table(
        "team_memberships",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("team_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("teams.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("role", sa.String(20), server_default="player"),
        sa.Column("joined_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("team_id", "user_id", name="uq_membership_team_user"),
    )

    # ─── Tournaments ───
    op.create_table(
        "tournaments",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("turf_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("turfs.id"), nullable=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("slug", sa.String(100), nullable=False),
        sa.Column("sport_type", sa.String(50), nullable=False),
        sa.Column("format", sa.String(20), nullable=False),
        sa.Column("status", sa.String(30), server_default="draft"),
        sa.Column("registration_starts", sa.DateTime(timezone=True), nullable=True),
        sa.Column("registration_ends", sa.DateTime(timezone=True), nullable=True),
        sa.Column("tournament_starts", sa.DateTime(timezone=True), nullable=False),
        sa.Column("tournament_ends", sa.DateTime(timezone=True), nullable=True),
        sa.Column("max_teams", sa.Integer(), nullable=True),
        sa.Column("min_teams", sa.Integer(), server_default="2"),
        sa.Column("entry_fee", sa.Numeric(10, 2), nullable=True),
        sa.Column("prize_pool", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb")),
        sa.Column("config", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "slug", name="uq_tournament_tenant_slug"),
    )

    # ─── Tournament Rule Sets ───
    op.create_table(
        "tournament_rule_sets",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tournament_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tournaments.id", ondelete="CASCADE"), nullable=False),
        sa.Column("rule_category", sa.String(50), nullable=False),
        sa.Column("rule_name", sa.String(100), nullable=False),
        sa.Column("priority", sa.Integer(), server_default="10"),
        sa.Column("rule_definition", postgresql.JSONB(), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tournament_id", "rule_category", "rule_name", name="uq_ruleset_tournament_cat_name"),
    )

    # ─── Tournament Registrations ───
    op.create_table(
        "tournament_registrations",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tournament_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tournaments.id", ondelete="CASCADE"), nullable=False),
        sa.Column("team_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("teams.id"), nullable=False),
        sa.Column("registered_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("status", sa.String(30), server_default="pending"),
        sa.Column("payment_status", sa.String(20), server_default="pending"),
        sa.Column("seed", sa.Integer(), nullable=True),
        sa.Column("group_name", sa.String(50), nullable=True),
        sa.Column("metadata", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tournament_id", "team_id", name="uq_registration_tournament_team"),
    )

    # ─── Tournament Matches ───
    op.create_table(
        "tournament_matches",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tournament_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tournaments.id", ondelete="CASCADE"), nullable=False),
        sa.Column("booking_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("bookings.id"), nullable=True),
        sa.Column("round_name", sa.String(50), nullable=False),
        sa.Column("group_name", sa.String(50), nullable=True),
        sa.Column("match_number", sa.Integer(), nullable=True),
        sa.Column("home_team_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("teams.id"), nullable=True),
        sa.Column("away_team_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("teams.id"), nullable=True),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(20), server_default="scheduled"),
        sa.Column("home_score", sa.Integer(), nullable=True),
        sa.Column("away_score", sa.Integer(), nullable=True),
        sa.Column("winner_team_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("is_draw", sa.Boolean(), server_default=sa.text("false")),
        sa.Column("extra_data", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id"),
    )

    # ─── Payment Transactions ───
    op.create_table(
        "payment_transactions",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("booking_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("bookings.id"), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("gateway", sa.String(50), server_default="razorpay"),
        sa.Column("gateway_txn_id", sa.String(255), nullable=True),
        sa.Column("gateway_order_id", sa.String(255), nullable=True),
        sa.Column("amount", sa.Numeric(10, 2), nullable=False),
        sa.Column("currency", sa.String(3), server_default="INR"),
        sa.Column("status", sa.String(30), server_default="initiated"),
        sa.Column("payment_method", sa.String(50), nullable=True),
        sa.Column("gateway_response", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb")),
        sa.Column("refund_id", sa.String(255), nullable=True),
        sa.Column("refund_amount", sa.Numeric(10, 2), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id"),
    )

    # ─── Coupons ───
    op.create_table(
        "coupons",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("code", sa.String(50), nullable=False),
        sa.Column("description", sa.Text(), server_default=""),
        sa.Column("discount_type", sa.String(20), server_default="percentage", nullable=False),
        sa.Column("discount_value", sa.Numeric(10, 2), nullable=False),
        sa.Column("max_discount", sa.Numeric(10, 2), nullable=True),
        sa.Column("min_booking_amount", sa.Numeric(10, 2), server_default="0"),
        sa.Column("usage_limit", sa.Integer(), nullable=True),
        sa.Column("used_count", sa.Integer(), server_default="0"),
        sa.Column("per_user_limit", sa.Integer(), server_default="1"),
        sa.Column("valid_from", sa.Date(), nullable=False),
        sa.Column("valid_until", sa.Date(), nullable=False),
        sa.Column("applicable_sports", postgresql.ARRAY(sa.String()), server_default=sa.text("ARRAY[]::varchar[]")),
        sa.Column("applicable_turf_ids", postgresql.ARRAY(postgresql.UUID(as_uuid=True)), server_default=sa.text("ARRAY[]::uuid[]")),
        sa.Column("applicable_booking_types", postgresql.ARRAY(sa.String()), server_default=sa.text("ARRAY[]::varchar[]")),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true")),
        sa.Column("metadata", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "code", name="uq_coupon_tenant_code"),
    )


def downgrade() -> None:
    op.drop_table("coupons")
    op.drop_table("payment_transactions")
    op.drop_table("tournament_matches")
    op.drop_table("tournament_registrations")
    op.drop_table("tournament_rule_sets")
    op.drop_table("tournaments")
    op.drop_table("team_memberships")
    op.drop_table("teams")
    op.drop_table("cancellation_policies")
    op.drop_table("pricing_rules")
    op.drop_index("ix_bookings_turf_date", table_name="bookings")
    op.drop_index("ix_bookings_user", table_name="bookings")
    op.drop_index("ix_bookings_conflict", table_name="bookings")
    op.drop_table("bookings")
    op.drop_table("slot_overrides")
    op.drop_table("turf_slot_rules")
    op.drop_table("turfs")
    op.drop_index("ix_users_tenant_email", table_name="users")
    op.drop_table("users")
    op.drop_table("tenants")
