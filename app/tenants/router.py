"""Tenant API routes."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import require_roles
from app.core.database import get_async_session
from app.shared.types import UserRole
from app.tenants.schemas import TenantCreate, TenantRead, TenantUpdate
from app.tenants.service import TenantService

router = APIRouter(prefix="/tenants", tags=["Tenants"])


def _get_service(db: AsyncSession = Depends(get_async_session)) -> TenantService:
    return TenantService(db)


@router.post("/", response_model=TenantRead, status_code=201)
async def create_tenant(
    body: TenantCreate,
    _=Depends(require_roles(UserRole.SUPER_ADMIN)),
    svc: TenantService = Depends(_get_service),
):
    """Create a new tenant. Auth: super_admin only."""
    return await svc.create_tenant(body)


@router.get("/", response_model=list[TenantRead])
async def list_tenants(
    _=Depends(require_roles(UserRole.SUPER_ADMIN)),
    svc: TenantService = Depends(_get_service),
):
    """List all tenants. Auth: super_admin only."""
    return await svc.list_tenants()


@router.get("/{tenant_id}", response_model=TenantRead)
async def get_tenant(
    tenant_id: uuid.UUID,
    _=Depends(require_roles(UserRole.SUPER_ADMIN)),
    svc: TenantService = Depends(_get_service),
):
    """Get a tenant by ID. Auth: super_admin only."""
    return await svc.get_tenant(tenant_id)


@router.patch("/{tenant_id}", response_model=TenantRead)
async def update_tenant(
    tenant_id: uuid.UUID,
    body: TenantUpdate,
    _=Depends(require_roles(UserRole.SUPER_ADMIN)),
    svc: TenantService = Depends(_get_service),
):
    """Update a tenant. Auth: super_admin only."""
    return await svc.update_tenant(tenant_id, body)
