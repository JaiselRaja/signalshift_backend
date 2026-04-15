"""User Pydantic schemas."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.shared.types import UserRole


class UserCreate(BaseModel):
    email: str = Field(..., max_length=320)
    full_name: str = Field(..., max_length=255)
    phone: str | None = Field(None, max_length=20)
    role: UserRole = UserRole.PLAYER


class UserUpdate(BaseModel):
    full_name: str | None = None
    phone: str | None = None
    avatar_url: str | None = None
    preferences: dict | None = None
    is_active: bool | None = None


class UserRoleUpdate(BaseModel):
    """Admin-only role change."""
    role: UserRole


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    email: str
    full_name: str
    phone: str | None
    avatar_url: str | None
    role: str
    is_active: bool
    last_login_at: datetime | None
    created_at: datetime


class UserMinimal(BaseModel):
    """Lightweight user reference for nested responses."""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    full_name: str
    email: str
    role: str
