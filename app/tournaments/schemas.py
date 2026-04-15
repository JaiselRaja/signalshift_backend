"""Tournament Pydantic schemas."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.shared.types import RuleCategory, TournamentFormat, TournamentStatus


# ─── Rule sets ───────────────────────────────────────

class RuleSetCreate(BaseModel):
    rule_category: RuleCategory
    rule_name: str = Field(..., max_length=100)
    priority: int = 0
    rule_definition: dict


class RuleSetRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    tournament_id: uuid.UUID
    rule_category: str
    rule_name: str
    priority: int
    rule_definition: dict
    is_active: bool


# ─── Tournament CRUD ─────────────────────────────────

class TournamentCreate(BaseModel):
    name: str = Field(..., max_length=255)
    slug: str = Field(..., pattern=r"^[a-z0-9\-]+$")
    sport_type: str
    format: TournamentFormat
    turf_id: uuid.UUID | None = None
    tournament_starts: date
    tournament_ends: date | None = None
    registration_starts: date | None = None
    registration_ends: date | None = None
    max_teams: int | None = Field(None, ge=2)
    min_teams: int = Field(2, ge=2)
    entry_fee: Decimal = Decimal("0")
    prize_pool: dict = Field(default_factory=dict)
    config: dict = Field(default_factory=dict)
    rules: list[RuleSetCreate] = Field(default_factory=list)


class TournamentUpdate(BaseModel):
    name: str | None = None
    status: TournamentStatus | None = None
    registration_starts: date | None = None
    registration_ends: date | None = None
    tournament_ends: date | None = None
    max_teams: int | None = None
    entry_fee: Decimal | None = None
    prize_pool: dict | None = None
    config: dict | None = None


class TournamentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    tenant_id: uuid.UUID
    turf_id: uuid.UUID | None
    name: str
    slug: str
    sport_type: str
    format: str
    status: str
    tournament_starts: date
    tournament_ends: date | None
    registration_starts: date | None
    registration_ends: date | None
    max_teams: int | None
    min_teams: int
    entry_fee: Decimal
    prize_pool: dict
    config: dict
    rule_sets: list[RuleSetRead] = []
    created_at: datetime


# ─── Registration ────────────────────────────────────

class RegistrationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    tournament_id: uuid.UUID
    team_id: uuid.UUID
    registered_by: uuid.UUID
    status: str
    payment_status: str
    seed: int | None
    group_name: str | None
    created_at: datetime


# ─── Match ───────────────────────────────────────────

class MatchCreate(BaseModel):
    round_name: str
    group_name: str | None = None
    match_number: int | None = None
    home_team_id: uuid.UUID | None = None
    away_team_id: uuid.UUID | None = None
    scheduled_at: datetime | None = None


class MatchResultUpdate(BaseModel):
    home_score: int = Field(..., ge=0)
    away_score: int = Field(..., ge=0)
    extra_data: dict = Field(default_factory=dict)


class MatchRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    tournament_id: uuid.UUID
    booking_id: uuid.UUID | None
    round_name: str
    group_name: str | None
    match_number: int | None
    home_team_id: uuid.UUID | None
    away_team_id: uuid.UUID | None
    scheduled_at: datetime | None
    status: str
    home_score: int | None
    away_score: int | None
    winner_team_id: uuid.UUID | None
    is_draw: bool
    extra_data: dict


# ─── Standings (computed, never stored) ──────────────

class TeamStanding(BaseModel):
    team_id: uuid.UUID
    team_name: str
    group_name: str | None = None
    played: int = 0
    wins: int = 0
    draws: int = 0
    losses: int = 0
    goals_for: int = 0
    goals_against: int = 0
    goal_difference: int = 0
    points: int = 0
    hours_played: float = 0.0
    custom_score: float | None = None
    is_qualified: bool = False
    rank: int | None = None


class QualificationResult(BaseModel):
    tournament_id: uuid.UUID
    stage: str
    qualified_teams: list[TeamStanding]
    eliminated_teams: list[TeamStanding]
    rule_applied: RuleSetRead
    computed_at: datetime
