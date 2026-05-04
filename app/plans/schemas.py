"""Pydantic schemas for the Plans API."""

from __future__ import annotations

import uuid
from datetime import datetime, time
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class PlanBase(BaseModel):
    code: str = Field(..., max_length=50, pattern=r"^[a-z0-9_\-]+$")
    name: str = Field(..., max_length=100)
    tagline: str | None = None
    plan_type: str = Field(default="monthly", pattern=r"^(monthly|daily)$")
    price: Decimal
    price_unit: str = Field(default="/month", max_length=20)
    hours_per_month: int | None = None
    discount_pct: int | None = None
    advance_window_days: int | None = None
    slot_window_start: time | None = None
    slot_window_end: time | None = None
    perks: list[str] = Field(default_factory=list)
    featured: bool = False
    display_order: int = 0
    is_active: bool = True


class PlanCreate(PlanBase):
    pass


class PlanUpdate(BaseModel):
    name: str | None = None
    tagline: str | None = None
    plan_type: str | None = Field(default=None, pattern=r"^(monthly|daily)$")
    price: Decimal | None = None
    price_unit: str | None = None
    hours_per_month: int | None = None
    discount_pct: int | None = None
    advance_window_days: int | None = None
    slot_window_start: time | None = None
    slot_window_end: time | None = None
    perks: list[str] | None = None
    featured: bool | None = None
    display_order: int | None = None
    is_active: bool | None = None


class PlanRead(PlanBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    created_at: datetime
    updated_at: datetime
