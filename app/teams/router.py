"""Team API routes."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user, resolve_tenant
from app.core.database import get_async_session
from app.teams.schemas import (
    MembershipCreate, MembershipRead,
    TeamCreate, TeamRead, TeamUpdate,
)
from app.teams.service import TeamService
from app.tenants.models import Tenant
from app.users.models import User

router = APIRouter(prefix="/teams", tags=["Teams"])


def _get_service(db: AsyncSession = Depends(get_async_session)) -> TeamService:
    return TeamService(db)


@router.post("/", response_model=TeamRead, status_code=201)
async def create_team(
    body: TeamCreate,
    current_user: User = Depends(get_current_user),
    svc: TeamService = Depends(_get_service),
):
    """Create a team (creator becomes manager + captain)."""
    return await svc.create_team(current_user, body)


@router.get("/", response_model=list[TeamRead])
async def list_teams(
    tenant: Tenant = Depends(resolve_tenant),
    svc: TeamService = Depends(_get_service),
):
    """List all teams in the tenant. Public."""
    return await svc.list_teams(tenant.id)


@router.get("/my", response_model=list[TeamRead])
async def my_teams(
    current_user: User = Depends(get_current_user),
    svc: TeamService = Depends(_get_service),
):
    """List teams the current user belongs to."""
    return await svc.list_my_teams(current_user.id)


@router.get("/{team_id}", response_model=TeamRead)
async def get_team(
    team_id: uuid.UUID,
    _: Tenant = Depends(resolve_tenant),
    svc: TeamService = Depends(_get_service),
):
    """Get team details. Public."""
    return await svc.get_team(team_id)


@router.patch("/{team_id}", response_model=TeamRead)
async def update_team(
    team_id: uuid.UUID,
    body: TeamUpdate,
    current_user: User = Depends(get_current_user),
    svc: TeamService = Depends(_get_service),
):
    """Update team (name, logo, active). Manager/captain only."""
    return await svc.update_team(team_id, current_user.id, body)


@router.post("/{team_id}/members", response_model=MembershipRead, status_code=201)
async def add_member(
    team_id: uuid.UUID,
    body: MembershipCreate,
    current_user: User = Depends(get_current_user),
    svc: TeamService = Depends(_get_service),
):
    """Add a member to the team. Auth: team manager/captain."""
    return await svc.add_member(current_user, team_id, body)


@router.get("/{team_id}/members", response_model=list[MembershipRead])
async def list_members(
    team_id: uuid.UUID,
    _: Tenant = Depends(resolve_tenant),
    svc: TeamService = Depends(_get_service),
):
    """List team members. Public."""
    return await svc.list_members(team_id)


@router.delete("/{team_id}/members/{user_id}", status_code=204)
async def remove_member(
    team_id: uuid.UUID,
    user_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    svc: TeamService = Depends(_get_service),
):
    """Remove a team member. Auth: team manager/captain."""
    await svc.remove_member(current_user, team_id, user_id)
