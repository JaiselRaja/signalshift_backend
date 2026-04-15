"""
Pricing engine — layered, configurable price calculation pipeline.

Rules are loaded from the pricing_rules table and evaluated
in priority order. New pricing dimensions are added by inserting
new database rows — zero code changes needed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, time
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.bookings.models import PricingRule
from app.bookings.schemas import AppliedPricingRule, PriceBreakdown
from app.shared.constants import DEFAULT_TAX_RATE_PCT


@dataclass
class PricingContext:
    """All inputs the pricing pipeline needs for computation."""
    turf_id: UUID
    base_price: Decimal
    booking_date: date
    start_time: time
    end_time: time | None = None
    slot_type: str = "regular"
    booking_type: str = "regular"
    membership_discount: Decimal = Decimal("0")
    coupon_discount: Decimal = Decimal("0")
    applied_rules: list[AppliedPricingRule] = field(default_factory=list)


class PricingPipeline:
    """
    Pipeline stages:
    1. Start with base_price from slot rule
    2. Apply non-stackable rules (first match wins per type)
    3. Apply stackable rules (all matching accumulate)
    4. Apply membership discount
    5. Apply coupon discount
    6. Compute tax
    7. Return full breakdown
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    async def compute_slot_price(
        self,
        turf_id: UUID,
        base_price: Decimal,
        booking_date: date,
        start_time: time,
        slot_type: str = "regular",
    ) -> Decimal:
        """Quick price computation for availability display."""
        ctx = PricingContext(
            turf_id=turf_id,
            base_price=base_price,
            booking_date=booking_date,
            start_time=start_time,
            slot_type=slot_type,
        )
        breakdown = await self._run_pipeline(ctx)
        return breakdown.total

    async def compute_full(
        self,
        turf_id: UUID,
        booking_date: date,
        start_time: time,
        end_time: time,
        booking_type: str,
        base_price: Decimal,
        membership_discount: Decimal = Decimal("0"),
        coupon_discount: Decimal = Decimal("0"),
    ) -> PriceBreakdown:
        """Full price computation with breakdown for booking creation."""
        ctx = PricingContext(
            turf_id=turf_id,
            base_price=base_price,
            booking_date=booking_date,
            start_time=start_time,
            end_time=end_time,
            booking_type=booking_type,
            membership_discount=membership_discount,
            coupon_discount=coupon_discount,
        )
        return await self._run_pipeline(ctx)

    async def _run_pipeline(self, ctx: PricingContext) -> PriceBreakdown:
        rules = await self._load_active_rules(ctx.turf_id)

        running_price = ctx.base_price
        exclusive_applied: set[str] = set()

        for rule in rules:
            if not self._matches_conditions(rule, ctx):
                continue

            # Non-stackable: first match per rule_type wins
            if not rule.stackable:
                if rule.rule_type in exclusive_applied:
                    continue
                exclusive_applied.add(rule.rule_type)

            effect = self._calculate_effect(rule, running_price)
            running_price += effect

            ctx.applied_rules.append(AppliedPricingRule(
                rule_name=rule.name,
                rule_type=rule.rule_type,
                adjustment_type=rule.adjustment_type,
                adjustment_value=Decimal(str(rule.adjustment_value)),
                effect_amount=effect,
            ))

        # Apply discounts
        total_discount = ctx.membership_discount + ctx.coupon_discount
        subtotal = max(running_price - total_discount, Decimal("0"))

        # Tax
        tax_rate = Decimal(str(DEFAULT_TAX_RATE_PCT)) / Decimal("100")
        tax = (subtotal * tax_rate).quantize(Decimal("0.01"))

        return PriceBreakdown(
            base_price=ctx.base_price,
            applied_rules=ctx.applied_rules,
            discount=ctx.membership_discount,
            coupon_discount=ctx.coupon_discount,
            subtotal=subtotal,
            tax=tax,
            total=subtotal + tax,
        )

    def _matches_conditions(self, rule: PricingRule, ctx: PricingContext) -> bool:
        """Evaluate JSONB conditions against the booking context."""
        cond = rule.conditions

        if "days" in cond:
            if ctx.booking_date.weekday() not in cond["days"]:
                return False

        if "time_range" in cond:
            tr_start = time.fromisoformat(cond["time_range"][0])
            tr_end = time.fromisoformat(cond["time_range"][1])
            if not (tr_start <= ctx.start_time < tr_end):
                return False

        if "booking_type" in cond:
            if ctx.booking_type != cond["booking_type"]:
                return False

        if "slot_type" in cond:
            if ctx.slot_type != cond["slot_type"]:
                return False

        # Validity window
        if rule.valid_from and ctx.booking_date < rule.valid_from:
            return False
        if rule.valid_until and ctx.booking_date > rule.valid_until:
            return False

        return True

    def _calculate_effect(self, rule: PricingRule, current_price: Decimal) -> Decimal:
        """Compute the monetary effect of a pricing rule."""
        value = Decimal(str(rule.adjustment_value))

        if rule.adjustment_type == "fixed":
            return value
        elif rule.adjustment_type == "percentage":
            return (current_price * value / Decimal("100")).quantize(Decimal("0.01"))
        elif rule.adjustment_type == "override":
            return value - current_price
        return Decimal("0")

    async def _load_active_rules(self, turf_id: UUID) -> list[PricingRule]:
        result = await self.db.execute(
            select(PricingRule)
            .where(and_(
                PricingRule.turf_id == turf_id,
                PricingRule.is_active.is_(True),
            ))
            .order_by(PricingRule.priority)
        )
        return list(result.scalars().all())
