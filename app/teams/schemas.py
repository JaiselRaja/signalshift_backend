"""Team Pydantic schemas."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.shared.types import TeamMemberRole


class TeamCreate(BaseModel):
    name: str = Field(..., max_length=255)
    slug: str = Field(..., max_length=100, pattern=r"^[a-z0-9\-]+$")
    sport_type: str
    logo_url: str | None = None


class TeamUpdate(BaseModel):
    name: str | None = None
    logo_url: str | None = None
    is_active: bool | None = None


class TeamRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    name: str
    slug: str
    sport_type: str
    logo_url: str | None
    captain_id: uuid.UUID | None
    is_active: bool
    created_at: datetime


class MembershipCreate(BaseModel):
    user_id: uuid.UUID
    role: TeamMemberRole = TeamMemberRole.PLAYER


class MembershipRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    team_id: uuid.UUID
    user_id: uuid.UUID
    role: str
    joined_at: datetime
    is_active: bool
