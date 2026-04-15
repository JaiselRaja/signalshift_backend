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
    booking_id: uuid.UUID
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
    created_at: datetime
    updated_at: datetime
