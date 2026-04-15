"""Turf business logic."""

from __future__ import annotations

import uuid

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError
from app.turfs.models import Turf, TurfSlotRule, SlotOverride
from app.turfs.schemas import (
    TurfCreate, TurfRead, TurfUpdate,
    SlotRuleCreate, SlotRuleRead, SlotRuleUpdate,
    SlotOverrideCreate, SlotOverrideRead,
)


class TurfService:
    def __init__(self, db: AsyncSession):
        self.db = db

    # ─── Turf CRUD ───────────────────────────────────

    async def create_turf(
        self, tenant_id: uuid.UUID, data: TurfCreate
    ) -> TurfRead:
        existing = await self.db.execute(
            select(Turf).where(and_(
                Turf.tenant_id == tenant_id, Turf.slug == data.slug
            ))
        )
        if existing.scalar_one_or_none():
            raise ConflictError(f"Turf with slug '{data.slug}' already exists")

        turf = Turf(tenant_id=tenant_id, **data.model_dump())
        self.db.add(turf)
        await self.db.commit()
        await self.db.refresh(turf)
        return TurfRead.model_validate(turf)

    async def get_turf(self, turf_id: uuid.UUID) -> TurfRead:
        turf = await self.db.get(Turf, turf_id)
        if not turf:
            raise NotFoundError("Turf", str(turf_id))
        return TurfRead.model_validate(turf)

    async def update_turf(
        self, turf_id: uuid.UUID, data: TurfUpdate
    ) -> TurfRead:
        turf = await self.db.get(Turf, turf_id)
        if not turf:
            raise NotFoundError("Turf", str(turf_id))

        for key, value in data.model_dump(exclude_unset=True).items():
            setattr(turf, key, value)

        await self.db.commit()
        await self.db.refresh(turf)
        return TurfRead.model_validate(turf)

    async def list_turfs(
        self, tenant_id: uuid.UUID, city: str | None = None
    ) -> list[TurfRead]:
        query = select(Turf).where(
            and_(Turf.tenant_id == tenant_id, Turf.is_active.is_(True))
        )
        if city:
            query = query.where(Turf.city == city)
        query = query.order_by(Turf.name)

        result = await self.db.execute(query)
        return [TurfRead.model_validate(t) for t in result.scalars().all()]

    # ─── Slot Rule CRUD ──────────────────────────────

    async def create_slot_rule(
        self, turf_id: uuid.UUID, data: SlotRuleCreate
    ) -> SlotRuleRead:
        # Verify turf exists
        turf = await self.db.get(Turf, turf_id)
        if not turf:
            raise NotFoundError("Turf", str(turf_id))

        rule = TurfSlotRule(turf_id=turf_id, **data.model_dump())
        self.db.add(rule)
        await self.db.commit()
        await self.db.refresh(rule)
        return SlotRuleRead.model_validate(rule)

    async def list_slot_rules(self, turf_id: uuid.UUID) -> list[SlotRuleRead]:
        result = await self.db.execute(
            select(TurfSlotRule)
            .where(TurfSlotRule.turf_id == turf_id)
            .order_by(TurfSlotRule.day_of_week, TurfSlotRule.start_time)
        )
        return [SlotRuleRead.model_validate(r) for r in result.scalars().all()]

    async def update_slot_rule(
        self, rule_id: uuid.UUID, data: SlotRuleUpdate
    ) -> SlotRuleRead:
        rule = await self.db.get(TurfSlotRule, rule_id)
        if not rule:
            raise NotFoundError("SlotRule", str(rule_id))

        for key, value in data.model_dump(exclude_unset=True).items():
            setattr(rule, key, value)

        await self.db.commit()
        await self.db.refresh(rule)
        return SlotRuleRead.model_validate(rule)

    async def delete_slot_rule(self, rule_id: uuid.UUID) -> None:
        rule = await self.db.get(TurfSlotRule, rule_id)
        if not rule:
            raise NotFoundError("SlotRule", str(rule_id))
        await self.db.delete(rule)
        await self.db.commit()

    # ─── Slot Override ───────────────────────────────

    async def create_override(
        self, turf_id: uuid.UUID, data: SlotOverrideCreate
    ) -> SlotOverrideRead:
        override = SlotOverride(turf_id=turf_id, **data.model_dump())
        self.db.add(override)
        await self.db.commit()
        await self.db.refresh(override)
        return SlotOverrideRead.model_validate(override)

    async def list_overrides(
        self, turf_id: uuid.UUID
    ) -> list[SlotOverrideRead]:
        result = await self.db.execute(
            select(SlotOverride)
            .where(SlotOverride.turf_id == turf_id)
            .order_by(SlotOverride.override_date)
        )
        return [SlotOverrideRead.model_validate(o) for o in result.scalars().all()]
