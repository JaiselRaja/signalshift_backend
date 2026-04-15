"""Booking Pydantic schemas."""

from __future__ import annotations

import uuid
from datetime import date, datetime, time
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class BookingCreate(BaseModel):
    turf_id: uuid.UUID
    booking_date: date
    start_time: time
    end_time: time
    booking_type: str = "regular"
    team_id: uuid.UUID | None = None
    coupon_code: str | None = None
    notes: str | None = None

    @model_validator(mode="after")
    def validate_time_ordering(self) -> "BookingCreate":
        if self.start_time >= self.end_time:
            raise ValueError("start_time must be before end_time")
        return self


class BookingRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    turf_id: uuid.UUID
    user_id: uuid.UUID
    team_id: uuid.UUID | None
    booking_date: date
    start_time: time
    end_time: time
    duration_mins: int
    status: str
    booking_type: str
    base_price: Decimal
    discount_amount: Decimal
    tax_amount: Decimal
    final_price: Decimal
    currency: str
    cancelled_at: datetime | None
    cancel_reason: str | None
    refund_amount: Decimal | None
    notes: str | None
    created_at: datetime
    updated_at: datetime


class BookingCancel(BaseModel):
    reason: str = Field(..., min_length=5, max_length=500)


class AppliedPricingRule(BaseModel):
    rule_name: str
    rule_type: str
    adjustment_type: str
    adjustment_value: Decimal
    effect_amount: Decimal


class PriceBreakdown(BaseModel):
    base_price: Decimal
    applied_rules: list[AppliedPricingRule] = Field(default_factory=list)
    discount: Decimal = Decimal("0")
    coupon_discount: Decimal = Decimal("0")
    subtotal: Decimal
    tax: Decimal
    total: Decimal


class PricingRuleCreate(BaseModel):
    name: str = Field(..., max_length=255)
    rule_type: str
    priority: int = 0
    conditions: dict = Field(default_factory=dict)
    adjustment_type: str
    adjustment_value: Decimal
    stackable: bool = False
    valid_from: date | None = None
    valid_until: date | None = None


class PricingRuleRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    turf_id: uuid.UUID
    name: str
    rule_type: str
    priority: int
    conditions: dict
    adjustment_type: str
    adjustment_value: Decimal
    stackable: bool
    valid_from: date | None
    valid_until: date | None
    is_active: bool


class CancellationPolicyCreate(BaseModel):
    name: str = Field(..., max_length=100)
    rules: list[dict]
    is_default: bool = False


class CancellationPolicyRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    turf_id: uuid.UUID
    name: str
    rules: dict  # list of {hours_before, refund_pct}
    is_default: bool
    is_active: bool
