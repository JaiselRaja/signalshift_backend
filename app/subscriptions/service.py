"""Subscription business logic — multi-slot recurring booking via UPI."""

from __future__ import annotations

import logging
import urllib.parse
import uuid
from datetime import date, datetime, time, timedelta

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.bookings.conflict_checker import ConflictChecker
from app.bookings.models import Booking
from app.config import settings
from app.core.event_bus import event_bus
from app.core.exceptions import (
    NotFoundError,
    PaymentError,
    ValidationError,
)
from app.payments.models import PaymentTransaction
from app.plans.models import Plan
from app.subscriptions.models import Subscription, SubscriptionSlot
from app.subscriptions.schemas import (
    AvailabilitySlot,
    SlotInput,
    SubscriptionInitiate,
    SubscriptionInitiateResponse,
    SubscriptionRead,
    SubscriptionSubmitUtr,
)
from app.turfs.models import Turf
from app.users.models import User

logger = logging.getLogger(__name__)

# How many weeks the subscription covers in a "month".
WEEKS_PER_MONTH = 4

# Each individual slot is exactly this many minutes. Number of slots per week
# is plan.hours_per_month / WEEKS_PER_MONTH × (60 / SLOT_DURATION_MINUTES).
SLOT_DURATION_MINUTES = 60


def _next_occurrence(target_dow: int, from_day: date | None = None) -> date:
    base = from_day or date.today()
    delta = (target_dow - base.weekday()) % 7
    return base + timedelta(days=delta)


