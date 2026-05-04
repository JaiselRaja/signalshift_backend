"""Subscription API routes."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user, require_roles
from app.core.database import get_async_session
from app.subscriptions.schemas import (
    AvailabilitySlot,
    SubscriptionInitiate,
    SubscriptionInitiateResponse,
    SubscriptionRead,
    SubscriptionSubmitUtr,
)
from app.subscriptions.service import SubscriptionService
from app.users.models import User

router = APIRouter(prefix="/subscriptions", tags=["Subscriptions"])


def _get_service(db: AsyncSession = Depends(get_async_session)) -> SubscriptionService:
    return SubscriptionService(db)


@router.get("/availability", response_model=list[AvailabilitySlot])
async def get_availability(
    turf_id: uuid.UUID = Query(...),
    day_of_week: int = Query(..., ge=0, le=6),
    duration_mins: int = Query(60, ge=15, le=240),
    plan_id: uuid.UUID | None = Query(None),
    _: User = Depends(get_current_user),
    svc: SubscriptionService = Depends(_get_service),
):
    """Return available start times for a recurring slot pick."""
    return await svc.availability(turf_id, day_of_week, duration_mins, plan_id)


@router.post("/initiate", response_model=SubscriptionInitiateResponse, status_code=201)
async def initiate_subscription(
    body: SubscriptionInitiate,
    current_user: User = Depends(get_current_user),
    svc: SubscriptionService = Depends(_get_service),
):
    """Create a pending subscription + UPI payment. Returns the deep-link/QR data."""
    return await svc.initiate(current_user, body)


@router.post("/submit-utr", response_model=SubscriptionRead)
async def submit_subscription_utr(
    body: SubscriptionSubmitUtr,
    current_user: User = Depends(get_current_user),
    svc: SubscriptionService = Depends(_get_service),
):
    """User uploads the UTR after completing UPI transfer."""
    return await svc.submit_utr(current_user, body)


@router.get("/me", response_model=list[SubscriptionRead])
async def list_my_subscriptions(
    current_user: User = Depends(get_current_user),
    svc: SubscriptionService = Depends(_get_service),
):
    return await svc.list_my(current_user.id)


class CancelBody(BaseModel):
    reason: str | None = None
    cancel_past: bool = False


@router.post("/{subscription_id}/cancel", response_model=SubscriptionRead)
async def cancel_subscription(
    subscription_id: uuid.UUID,
    body: CancelBody | None = None,
    current_user: User = Depends(get_current_user),
    svc: SubscriptionService = Depends(_get_service),
):
    """Cancel a subscription and all its future bookings.
    Owner or admin can call this."""
    body = body or CancelBody()
    return await svc.cancel(
        subscription_id, current_user,
        reason=body.reason, cancel_past=body.cancel_past,
    )


@router.get("/admin", response_model=list[SubscriptionRead])
async def list_all_subscriptions(
    current_user: User = Depends(require_roles("super_admin", "turf_admin")),
    svc: SubscriptionService = Depends(_get_service),
):
    """Admin view — every subscription in the tenant."""
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload
    from app.subscriptions.models import Subscription

    result = await svc.db.execute(
        select(Subscription)
        .options(
            selectinload(Subscription.plan),
            selectinload(Subscription.payment),
        )
        .where(Subscription.tenant_id == current_user.tenant_id)
        .order_by(Subscription.created_at.desc())
    )
    return [SubscriptionRead.model_validate(s) for s in result.scalars().all()]
