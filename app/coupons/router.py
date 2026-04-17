"""Coupon API routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user, require_roles
from app.core.database import get_async_session
from app.coupons.schemas import CouponCreate, CouponRead, CouponUpdate
from app.coupons.service import CouponService
from app.users.models import User

router = APIRouter(prefix="/coupons", tags=["Coupons"])


def _get_service(db: AsyncSession = Depends(get_async_session)) -> CouponService:
    return CouponService(db)


@router.post("/", response_model=CouponRead, status_code=201)
async def create_coupon(
    body: CouponCreate,
    current_user: User = Depends(require_roles("super_admin", "turf_admin")),
    svc: CouponService = Depends(_get_service),
):
    """Create a new coupon code. Admin only."""
    return await svc.create_coupon(current_user.tenant_id, body)


@router.get("/", response_model=list[CouponRead])
async def list_coupons(
    current_user: User = Depends(require_roles("super_admin", "turf_admin")),
    svc: CouponService = Depends(_get_service),
):
    """List all coupons for the tenant. Admin only."""
    return await svc.list_coupons(current_user.tenant_id)


@router.get("/{coupon_id}", response_model=CouponRead)
async def get_coupon(
    coupon_id: str,
    current_user: User = Depends(require_roles("super_admin", "turf_admin")),
    svc: CouponService = Depends(_get_service),
):
    """Get coupon details. Admin only."""
    import uuid
    return await svc.get_coupon(uuid.UUID(coupon_id))


@router.patch("/{coupon_id}", response_model=CouponRead)
async def update_coupon(
    coupon_id: str,
    body: CouponUpdate,
    current_user: User = Depends(require_roles("super_admin", "turf_admin")),
    svc: CouponService = Depends(_get_service),
):
    """Update a coupon. Admin only."""
    import uuid
    return await svc.update_coupon(uuid.UUID(coupon_id), body)


@router.delete("/{coupon_id}", status_code=204)
async def delete_coupon(
    coupon_id: str,
    current_user: User = Depends(require_roles("super_admin", "turf_admin")),
    svc: CouponService = Depends(_get_service),
):
    """Delete a coupon. Admin only."""
    import uuid
    await svc.delete_coupon(uuid.UUID(coupon_id))


@router.post("/validate")
async def validate_coupon(
    code: str,
    booking_amount: float,
    turf_id: str | None = None,
    booking_type: str = "regular",
    current_user: User = Depends(get_current_user),
    svc: CouponService = Depends(_get_service),
):
    """Validate a coupon code and return the discount amount."""
    import uuid
    from decimal import Decimal
    discount = await svc.validate_and_compute_discount(
        tenant_id=current_user.tenant_id,
        coupon_code=code,
        booking_amount=Decimal(str(booking_amount)),
        turf_id=uuid.UUID(turf_id) if turf_id else None,
        booking_type=booking_type,
    )
    return {"code": code.upper(), "discount": float(discount), "valid": True}
