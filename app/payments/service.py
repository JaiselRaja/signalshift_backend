"""
Payment service — Razorpay integration with HMAC webhook verification.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import urllib.parse
import uuid
from datetime import datetime, timezone

import razorpay
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.bookings.models import Booking
from app.bookings.state_machine import BookingStateMachine
from app.config import settings
from app.core.event_bus import event_bus
from app.core.exceptions import NotFoundError, PaymentError, ValidationError
from app.payments.models import PaymentTransaction
from app.payments.schemas import (
    PaymentCallbackData,
    PaymentInitiate,
    PaymentRead,
    RazorpayInitiateResponse,
    UpiInitiateResponse,
    UpiSubmitUtr,
)
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


def _humanize_razorpay_error(entity: dict) -> str:
    """Turn a Razorpay error entity into a user-friendly reason string."""
    desc = entity.get("error_description") or entity.get("error_reason")
    if desc:
        return str(desc)
    code = entity.get("error_code")
    if code:
        return f"Payment was declined (code: {code})."
    return "Payment was declined by the gateway."


class PaymentService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def initiate_payment(
        self, user: User, data: PaymentInitiate
    ) -> RazorpayInitiateResponse:
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
                    # Razorpay caps receipt at 40 chars; "b_" + 36-char UUID = 38.
                    "receipt": f"b_{booking.id}",
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
            raise PaymentError("Payment gateway is not configured")

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

        return RazorpayInitiateResponse(
            payment_id=txn.id,
            booking_id=booking.id,
            razorpay_order_id=gateway_order_id,
            razorpay_key_id=settings.razorpay_key_id,
            amount_paise=amount_paise,
            currency=booking.currency or "INR",
        )

    async def handle_callback(
        self, data: PaymentCallbackData
    ) -> PaymentRead:
        """Process Razorpay callback after user completes payment."""
        # Verify signature
        if not self._verify_razorpay_signature(data):
            # Look up the txn so the failure email can find its booking / user.
            sig_result = await self.db.execute(
                select(PaymentTransaction).where(
                    PaymentTransaction.gateway_order_id == data.razorpay_order_id
                )
            )
            sig_txn = sig_result.scalar_one_or_none()
            if sig_txn:
                sig_txn.status = "failed"
                await self.db.commit()
                await event_bus.emit("payment.failed", {
                    "txn_id": str(sig_txn.id),
                    "reason": "Verification failed — please contact support if money was deducted.",
                })
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

        # If the server-to-server webhook already processed this payment (race condition:
        # webhook lands before the client callback), there's nothing left to do — emails
        # were already sent and the booking was already confirmed. Return the existing
        # txn so the frontend sees success and redirects.
        if txn.status == "success":
            logger.info(
                "Payment callback for txn %s: webhook already processed, returning existing state",
                txn.id,
            )
            return PaymentRead.model_validate(txn)

        # Fetch the payment from Razorpay to authoritatively check status + get method.
        # Razorpay's `handler` callback can fire for failed payments (especially in
        # test mode with decline cards), so the signed callback alone isn't enough —
        # we must verify the payment's actual server-side status before marking success.
        rz_payment: dict | None = None
        method: str | None = None
        rz_status: str | None = None
        rz_client = _get_razorpay_client()
        if rz_client is not None:
            try:
                rz_payment = rz_client.payment.fetch(data.razorpay_payment_id)
                method = rz_payment.get("method")
                rz_status = rz_payment.get("status")
            except Exception as exc:
                logger.warning(
                    "Razorpay payment.fetch failed for %s: %s — falling back to signed callback",
                    data.razorpay_payment_id, exc,
                )

        # Decide success vs failure from authoritative Razorpay status.
        # If we couldn't fetch (rz_status is None), trust the signed callback — better
        # to occasionally over-confirm than block a legit user on a transient blip.
        SUCCESS_STATUSES = {"authorized", "captured"}
        if rz_status is not None and rz_status not in SUCCESS_STATUSES:
            # Payment did NOT succeed despite handler firing. Mark failed + emit failure.
            txn.gateway_txn_id = data.razorpay_payment_id
            txn.status = "failed"
            txn.gateway_response = rz_payment or {
                "payment_id": data.razorpay_payment_id,
                "order_id": data.razorpay_order_id,
            }
            if method:
                txn.payment_method = method
            await self.db.commit()
            await event_bus.emit("payment.failed", {
                "txn_id": str(txn.id),
                "reason": _humanize_razorpay_error(rz_payment or {})
                          if rz_status == "failed"
                          else f"Payment is in '{rz_status}' state — please retry.",
            })
            raise PaymentError(
                f"Payment did not succeed (status: {rz_status}). Please try again."
            )

        # Update transaction (success path)
        txn.gateway_txn_id = data.razorpay_payment_id
        txn.status = "success"
        txn.gateway_response = rz_payment or {
            "payment_id": data.razorpay_payment_id,
            "order_id": data.razorpay_order_id,
        }
        if method:
            txn.payment_method = method

        # Confirm the booking — only if still pending. If it's already confirmed
        # (e.g. a manual admin confirm, or webhook beat us in a very narrow race),
        # skip the transition silently instead of erroring on confirmed→confirmed.
        booking = await self.db.get(Booking, txn.booking_id)
        newly_confirmed = False
        if booking and booking.status == "pending":
            BookingStateMachine.validate_transition(booking.status, "confirmed")
            booking.status = "confirmed"
            booking.version += 1
            newly_confirmed = True

        await self.db.commit()
        await self.db.refresh(txn)

        await event_bus.emit("payment.success", {
            "txn_id": str(txn.id),
            "booking_id": str(txn.booking_id),
        })
        if newly_confirmed and booking:
            await event_bus.emit("booking.confirmed", {
                "booking_id": str(booking.id),
                "user_id": str(booking.user_id),
                "turf_id": str(booking.turf_id),
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
            return False

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
            if not txn.payment_method:
                txn.payment_method = entity.get("method")

            booking = await self.db.get(Booking, txn.booking_id)
            newly_confirmed = False
            if booking and booking.status == "pending":
                booking.status = "confirmed"
                booking.version += 1
                newly_confirmed = True

            await self.db.commit()

            if newly_confirmed and booking:
                await event_bus.emit("booking.confirmed", {
                    "booking_id": str(booking.id),
                    "user_id": str(booking.user_id),
                    "turf_id": str(booking.turf_id),
                })

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
            raise PaymentError("Cannot process refund: payment gateway not configured")

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
        if not txn:
            return

        txn.status = "failed"
        txn.gateway_response = entity
        if not txn.payment_method:
            txn.payment_method = entity.get("method")
        await self.db.commit()

        await event_bus.emit("payment.failed", {
            "txn_id": str(txn.id),
            "reason": _humanize_razorpay_error(entity),
        })

    # ─── UPI (manual verification) ──────────────────────

    async def initiate_upi_payment(
        self, user: User, data: PaymentInitiate
    ) -> UpiInitiateResponse:
        """
        Create a pending UPI payment and return the deep-link URI and
        amount for the client to render a QR + open-in-app button.
        """
        if not settings.upi_vpa:
            raise PaymentError("UPI payments are not configured on this server.")

        booking = await self.db.get(Booking, data.booking_id)
        if not booking:
            raise NotFoundError("Booking", str(data.booking_id))

        if booking.user_id != user.id:
            raise ValidationError("You can only pay for your own bookings.")

        if booking.status != "pending":
            raise ValidationError("Can only pay for pending bookings.")

        # Reuse any existing initiated txn rather than creating duplicates
        existing = await self.db.execute(
            select(PaymentTransaction).where(
                PaymentTransaction.booking_id == booking.id,
                PaymentTransaction.status.in_(("initiated", "processing")),
            )
        )
        txn = existing.scalar_one_or_none()

        amount = float(booking.final_price)
        if txn is None:
            txn = PaymentTransaction(
                booking_id=booking.id,
                user_id=user.id,
                gateway="upi_manual",
                amount=amount,
                currency=booking.currency or "INR",
                status="initiated",
            )
            self.db.add(txn)
            await self.db.commit()
            await self.db.refresh(txn)

        note = f"Booking {str(booking.id)[:8]}"
        upi_uri = (
            f"upi://pay?pa={urllib.parse.quote(settings.upi_vpa)}"
            f"&pn={urllib.parse.quote(settings.upi_payee_name)}"
            f"&am={amount:.2f}"
            f"&cu={booking.currency or 'INR'}"
            f"&tn={urllib.parse.quote(note)}"
        )

        return UpiInitiateResponse(
            payment_id=txn.id,
            booking_id=booking.id,
            amount=amount,
            currency=booking.currency or "INR",
            upi_uri=upi_uri,
            upi_vpa=settings.upi_vpa,
            payee_name=settings.upi_payee_name,
        )

    async def submit_utr(self, user: User, data: UpiSubmitUtr) -> PaymentRead:
        """User submits the UTR after completing UPI transfer.

        Transitions the payment from 'initiated' → 'processing' (awaiting admin verify).
        """
        txn = await self.db.get(PaymentTransaction, data.payment_id)
        if not txn:
            raise NotFoundError("Payment", str(data.payment_id))

        if txn.user_id != user.id:
            raise ValidationError("This payment is not yours.")

        if txn.status not in ("initiated", "processing"):
            raise ValidationError(
                f"Payment is already {txn.status} and cannot be updated."
            )

        txn.utr = data.utr.strip()
        txn.status = "processing"
        await self.db.commit()
        await self.db.refresh(txn)

        logger.info("UPI UTR submitted: txn=%s utr=%s", txn.id, txn.utr)
        return PaymentRead.model_validate(txn)

    async def verify_upi_payment(
        self, payment_id: uuid.UUID, admin: User
    ) -> PaymentRead:
        """Admin action: mark payment as success and confirm the booking."""
        txn = await self.db.get(PaymentTransaction, payment_id)
        if not txn:
            raise NotFoundError("Payment", str(payment_id))

        if txn.status != "processing":
            raise ValidationError(
                f"Payment must be in 'processing' status to verify (currently '{txn.status}')."
            )

        txn.status = "success"
        txn.verified_by = admin.id
        txn.verified_at = datetime.now(timezone.utc)

        # txn.booking_id may be null for subscription payments
        booking = (
            await self.db.get(Booking, txn.booking_id) if txn.booking_id else None
        )
        if booking and booking.status == "pending":
            BookingStateMachine.validate_transition(booking.status, "confirmed")
            booking.status = "confirmed"
            booking.version += 1

        await self.db.commit()
        await self.db.refresh(txn)

        await event_bus.emit("payment.success", {
            "txn_id": str(txn.id),
            "booking_id": str(txn.booking_id) if txn.booking_id else None,
        })
        if booking and booking.status == "confirmed":
            await event_bus.emit("booking.confirmed", {
                "booking_id": str(booking.id),
                "user_id": str(booking.user_id),
                "turf_id": str(booking.turf_id),
            })

        logger.info("UPI payment verified: txn=%s by admin=%s", txn.id, admin.id)
        return PaymentRead.model_validate(txn)

    async def reject_upi_payment(
        self, payment_id: uuid.UUID, admin: User, reason: str
    ) -> PaymentRead:
        """Admin action: mark payment as failed with a rejection reason."""
        txn = await self.db.get(PaymentTransaction, payment_id)
        if not txn:
            raise NotFoundError("Payment", str(payment_id))

        if txn.status not in ("initiated", "processing"):
            raise ValidationError(
                f"Payment must be initiated or processing to reject (currently '{txn.status}')."
            )

        txn.status = "failed"
        txn.verified_by = admin.id
        txn.verified_at = datetime.now(timezone.utc)
        txn.reject_reason = reason.strip()
        await self.db.commit()
        await self.db.refresh(txn)

        await event_bus.emit("payment.rejected", {
            "txn_id": str(txn.id),
            "booking_id": str(txn.booking_id) if txn.booking_id else None,
            "reason": reason.strip(),
        })

        logger.info("UPI payment rejected: txn=%s by admin=%s reason=%s", txn.id, admin.id, reason)
        return PaymentRead.model_validate(txn)
