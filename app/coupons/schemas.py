"""Coupon Pydantic schemas."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, field_validator


class CouponCreate(BaseModel):
    code: str
    description: str = ""
    discount_type: str = "percentage"  # percentage | flat
    discount_value: Decimal
    max_discount: Decimal | None = None
    min_booking_amount: Decimal = Decimal("0")
    usage_limit: int | None = None
    per_user_limit: int = 1
    valid_from: date
    valid_until: date
    applicable_sports: list[str] = []
    applicable_turf_ids: list[UUID] = []
    applicable_booking_types: list[str] = []

    @field_validator("code")
    @classmethod
    def normalize_code(cls, v: str) -> str:
        return v.upper().strip()

    @field_validator("discount_type")
    @classmethod
    def valid_discount_type(cls, v: str) -> str:
        if v not in ("percentage", "flat"):
            raise ValueError("discount_type must be 'percentage' or 'flat'")
        return v


class CouponUpdate(BaseModel):
    description: str | None = None
    discount_value: Decimal | None = None
    max_discount: Decimal | None = None
    min_booking_amount: Decimal | None = None
    usage_limit: int | None = None
    per_user_limit: int | None = None
    valid_until: date | None = None
    applicable_sports: list[str] | None = None
    is_active: bool | None = None


class CouponRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: UUID
    code: str
    description: str
    discount_type: str
    discount_value: Decimal
    max_discount: Decimal | None
    min_booking_amount: Decimal
    usage_limit: int | None
    used_count: int
    per_user_limit: int
    valid_from: date
    valid_until: date
    applicable_sports: list[str]
    applicable_turf_ids: list[UUID]
    applicable_booking_types: list[str]
    is_active: bool
    created_at: str | None = None
    updated_at: str | None = None
