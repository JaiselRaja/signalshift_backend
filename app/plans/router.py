"""Plan API routes — public list + admin CRUD."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import require_roles, resolve_tenant
from app.core.database import get_async_session
from app.plans.schemas import PlanCreate, PlanRead, PlanUpdate
from app.plans.service import PlanService
from app.tenants.models import Tenant
from app.users.models import User

router = APIRouter(prefix="/plans", tags=["Plans"])


def _get_service(db: AsyncSession = Depends(get_async_session)) -> PlanService:
    return PlanService(db)


@router.get("/", response_model=list[PlanRead])
async def list_plans(
    tenant: Tenant = Depends(resolve_tenant),
    svc: PlanService = Depends(_get_service),
):
    """Public list — active plans only, sorted for display."""
    return await svc.list_public(tenant.id)


@router.get("/admin", response_model=list[PlanRead])
async def list_plans_admin(
    current_user: User = Depends(require_roles("super_admin", "turf_admin")),
    svc: PlanService = Depends(_get_service),
):
    """Admin list — includes inactive plans."""
    return await svc.list_admin(current_user.tenant_id)


@router.post("/", response_model=PlanRead, status_code=201)
async def create_plan(
    body: PlanCreate,
    current_user: User = Depends(require_roles("super_admin", "turf_admin")),
    svc: PlanService = Depends(_get_service),
):
    return await svc.create(current_user.tenant_id, body)


@router.get("/{plan_id}", response_model=PlanRead)
async def get_plan(
    plan_id: uuid.UUID,
    current_user: User = Depends(require_roles("super_admin", "turf_admin")),
    svc: PlanService = Depends(_get_service),
):
    return await svc.get(plan_id)


@router.patch("/{plan_id}", response_model=PlanRead)
async def update_plan(
    plan_id: uuid.UUID,
    body: PlanUpdate,
    current_user: User = Depends(require_roles("super_admin", "turf_admin")),
    svc: PlanService = Depends(_get_service),
):
    return await svc.update(plan_id, body)


@router.delete("/{plan_id}", status_code=204)
async def delete_plan(
    plan_id: uuid.UUID,
    current_user: User = Depends(require_roles("super_admin", "turf_admin")),
    svc: PlanService = Depends(_get_service),
):
    await svc.delete(plan_id)
