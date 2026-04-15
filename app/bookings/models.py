"""Booking & CancellationPolicy SQLAlchemy models."""

from __future__ import annotations

import uuid
from datetime import date, datetime, time

from sqlalchemy import (
    Boolean, Date, ForeignKey, Integer, Numeric,
    String, Text, Time, Index,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base, TimestampMixin, UUIDMixin


class Booking(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "bookings"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False
    )
    turf_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("turfs.id"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    team_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("teams.id")
    )

    booking_date: Mapped[date] = mapped_column(Date, nullable=False)
    start_time: Mapped[time] = mapped_column(Time, nullable=False)
    end_time: Mapped[time] = mapped_column(Time, nullable=False)
    duration_mins: Mapped[int] = mapped_column(Integer, nullable=False)

    status: Mapped[str] = mapped_column(String(30), nullable=False, default="pending")
    booking_type: Mapped[str] = mapped_column(String(30), nullable=False, default="regular")

    # Pricing snapshot (immutable after confirmation)
    base_price: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    discount_amount: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False, default=0)
    tax_amount: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False, default=0)
    final_price: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="INR")

    cancelled_at: Mapped[datetime | None] = mapped_column()
    cancel_reason: Mapped[str | None] = mapped_column(Text)
    refund_amount: Mapped[float | None] = mapped_column(Numeric(10, 2))

    # Optimistic locking
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    notes: Mapped[str | None] = mapped_column(Text)
    metadata_: Mapped[dict] = mapped_column("metadata", JSONB, nullable=False, default=dict)

    # Relationships
    turf: Mapped["Turf"] = relationship("Turf", back_populates="bookings")
    user: Mapped["User"] = relationship("User")
    team: Mapped["Team | None"] = relationship("Team")
    payments: Mapped[list["PaymentTransaction"]] = relationship(
        "PaymentTransaction", back_populates="booking"
    )

    __table_args__ = (
        Index(
            "idx_bookings_conflict",
            "turf_id", "booking_date", "start_time", "end_time",
            postgresql_where=(
                "status IN ('pending', 'confirmed')"
            ),
        ),
        Index("idx_bookings_user", "user_id", "booking_date"),
        Index("idx_bookings_turf_date", "turf_id", "booking_date", "status"),
    )


class PricingRule(Base, UUIDMixin):
    """Configurable pricing rule with JSONB conditions."""
    __tablename__ = "pricing_rules"

    turf_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("turfs.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    rule_type: Mapped[str] = mapped_column(String(50), nullable=False)
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    conditions: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    adjustment_type: Mapped[str] = mapped_column(String(20), nullable=False)
    adjustment_value: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    stackable: Mapped[bool] = mapped_column(Boolean, default=False)
    valid_from: Mapped[date | None] = mapped_column(Date)
    valid_until: Mapped[date | None] = mapped_column(Date)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(server_default="now()")

    turf: Mapped["Turf"] = relationship("Turf", back_populates="pricing_rules")


class CancellationPolicy(Base, UUIDMixin):
    """Per-turf configurable refund tiers stored as JSONB."""
    __tablename__ = "cancellation_policies"

    turf_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("turfs.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    rules: Mapped[dict] = mapped_column(JSONB, nullable=False)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(server_default="now()")

    turf: Mapped["Turf"] = relationship("Turf", back_populates="cancellation_policies")
