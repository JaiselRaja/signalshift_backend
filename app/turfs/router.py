"""Turf API routes: CRUD, slot rules, overrides, availability."""

from __future__ import annotations

import uuid
from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user, require_roles, resolve_tenant
from app.core.database import get_async_session
from app.shared.types import UserRole
from app.tenants.models import Tenant
from app.turfs.availability import AvailabilityEngine
from app.turfs.schemas import (
    AvailableSlot, SlotOverrideCreate, SlotOverrideRead,
    SlotRuleCreate, SlotRuleRead, SlotRuleUpdate,
    TurfCreate, TurfRead, TurfUpdate,
)
from app.turfs.service import TurfService
from app.users.models import User

router = APIRouter(prefix="/turfs", tags=["Turfs"])


def _get_service(db: AsyncSession = Depends(get_async_session)) -> TurfService:
    return TurfService(db)


def _get_availability(db: AsyncSession = Depends(get_async_session)) -> AvailabilityEngine:
    return AvailabilityEngine(db)


# ─── Turf CRUD ───────────────────────────────────────

@router.post("/", response_model=TurfRead, status_code=201)
async def create_turf(
    body: TurfCreate,
    current_user: User = Depends(require_roles(UserRole.TURF_ADMIN, UserRole.SUPER_ADMIN)),
    svc: TurfService = Depends(_get_service),
):
    """Create a new turf. Auth: turf_admin or super_admin."""
    return await svc.create_turf(current_user.tenant_id, body)


@router.get("/", response_model=list[TurfRead])
async def list_turfs(
    city: str | None = Query(None),
    tenant: Tenant = Depends(resolve_tenant),
    svc: TurfService = Depends(_get_service),
):
    """List turfs in the current tenant. Public (tenant resolved via X-Tenant-Slug header)."""
    return await svc.list_turfs(tenant.id, city)


@router.get("/{turf_id}", response_model=TurfRead)
async def get_turf(
    turf_id: uuid.UUID,
    _: Tenant = Depends(resolve_tenant),
    svc: TurfService = Depends(_get_service),
):
    """Get turf details. Public."""
    return await svc.get_turf(turf_id)


@router.patch("/{turf_id}", response_model=TurfRead)
async def update_turf(
    turf_id: uuid.UUID,
    body: TurfUpdate,
    _=Depends(require_roles(UserRole.TURF_ADMIN, UserRole.SUPER_ADMIN)),
    svc: TurfService = Depends(_get_service),
):
    """Update turf. Auth: turf_admin or super_admin."""
    return await svc.update_turf(turf_id, body)


# ─── Slot Rules ──────────────────────────────────────

@router.post("/{turf_id}/slot-rules", response_model=SlotRuleRead, status_code=201)
async def create_slot_rule(
    turf_id: uuid.UUID,
    body: SlotRuleCreate,
    _=Depends(require_roles(UserRole.TURF_ADMIN, UserRole.SUPER_ADMIN)),
    svc: TurfService = Depends(_get_service),
):
    """Add a slot rule to a turf. Auth: turf_admin or super_admin."""
    return await svc.create_slot_rule(turf_id, body)


@router.get("/{turf_id}/slot-rules", response_model=list[SlotRuleRead])
async def list_slot_rules(
    turf_id: uuid.UUID,
    _=Depends(get_current_user),
    svc: TurfService = Depends(_get_service),
):
    """List all slot rules for a turf."""
    return await svc.list_slot_rules(turf_id)


@router.patch("/slot-rules/{rule_id}", response_model=SlotRuleRead)
async def update_slot_rule(
    rule_id: uuid.UUID,
    body: SlotRuleUpdate,
    _=Depends(require_roles(UserRole.TURF_ADMIN, UserRole.SUPER_ADMIN)),
    svc: TurfService = Depends(_get_service),
):
    """Update a slot rule. Auth: turf_admin or super_admin."""
    return await svc.update_slot_rule(rule_id, body)


@router.delete("/slot-rules/{rule_id}", status_code=204)
async def delete_slot_rule(
    rule_id: uuid.UUID,
    _=Depends(require_roles(UserRole.TURF_ADMIN, UserRole.SUPER_ADMIN)),
    svc: TurfService = Depends(_get_service),
):
    """Delete a slot rule. Auth: turf_admin or super_admin."""
    await svc.delete_slot_rule(rule_id)


# ─── Overrides ───────────────────────────────────────

@router.post("/{turf_id}/overrides", response_model=SlotOverrideRead, status_code=201)
async def create_override(
    turf_id: uuid.UUID,
    body: SlotOverrideCreate,
    _=Depends(require_roles(UserRole.TURF_ADMIN, UserRole.SUPER_ADMIN)),
    svc: TurfService = Depends(_get_service),
):
    """Create a date-specific override. Auth: turf_admin or super_admin."""
    return await svc.create_override(turf_id, body)


@router.get("/{turf_id}/overrides", response_model=list[SlotOverrideRead])
async def list_overrides(
    turf_id: uuid.UUID,
    _=Depends(require_roles(UserRole.TURF_ADMIN, UserRole.SUPER_ADMIN)),
    svc: TurfService = Depends(_get_service),
):
    """List overrides for a turf. Auth: turf_admin or super_admin."""
    return await svc.list_overrides(turf_id)


@router.delete("/overrides/{override_id}", status_code=204)
async def delete_override(
    override_id: uuid.UUID,
    _=Depends(require_roles(UserRole.TURF_ADMIN, UserRole.SUPER_ADMIN)),
    svc: TurfService = Depends(_get_service),
):
    """Delete a slot override. Auth: turf_admin or super_admin."""
    await svc.delete_override(override_id)


# ─── Availability ────────────────────────────────────

@router.get("/{turf_id}/availability", response_model=list[AvailableSlot])
async def get_availability(
    turf_id: uuid.UUID,
    target_date: date = Query(..., description="Date to check availability"),
    sport_type: str | None = Query(None),
    _: Tenant = Depends(resolve_tenant),
    engine: AvailabilityEngine = Depends(_get_availability),
):
    """Real-time slot availability. Public."""
    return await engine.compute_availability(turf_id, target_date, sport_type)


@router.get(
    "/{turf_id}/availability/range",
    response_model=dict[str, list[AvailableSlot]],
)
async def get_availability_range(
    turf_id: uuid.UUID,
    start_date: date = Query(...),
    end_date: date = Query(...),
    _: Tenant = Depends(resolve_tenant),
    engine: AvailabilityEngine = Depends(_get_availability),
):
    """Availability for a date range (max 14 days). Public."""
    if (end_date - start_date).days > 14 or end_date < start_date:
        from fastapi import HTTPException
        raise HTTPException(400, "Range must be 0–14 days")
    return await engine.compute_availability_range(turf_id, start_date, end_date)
