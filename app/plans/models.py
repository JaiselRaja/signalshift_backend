"""Plan model — subscription/pass tiers shown on the public Plans page."""

from __future__ import annotations

import uuid
from datetime import time

from sqlalchemy import Boolean, ForeignKey, Integer, Numeric, String, Text, Time, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base, TimestampMixin, UUIDMixin


class Plan(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "plans"
    __table_args__ = (UniqueConstraint("tenant_id", "code", name="uq_plans_tenant_code"),)

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True
    )

    # Stable identifier for code paths that need to find a specific plan
    # (e.g. the homepage preview pulls "starter" + "pro" + "daily"). Lowercase slug.
    code: Mapped[str] = mapped_column(String(50), nullable=False)

    name: Mapped[str] = mapped_column(String(100), nullable=False)
    tagline: Mapped[str | None] = mapped_column(Text)

    # "monthly" or "daily" — drives card layout on the frontend
    plan_type: Mapped[str] = mapped_column(String(20), nullable=False, default="monthly")

    price: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    price_unit: Mapped[str] = mapped_column(String(20), nullable=False, default="/month")

    # Monthly-only fields (nullable for daily passes)
    hours_per_month: Mapped[int | None] = mapped_column(Integer)
    discount_pct: Mapped[int | None] = mapped_column(Integer)
    advance_window_days: Mapped[int | None] = mapped_column(Integer)

    # Optional slot window — recurring slot must fall within these hours.
    # NULL = full operating hours of the turf.
    slot_window_start: Mapped[time | None] = mapped_column(Time)
    slot_window_end: Mapped[time | None] = mapped_column(Time)

    # Bullet list shown on the card
    perks: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)

    # Visual flags
    featured: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    display_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
