"""Subscription Pydantic schemas."""

from __future__ import annotations

import uuid
from datetime import date, datetime, time

from pydantic import BaseModel, ConfigDict, Field


class SlotInput(BaseModel):
    """A single recurring weekly slot, supplied by the customer."""
    day_of_week: int = Field(..., ge=0, le=6)
    start_time: time
    end_time: time | None = None  # server fills if omitted


class SubscriptionInitiate(BaseModel):
    plan_id: uuid.UUID
    turf_id: uuid.UUID
    slots: list[SlotInput] = Field(..., min_length=1, max_length=14)


class SubscriptionSubmitUtr(BaseModel):
    subscription_id: uuid.UUID
    utr: str = Field(..., min_length=4, max_length=32)


class PaymentSnapshot(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    status: str
    utr: str | None = None
    amount: float
    currency: str = "INR"


class PlanSnapshot(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    code: str
    name: str
    plan_type: str
    price: float
    price_unit: str
    hours_per_month: int | None = None


class SubscriptionSlotRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    day_of_week: int
    start_time: time
    end_time: time


class SubscriptionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    user_id: uuid.UUID
    plan_id: uuid.UUID
    turf_id: uuid.UUID
    status: str
    starts_on: date | None = None
    expires_on: date | None = None
    payment_id: uuid.UUID | None = None
    cancelled_at: datetime | None = None
    cancel_reason: str | None = None
    created_at: datetime
    updated_at: datetime

    slots: list[SubscriptionSlotRead] = []
    plan: PlanSnapshot | None = None
    payment: PaymentSnapshot | None = None


class SubscriptionInitiateResponse(BaseModel):
    subscription: SubscriptionRead
    payment_id: uuid.UUID
    amount: float
    currency: str = "INR"
    upi_uri: str
    upi_vpa: str
    payee_name: str


class AvailabilitySlot(BaseModel):
    start_time: time
    end_time: time
    available: bool
    reason: str | None = None  # "booking_conflict" | "subscription_conflict" | None
