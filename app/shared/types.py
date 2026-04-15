"""
Domain enumerations and type aliases.

All status fields, role types, and categorical values are defined here
as StrEnum so they serialize naturally to/from JSON strings.
"""

from __future__ import annotations

from enum import StrEnum


# ─── User ────────────────────────────────────────────

class UserRole(StrEnum):
    SUPER_ADMIN  = "super_admin"
    TURF_ADMIN   = "turf_admin"
    TEAM_MANAGER = "team_manager"
    PLAYER       = "player"


# ─── Booking ─────────────────────────────────────────

class BookingStatus(StrEnum):
    PENDING        = "pending"
    CONFIRMED      = "confirmed"
    CANCELLED      = "cancelled"
    COMPLETED      = "completed"
    NO_SHOW        = "no_show"
    REFUND_PENDING = "refund_pending"
    REFUNDED       = "refunded"


class BookingType(StrEnum):
    REGULAR    = "regular"
    TOURNAMENT = "tournament"
    PRACTICE   = "practice"
    EVENT      = "event"


# ─── Turf Slots ──────────────────────────────────────

class SlotType(StrEnum):
    PEAK        = "peak"
    OFFPEAK     = "offpeak"
    REGULAR     = "regular"
    BLOCKED     = "blocked"
    MAINTENANCE = "maintenance"


class OverrideType(StrEnum):
    PRICE_CHANGE = "price_change"
    BLOCKED      = "blocked"
    EXTENDED     = "extended"
    CUSTOM       = "custom"


# ─── Tournament ──────────────────────────────────────

class TournamentFormat(StrEnum):
    LEAGUE         = "league"
    KNOCKOUT       = "knockout"
    GROUP_KNOCKOUT = "group_knockout"
    ROUND_ROBIN    = "round_robin"
    SWISS          = "swiss"
    CUSTOM         = "custom"


class TournamentStatus(StrEnum):
    DRAFT               = "draft"
    REGISTRATION_OPEN   = "registration_open"
    REGISTRATION_CLOSED = "registration_closed"
    IN_PROGRESS         = "in_progress"
    COMPLETED           = "completed"
    CANCELLED           = "cancelled"


class MatchStatus(StrEnum):
    SCHEDULED = "scheduled"
    LIVE      = "live"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    POSTPONED = "postponed"
    WALKOVER  = "walkover"


class RuleCategory(StrEnum):
    SCORING       = "scoring"
    QUALIFICATION = "qualification"
    TIEBREAKER    = "tiebreaker"
    SCHEDULING    = "scheduling"
    PENALTY       = "penalty"
    CUSTOM        = "custom"


class RegistrationStatus(StrEnum):
    PENDING   = "pending"
    APPROVED  = "approved"
    REJECTED  = "rejected"
    WITHDRAWN = "withdrawn"


# ─── Pricing ─────────────────────────────────────────

class PricingRuleType(StrEnum):
    BASE        = "base"
    TIME_OF_DAY = "time_of_day"
    DAY_OF_WEEK = "day_of_week"
    EVENT_TYPE  = "event_type"
    MEMBERSHIP  = "membership"
    EARLY_BIRD  = "early_bird"
    SURGE       = "surge"
    HOLIDAY     = "holiday"
    CUSTOM      = "custom"


class AdjustmentType(StrEnum):
    FIXED      = "fixed"
    PERCENTAGE = "percentage"
    OVERRIDE   = "override"


# ─── Payment ─────────────────────────────────────────

class PaymentStatus(StrEnum):
    INITIATED          = "initiated"
    PROCESSING         = "processing"
    SUCCESS            = "success"
    FAILED             = "failed"
    REFUNDED           = "refunded"
    PARTIALLY_REFUNDED = "partially_refunded"


class PaymentGateway(StrEnum):
    RAZORPAY = "razorpay"
    CASHFREE = "cashfree"
    WALLET   = "wallet"
    MANUAL   = "manual"


# ─── Team ────────────────────────────────────────────

class TeamMemberRole(StrEnum):
    MANAGER = "manager"
    CAPTAIN = "captain"
    PLAYER  = "player"


# ─── Membership ──────────────────────────────────────

class MembershipStatus(StrEnum):
    ACTIVE    = "active"
    EXPIRED   = "expired"
    CANCELLED = "cancelled"
