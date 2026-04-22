"""Team business logic."""

from __future__ import annotations

import uuid

from sqlalchemy import select, and_, or_, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.event_bus import event_bus
from app.core.exceptions import ConflictError, NotFoundError, AuthorizationError
from app.teams.models import Team, TeamMembership
from app.teams.schemas import (
    MembershipCreate, MembershipRead,
    TeamCreate, TeamInvite, TeamInviteResult, TeamRead, TeamUpdate,
)
from app.users.models import User


class TeamService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_team(
        self, user: User, data: TeamCreate
    ) -> TeamRead:
        existing = await self.db.execute(
            select(Team).where(and_(
                Team.tenant_id == user.tenant_id, Team.slug == data.slug
            ))
        )
        if existing.scalar_one_or_none():
            raise ConflictError(f"Team '{data.slug}' already exists")

        team = Team(
            tenant_id=user.tenant_id,
            captain_id=user.id,
            **data.model_dump(),
        )
        self.db.add(team)
        await self.db.flush()

        # Auto-add creator as manager
        membership = TeamMembership(
            team_id=team.id, user_id=user.id, role="manager"
        )
        self.db.add(membership)
        await self.db.commit()
        await self.db.refresh(team)
        return TeamRead.model_validate(team)

    async def get_team(self, team_id: uuid.UUID) -> TeamRead:
        team = await self.db.get(Team, team_id)
        if not team:
            raise NotFoundError("Team", str(team_id))
        return TeamRead.model_validate(team)

    async def update_team(
        self, team_id: uuid.UUID, user_id: uuid.UUID, data: "TeamUpdate",
    ) -> TeamRead:
        """Manager/captain only — update team fields (name, logo_url, is_active)."""
        team = await self.db.get(Team, team_id)
        if not team:
            raise NotFoundError("Team", str(team_id))
        await self._require_team_manager(user_id, team_id)
        payload = data.model_dump(exclude_unset=True)
        for key, value in payload.items():
            setattr(team, key, value)
        await self.db.commit()
        await self.db.refresh(team)
        return TeamRead.model_validate(team)

    async def list_teams(self, tenant_id: uuid.UUID) -> list[TeamRead]:
        result = await self.db.execute(
            select(Team)
            .where(and_(Team.tenant_id == tenant_id, Team.is_active.is_(True)))
            .order_by(Team.name)
        )
        return [TeamRead.model_validate(t) for t in result.scalars().all()]

    async def list_my_teams(self, user_id: uuid.UUID) -> list[TeamRead]:
        result = await self.db.execute(
            select(Team)
            .join(TeamMembership)
            .where(and_(
                TeamMembership.user_id == user_id,
                TeamMembership.is_active.is_(True),
            ))
            .order_by(Team.name)
        )
        return [TeamRead.model_validate(t) for t in result.scalars().all()]

    async def add_member(
        self, user: User, team_id: uuid.UUID, data: MembershipCreate
    ) -> MembershipRead:
        # Verify caller is manager/captain of the team
        await self._require_team_manager(user.id, team_id)

        # Check not already a member
        existing = await self.db.execute(
            select(TeamMembership).where(and_(
                TeamMembership.team_id == team_id,
                TeamMembership.user_id == data.user_id,
            ))
        )
        if existing.scalar_one_or_none():
            raise ConflictError("User is already a team member")

        membership = TeamMembership(team_id=team_id, **data.model_dump())
        self.db.add(membership)
        await self.db.commit()
        # Reload with user relation for enriched response
        result = await self.db.execute(
            select(TeamMembership)
            .options(selectinload(TeamMembership.user))
            .where(TeamMembership.id == membership.id)
        )
        loaded = result.scalar_one()

        await event_bus.emit("team.member_added", {
            "team_id": str(team_id),
            "new_user_id": str(data.user_id),
            "inviter_id": str(user.id),
        })

        return _to_membership_read(loaded)

    async def invite_by_email(
        self, user: User, team_id: uuid.UUID, data: TeamInvite
    ) -> TeamInviteResult:
        """
        Invite someone to a team by email.

        If the email matches an existing user in the same tenant, they
        are added to the roster immediately (and emailed that they've
        joined). Otherwise, an invitation email is sent with a signup
        link — they'll be added when they register with that email.
        """
        team = await self.db.get(Team, team_id)
        if not team:
            raise NotFoundError("Team", str(team_id))
        await self._require_team_manager(user.id, team_id)

        email = str(data.email).lower().strip()

        existing = await self.db.execute(
            select(User).where(and_(
                User.tenant_id == team.tenant_id,
                func.lower(User.email) == email,
            ))
        )
        matched = existing.scalar_one_or_none()

        if matched:
            # Avoid duplicate membership
            dup = await self.db.execute(
                select(TeamMembership).where(and_(
                    TeamMembership.team_id == team_id,
                    TeamMembership.user_id == matched.id,
                    TeamMembership.is_active.is_(True),
                ))
            )
            if dup.scalar_one_or_none():
                raise ConflictError("User is already on this team")

            membership = TeamMembership(
                team_id=team_id, user_id=matched.id, role=data.role,
            )
            self.db.add(membership)
            await self.db.commit()

            await event_bus.emit("team.member_added", {
                "team_id": str(team_id),
                "new_user_id": str(matched.id),
                "inviter_id": str(user.id),
            })
            return TeamInviteResult(status="added", email=matched.email, user_id=matched.id)

        # Unknown email → send invitation with signup link
        await event_bus.emit("team.invitation_sent", {
            "team_id": str(team_id),
            "invitee_email": email,
            "inviter_id": str(user.id),
        })
        return TeamInviteResult(status="invited", email=email, user_id=None)

    async def list_members(self, team_id: uuid.UUID) -> list[MembershipRead]:
        result = await self.db.execute(
            select(TeamMembership)
            .options(selectinload(TeamMembership.user))
            .where(and_(
                TeamMembership.team_id == team_id,
                TeamMembership.is_active.is_(True),
            ))
        )
        return [_to_membership_read(m) for m in result.scalars().all()]

    async def search_users(
        self, tenant_id: uuid.UUID, query: str, limit: int = 10
    ) -> list[dict]:
        """Search users in the same tenant by name or email (case-insensitive substring)."""
        q = query.strip().lower()
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
            .limit(limit)
        )
        return [
            {
                "id": str(u.id),
                "email": u.email,
                "full_name": u.full_name,
                "avatar_url": u.avatar_url,
                "role": u.role,
            }
            for u in result.scalars().all()
        ]

    async def remove_member(
        self, user: User, team_id: uuid.UUID, member_user_id: uuid.UUID
    ) -> None:
        await self._require_team_manager(user.id, team_id)
        result = await self.db.execute(
            select(TeamMembership).where(and_(
                TeamMembership.team_id == team_id,
                TeamMembership.user_id == member_user_id,
            ))
        )
        membership = result.scalar_one_or_none()
        if not membership:
            raise NotFoundError("TeamMember")
        membership.is_active = False
        await self.db.commit()

    async def _require_team_manager(
        self, user_id: uuid.UUID, team_id: uuid.UUID
    ) -> None:
        result = await self.db.execute(
            select(TeamMembership).where(and_(
                TeamMembership.team_id == team_id,
                TeamMembership.user_id == user_id,
                TeamMembership.role.in_(["manager", "captain"]),
                TeamMembership.is_active.is_(True),
            ))
        )
        if not result.scalar_one_or_none():
            raise AuthorizationError("Must be team manager or captain")


def _to_membership_read(membership: TeamMembership) -> MembershipRead:
    """Build a MembershipRead with the user's name/email/avatar populated."""
    data = MembershipRead.model_validate(membership)
    user = getattr(membership, "user", None)
    if user is not None:
        data.user_name = user.full_name
        data.user_email = user.email
        data.user_avatar_url = user.avatar_url
    return data
