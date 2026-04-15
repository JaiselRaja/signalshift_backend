"""
Availability engine: generates virtual slots from rules and marks conflicts.

This module is the core of the real-time availability system.
It follows a "generate all possible → subtract occupied" strategy.
"""

from __future__ import annotations

import json
import logging
from datetime import date, time, timedelta
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.bookings.models import Booking
from app.shared.constants import (
    CACHE_TTL_AVAILABILITY_BEYOND,
    CACHE_TTL_AVAILABILITY_TODAY,
    CACHE_TTL_AVAILABILITY_WEEK,
)
from app.turfs.models import SlotOverride, TurfSlotRule
from app.turfs.schemas import AvailableSlot

logger = logging.getLogger(__name__)


class AvailabilityEngine:
    """Computes available slots from rules, overrides, and bookings."""

    def __init__(self, db: AsyncSession, cache=None):
        self.db = db
        self.cache = cache

    async def compute_availability(
        self,
        turf_id: UUID,
        target_date: date,
        sport_type: str | None = None,
    ) -> list[AvailableSlot]:
        """
        Generate all available slots for a turf on a given date.

        Steps:
        1. Load slot rules for turf + matching day_of_week
        2. Load date-specific overrides
        3. Generate virtual time slots from rules
        4. Load confirmed/pending bookings for conflict check
        5. Mark occupied slots
        6. Return list with availability status
        """

        day_of_week = target_date.weekday()  # 0=Mon, 6=Sun

        # Step 1: Load slot rules
        rules = await self._load_slot_rules(turf_id, day_of_week, target_date)

        # Step 2: Load overrides
        overrides = await self._load_overrides(turf_id, target_date)

        # Step 3: Generate virtual slots
        virtual_slots = self._generate_slots(rules, target_date, overrides)

        # Step 4: Load active bookings
        bookings = await self._load_active_bookings(turf_id, target_date)

        # Step 5: Mark conflicts
        result = self._mark_conflicts(virtual_slots, bookings)

        return result

    async def compute_availability_range(
        self,
        turf_id: UUID,
        start_date: date,
        end_date: date,
    ) -> dict[str, list[AvailableSlot]]:
        """Compute availability for a date range (max 14 days)."""
        result = {}
        current = start_date
        while current <= end_date:
            slots = await self.compute_availability(turf_id, current)
            result[current.isoformat()] = slots
            current += timedelta(days=1)
        return result

    # ─── Private helpers ─────────────────────────────

    async def _load_slot_rules(
        self, turf_id: UUID, day_of_week: int, target_date: date
    ) -> list[TurfSlotRule]:
        result = await self.db.execute(
            select(TurfSlotRule)
            .where(and_(
                TurfSlotRule.turf_id == turf_id,
                TurfSlotRule.day_of_week == day_of_week,
                TurfSlotRule.is_active.is_(True),
            ))
            .order_by(TurfSlotRule.start_time)
        )
        rules = list(result.scalars().all())

        # Filter by validity window
        return [
            r for r in rules
            if (not r.valid_from or target_date >= r.valid_from)
            and (not r.valid_until or target_date <= r.valid_until)
        ]

    async def _load_overrides(
        self, turf_id: UUID, target_date: date
    ) -> list[SlotOverride]:
        result = await self.db.execute(
            select(SlotOverride).where(and_(
                SlotOverride.turf_id == turf_id,
                SlotOverride.override_date == target_date,
            ))
        )
        return list(result.scalars().all())

    async def _load_active_bookings(
        self, turf_id: UUID, target_date: date
    ) -> list[Booking]:
        result = await self.db.execute(
            select(Booking).where(and_(
                Booking.turf_id == turf_id,
                Booking.booking_date == target_date,
                Booking.status.in_(["pending", "confirmed"]),
            ))
        )
        return list(result.scalars().all())

    def _generate_slots(
        self,
        rules: list[TurfSlotRule],
        target_date: date,
        overrides: list[SlotOverride],
    ) -> list[AvailableSlot]:
        """
        For each rule, step through [start_time, end_time) by duration_mins.
        Skip slots that are blocked by overrides.
        """
        blocked_ranges = set()
        price_overrides: dict[tuple[time, time], Decimal] = {}

        for ovr in overrides:
            if ovr.override_type == "blocked" and ovr.start_time and ovr.end_time:
                blocked_ranges.add((ovr.start_time, ovr.end_time))
            elif ovr.override_type == "price_change" and ovr.start_time and ovr.end_time:
                if ovr.override_price is not None:
                    price_overrides[(ovr.start_time, ovr.end_time)] = Decimal(
                        str(ovr.override_price)
                    )

        # Check if the entire date is blocked
        full_day_blocked = any(
            ovr.override_type == "blocked" and ovr.start_time is None
            for ovr in overrides
        )
        if full_day_blocked:
            return []

        slots: list[AvailableSlot] = []

        for rule in rules:
            if rule.slot_type in ("blocked", "maintenance"):
                continue

            cursor = rule.start_time
            while cursor < rule.end_time:
                slot_end = _add_minutes(cursor, rule.duration_mins)
                if slot_end > rule.end_time:
                    break

                # Skip blocked overrides
                is_blocked = any(
                    cursor < b_end and slot_end > b_start
                    for b_start, b_end in blocked_ranges
                )
                if is_blocked:
                    cursor = slot_end
                    continue

                # Check for price override
                base = Decimal(str(rule.base_price))
                for (p_start, p_end), p_price in price_overrides.items():
                    if cursor >= p_start and slot_end <= p_end:
                        base = p_price
                        break

                slots.append(AvailableSlot(
                    date=target_date,
                    start_time=cursor,
                    end_time=slot_end,
                    duration_mins=rule.duration_mins,
                    slot_type=rule.slot_type,
                    base_price=base,
                    computed_price=base,  # Will be refined by pricing engine
                    is_available=True,
                    remaining_capacity=rule.max_capacity,
                ))

                cursor = slot_end

        return slots

    def _mark_conflicts(
        self,
        slots: list[AvailableSlot],
        bookings: list[Booking],
    ) -> list[AvailableSlot]:
        """
        Time-range overlap check:
        A overlaps B ⟺ A.start < B.end AND A.end > B.start
        """
        for slot in slots:
            for bk in bookings:
                if slot.start_time < bk.end_time and slot.end_time > bk.start_time:
                    slot.remaining_capacity -= 1
                    if slot.remaining_capacity <= 0:
                        slot.is_available = False
                        break
        return slots


def _add_minutes(t: time, mins: int) -> time:
    """Add minutes to a time object, handling hour overflow."""
    total_mins = t.hour * 60 + t.minute + mins
    hours = total_mins // 60
    minutes = total_mins % 60
    if hours >= 24:
        hours = 23
        minutes = 59
    return time(hours, minutes)
