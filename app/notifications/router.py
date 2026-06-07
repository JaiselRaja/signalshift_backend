"""Admin notification recipients API."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import require_roles
from app.core.database import get_async_session
from app.notifications.models import AdminNotificationRecipient
from app.notifications.schemas import (
    AdminRecipientCreate,
    AdminRecipientRead,
    AdminRecipientUpdate,
)
from app.shared.types import UserRole
from app.users.models import User

router = APIRouter(prefix="/notifications", tags=["Notifications"])


@router.get("/recipients", response_model=list[AdminRecipientRead])
async def list_recipients(
    current_user: User = Depends(require_roles(UserRole.TURF_ADMIN, UserRole.SUPER_ADMIN)),
    db: AsyncSession = Depends(get_async_session),
):
    """List admin notification recipients for the current tenant."""
    result = await db.execute(
        select(AdminNotificationRecipient)
        .where(AdminNotificationRecipient.tenant_id == current_user.tenant_id)
        .order_by(AdminNotificationRecipient.email)
    )
    return [AdminRecipientRead.model_validate(r) for r in result.scalars().all()]


@router.post("/recipients", response_model=AdminRecipientRead, status_code=201)
async def create_recipient(
    body: AdminRecipientCreate,
    current_user: User = Depends(require_roles(UserRole.TURF_ADMIN, UserRole.SUPER_ADMIN)),
    db: AsyncSession = Depends(get_async_session),
):
    """Add a recipient. Duplicate email for the tenant returns 409."""
    recipient = AdminNotificationRecipient(
        tenant_id=current_user.tenant_id,
        email=body.email.lower(),
        label=body.label,
        is_active=body.is_active,
    )
    db.add(recipient)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="This email is already in the list.")
    await db.refresh(recipient)
    return AdminRecipientRead.model_validate(recipient)


@router.patch("/recipients/{recipient_id}", response_model=AdminRecipientRead)
async def update_recipient(
    recipient_id: uuid.UUID,
    body: AdminRecipientUpdate,
    current_user: User = Depends(require_roles(UserRole.TURF_ADMIN, UserRole.SUPER_ADMIN)),
    db: AsyncSession = Depends(get_async_session),
):
    """Update label or active flag. Email is immutable; delete + recreate to change it."""
    recipient = await db.get(AdminNotificationRecipient, recipient_id)
    if not recipient or recipient.tenant_id != current_user.tenant_id:
        raise HTTPException(status_code=404, detail="Recipient not found")
    updates = body.model_dump(exclude_unset=True)
    for field, value in updates.items():
        setattr(recipient, field, value)
    await db.commit()
    await db.refresh(recipient)
    return AdminRecipientRead.model_validate(recipient)


@router.delete("/recipients/{recipient_id}", status_code=204)
async def delete_recipient(
    recipient_id: uuid.UUID,
    current_user: User = Depends(require_roles(UserRole.TURF_ADMIN, UserRole.SUPER_ADMIN)),
    db: AsyncSession = Depends(get_async_session),
):
    """Delete a recipient."""
    recipient = await db.get(AdminNotificationRecipient, recipient_id)
    if not recipient or recipient.tenant_id != current_user.tenant_id:
        raise HTTPException(status_code=404, detail="Recipient not found")
    await db.delete(recipient)
    await db.commit()
