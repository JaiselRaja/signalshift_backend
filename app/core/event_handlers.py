"""
Event bus handlers — registered at application startup.

Handles cache invalidation, logging, and notification triggers
for domain events emitted throughout the application.
"""

from __future__ import annotations

import logging
from typing import Any

from app.core.event_bus import event_bus

logger = logging.getLogger(__name__)


# ─── Cache Invalidation ─────────────────────────────────


async def invalidate_availability_cache(payload: dict[str, Any]) -> None:
    """Invalidate cached availability data when a booking changes."""
    from app.core.redis import get_redis

    turf_id = payload.get("turf_id")
    if not turf_id:
        return

    try:
        redis = get_redis()
        # Invalidate all availability cache entries for this turf
        pattern = f"availability:{turf_id}:*"
        cursor = 0
        while True:
            cursor, keys = await redis.scan(cursor, match=pattern, count=100)
            if keys:
                await redis.delete(*keys)
            if cursor == 0:
                break
        logger.info("Invalidated availability cache for turf %s", turf_id)
    except Exception:
        logger.warning("Failed to invalidate availability cache for turf %s", turf_id, exc_info=True)


# ─── Logging / Audit ────────────────────────────────────


async def log_booking_created(payload: dict[str, Any]) -> None:
    """Log booking creation for audit trail."""
    logger.info(
        "AUDIT: Booking %s created by user %s for turf %s on %s",
        payload.get("booking_id"),
        payload.get("user_id"),
        payload.get("turf_id"),
        payload.get("date"),
    )


async def log_booking_cancelled(payload: dict[str, Any]) -> None:
    """Log booking cancellation for audit trail."""
    logger.info(
        "AUDIT: Booking %s cancelled by user %s, refund: ₹%s (%s%%)",
        payload.get("booking_id"),
        payload.get("user_id"),
        payload.get("refund_amount"),
        payload.get("refund_pct"),
    )


async def log_payment_success(payload: dict[str, Any]) -> None:
    """Log successful payment."""
    logger.info(
        "AUDIT: Payment %s succeeded for booking %s",
        payload.get("txn_id"),
        payload.get("booking_id"),
    )


async def activate_subscription_on_payment(payload: dict[str, Any]) -> None:
    """If the payment is for a subscription, mark it active and create the
    weekly recurring bookings."""
    import uuid

    from app.core.database import async_session_factory
    from app.subscriptions.service import SubscriptionService

    txn_id = payload.get("txn_id")
    if not txn_id:
        return
    try:
        pid = uuid.UUID(txn_id)
    except (ValueError, TypeError):
        return

    async with async_session_factory() as session:
        svc = SubscriptionService(session)
        try:
            await svc.activate_after_payment(pid)
        except Exception:
            logger.exception("Failed to activate subscription for payment %s", pid)


async def log_payment_refunded(payload: dict[str, Any]) -> None:
    """Log refund processed."""
    logger.info(
        "AUDIT: Refund processed for booking %s, amount: ₹%s",
        payload.get("booking_id"),
        payload.get("refund_amount"),
    )


# ─── Registration ───────────────────────────────────────


def register_all_handlers() -> None:
    """Subscribe all handlers to the global event bus. Call once at startup."""

    # Email notifications live in app.core.notifications (SendGrid-backed).
    from app.core.notifications import (
        on_booking_cancelled,
        on_booking_confirmed,
        on_booking_created,
        on_payment_rejected,
        on_team_invitation,
        on_team_member_added,
        on_tournament_registered,
    )

    # Booking events
    event_bus.subscribe("booking.created", log_booking_created)
    event_bus.subscribe("booking.created", invalidate_availability_cache)
    event_bus.subscribe("booking.created", on_booking_created)

    event_bus.subscribe("booking.cancelled", log_booking_cancelled)
    event_bus.subscribe("booking.cancelled", invalidate_availability_cache)
    event_bus.subscribe("booking.cancelled", on_booking_cancelled)

    event_bus.subscribe("booking.confirmed", invalidate_availability_cache)
    event_bus.subscribe("booking.confirmed", on_booking_confirmed)

    event_bus.subscribe("booking.completed", invalidate_availability_cache)
    event_bus.subscribe("booking.no_show", invalidate_availability_cache)

    # Payment events — booking.confirmed carries the user-facing email,
    # so we don't also send a separate "payment received" note here.
    event_bus.subscribe("payment.success", log_payment_success)
    event_bus.subscribe("payment.success", activate_subscription_on_payment)
    event_bus.subscribe("payment.rejected", on_payment_rejected)
    event_bus.subscribe("payment.refunded", log_payment_refunded)

    # Team events
    event_bus.subscribe("team.member_added", on_team_member_added)
    event_bus.subscribe("team.invitation_sent", on_team_invitation)

    # Tournament events
    event_bus.subscribe("tournament.registered", on_tournament_registered)

    logger.info("All event handlers registered")
