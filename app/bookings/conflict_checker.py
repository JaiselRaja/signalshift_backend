"""
Booking conflict checker — time-range overlap detection.

Two time ranges [S1, E1) and [S2, E2) overlap if and only if:
    S1 < E2 AND E1 > S2
"""

from __future__ import annotations

from datetime import date, time
from uuid import UUID

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.bookings.models import Booking


class ConflictChecker:
    """Detects overlapping bookings for a turf on a given date."""

    async def find_conflict(
        self,
        db: AsyncSession,
        turf_id: UUID,
        booking_date: date,
        start_time: time,
        end_time: time,
        exclude_booking_id: UUID | None = None,
    ) -> Booking | None:
        """
        Find the first booking that conflicts with the proposed time range.
        Returns None if no conflict exists.
        """
        query = (
            select(Booking)
            .where(and_(
                Booking.turf_id == turf_id,
                Booking.booking_date == booking_date,
                Booking.status.in_(["pending", "confirmed"]),
                # Time-range overlap predicate
                Booking.start_time < end_time,
                Booking.end_time > start_time,
            ))
            .limit(1)
        )

        if exclude_booking_id:
            query = query.where(Booking.id != exclude_booking_id)

        result = await db.execute(query)
        return result.scalar_one_or_none()

    async def has_conflict(
        self,
        db: AsyncSession,
        turf_id: UUID,
        booking_date: date,
        start_time: time,
        end_time: time,
    ) -> bool:
        """Quick boolean check for overlap."""
        conflict = await self.find_conflict(
            db, turf_id, booking_date, start_time, end_time
        )
        return conflict is not None
