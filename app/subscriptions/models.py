"""Subscription models — recurring weekly slots tied to a Plan."""

from __future__ import annotations

import uuid
from datetime import date, datetime, time

from sqlalchemy import Date, DateTime, ForeignKey, Integer, String, Text, Time, text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base, TimestampMixin, UUIDMixin


class Subscription(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "subscriptions"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True
    )
    plan_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("plans.id"), nullable=False, index=True
    )
    turf_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("turfs.id"), nullable=False, index=True
    )

    # Lifecycle
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="pending"
    )  # pending | active | cancelled | expired
    starts_on: Mapped[date | None] = mapped_column(Date)
    expires_on: Mapped[date | None] = mapped_column(Date)

    # Payment tying — points to the UPI PaymentTransaction the user submitted.
    payment_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("payment_transactions.id"), index=True
    )

    cancelled_at: Mapped[datetime | None] = mapped_column()
    cancel_reason: Mapped[str | None] = mapped_column(Text)

    # Relationships
    plan: Mapped["Plan"] = relationship("Plan", lazy="joined")  # noqa: F821
    user: Mapped["User"] = relationship("User", lazy="joined")  # noqa: F821
    turf: Mapped["Turf"] = relationship("Turf", lazy="joined")  # noqa: F821
    payment: Mapped["PaymentTransaction | None"] = relationship(  # noqa: F821
        "PaymentTransaction", lazy="joined"
    )
    slots: Mapped[list["SubscriptionSlot"]] = relationship(
        "SubscriptionSlot",
        back_populates="subscription",
        cascade="all, delete-orphan",
        lazy="selectin",
    )


class SubscriptionSlot(Base, UUIDMixin):
    """A single recurring weekly slot belonging to a Subscription."""

    __tablename__ = "subscription_slots"

    subscription_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("subscriptions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Monday=0 … Sunday=6 (Python's datetime.weekday() convention)
    day_of_week: Mapped[int] = mapped_column(Integer, nullable=False)
    start_time: Mapped[time] = mapped_column(Time, nullable=False)
    end_time: Mapped[time] = mapped_column(Time, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=text("now()"), nullable=False,
    )

    subscription: Mapped[Subscription] = relationship(
        "Subscription", back_populates="slots"
    )
