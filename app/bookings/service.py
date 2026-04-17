"""
Booking service — the core transactional booking lifecycle.

Handles: creation (with advisory locking), cancellation (with refund),
status transitions, and user booking queries.
"""

from __future__ import annotations

import hashlib
import logging
import uuid
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import select, and_, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.bookings.conflict_checker import ConflictChecker
from app.bookings.models import Booking, CancellationPolicy
from app.bookings.pricing_engine import PricingPipeline
from app.bookings.schemas import (
    BookingCancel, BookingCreate, BookingRead, PriceBreakdown,
)
from app.bookings.state_machine import BookingStateMachine
from app.core.event_bus import event_bus
from app.core.exceptions import (
    AuthorizationError,
    BookingConflictError,
    NotFoundError,
    ValidationError,
)
from app.coupons.service import CouponService
from app.turfs.models import TurfSlotRule
from app.users.models import User

logger = logging.getLogger(__name__)


class BookingService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.conflict_checker = ConflictChecker()
        self.pricing = PricingPipeline(db)
        self.coupon_service = CouponService(db)

    async def create_booking(
        self, user: User, body: BookingCreate
    ) -> BookingRead:
        """
        Create a booking with atomic conflict prevention.
        Uses pg_advisory_xact_lock scoped to turf + date.
        """
        async with self.db.begin():
            # STEP 1: Acquire advisory lock
            lock_key = _compute_lock_key(body.turf_id, body.booking_date)
            await self.db.execute(
                text("SELECT pg_advisory_xact_lock(:key)"),
                {"key": lock_key},
            )

            # STEP 2: Check for conflicts
            conflict = await self.conflict_checker.find_conflict(
                db=self.db,
                turf_id=body.turf_id,
                booking_date=body.booking_date,
                start_time=body.start_time,
                end_time=body.end_time,
            )
            if conflict:
                raise BookingConflictError(
                    f"Slot {body.start_time}–{body.end_time} on "
                    f"{body.booking_date} is already booked"
                )

            # STEP 3: Get base price from slot rules
            base_price = await self._resolve_base_price(
                body.turf_id, body.booking_date, body.start_time
            )

            # STEP 3.5: Validate coupon if provided
            coupon_discount = Decimal("0")
            if body.coupon_code:
                try:
                    coupon_discount = await self.coupon_service.validate_and_compute_discount(
                        tenant_id=user.tenant_id,
                        coupon_code=body.coupon_code,
                        booking_amount=base_price,
                        turf_id=body.turf_id,
                        booking_type=body.booking_type,
                    )
                except Exception:
                    # Coupon validation failure should not block booking
                    coupon_discount = Decimal("0")

            # STEP 4: Compute full price
            price = await self.pricing.compute_full(
                turf_id=body.turf_id,
                booking_date=body.booking_date,
                start_time=body.start_time,
                end_time=body.end_time,
                booking_type=body.booking_type,
                base_price=base_price,
                coupon_discount=coupon_discount,
            )

            # STEP 5: Insert booking
            duration = _calc_duration_mins(body.start_time, body.end_time)
            booking = Booking(
                tenant_id=user.tenant_id,
                turf_id=body.turf_id,
                user_id=user.id,
                team_id=body.team_id,
                booking_date=body.booking_date,
                start_time=body.start_time,
                end_time=body.end_time,
                duration_mins=duration,
                status="pending",
                booking_type=body.booking_type,
                base_price=float(price.base_price),
                discount_amount=float(price.discount + price.coupon_discount),
                tax_amount=float(price.tax),
                final_price=float(price.total),
                notes=body.notes,
            )
            self.db.add(booking)

        # Refresh to get DB-generated fields
        await self.db.refresh(booking)

        # Increment coupon usage if one was applied
        if body.coupon_code and coupon_discount > 0:
            await self.coupon_service.increment_usage(user.tenant_id, body.coupon_code)
            await self.db.commit()

        # Post-commit: emit event
        await event_bus.emit("booking.created", {
            "booking_id": str(booking.id),
            "user_id": str(user.id),
            "turf_id": str(body.turf_id),
            "date": body.booking_date.isoformat(),
        })

        logger.info(
            "Booking created: %s for user %s on %s %s–%s",
            booking.id, user.id, body.booking_date,
            body.start_time, body.end_time,
        )

        return BookingRead.model_validate(booking)

    async def preview_price(
        self, user: User, body: BookingCreate
    ) -> PriceBreakdown:
        """Compute price without creating a booking."""
        base_price = await self._resolve_base_price(
            body.turf_id, body.booking_date, body.start_time
        )

        coupon_discount = Decimal("0")
        if body.coupon_code:
            try:
                coupon_discount = await self.coupon_service.validate_and_compute_discount(
                    tenant_id=user.tenant_id,
                    coupon_code=body.coupon_code,
                    booking_amount=base_price,
                    turf_id=body.turf_id,
                    booking_type=body.booking_type,
                )
            except Exception:
                coupon_discount = Decimal("0")

        return await self.pricing.compute_full(
            turf_id=body.turf_id,
            booking_date=body.booking_date,
            start_time=body.start_time,
            end_time=body.end_time,
            booking_type=body.booking_type,
            base_price=base_price,
            coupon_discount=coupon_discount,
        )

    async def cancel_booking(
        self, user: User, booking_id: uuid.UUID, body: BookingCancel
    ) -> BookingRead:
        """Cancel a booking with refund computation."""
        booking = await self._get_booking(booking_id)

        # Authorization: owner or admin
        self._authorize_cancel(user, booking)

        # State machine check
        BookingStateMachine.validate_transition(booking.status, "cancelled")

        # Compute refund
        refund_amount, refund_pct = await self._compute_refund(booking)

        # Apply cancellation
        booking.status = "cancelled"
        booking.cancelled_at = datetime.now(timezone.utc)
        booking.cancel_reason = body.reason
        booking.refund_amount = float(refund_amount)
        booking.version += 1

        await self.db.commit()
        await self.db.refresh(booking)

        # Post-commit event
        await event_bus.emit("booking.cancelled", {
            "booking_id": str(booking_id),
            "user_id": str(user.id),
            "refund_amount": float(refund_amount),
            "refund_pct": refund_pct,
        })

        logger.info(
            "Booking %s cancelled by %s, refund: ₹%.2f (%d%%)",
            booking_id, user.id, refund_amount, refund_pct,
        )

        return BookingRead.model_validate(booking)

    async def transition_status(
        self,
        booking_id: uuid.UUID,
        new_status: str,
        user: User,
    ) -> BookingRead:
        """Generic status transition with state machine validation."""
        booking = await self._get_booking(booking_id)
        BookingStateMachine.validate_transition(booking.status, new_status)

        booking.status = new_status
        booking.version += 1

        await self.db.commit()
        await self.db.refresh(booking)

        await event_bus.emit(f"booking.{new_status}", {
            "booking_id": str(booking_id),
        })

        return BookingRead.model_validate(booking)

    async def get_user_bookings(self, user_id: uuid.UUID) -> list[BookingRead]:
        """Get bookings for a user, most recent first."""
        result = await self.db.execute(
            select(Booking)
            .where(Booking.user_id == user_id)
            .order_by(Booking.booking_date.desc(), Booking.start_time.desc())
            .limit(50)
        )
        return [BookingRead.model_validate(b) for b in result.scalars().all()]

    async def get_turf_bookings(
        self, turf_id: uuid.UUID, target_date=None
    ) -> list[BookingRead]:
        """Get bookings for a turf, optionally filtered by date."""
        query = select(Booking).where(Booking.turf_id == turf_id)
        if target_date:
            query = query.where(Booking.booking_date == target_date)
        query = query.order_by(Booking.booking_date.desc(), Booking.start_time)

        result = await self.db.execute(query)
        return [BookingRead.model_validate(b) for b in result.scalars().all()]

    # ─── Private helpers ─────────────────────────────

    async def _get_booking(self, booking_id: uuid.UUID) -> Booking:
        booking = await self.db.get(Booking, booking_id)
        if not booking:
            raise NotFoundError("Booking", str(booking_id))
        return booking

    async def _resolve_base_price(
        self, turf_id: uuid.UUID, booking_date, start_time
    ) -> Decimal:
        """Find the matching slot rule's base price."""
        day_of_week = booking_date.weekday()
        result = await self.db.execute(
            select(TurfSlotRule).where(and_(
                TurfSlotRule.turf_id == turf_id,
                TurfSlotRule.day_of_week == day_of_week,
                TurfSlotRule.is_active.is_(True),
                TurfSlotRule.start_time <= start_time,
                TurfSlotRule.end_time > start_time,
            )).limit(1)
        )
        rule = result.scalar_one_or_none()
        if not rule:
            raise ValidationError(
                f"No active slot rule found for {booking_date} at {start_time}"
            )
        return Decimal(str(rule.base_price))

    def _authorize_cancel(self, user: User, booking: Booking) -> None:
        """Only booking owner or admins can cancel."""
        if user.id == booking.user_id:
            return
        if user.role in ("super_admin", "turf_admin"):
            return
        raise AuthorizationError("You can only cancel your own bookings")

    async def _compute_refund(self, booking: Booking) -> tuple[Decimal, int]:
        """Compute refund amount based on turf's cancellation policy."""
        # Load default policy for the turf
        result = await self.db.execute(
            select(CancellationPolicy).where(and_(
                CancellationPolicy.turf_id == booking.turf_id,
                CancellationPolicy.is_active.is_(True),
                CancellationPolicy.is_default.is_(True),
            )).limit(1)
        )
        policy = result.scalar_one_or_none()

        if not policy:
            # No policy = full refund
            return Decimal(str(booking.final_price)), 100

        # Compute hours until booking
        booking_dt = datetime.combine(
            booking.booking_date, booking.start_time,
            tzinfo=timezone.utc,
        )
        hours_until = max(
            0.0,
            (booking_dt - datetime.now(timezone.utc)).total_seconds() / 3600,
        )

        # Walk tiers (descending by hours_before)
        tiers = sorted(policy.rules, key=lambda r: r["hours_before"], reverse=True)

        refund_pct = 0
        for tier in tiers:
            if hours_until >= tier["hours_before"]:
                refund_pct = tier["refund_pct"]
                break

        refund_amount = (
            Decimal(str(booking.final_price))
            * Decimal(str(refund_pct))
            / Decimal("100")
        ).quantize(Decimal("0.01"))

        return refund_amount, refund_pct


def _compute_lock_key(turf_id: uuid.UUID, booking_date) -> int:
    """Deterministic bigint for pg_advisory_xact_lock."""
    raw = f"{turf_id}:{booking_date.isoformat()}"
    return int(hashlib.sha256(raw.encode()).hexdigest()[:15], 16)


def _calc_duration_mins(start: any, end: any) -> int:
    """Calculate duration in minutes between two time objects."""
    return (end.hour * 60 + end.minute) - (start.hour * 60 + start.minute)
