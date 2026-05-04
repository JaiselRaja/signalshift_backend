"""Plan business logic."""

from __future__ import annotations

import uuid

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError
from app.plans.models import Plan
from app.plans.schemas import PlanCreate, PlanRead, PlanUpdate


class PlanService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def list_public(self, tenant_id: uuid.UUID) -> list[PlanRead]:
        """Active plans only, sorted for the public Plans page."""
        result = await self.db.execute(
            select(Plan)
            .where(and_(Plan.tenant_id == tenant_id, Plan.is_active.is_(True)))
            .order_by(Plan.display_order, Plan.price)
        )
        return [PlanRead.model_validate(p) for p in result.scalars().all()]

    async def list_admin(self, tenant_id: uuid.UUID) -> list[PlanRead]:
        """Every plan (active + archived) for the admin panel."""
        result = await self.db.execute(
            select(Plan)
            .where(Plan.tenant_id == tenant_id)
            .order_by(Plan.display_order, Plan.price)
        )
        return [PlanRead.model_validate(p) for p in result.scalars().all()]

    async def get(self, plan_id: uuid.UUID) -> PlanRead:
        plan = await self.db.get(Plan, plan_id)
        if not plan:
            raise NotFoundError("Plan", str(plan_id))
        return PlanRead.model_validate(plan)

    async def create(self, tenant_id: uuid.UUID, data: PlanCreate) -> PlanRead:
        existing = await self.db.execute(
            select(Plan).where(and_(Plan.tenant_id == tenant_id, Plan.code == data.code))
        )
        if existing.scalar_one_or_none():
            raise ConflictError(f"A plan with code '{data.code}' already exists")

        plan = Plan(
            tenant_id=tenant_id,
            code=data.code,
            name=data.name,
            tagline=data.tagline,
            plan_type=data.plan_type,
            price=float(data.price),
            price_unit=data.price_unit,
            hours_per_month=data.hours_per_month,
            discount_pct=data.discount_pct,
            advance_window_days=data.advance_window_days,
            slot_window_start=data.slot_window_start,
            slot_window_end=data.slot_window_end,
            perks=data.perks,
            featured=data.featured,
            display_order=data.display_order,
            is_active=data.is_active,
        )
        self.db.add(plan)
        await self.db.commit()
        await self.db.refresh(plan)
        return PlanRead.model_validate(plan)

    async def update(self, plan_id: uuid.UUID, data: PlanUpdate) -> PlanRead:
        plan = await self.db.get(Plan, plan_id)
        if not plan:
            raise NotFoundError("Plan", str(plan_id))

        payload = data.model_dump(exclude_unset=True)
        if "price" in payload and payload["price"] is not None:
            payload["price"] = float(payload["price"])
        for key, value in payload.items():
            setattr(plan, key, value)

        await self.db.commit()
        await self.db.refresh(plan)
        return PlanRead.model_validate(plan)

    async def delete(self, plan_id: uuid.UUID) -> None:
        plan = await self.db.get(Plan, plan_id)
        if not plan:
            raise NotFoundError("Plan", str(plan_id))
        await self.db.delete(plan)
        await self.db.commit()
