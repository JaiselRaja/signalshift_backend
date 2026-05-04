"""Payment Pydantic schemas."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class PaymentInitiate(BaseModel):
    booking_id: uuid.UUID


class PaymentCallbackData(BaseModel):
    razorpay_payment_id: str
    razorpay_order_id: str
    razorpay_signature: str


class PaymentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    # Nullable because subscription payments don't tie to a single booking.
    booking_id: uuid.UUID | None = None
    user_id: uuid.UUID
    gateway: str
    gateway_txn_id: str | None
    gateway_order_id: str | None
    amount: Decimal
    currency: str
    status: str
    payment_method: str | None
    refund_id: str | None
    refund_amount: Decimal | None
    utr: str | None = None
    verified_by: uuid.UUID | None = None
    verified_at: datetime | None = None
    reject_reason: str | None = None
    created_at: datetime
    updated_at: datetime


class UpiInitiateResponse(BaseModel):
    payment_id: uuid.UUID
    booking_id: uuid.UUID
    amount: Decimal
    currency: str
    upi_uri: str
    upi_vpa: str
    payee_name: str


class UpiSubmitUtr(BaseModel):
    payment_id: uuid.UUID
    utr: str = Field(..., min_length=8, max_length=32)


class PaymentRejectRequest(BaseModel):
    reason: str = Field(..., min_length=2, max_length=500)
