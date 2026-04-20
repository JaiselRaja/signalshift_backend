"""User API routes."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user, require_roles
from app.core.database import get_async_session
from app.shared.types import UserRole
from app.users.models import User
from app.users.schemas import UserRead, UserSummary, UserUpdate, UserRoleUpdate
from app.users.service import UserService

router = APIRouter(prefix="/users", tags=["Users"])


def _get_service(db: AsyncSession = Depends(get_async_session)) -> UserService:
    return UserService(db)


@router.get("/me", response_model=UserRead)
async def get_me(current_user: User = Depends(get_current_user)):
    """Get current authenticated user's profile."""
    return UserRead.model_validate(current_user)


@router.patch("/me", response_model=UserRead)
async def update_me(
    body: UserUpdate,
    current_user: User = Depends(get_current_user),
    svc: UserService = Depends(_get_service),
):
    """Update current user's profile."""
    return await svc.update_user(current_user.id, body)


@router.get("/", response_model=list[UserRead])
async def list_users(
    role: str | None = Query(None),
    current_user: User = Depends(require_roles(UserRole.TURF_ADMIN, UserRole.SUPER_ADMIN)),
    svc: UserService = Depends(_get_service),
):
    """List users in current tenant. Auth: turf_admin or super_admin."""
    return await svc.list_users(current_user.tenant_id, role)


@router.get("/search", response_model=list[UserSummary])
async def search_users(
    q: str = Query(..., min_length=2, max_length=120),
    limit: int = Query(10, ge=1, le=25),
    current_user: User = Depends(get_current_user),
    svc: UserService = Depends(_get_service),
):
    """Search users in your tenant by name or email (case-insensitive substring).
    Any authenticated user can use this — needed for team-member typeahead."""
    return await svc.search_users(current_user.tenant_id, q, limit)


@router.get("/{user_id}", response_model=UserRead)
async def get_user(
    user_id: uuid.UUID,
    _=Depends(require_roles(UserRole.TURF_ADMIN, UserRole.SUPER_ADMIN)),
    svc: UserService = Depends(_get_service),
):
    """Get a user by ID. Auth: turf_admin or super_admin."""
    return await svc.get_user(user_id)


@router.patch("/{user_id}/role", response_model=UserRead)
async def change_role(
    user_id: uuid.UUID,
    body: UserRoleUpdate,
    _=Depends(require_roles(UserRole.SUPER_ADMIN)),
    svc: UserService = Depends(_get_service),
):
    """Change a user's role. Auth: super_admin only."""
    return await svc.update_role(user_id, body)
