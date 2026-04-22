"""
Transactional email handlers.

Subscribed to domain events via the event bus. Each handler opens its
own DB session (event handlers run as fire-and-forget tasks after the
originating request has returned), loads the entities it needs, renders
an HTML template, and hands it to SendGridClient.send.

Failures are logged but never re-raised — a missed email must never
roll back a booking, payment, or team change.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.bookings.models import Booking
from app.config import settings
from app.core.database import async_session_factory
from app.core.email_sendgrid import get_sendgrid_client
from app.core.email_templates import (
    admin_new_booking,
    booking_cancelled as tpl_booking_cancelled,
    booking_confirmed as tpl_booking_confirmed,
    booking_created as tpl_booking_created,
    payment_rejected as tpl_payment_rejected,
    payment_verified as tpl_payment_verified,
    team_invitation as tpl_team_invitation,
    team_member_added as tpl_team_member_added,
    tournament_registered as tpl_tournament_registered,
)
from app.payments.models import PaymentTransaction
from app.teams.models import Team
from app.tournaments.models import Tournament
from app.turfs.models import Turf
from app.users.models import User

logger = logging.getLogger(__name__)


# ─── Low-level helper ────────────────────────────────────

async def _send(to_email: str, to_name: str, subject: str, html: str, text: str) -> None:
    if not to_email:
        return
    client = get_sendgrid_client()
    if not client.configured:
        logger.info("SendGrid not configured — would have sent '%s' to %s", subject, to_email)
        return
    await client.send(
        to_email=to_email, to_name=to_name or to_email,
        subject=subject, html=html, text=text,
    )


async def _load_booking_context(session, booking_id: str) -> tuple[Booking, Turf, User] | None:
    """Fetch booking + turf + user in a single round-trip. Returns None if missing."""
    try:
        bid = uuid.UUID(booking_id)
    except (ValueError, TypeError):
        return None

    result = await session.execute(
        select(Booking)
        .options(selectinload(Booking.turf), selectinload(Booking.user))
        .where(Booking.id == bid)
    )
    booking = result.scalar_one_or_none()
    if not booking:
        return None
    return booking, booking.turf, booking.user


# ─── Booking lifecycle ───────────────────────────────────

async def on_booking_created(payload: dict[str, Any]) -> None:
    async with async_session_factory() as session:
        ctx = await _load_booking_context(session, payload.get("booking_id"))
        if not ctx:
            return
        booking, turf, user = ctx
        if user and user.email:
            subject, html, text = tpl_booking_created(
                user_name=user.full_name or "",
                turf_name=turf.name if turf else "your turf",
                booking_date=booking.booking_date,
                start_time=booking.start_time,
                end_time=booking.end_time,
                final_price=booking.final_price,
                booking_id=str(booking.id),
                upi_vpa=settings.upi_vpa or None,
            )
            await _send(user.email, user.full_name or "", subject, html, text)

        # Admin alert (optional — only if env var set)
        if settings.admin_notification_email:
            subject, html, text = admin_new_booking(
                user_name=user.full_name or "",
                user_email=user.email or "",
                user_phone=user.phone,
                turf_name=turf.name if turf else "—",
                booking_date=booking.booking_date,
                start_time=booking.start_time,
                end_time=booking.end_time,
                final_price=booking.final_price,
                booking_id=str(booking.id),
            )
            await _send(settings.admin_notification_email, "Signal Shift Admin", subject, html, text)


async def on_booking_confirmed(payload: dict[str, Any]) -> None:
    async with async_session_factory() as session:
        ctx = await _load_booking_context(session, payload.get("booking_id"))
        if not ctx:
            return
        booking, turf, user = ctx
        if not user or not user.email:
            return
        subject, html, text = tpl_booking_confirmed(
            user_name=user.full_name or "",
            turf_name=turf.name if turf else "your turf",
            booking_date=booking.booking_date,
            start_time=booking.start_time,
            end_time=booking.end_time,
            final_price=booking.final_price,
            booking_id=str(booking.id),
        )
        await _send(user.email, user.full_name or "", subject, html, text)


async def on_booking_cancelled(payload: dict[str, Any]) -> None:
    async with async_session_factory() as session:
        ctx = await _load_booking_context(session, payload.get("booking_id"))
        if not ctx:
            return
        booking, turf, user = ctx
        if not user or not user.email:
            return
        subject, html, text = tpl_booking_cancelled(
            user_name=user.full_name or "",
            turf_name=turf.name if turf else "your turf",
            booking_date=booking.booking_date,
            start_time=booking.start_time,
            end_time=booking.end_time,
            refund_amount=payload.get("refund_amount") or booking.refund_amount or 0,
            refund_pct=payload.get("refund_pct"),
            booking_id=str(booking.id),
        )
        await _send(user.email, user.full_name or "", subject, html, text)


# ─── Payment lifecycle ───────────────────────────────────

async def _load_payment_context(session, txn_id: str) -> tuple[PaymentTransaction, Booking, Turf, User] | None:
    try:
        pid = uuid.UUID(txn_id)
    except (ValueError, TypeError):
        return None
    txn = await session.get(PaymentTransaction, pid)
    if not txn:
        return None
    ctx = await _load_booking_context(session, str(txn.booking_id))
    if not ctx:
        return None
    booking, turf, user = ctx
    return txn, booking, turf, user


async def on_payment_verified(payload: dict[str, Any]) -> None:
    async with async_session_factory() as session:
        ctx = await _load_payment_context(session, payload.get("txn_id"))
        if not ctx:
            return
        txn, booking, turf, user = ctx
        if not user or not user.email:
            return
        subject, html, text = tpl_payment_verified(
            user_name=user.full_name or "",
            amount=txn.amount,
            utr=txn.utr,
            booking_ref=str(booking.id),
            turf_name=turf.name if turf else "your turf",
        )
        await _send(user.email, user.full_name or "", subject, html, text)


async def on_payment_rejected(payload: dict[str, Any]) -> None:
    async with async_session_factory() as session:
        ctx = await _load_payment_context(session, payload.get("txn_id"))
        if not ctx:
            return
        txn, booking, turf, user = ctx
        if not user or not user.email:
            return
        subject, html, text = tpl_payment_rejected(
            user_name=user.full_name or "",
            amount=txn.amount,
            utr=txn.utr,
            booking_ref=str(booking.id),
            turf_name=turf.name if turf else "your turf",
            reason=payload.get("reason") or txn.reject_reason or "—",
        )
        await _send(user.email, user.full_name or "", subject, html, text)


# ─── Team lifecycle ──────────────────────────────────────

async def on_team_member_added(payload: dict[str, Any]) -> None:
    team_id = payload.get("team_id")
    new_user_id = payload.get("new_user_id")
    inviter_id = payload.get("inviter_id")
    if not team_id or not new_user_id:
        return
    async with async_session_factory() as session:
        try:
            team = await session.get(Team, uuid.UUID(team_id))
            new_user = await session.get(User, uuid.UUID(new_user_id))
            inviter = await session.get(User, uuid.UUID(inviter_id)) if inviter_id else None
        except (ValueError, TypeError):
            return
        if not team or not new_user or not new_user.email:
            return
        subject, html, text = tpl_team_member_added(
            new_member_name=new_user.full_name or "",
            team_name=team.name,
            inviter_name=(inviter.full_name if inviter else "A teammate"),
        )
        await _send(new_user.email, new_user.full_name or "", subject, html, text)


async def on_team_invitation(payload: dict[str, Any]) -> None:
    team_id = payload.get("team_id")
    invitee_email = payload.get("invitee_email")
    inviter_id = payload.get("inviter_id")
    if not team_id or not invitee_email:
        return
    async with async_session_factory() as session:
        try:
            team = await session.get(Team, uuid.UUID(team_id))
            inviter = await session.get(User, uuid.UUID(inviter_id)) if inviter_id else None
        except (ValueError, TypeError):
            return
        if not team:
            return
        subject, html, text = tpl_team_invitation(
            invitee_email=invitee_email,
            team_name=team.name,
            inviter_name=(inviter.full_name if inviter else "A teammate"),
        )
        await _send(invitee_email, invitee_email, subject, html, text)


# ─── Tournament lifecycle ────────────────────────────────

async def on_tournament_registered(payload: dict[str, Any]) -> None:
    tournament_id = payload.get("tournament_id")
    team_id = payload.get("team_id")
    captain_id = payload.get("captain_id")
    if not tournament_id or not team_id:
        return
    async with async_session_factory() as session:
        try:
            tournament = await session.get(Tournament, uuid.UUID(tournament_id))
            team = await session.get(Team, uuid.UUID(team_id))
            captain = await session.get(User, uuid.UUID(captain_id)) if captain_id else None
        except (ValueError, TypeError):
            return
        if not tournament or not team or not captain or not captain.email:
            return
        subject, html, text = tpl_tournament_registered(
            captain_name=captain.full_name or "",
            tournament_name=tournament.name,
            team_name=team.name,
            starts_on=tournament.tournament_starts,
            entry_fee=tournament.entry_fee,
            payment_status=payload.get("payment_status") or "unpaid",
        )
        await _send(captain.email, captain.full_name or "", subject, html, text)
