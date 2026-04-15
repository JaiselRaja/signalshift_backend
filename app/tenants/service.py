"""Tenant business logic."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError
from app.tenants.models import Tenant
from app.tenants.schemas import TenantCreate, TenantRead, TenantUpdate


class TenantService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_tenant(self, data: TenantCreate) -> TenantRead:
        existing = await self.db.execute(
            select(Tenant).where(Tenant.slug == data.slug)
        )
        if existing.scalar_one_or_none():
            raise ConflictError(f"Tenant with slug '{data.slug}' already exists")

        tenant = Tenant(**data.model_dump())
        self.db.add(tenant)
        await self.db.commit()
        await self.db.refresh(tenant)
        return TenantRead.model_validate(tenant)

    async def get_tenant(self, tenant_id: uuid.UUID) -> TenantRead:
        tenant = await self.db.get(Tenant, tenant_id)
        if not tenant:
            raise NotFoundError("Tenant", str(tenant_id))
        return TenantRead.model_validate(tenant)

    async def update_tenant(
        self, tenant_id: uuid.UUID, data: TenantUpdate
    ) -> TenantRead:
        tenant = await self.db.get(Tenant, tenant_id)
        if not tenant:
            raise NotFoundError("Tenant", str(tenant_id))

        for key, value in data.model_dump(exclude_unset=True).items():
            setattr(tenant, key, value)

        await self.db.commit()
        await self.db.refresh(tenant)
        return TenantRead.model_validate(tenant)

    async def list_tenants(self) -> list[TenantRead]:
        result = await self.db.execute(select(Tenant).order_by(Tenant.name))
        tenants = result.scalars().all()
        return [TenantRead.model_validate(t) for t in tenants]