def _slots_per_week(plan: Plan) -> int:
    """How many recurring weekly slots this plan unlocks."""
    if not plan.hours_per_month:
        return 1
    total_minutes = plan.hours_per_month * 60
    weekly_minutes = total_minutes // WEEKS_PER_MONTH
    count = max(1, weekly_minutes // SLOT_DURATION_MINUTES)
    return int(count)


def _add_minutes(t: time, minutes: int) -> time:
    total = t.hour * 60 + t.minute + minutes
    return time(total // 60 % 24, total % 60)


def _to_min(t: time) -> int:
    return t.hour * 60 + t.minute


class SubscriptionService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.conflict_checker = ConflictChecker()

    # ─── Read ────────────────────────────────────────────

    async def list_my(self, user_id: uuid.UUID) -> list[SubscriptionRead]:
        result = await self.db.execute(
            select(Subscription)
            .options(
                selectinload(Subscription.plan),
                selectinload(Subscription.payment),
                selectinload(Subscription.slots),
            )
            .where(Subscription.user_id == user_id)
            .order_by(Subscription.created_at.desc())
        )
        return [SubscriptionRead.model_validate(s) for s in result.scalars().all()]

    async def get(self, subscription_id: uuid.UUID) -> Subscription:
        sub = await self.db.get(Subscription, subscription_id)
        if not sub:
            raise NotFoundError("Subscription", str(subscription_id))
        return sub

    # ─── Availability ───────────────────────────────────

    async def availability(
        self,
        turf_id: uuid.UUID,
        day_of_week: int,
        duration_mins: int,
        plan_id: uuid.UUID | None = None,
    ) -> list[AvailabilitySlot]:
        """For each candidate start time on this day-of-week, return whether
        the slot is free for the next 4 weeks (no booking or active-subscription
        slot overlap). Plan window narrows the range when supplied."""
        if day_of_week < 0 or day_of_week > 6:
            raise ValidationError("day_of_week must be 0-6")

        turf = await self.db.get(Turf, turf_id)
        if not turf:
            raise NotFoundError("Turf", str(turf_id))

        day_name = ["monday", "tuesday", "wednesday", "thursday",
                    "friday", "saturday", "sunday"][day_of_week]
        hours = (turf.operating_hours or {}).get(day_name) or {
            "open": "06:00",
            "close": "23:30",
        }
        open_t = _parse_time(hours.get("open", "06:00"))
        close_t = _parse_time(hours.get("close", "23:30"))

        if plan_id is not None:
            plan = await self.db.get(Plan, plan_id)
            if plan and plan.slot_window_start:
                open_t = max(open_t, plan.slot_window_start)
            if plan and plan.slot_window_end:
                close_t = min(close_t, plan.slot_window_end)
            if _to_min(open_t) >= _to_min(close_t):
                return []

        # Pre-load future bookings + active sub slots for this dow
        first_date = _next_occurrence(day_of_week)
        booking_dates = [first_date + timedelta(days=7 * i) for i in range(WEEKS_PER_MONTH)]

        bookings_q = await self.db.execute(
            select(Booking).where(and_(
                Booking.turf_id == turf_id,
                Booking.status.in_(["pending", "confirmed"]),
                Booking.booking_date.in_(booking_dates),
            ))
        )
        future_bookings = list(bookings_q.scalars().all())

        slots_q = await self.db.execute(
            select(SubscriptionSlot)
            .join(Subscription, SubscriptionSlot.subscription_id == Subscription.id)
            .where(and_(
                Subscription.turf_id == turf_id,
                Subscription.status.in_(["pending", "active"]),
                SubscriptionSlot.day_of_week == day_of_week,
            ))
        )
        active_sub_slots = list(slots_q.scalars().all())

        # Build candidate start times — increment in 30-minute buckets.
        slots: list[AvailabilitySlot] = []
        cursor = open_t
        end_limit = _add_minutes(close_t, -duration_mins)

        while _to_min(cursor) <= _to_min(end_limit):
            slot_end = _add_minutes(cursor, duration_mins)
            available = True
            reason: str | None = None

            for b in future_bookings:
                if b.start_time < slot_end and b.end_time > cursor:
                    available = False
                    reason = "booking_conflict"
                    break

            if available:
                for s in active_sub_slots:
                    if s.start_time < slot_end and s.end_time > cursor:
                        available = False
                        reason = "subscription_conflict"
                        break

            slots.append(AvailabilitySlot(
                start_time=cursor, end_time=slot_end,
                available=available, reason=reason,
            ))
            cursor = _add_minutes(cursor, 30)

        return slots

    # ─── Initiate (create subscription + UPI payment) ───

    async def initiate(
        self, user: User, data: SubscriptionInitiate
    ) -> SubscriptionInitiateResponse:
        if not settings.upi_vpa:
            raise PaymentError("UPI payments are not configured on this server.")
        if not user.phone or not user.phone.strip():
            raise ValidationError(
                "Please add your phone number to your profile before subscribing.",
                detail={"missing_field": "phone"},
            )

        # Plan + turf validation
        plan = await self.db.get(Plan, data.plan_id)
        if not plan or not plan.is_active:
            raise NotFoundError("Plan", str(data.plan_id))
        if plan.plan_type != "monthly":
            raise ValidationError("Only monthly plans support recurring subscriptions.")
        if plan.tenant_id != user.tenant_id:
            raise ValidationError("Plan does not belong to this tenant.")

        turf = await self.db.get(Turf, data.turf_id)
        if not turf or not turf.is_active:
            raise NotFoundError("Turf", str(data.turf_id))

        # Validate slot count matches plan
        required = _slots_per_week(plan)
        if len(data.slots) != required:
            raise ValidationError(
                f"This plan needs exactly {required} weekly slot{'s' if required != 1 else ''} "
                f"({SLOT_DURATION_MINUTES} min each). You picked {len(data.slots)}."
            )

        # Normalize: derive end_time, validate window, check internal collisions
        normalized: list[SlotInput] = []
        for s in data.slots:
            derived_end = _add_minutes(s.start_time, SLOT_DURATION_MINUTES)
            end = s.end_time or derived_end
            if end != derived_end:
                raise ValidationError(
                    f"Each slot must be {SLOT_DURATION_MINUTES} minutes."
                )
            if plan.slot_window_start and s.start_time < plan.slot_window_start:
                raise ValidationError(
                    f"Slot {s.start_time.strftime('%H:%M')} is before the plan's window starts."
                )
            if plan.slot_window_end and end > plan.slot_window_end:
                raise ValidationError(
                    f"Slot {s.start_time.strftime('%H:%M')} ends after the plan's window."
                )
            normalized.append(SlotInput(
                day_of_week=s.day_of_week, start_time=s.start_time, end_time=end,
            ))

        # No two picked slots may overlap each other
        for i, a in enumerate(normalized):
            for b in normalized[i + 1:]:
                if a.day_of_week == b.day_of_week:
                    if a.start_time < b.end_time and a.end_time > b.start_time:
                        raise ValidationError(
                            f"Two of your slots overlap on the same day."
                        )

        # Conflict check across the next 4 weeks of bookings + existing subs
        for s in normalized:
            await self._validate_no_conflicts(
                turf_id=turf.id,
                day_of_week=s.day_of_week,
                start_time=s.start_time,
                end_time=s.end_time,  # type: ignore[arg-type]
            )

        # Create UPI payment transaction
        txn = PaymentTransaction(
            user_id=user.id,
            gateway="upi_manual",
            amount=float(plan.price),
            currency="INR",
            status="initiated",
        )
        self.db.add(txn)
        await self.db.flush()

        # Subscription starts on the earliest upcoming occurrence of any picked day
        upcoming_dates = [_next_occurrence(s.day_of_week) for s in normalized]
        starts_on = min(upcoming_dates)
        expires_on = starts_on + timedelta(days=7 * WEEKS_PER_MONTH)

        sub = Subscription(
            tenant_id=user.tenant_id,
            user_id=user.id,
            plan_id=plan.id,
            turf_id=turf.id,
            status="pending",
            starts_on=starts_on,
            expires_on=expires_on,
            payment_id=txn.id,
        )
        self.db.add(sub)
        await self.db.flush()

        for s in normalized:
            self.db.add(SubscriptionSlot(
                subscription_id=sub.id,
                day_of_week=s.day_of_week,
                start_time=s.start_time,
                end_time=s.end_time,  # type: ignore[arg-type]
            ))

        await self.db.commit()
        await self.db.refresh(sub)
        await self.db.refresh(txn)

        # UPI deep-link
        note = f"Sub {plan.code} {str(sub.id)[:8]}"
        amount = float(plan.price)
        upi_uri = (
            f"upi://pay?pa={urllib.parse.quote(settings.upi_vpa)}"
            f"&pn={urllib.parse.quote(settings.upi_payee_name)}"
            f"&am={amount:.2f}"
            f"&cu=INR"
            f"&tn={urllib.parse.quote(note)}"
        )

        # Reload with relationships
        result = await self.db.execute(
            select(Subscription)
            .options(
                selectinload(Subscription.plan),
                selectinload(Subscription.payment),
                selectinload(Subscription.slots),
            )
            .where(Subscription.id == sub.id)
        )
        loaded = result.scalar_one()

        return SubscriptionInitiateResponse(
            subscription=SubscriptionRead.model_validate(loaded),
            payment_id=txn.id,
            amount=amount,
            currency="INR",
            upi_uri=upi_uri,
            upi_vpa=settings.upi_vpa,
            payee_name=settings.upi_payee_name,
        )

    # ─── Submit UTR (user uploads payment proof) ────────

    async def submit_utr(
        self, user: User, data: SubscriptionSubmitUtr
    ) -> SubscriptionRead:
        sub = await self.db.get(Subscription, data.subscription_id)
        if not sub:
            raise NotFoundError("Subscription", str(data.subscription_id))
        if sub.user_id != user.id:
            raise ValidationError("This subscription is not yours.")
        if not sub.payment_id:
            raise ValidationError("Subscription has no linked payment.")

        txn = await self.db.get(PaymentTransaction, sub.payment_id)
        if not txn:
            raise NotFoundError("Payment", str(sub.payment_id))
        if txn.status not in ("initiated", "processing"):
            raise ValidationError(
                f"Payment is already {txn.status} and cannot be updated."
            )

        txn.utr = data.utr.strip()
        txn.status = "processing"
        await self.db.commit()

        result = await self.db.execute(
            select(Subscription)
            .options(
                selectinload(Subscription.plan),
                selectinload(Subscription.payment),
                selectinload(Subscription.slots),
            )
            .where(Subscription.id == sub.id)
        )
        return SubscriptionRead.model_validate(result.scalar_one())

    # ─── Activate (called after admin verifies payment) ──

    async def activate_after_payment(self, payment_id: uuid.UUID) -> None:
        result = await self.db.execute(
            select(Subscription)
            .options(
                selectinload(Subscription.plan),
                selectinload(Subscription.slots),
            )
            .where(Subscription.payment_id == payment_id)
        )
        sub = result.scalar_one_or_none()
        if not sub:
            return  # not a subscription payment, nothing to do
        if sub.status == "active":
            return

        sub.status = "active"
        await self.db.flush()

        await self._create_weekly_bookings(sub)
        await self.db.commit()

        await event_bus.emit("subscription.activated", {
            "subscription_id": str(sub.id),
            "user_id": str(sub.user_id),
        })

        logger.info(
            "Subscription %s activated, %d slots × %d weeks bookings prepared",
            sub.id, len(sub.slots), WEEKS_PER_MONTH,
        )

    # ─── Cancel ─────────────────────────────────────────

    async def cancel(
        self,
        subscription_id: uuid.UUID,
        actor: User,
        reason: str | None = None,
        cancel_past: bool = False,
    ) -> SubscriptionRead:
        """Cancel a subscription and all its future child bookings.

        - actor must be the subscription owner OR a super_admin/turf_admin.
        - Past bookings are kept by default (they already happened).
        """
        sub = await self.db.get(Subscription, subscription_id)
        if not sub:
            raise NotFoundError("Subscription", str(subscription_id))

        is_owner = sub.user_id == actor.id
        is_admin = actor.role in ("super_admin", "turf_admin")
        if not (is_owner or is_admin):
            from app.core.exceptions import AuthorizationError
            raise AuthorizationError("Only the owner or an admin can cancel this subscription.")

        if sub.status == "cancelled":
            # idempotent
            return await self._reload(sub.id)

        sub.status = "cancelled"
        sub.cancelled_at = datetime.utcnow()
        sub.cancel_reason = (reason or "").strip() or None

        # Cancel future (or all) child bookings
        today = date.today()
        bq = select(Booking).where(Booking.subscription_id == sub.id)
        if not cancel_past:
            bq = bq.where(Booking.booking_date >= today)
        bookings = (await self.db.execute(bq)).scalars().all()
        for b in bookings:
            if b.status in ("pending", "confirmed"):
                b.status = "cancelled"
                b.cancelled_at = datetime.utcnow().replace(tzinfo=None)
                b.cancel_reason = "Subscription cancelled"
                b.version += 1

        await self.db.commit()

        await event_bus.emit("subscription.cancelled", {
            "subscription_id": str(sub.id),
            "user_id": str(sub.user_id),
            "cancelled_bookings": len(bookings),
        })

        logger.info(
            "Subscription %s cancelled by %s — %d future bookings cancelled",
            sub.id, actor.id, len(bookings),
        )

        return await self._reload(sub.id)

    async def _reload(self, sub_id: uuid.UUID) -> SubscriptionRead:
        result = await self.db.execute(
            select(Subscription)
            .options(
                selectinload(Subscription.plan),
                selectinload(Subscription.payment),
                selectinload(Subscription.slots),
            )
            .where(Subscription.id == sub_id)
        )
        return SubscriptionRead.model_validate(result.scalar_one())

    # ─── Internals ──────────────────────────────────────

    async def _validate_no_conflicts(
        self,
        turf_id: uuid.UUID,
        day_of_week: int,
        start_time: time,
        end_time: time,
    ) -> None:
        first_date = _next_occurrence(day_of_week)
        for week in range(WEEKS_PER_MONTH):
            d = first_date + timedelta(days=7 * week)
            conflict = await self.conflict_checker.find_conflict(
                db=self.db, turf_id=turf_id,
                booking_date=d, start_time=start_time, end_time=end_time,
            )
            if conflict:
                raise ValidationError(
                    f"Slot conflicts with an existing booking on {d.isoformat()}."
                )

        # Existing subscription slot overlap on the same day_of_week
        result = await self.db.execute(
            select(SubscriptionSlot)
            .join(Subscription, SubscriptionSlot.subscription_id == Subscription.id)
            .where(and_(
                Subscription.turf_id == turf_id,
                Subscription.status.in_(["pending", "active"]),
                SubscriptionSlot.day_of_week == day_of_week,
                SubscriptionSlot.start_time < end_time,
                SubscriptionSlot.end_time > start_time,
            ))
        )
        if result.scalar_one_or_none():
            raise ValidationError(
                "An active subscription already covers this slot."
            )

    async def _create_weekly_bookings(self, sub: Subscription) -> None:
        """Insert bookings for each (slot × 4 weeks) combination."""
        first_date = sub.starts_on or date.today()
        for slot in sub.slots:
            duration_mins = (
                _to_min(slot.end_time) - _to_min(slot.start_time)
            )
            slot_first = _next_occurrence(slot.day_of_week, from_day=first_date)

            for week in range(WEEKS_PER_MONTH):
                booking_date = slot_first + timedelta(days=7 * week)
                existing = await self.conflict_checker.find_conflict(
                    db=self.db, turf_id=sub.turf_id,
                    booking_date=booking_date,
                    start_time=slot.start_time, end_time=slot.end_time,
                )
                if existing:
                    logger.warning(
                        "Subscription %s skipped recurring booking on %s — slot taken.",
                        sub.id, booking_date,
                    )
                    continue

                booking = Booking(
                    tenant_id=sub.tenant_id,
                    turf_id=sub.turf_id,
                    user_id=sub.user_id,
                    subscription_id=sub.id,
                    booking_date=booking_date,
                    start_time=slot.start_time,
                    end_time=slot.end_time,
                    duration_mins=duration_mins,
                    status="confirmed",
                    booking_type="subscription",
                    base_price=0,
                    discount_amount=0,
                    tax_amount=0,
                    final_price=0,
                    notes=f"Auto-created from subscription {sub.id}",
                )
                self.db.add(booking)


def _parse_time(s: str) -> time:
    parts = s.split(":")
    h = int(parts[0])
    m = int(parts[1]) if len(parts) > 1 else 0
    return time(h, m)
