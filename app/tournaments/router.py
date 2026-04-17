"""Tournament API routes."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user, require_roles, resolve_tenant
from app.core.database import get_async_session
from app.shared.types import UserRole
from app.tenants.models import Tenant
from app.tournaments.schemas import (
    MatchCreate, MatchRead, MatchResultUpdate,
    QualificationResult, RegistrationRead,
    RuleSetCreate, RuleSetRead, TeamStanding,
    TournamentCreate, TournamentRead, TournamentUpdate,
)
from app.tournaments.service import TournamentService
from app.users.models import User

router = APIRouter(prefix="/tournaments", tags=["Tournaments"])


def _get_service(db: AsyncSession = Depends(get_async_session)) -> TournamentService:
    return TournamentService(db)


# ─── Tournament CRUD ─────────────────────────────────

@router.post("/", response_model=TournamentRead, status_code=201)
async def create_tournament(
    body: TournamentCreate,
    current_user: User = Depends(require_roles(UserRole.TURF_ADMIN, UserRole.SUPER_ADMIN)),
    svc: TournamentService = Depends(_get_service),
):
    """Create tournament with optional inline rules. Auth: turf_admin or super_admin."""
    return await svc.create_tournament(current_user, body)


@router.get("/", response_model=list[TournamentRead])
async def list_tournaments(
    tournament_status: str | None = Query(None, alias="status"),
    tenant: Tenant = Depends(resolve_tenant),
    svc: TournamentService = Depends(_get_service),
):
    """List tournaments in the tenant. Public."""
    return await svc.list_tournaments(tenant.id, tournament_status)


@router.get("/{tournament_id}", response_model=TournamentRead)
async def get_tournament(
    tournament_id: uuid.UUID,
    _: Tenant = Depends(resolve_tenant),
    svc: TournamentService = Depends(_get_service),
):
    """Get tournament details with rules. Public."""
    return await svc.get_tournament(tournament_id)


@router.patch("/{tournament_id}", response_model=TournamentRead)
async def update_tournament(
    tournament_id: uuid.UUID,
    body: TournamentUpdate,
    _=Depends(require_roles(UserRole.TURF_ADMIN, UserRole.SUPER_ADMIN)),
    svc: TournamentService = Depends(_get_service),
):
    """Update tournament. Auth: turf_admin or super_admin."""
    return await svc.update_tournament(tournament_id, body)


# ─── Rule Management ─────────────────────────────────

@router.post("/{tournament_id}/rules", response_model=RuleSetRead, status_code=201)
async def add_rule(
    tournament_id: uuid.UUID,
    body: RuleSetCreate,
    _=Depends(require_roles(UserRole.TURF_ADMIN, UserRole.SUPER_ADMIN)),
    svc: TournamentService = Depends(_get_service),
):
    """Add a rule to a tournament. Auth: turf_admin or super_admin."""
    return await svc.add_rule(tournament_id, body)


@router.get("/{tournament_id}/rules", response_model=list[RuleSetRead])
async def list_rules(
    tournament_id: uuid.UUID,
    category: str | None = Query(None),
    _=Depends(get_current_user),
    svc: TournamentService = Depends(_get_service),
):
    """List tournament rules, optionally filtered by category."""
    return await svc.get_rules(tournament_id, category)


# ─── Registration ────────────────────────────────────

@router.post("/{tournament_id}/register", status_code=201, response_model=RegistrationRead)
async def register_team(
    tournament_id: uuid.UUID,
    team_id: uuid.UUID = Query(...),
    current_user: User = Depends(get_current_user),
    svc: TournamentService = Depends(_get_service),
):
    """Register a team. Auth: team manager/captain."""
    return await svc.register_team(current_user, tournament_id, team_id)


@router.get("/{tournament_id}/registrations", response_model=list[RegistrationRead])
async def list_registrations(
    tournament_id: uuid.UUID,
    _=Depends(get_current_user),
    svc: TournamentService = Depends(_get_service),
):
    """List tournament registrations."""
    return await svc.list_registrations(tournament_id)


# ─── Matches ─────────────────────────────────────────

@router.post("/{tournament_id}/matches", response_model=MatchRead, status_code=201)
async def create_match(
    tournament_id: uuid.UUID,
    body: MatchCreate,
    _=Depends(require_roles(UserRole.TURF_ADMIN, UserRole.SUPER_ADMIN)),
    svc: TournamentService = Depends(_get_service),
):
    """Schedule a match. Auth: turf_admin or super_admin."""
    return await svc.create_match(tournament_id, body)


@router.get("/{tournament_id}/matches", response_model=list[MatchRead])
async def list_matches(
    tournament_id: uuid.UUID,
    round_name: str | None = Query(None),
    _: Tenant = Depends(resolve_tenant),
    svc: TournamentService = Depends(_get_service),
):
    """List matches, optionally filtered by round. Public."""
    return await svc.list_matches(tournament_id, round_name)


@router.patch("/matches/{match_id}/result", response_model=MatchRead)
async def update_match_result(
    match_id: uuid.UUID,
    body: MatchResultUpdate,
    _=Depends(require_roles(UserRole.TURF_ADMIN, UserRole.SUPER_ADMIN)),
    svc: TournamentService = Depends(_get_service),
):
    """Record match result. Auth: turf_admin or super_admin."""
    return await svc.update_result(match_id, body)


# ─── Standings & Qualification ───────────────────────

@router.get("/{tournament_id}/standings", response_model=list[TeamStanding])
async def get_standings(
    tournament_id: uuid.UUID,
    group_name: str | None = Query(None),
    _: Tenant = Depends(resolve_tenant),
    svc: TournamentService = Depends(_get_service),
):
    """Compute live standings. Public."""
    return await svc.compute_standings(tournament_id, group_name)


@router.get("/{tournament_id}/qualified", response_model=QualificationResult)
async def get_qualified_teams(
    tournament_id: uuid.UUID,
    stage: str = Query("group_stage"),
    _=Depends(get_current_user),
    svc: TournamentService = Depends(_get_service),
):
    """Evaluate qualification from a stage. Auth: any authenticated user."""
    return await svc.evaluate_qualification(tournament_id, stage)
