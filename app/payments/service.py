"""
Payment service — Razorpay integration with HMAC webhook verification.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import uuid

import razorpay
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

# Razorpay client (initialized once at module level)
_razorpay_client: razorpay.Client | None = None


def _get_razorpay_client() -> razorpay.Client | None:
    """Lazy-init Razorpay client. Returns None if credentials are not configured."""
    global _razorpay_client
    if _razorpay_client is not None:
        return _razorpay_client
    if settings.razorpay_key_id and settings.razorpay_key_secret:
        _razorpay_client = razorpay.Client(
            auth=(settings.razorpay_key_id, settings.razorpay_key_secret)
        )
        return _razorpay_client
    return None


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

        # Create Razorpay order via SDK
        amount_paise = int(float(booking.final_price) * 100)
        rz_client = _get_razorpay_client()

        if rz_client:
            try:
                order = rz_client.order.create({
                    "amount": amount_paise,
                    "currency": booking.currency or "INR",
                    "receipt": f"booking_{booking.id}",
                    "notes": {
                        "booking_id": str(booking.id),
                        "user_id": str(user.id),
                    },
                })
                gateway_order_id = order["id"]
            except Exception as exc:
                logger.error("Razorpay order creation failed: %s", exc)
                raise PaymentError(f"Payment gateway error: {exc}") from exc
        else:
            # Development fallback when Razorpay credentials are not configured
            if not settings.is_development:
                raise PaymentError("Payment gateway is not configured")
            gateway_order_id = f"order_dev_{uuid.uuid4().hex[:16]}"
            logger.warning("DEV MODE: Using fake order ID %s", gateway_order_id)

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

    async def initiate_refund(
        self, booking_id: uuid.UUID
    ) -> PaymentRead:
        """Initiate a refund for a cancelled booking via Razorpay."""
        # Find the successful payment for this booking
        result = await self.db.execute(
            select(PaymentTransaction).where(
                PaymentTransaction.booking_id == booking_id,
                PaymentTransaction.status == "success",
            )
        )
        txn = result.scalar_one_or_none()
        if not txn:
            raise NotFoundError("Payment", str(booking_id))

        booking = await self.db.get(Booking, booking_id)
        if not booking or not booking.refund_amount:
            raise ValidationError("No refund amount computed for this booking")

        refund_amount_paise = int(float(booking.refund_amount) * 100)

        rz_client = _get_razorpay_client()
        if rz_client and txn.gateway_txn_id:
            try:
                refund = rz_client.payment.refund(txn.gateway_txn_id, {
                    "amount": refund_amount_paise,
                    "notes": {"booking_id": str(booking_id)},
                })
                txn.refund_id = refund.get("id")
            except Exception as exc:
                logger.error("Razorpay refund failed: %s", exc)
                raise PaymentError(f"Refund failed: {exc}") from exc
        else:
            if not settings.is_development:
                raise PaymentError("Cannot process refund: payment gateway not configured")
            txn.refund_id = f"rfnd_dev_{uuid.uuid4().hex[:12]}"
            logger.warning("DEV MODE: Using fake refund ID %s", txn.refund_id)

        txn.refund_amount = float(booking.refund_amount)
        txn.status = "refunded"

        # Transition booking to refunded
        BookingStateMachine.validate_transition(booking.status, "refund_pending")
        booking.status = "refund_pending"
        booking.version += 1

        await self.db.commit()
        await self.db.refresh(txn)

        # Move to refunded immediately (in production, this would be async via webhook)
        BookingStateMachine.validate_transition(booking.status, "refunded")
        booking.status = "refunded"
        booking.version += 1
        await self.db.commit()

        await event_bus.emit("payment.refunded", {
            "txn_id": str(txn.id),
            "booking_id": str(booking_id),
            "refund_amount": float(booking.refund_amount),
        })

        logger.info(
            "Refund processed: %s for booking %s, amount ₹%.2f",
            txn.refund_id, booking_id, booking.refund_amount,
        )

        return PaymentRead.model_validate(txn)

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
