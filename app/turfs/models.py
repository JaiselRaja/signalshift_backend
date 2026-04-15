"""Turf & TurfSlotRule SQLAlchemy models."""

from __future__ import annotations

import uuid
from datetime import date, time

from sqlalchemy import (
    Boolean, Date, ForeignKey, Integer, Numeric,
    SmallInteger, String, Text, Time, UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base, TimestampMixin, UUIDMixin


class Turf(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "turfs"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), nullable=False)
    sport_types: Mapped[list[str]] = mapped_column(ARRAY(String(50)), default=list)
    address: Mapped[str | None] = mapped_column(Text)
    city: Mapped[str | None] = mapped_column(String(100))
    lat: Mapped[float | None] = mapped_column(Numeric(10, 7))
    lng: Mapped[float | None] = mapped_column(Numeric(10, 7))
    amenities: Mapped[dict] = mapped_column(JSONB, nullable=False, default=list)
    operating_hours: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    metadata_: Mapped[dict] = mapped_column("metadata", JSONB, nullable=False, default=dict)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    # Relationships
    tenant: Mapped["Tenant"] = relationship("Tenant", back_populates="turfs")
    slot_rules: Mapped[list["TurfSlotRule"]] = relationship(
        back_populates="turf", lazy="selectin", cascade="all, delete-orphan"
    )
    bookings: Mapped[list["Booking"]] = relationship("Booking", back_populates="turf")
    pricing_rules: Mapped[list["PricingRule"]] = relationship(
        "PricingRule", back_populates="turf", cascade="all, delete-orphan"
    )
    cancellation_policies: Mapped[list["CancellationPolicy"]] = relationship(
        "CancellationPolicy", back_populates="turf", cascade="all, delete-orphan"
    )

    __table_args__ = (
        UniqueConstraint("tenant_id", "slug", name="uq_turfs_tenant_slug"),
    )


class TurfSlotRule(Base, UUIDMixin, TimestampMixin):
    """
    Recurring availability rule that generates virtual slots at query time.
    NOT an individual bookable slot — it's a TEMPLATE.
    """
    __tablename__ = "turf_slot_rules"

    turf_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("turfs.id", ondelete="CASCADE"), nullable=False
    )
    day_of_week: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    start_time: Mapped[time] = mapped_column(Time, nullable=False)
    end_time: Mapped[time] = mapped_column(Time, nullable=False)
    duration_mins: Mapped[int] = mapped_column(Integer, nullable=False, default=60)
    slot_type: Mapped[str] = mapped_column(String(30), nullable=False, default="regular")
    base_price: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="INR")
    max_capacity: Mapped[int] = mapped_column(Integer, default=1)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    valid_from: Mapped[date | None] = mapped_column(Date)
    valid_until: Mapped[date | None] = mapped_column(Date)
    metadata_: Mapped[dict] = mapped_column("metadata", JSONB, nullable=False, default=dict)

    # Relationships
    turf: Mapped[Turf] = relationship(back_populates="slot_rules")


class SlotOverride(Base, UUIDMixin):
    """Date-specific override: holidays, blocked dates, price changes."""
    __tablename__ = "slot_overrides"

    turf_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("turfs.id", ondelete="CASCADE"), nullable=False
    )
    override_date: Mapped[date] = mapped_column(Date, nullable=False)
    start_time: Mapped[time | None] = mapped_column(Time)
    end_time: Mapped[time | None] = mapped_column(Time)
    override_type: Mapped[str] = mapped_column(String(30), nullable=False)
    override_price: Mapped[float | None] = mapped_column(Numeric(10, 2))
    reason: Mapped[str | None] = mapped_column(Text)
    metadata_: Mapped[dict] = mapped_column("metadata", JSONB, nullable=False, default=dict)
    created_at: Mapped[date] = mapped_column(server_default="now()")

    __table_args__ = (
        UniqueConstraint("turf_id", "override_date", "start_time", name="uq_override_turf_date"),
    )
