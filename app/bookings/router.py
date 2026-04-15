"""Booking API routes."""

from __future__ import annotations

import uuid
from datetime import date

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user, require_roles
from app.bookings.schemas import (
    BookingCancel, BookingCreate, BookingRead,
    CancellationPolicyCreate, CancellationPolicyRead,
    PriceBreakdown, PricingRuleCreate, PricingRuleRead,
)
from app.bookings.service import BookingService
from app.bookings.models import CancellationPolicy, PricingRule
from app.core.database import get_async_session
from app.shared.types import UserRole
from app.users.models import User

router = APIRouter(prefix="/bookings", tags=["Bookings"])


def _get_service(db: AsyncSession = Depends(get_async_session)) -> BookingService:
    return BookingService(db)


# ─── Booking CRUD ────────────────────────────────────

@router.post("/", response_model=BookingRead, status_code=status.HTTP_201_CREATED)
async def create_booking(
    body: BookingCreate,
    current_user: User = Depends(get_current_user),
    svc: BookingService = Depends(_get_service),
):
    """
    Create a booking with atomic conflict prevention.
    Uses advisory locking + overlap detection.
    Auth: any authenticated user.
    """
    return await svc.create_booking(current_user, body)


@router.post("/preview-price", response_model=PriceBreakdown)
async def preview_price(
    body: BookingCreate,
    current_user: User = Depends(get_current_user),
    svc: BookingService = Depends(_get_service),
):
    """Preview price breakdown without creating a booking."""
    return await svc.preview_price(current_user, body)


@router.get("/my", response_model=list[BookingRead])
async def my_bookings(
    current_user: User = Depends(get_current_user),
    svc: BookingService = Depends(_get_service),
):
    """Get current user's bookings. Auth: any authenticated user."""
    return await svc.get_user_bookings(current_user.id)


@router.get("/turf/{turf_id}", response_model=list[BookingRead])
async def turf_bookings(
    turf_id: uuid.UUID,
    target_date: date | None = Query(None),
    _=Depends(require_roles(UserRole.TURF_ADMIN, UserRole.SUPER_ADMIN)),
    svc: BookingService = Depends(_get_service),
):
    """List bookings for a turf. Auth: turf_admin or super_admin."""
    return await svc.get_turf_bookings(turf_id, target_date)


@router.post("/{booking_id}/cancel", response_model=BookingRead)
async def cancel_booking(
    booking_id: uuid.UUID,
    body: BookingCancel,
    current_user: User = Depends(get_current_user),
    svc: BookingService = Depends(_get_service),
):
    """
    Cancel a booking with automatic refund computation.
    Auth: booking owner or turf_admin / super_admin.
    """
    return await svc.cancel_booking(current_user, booking_id, body)


@router.patch("/{booking_id}/confirm", response_model=BookingRead)
async def confirm_booking(
    booking_id: uuid.UUID,
    current_user: User = Depends(require_roles(UserRole.TURF_ADMIN, UserRole.SUPER_ADMIN)),
    svc: BookingService = Depends(_get_service),
):
    """Confirm a pending booking. Auth: turf_admin or super_admin."""
    return await svc.transition_status(booking_id, "confirmed", current_user)


@router.patch("/{booking_id}/complete", response_model=BookingRead)
async def complete_booking(
    booking_id: uuid.UUID,
    current_user: User = Depends(require_roles(UserRole.TURF_ADMIN, UserRole.SUPER_ADMIN)),
    svc: BookingService = Depends(_get_service),
):
    """Mark booking as completed. Auth: turf_admin or super_admin."""
    return await svc.transition_status(booking_id, "completed", current_user)


@router.patch("/{booking_id}/no-show", response_model=BookingRead)
async def mark_no_show(
    booking_id: uuid.UUID,
    current_user: User = Depends(require_roles(UserRole.TURF_ADMIN, UserRole.SUPER_ADMIN)),
    svc: BookingService = Depends(_get_service),
):
    """Mark booking as no-show. Auth: turf_admin or super_admin."""
    return await svc.transition_status(booking_id, "no_show", current_user)


# ─── Pricing Rules ───────────────────────────────────

@router.post(
    "/pricing-rules/{turf_id}",
    response_model=PricingRuleRead,
    status_code=201,
    tags=["Pricing"],
)
async def create_pricing_rule(
    turf_id: uuid.UUID,
    body: PricingRuleCreate,
    _=Depends(require_roles(UserRole.TURF_ADMIN, UserRole.SUPER_ADMIN)),
    db: AsyncSession = Depends(get_async_session),
):
    """Create a pricing rule for a turf. Auth: turf_admin or super_admin."""
    rule = PricingRule(turf_id=turf_id, **body.model_dump())
    db.add(rule)
    await db.commit()
    await db.refresh(rule)
    return PricingRuleRead.model_validate(rule)


# ─── Cancellation Policies ───────────────────────────

@router.post(
    "/cancellation-policies/{turf_id}",
    response_model=CancellationPolicyRead,
    status_code=201,
    tags=["Cancellation"],
)
async def create_cancellation_policy(
    turf_id: uuid.UUID,
    body: CancellationPolicyCreate,
    _=Depends(require_roles(UserRole.TURF_ADMIN, UserRole.SUPER_ADMIN)),
    db: AsyncSession = Depends(get_async_session),
):
    """Create a cancellation policy for a turf. Auth: turf_admin or super_admin."""
    policy = CancellationPolicy(turf_id=turf_id, **body.model_dump())
    db.add(policy)
    await db.commit()
    await db.refresh(policy)
    return CancellationPolicyRead.model_validate(policy)
