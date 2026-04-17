"""Coupon service — validation and discount computation."""

from __future__ import annotations

import logging
from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError, ValidationError
from app.coupons.models import Coupon
from app.coupons.schemas import CouponCreate, CouponRead, CouponUpdate

logger = logging.getLogger(__name__)


class CouponService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_coupon(
        self, tenant_id: UUID, body: CouponCreate
    ) -> CouponRead:
        """Create a new coupon code."""
        # Check uniqueness within tenant
        existing = await self.db.execute(
            select(Coupon).where(
                Coupon.tenant_id == tenant_id,
                Coupon.code == body.code,
            )
        )
        if existing.scalar_one_or_none():
            raise ValidationError(f"Coupon code '{body.code}' already exists")

        coupon = Coupon(
            tenant_id=tenant_id,
            **body.model_dump(),
        )
        self.db.add(coupon)
        await self.db.commit()
        await self.db.refresh(coupon)
        return CouponRead.model_validate(coupon)

    async def get_coupon(self, coupon_id: UUID) -> CouponRead:
        coupon = await self.db.get(Coupon, coupon_id)
        if not coupon:
            raise NotFoundError("Coupon", str(coupon_id))
        return CouponRead.model_validate(coupon)

    async def update_coupon(
        self, coupon_id: UUID, body: CouponUpdate
    ) -> CouponRead:
        coupon = await self.db.get(Coupon, coupon_id)
        if not coupon:
            raise NotFoundError("Coupon", str(coupon_id))

        for field, value in body.model_dump(exclude_unset=True).items():
            setattr(coupon, field, value)

        await self.db.commit()
        await self.db.refresh(coupon)
        return CouponRead.model_validate(coupon)

    async def list_coupons(self, tenant_id: UUID) -> list[CouponRead]:
        result = await self.db.execute(
            select(Coupon)
            .where(Coupon.tenant_id == tenant_id)
            .order_by(Coupon.created_at.desc())
        )
        return [CouponRead.model_validate(c) for c in result.scalars().all()]

    async def delete_coupon(self, coupon_id: UUID) -> None:
        coupon = await self.db.get(Coupon, coupon_id)
        if not coupon:
            raise NotFoundError("Coupon", str(coupon_id))
        await self.db.delete(coupon)
        await self.db.commit()

    async def validate_and_compute_discount(
        self,
        tenant_id: UUID,
        coupon_code: str,
        booking_amount: Decimal,
        turf_id: UUID | None = None,
        sport_type: str | None = None,
        booking_type: str = "regular",
        user_id: UUID | None = None,
    ) -> Decimal:
        """
        Validate a coupon code and return the discount amount.
        Returns Decimal("0") if coupon is invalid.
        Raises ValidationError with specific message for user-facing errors.
        """
        result = await self.db.execute(
            select(Coupon).where(and_(
                Coupon.tenant_id == tenant_id,
                Coupon.code == coupon_code.upper().strip(),
                Coupon.is_active.is_(True),
            ))
        )
        coupon = result.scalar_one_or_none()
        if not coupon:
            raise ValidationError("Invalid coupon code")

        today = date.today()

        # Check validity window
        if today < coupon.valid_from or today > coupon.valid_until:
            raise ValidationError("This coupon has expired")

        # Check usage limit
        if coupon.usage_limit is not None and coupon.used_count >= coupon.usage_limit:
            raise ValidationError("This coupon has reached its usage limit")

        # Check minimum booking amount
        if booking_amount < coupon.min_booking_amount:
            raise ValidationError(
                f"Minimum booking amount for this coupon is ₹{coupon.min_booking_amount}"
            )

        # Check turf scope
        if coupon.applicable_turf_ids and turf_id:
            if turf_id not in coupon.applicable_turf_ids:
                raise ValidationError("This coupon is not valid for this turf")

        # Check sport scope
        if coupon.applicable_sports and sport_type:
            if sport_type not in coupon.applicable_sports:
                raise ValidationError("This coupon is not valid for this sport")

        # Check booking type scope
        if coupon.applicable_booking_types:
            if booking_type not in coupon.applicable_booking_types:
                raise ValidationError("This coupon is not valid for this booking type")

        # Compute discount
        if coupon.discount_type == "percentage":
            discount = (booking_amount * Decimal(str(coupon.discount_value)) / Decimal("100")).quantize(Decimal("0.01"))
            if coupon.max_discount is not None:
                discount = min(discount, Decimal(str(coupon.max_discount)))
        else:
            discount = Decimal(str(coupon.discount_value))

        # Never discount more than the booking amount
        discount = min(discount, booking_amount)

        return discount

    async def increment_usage(self, tenant_id: UUID, coupon_code: str) -> None:
        """Increment the used_count after a successful booking."""
        result = await self.db.execute(
            select(Coupon).where(and_(
                Coupon.tenant_id == tenant_id,
                Coupon.code == coupon_code.upper().strip(),
            ))
        )
        coupon = result.scalar_one_or_none()
        if coupon:
            coupon.used_count += 1
