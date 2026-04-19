"""Payment transaction SQLAlchemy model."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base, TimestampMixin, UUIDMixin


class PaymentTransaction(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "payment_transactions"

    booking_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("bookings.id"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    gateway: Mapped[str] = mapped_column(String(50), nullable=False)
    gateway_txn_id: Mapped[str | None] = mapped_column(String(255))
    gateway_order_id: Mapped[str | None] = mapped_column(String(255))
    amount: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="INR")
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="initiated")
    payment_method: Mapped[str | None] = mapped_column(String(50))
    gateway_response: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    refund_id: Mapped[str | None] = mapped_column(String(255))
    refund_amount: Mapped[float | None] = mapped_column(Numeric(10, 2))

    # UPI (manual verification flow)
    utr: Mapped[str | None] = mapped_column(String(32))
    verified_by: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id")
    )
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reject_reason: Mapped[str | None] = mapped_column(Text)

    # Relationships
    booking: Mapped["Booking"] = relationship("Booking", back_populates="payments")
    user: Mapped["User"] = relationship("User", foreign_keys=[user_id])
