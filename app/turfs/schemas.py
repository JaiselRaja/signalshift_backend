"""Turf Pydantic schemas."""

from __future__ import annotations

import uuid
from datetime import date, time, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


# ─── Turf ────────────────────────────────────────────

class TurfBase(BaseModel):
    name: str = Field(..., max_length=255)
    slug: str = Field(..., max_length=100, pattern=r"^[a-z0-9\-]+$")
    sport_types: list[str] = Field(default_factory=list)
    address: str | None = None
    city: str | None = None
    lat: float | None = None
    lng: float | None = None
    amenities: list[dict] = Field(default_factory=list)
    operating_hours: dict = Field(default_factory=dict)


class TurfCreate(TurfBase):
    pass


class TurfUpdate(BaseModel):
    name: str | None = None
    sport_types: list[str] | None = None
    address: str | None = None
    city: str | None = None
    lat: float | None = None
    lng: float | None = None
    amenities: list[dict] | None = None
    operating_hours: dict | None = None
    is_active: bool | None = None


class TurfRead(TurfBase):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    tenant_id: uuid.UUID
    is_active: bool
    created_at: datetime
    updated_at: datetime


# ─── Slot Rule ───────────────────────────────────────

class SlotRuleBase(BaseModel):
    day_of_week: int = Field(..., ge=0, le=6, description="0=Mon, 6=Sun")
    start_time: time
    end_time: time
    duration_mins: int = Field(default=60, ge=15, le=480)
    slot_type: str = "regular"
    base_price: Decimal = Field(..., ge=0)
    currency: str = "INR"
    max_capacity: int = Field(default=1, ge=1)


class SlotRuleCreate(SlotRuleBase):
    valid_from: date | None = None
    valid_until: date | None = None


class SlotRuleUpdate(BaseModel):
    start_time: time | None = None
    end_time: time | None = None
    duration_mins: int | None = None
    slot_type: str | None = None
    base_price: Decimal | None = None
    max_capacity: int | None = None
    is_active: bool | None = None


class SlotRuleRead(SlotRuleBase):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    turf_id: uuid.UUID
    is_active: bool
    valid_from: date | None = None
    valid_until: date | None = None


# ─── Slot Override ───────────────────────────────────

class SlotOverrideCreate(BaseModel):
    override_date: date
    start_time: time | None = None
    end_time: time | None = None
    override_type: str
    override_price: Decimal | None = None
    reason: str | None = None


class SlotOverrideRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    turf_id: uuid.UUID
    override_date: date
    start_time: time | None
    end_time: time | None
    override_type: str
    override_price: Decimal | None
    reason: str | None


# ─── Available Slot (computed, never persisted) ──────

class AvailableSlot(BaseModel):
    """Virtual slot generated at query time from rules + bookings."""
    date: date
    start_time: time
    end_time: time
    duration_mins: int
    slot_type: str
    base_price: Decimal
    computed_price: Decimal
    is_available: bool
    remaining_capacity: int
