"""
Payment service — Razorpay integration with HMAC webhook verification.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.bookings.models import Booking
from app.bookings.state_machine import BookingStateMachine
from app.config import settings
from app.core.event_bus import event_bus
from app.core.exceptions import NotFoundError, PaymentError, ValidationError
from app.payments.models import PaymentTransaction
from app.payments.schemas import PaymentCallbackData, PaymentInitiate, PaymentRead
from app.users.models import User

logger = logging.getLogger(__name__)


class PaymentService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def initiate_payment(
        self, user: User, data: PaymentInitiate
    ) -> PaymentRead:
        """Create a payment record and initiate with Razorpay."""
        booking = await self.db.get(Booking, data.booking_id)
        if not booking:
            raise NotFoundError("Booking", str(data.booking_id))

        if booking.status != "pending":
            raise ValidationError("Can only pay for pending bookings")

        # Create Razorpay order (placeholder for actual API call)
        gateway_order_id = f"order_{uuid.uuid4().hex[:16]}"

        txn = PaymentTransaction(
            booking_id=booking.id,
            user_id=user.id,
            gateway="razorpay",
            gateway_order_id=gateway_order_id,
            amount=float(booking.final_price),
            status="initiated",
        )
        self.db.add(txn)
        await self.db.commit()
        await self.db.refresh(txn)

        logger.info(
            "Payment initiated: %s for booking %s, amount ₹%.2f",
            txn.id, booking.id, booking.final_price,
        )

        return PaymentRead.model_validate(txn)

    async def handle_callback(
        self, data: PaymentCallbackData
    ) -> PaymentRead:
        """Process Razorpay callback after user completes payment."""
        # Verify signature
        if not self._verify_razorpay_signature(data):
            raise PaymentError("Invalid payment signature")

        # Find the transaction
        result = await self.db.execute(
            select(PaymentTransaction).where(
                PaymentTransaction.gateway_order_id == data.razorpay_order_id
            )
        )
        txn = result.scalar_one_or_none()
        if not txn:
            raise NotFoundError("Payment", data.razorpay_order_id)

        # Update transaction
        txn.gateway_txn_id = data.razorpay_payment_id
        txn.status = "success"
        txn.gateway_response = {
            "payment_id": data.razorpay_payment_id,
            "order_id": data.razorpay_order_id,
        }

        # Confirm the booking
        booking = await self.db.get(Booking, txn.booking_id)
        if booking:
            BookingStateMachine.validate_transition(booking.status, "confirmed")
            booking.status = "confirmed"
            booking.version += 1

        await self.db.commit()
        await self.db.refresh(txn)

        await event_bus.emit("payment.success", {
            "txn_id": str(txn.id),
            "booking_id": str(txn.booking_id),
        })

        return PaymentRead.model_validate(txn)

    async def handle_webhook(self, payload: dict) -> None:
        """Process Razorpay webhook events (server-to-server)."""
        event_type = payload.get("event")
        payment_entity = (
            payload.get("payload", {}).get("payment", {}).get("entity", {})
        )

        logger.info("Webhook event: %s, id: %s", event_type, payment_entity.get("id"))

        if event_type == "payment.authorized":
            # Auto-capture is typically enabled — nothing to do here
            pass
        elif event_type == "payment.captured":
            await self._process_captured(payment_entity)
        elif event_type == "payment.failed":
            await self._process_failed(payment_entity)

    def _verify_razorpay_signature(self, data: PaymentCallbackData) -> bool:
        """HMAC-SHA256 signature verification for Razorpay."""
        if not settings.razorpay_key_secret:
            return settings.is_development  # Allow in development

        message = f"{data.razorpay_order_id}|{data.razorpay_payment_id}"
        expected_sig = hmac.new(
            settings.razorpay_key_secret.encode(),
            message.encode(),
            hashlib.sha256,
        ).hexdigest()
        return hmac.compare_digest(expected_sig, data.razorpay_signature)

    async def _process_captured(self, entity: dict) -> None:
        order_id = entity.get("order_id")
        if not order_id:
            return

        result = await self.db.execute(
            select(PaymentTransaction).where(
                PaymentTransaction.gateway_order_id == order_id
            )
        )
        txn = result.scalar_one_or_none()
        if txn and txn.status != "success":
            txn.status = "success"
            txn.gateway_txn_id = entity.get("id")
            txn.gateway_response = entity

            booking = await self.db.get(Booking, txn.booking_id)
            if booking and booking.status == "pending":
                booking.status = "confirmed"
                booking.version += 1

            await self.db.commit()

    async def _process_failed(self, entity: dict) -> None:
        order_id = entity.get("order_id")
        if not order_id:
            return

        result = await self.db.execute(
            select(PaymentTransaction).where(
                PaymentTransaction.gateway_order_id == order_id
            )
        )
        txn = result.scalar_one_or_none()
        if txn:
            txn.status = "failed"
            txn.gateway_response = entity
            await self.db.commit()
