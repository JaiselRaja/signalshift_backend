"""User business logic."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import select, and_, or_, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError
from app.users.models import User
from app.users.schemas import UserCreate, UserRead, UserSummary, UserUpdate, UserRoleUpdate


class UserService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_user(
        self, tenant_id: uuid.UUID, data: UserCreate
    ) -> UserRead:
        # Check for duplicate email within tenant
        existing = await self.db.execute(
            select(User).where(
                and_(User.tenant_id == tenant_id, User.email == data.email)
            )
        )
        if existing.scalar_one_or_none():
            raise ConflictError(f"User with email '{data.email}' already exists")

        user = User(tenant_id=tenant_id, **data.model_dump())
        self.db.add(user)
        await self.db.commit()
        await self.db.refresh(user)
        return UserRead.model_validate(user)

    async def get_user(self, user_id: uuid.UUID) -> UserRead:
        user = await self.db.get(User, user_id)
        if not user:
            raise NotFoundError("User", str(user_id))
        return UserRead.model_validate(user)

    async def get_user_by_email(
        self, tenant_id: uuid.UUID, email: str
    ) -> User | None:
        result = await self.db.execute(
            select(User).where(
                and_(User.tenant_id == tenant_id, User.email == email)
            )
        )
        return result.scalar_one_or_none()

    async def get_or_create_by_email(
        self, tenant_id: uuid.UUID, email: str
    ) -> User:
        """Used during OTP verification — auto-create player accounts."""
        user = await self.get_user_by_email(tenant_id, email)
        if user:
            user.last_login_at = datetime.now(timezone.utc)
            await self.db.commit()
            return user

        # Auto-create a player account
        user = User(
            tenant_id=tenant_id,
            email=email,
            full_name=email.split("@")[0],
            role="player",
            last_login_at=datetime.now(timezone.utc),
        )
        self.db.add(user)
        await self.db.commit()
        await self.db.refresh(user)
        return user

    async def update_user(
        self, user_id: uuid.UUID, data: UserUpdate
    ) -> UserRead:
        user = await self.db.get(User, user_id)
        if not user:
            raise NotFoundError("User", str(user_id))

        for key, value in data.model_dump(exclude_unset=True).items():
            setattr(user, key, value)

        await self.db.commit()
        await self.db.refresh(user)
        return UserRead.model_validate(user)

    async def update_role(
        self, user_id: uuid.UUID, data: UserRoleUpdate
    ) -> UserRead:
        user = await self.db.get(User, user_id)
        if not user:
            raise NotFoundError("User", str(user_id))

        user.role = data.role
        await self.db.commit()
        await self.db.refresh(user)
        return UserRead.model_validate(user)

    async def list_users(
        self, tenant_id: uuid.UUID, role: str | None = None
    ) -> list[UserRead]:
        query = select(User).where(User.tenant_id == tenant_id)
        if role:
            query = query.where(User.role == role)
        query = query.order_by(User.full_name)

        result = await self.db.execute(query)
        return [UserRead.model_validate(u) for u in result.scalars().all()]

    async def search_users(
        self, tenant_id: uuid.UUID, query: str, limit: int = 10
    ) -> list[UserSummary]:
        """Case-insensitive substring search on email/full_name scoped to a tenant."""
        q = (query or "").strip().lower()
        if len(q) < 2:
            return []
        pattern = f"%{q}%"
        result = await self.db.execute(
            select(User)
            .where(and_(
                User.tenant_id == tenant_id,
                User.is_active.is_(True),
                or_(
                    func.lower(User.email).like(pattern),
                    func.lower(User.full_name).like(pattern),
                ),
            ))
            .order_by(User.full_name)
            .limit(limit)
        )
        return [UserSummary.model_validate(u) for u in result.scalars().all()]
