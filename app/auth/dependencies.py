"""
Auth dependencies: JWT extraction, user resolution, role checks.

These are used as FastAPI Depends() throughout all routers.
"""

from __future__ import annotations

import uuid

from fastapi import Depends, Header, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_async_session
from app.core.security import decode_token
from app.shared.types import UserRole
from app.tenants.models import Tenant
from app.users.models import User

bearer_scheme = HTTPBearer()
optional_bearer_scheme = HTTPBearer(auto_error=False)


async def resolve_tenant(
    x_tenant_slug: str | None = Header(default=None, alias="X-Tenant-Slug"),
    db: AsyncSession = Depends(get_async_session),
) -> Tenant:
    """
    Resolve the tenant for public (unauthenticated) requests from the
    `X-Tenant-Slug` header. Defaults to "default" when not provided.
    """
    slug = (x_tenant_slug or "default").strip().lower()
    result = await db.execute(select(Tenant).where(Tenant.slug == slug))
    tenant = result.scalar_one_or_none()
    if not tenant or not tenant.is_active:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Tenant '{slug}' not found",
        )
    return tenant


async def get_optional_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(optional_bearer_scheme),
    db: AsyncSession = Depends(get_async_session),
) -> User | None:
    """
    Return the current user if a valid access token is provided, otherwise None.
    Used by endpoints that work for both anonymous and authenticated users.
    """
    if credentials is None:
        return None
    payload = decode_token(credentials.credentials)
    if not payload or payload.get("type") != "access":
        return None
    try:
        user_id = uuid.UUID(payload["sub"])
    except (KeyError, ValueError):
        return None
    user = await db.get(User, user_id)
    if not user or not user.is_active:
        return None
    return user


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_async_session),
) -> User:
    """
    Extract JWT from Authorization header, validate it,
    and return the full User ORM object.
    """
    payload = decode_token(credentials.credentials)
    if not payload or payload.get("type") != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired access token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_id = uuid.UUID(payload["sub"])
    user = await db.get(User, user_id)

    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or deactivated",
        )

    return user


def require_roles(*roles: UserRole):
    """
    Factory that returns a dependency which enforces role-based access.

    Usage:
        @router.get("/admin-only")
        async def admin_endpoint(
            user=Depends(require_roles(UserRole.SUPER_ADMIN, UserRole.TURF_ADMIN))
        ):
            ...
    """
    async def _role_checker(
        current_user: User = Depends(get_current_user),
    ) -> User:
        allowed = [r.value if hasattr(r, "value") else r for r in roles]
        if current_user.role not in allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Requires one of: {', '.join(allowed)}",
            )
        return current_user

    return _role_checker
