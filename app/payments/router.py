"""Payment API routes."""

from __future__ import annotations

import hmac
import hashlib
import logging

from fastapi import APIRouter, Depends, Request, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.config import settings
from app.core.database import get_async_session
from app.payments.schemas import PaymentCallbackData, PaymentInitiate, PaymentRead
from app.payments.service import PaymentService
from app.users.models import User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/payments", tags=["Payments"])


def _get_service(db: AsyncSession = Depends(get_async_session)) -> PaymentService:
    return PaymentService(db)


@router.post("/initiate", response_model=PaymentRead, status_code=201)
async def initiate_payment(
    body: PaymentInitiate,
    current_user: User = Depends(get_current_user),
    svc: PaymentService = Depends(_get_service),
):
    """Initiate a payment for a pending booking."""
    return await svc.initiate_payment(current_user, body)


@router.post("/callback", response_model=PaymentRead)
async def payment_callback(
    body: PaymentCallbackData,
    svc: PaymentService = Depends(_get_service),
):
    """Handle Razorpay client-side callback (signature verified)."""
    return await svc.handle_callback(body)


@router.post("/webhook", status_code=200)
async def webhook(
    request: Request,
    db: AsyncSession = Depends(get_async_session),
):
    """
    Razorpay server-to-server webhook endpoint.
    Verifies X-Razorpay-Signature header using HMAC-SHA256.
    No JWT auth — protected by signature verification.
    """
    body = await request.body()
    signature = request.headers.get("X-Razorpay-Signature", "")

    # Verify webhook signature
    if settings.razorpay_webhook_secret:
        expected = hmac.new(
            settings.razorpay_webhook_secret.encode(),
            body,
            hashlib.sha256,
        ).hexdigest()
        if not hmac.compare_digest(expected, signature):
            logger.warning("Webhook signature mismatch")
            raise HTTPException(status_code=400, detail="Invalid signature")

    payload = await request.json()
    svc = PaymentService(db)
    await svc.handle_webhook(payload)

    return {"status": "ok"}
