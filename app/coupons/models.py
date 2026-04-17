"""Coupon / Promo code models."""

from __future__ import annotations

from sqlalchemy import (
    Boolean, Column, Date, ForeignKey, Integer, Numeric, String, Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import relationship

from app.core.database import Base, TimestampMixin, UUIDMixin


class Coupon(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "coupons"

    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False)
    code = Column(String(50), nullable=False)
    description = Column(Text, default="")

    # Discount configuration
    discount_type = Column(String(20), nullable=False, default="percentage")  # percentage | flat
    discount_value = Column(Numeric(10, 2), nullable=False)
    max_discount = Column(Numeric(10, 2), nullable=True)  # cap for percentage discounts
    min_booking_amount = Column(Numeric(10, 2), default=0)

    # Usage limits
    usage_limit = Column(Integer, nullable=True)  # null = unlimited
    used_count = Column(Integer, default=0)
    per_user_limit = Column(Integer, default=1)

    # Validity
    valid_from = Column(Date, nullable=False)
    valid_until = Column(Date, nullable=False)

    # Scope
    applicable_sports = Column(ARRAY(String), default=list)  # empty = all sports
    applicable_turf_ids = Column(ARRAY(UUID(as_uuid=True)), default=list)  # empty = all turfs
    applicable_booking_types = Column(ARRAY(String), default=list)  # empty = all types

    is_active = Column(Boolean, default=True)
    metadata_ = Column("metadata", JSONB, default=dict)

    # Relationships
    tenant = relationship("Tenant")

    __table_args__ = (
        UniqueConstraint("tenant_id", "code", name="uq_coupon_tenant_code"),
    )
