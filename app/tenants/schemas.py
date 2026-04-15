"""Tenant Pydantic schemas."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class TenantCreate(BaseModel):
    name: str = Field(..., max_length=255)
    slug: str = Field(..., max_length=100, pattern=r"^[a-z0-9\-]+$")
    config: dict = Field(default_factory=dict)


class TenantUpdate(BaseModel):
    name: str | None = None
    config: dict | None = None
    is_active: bool | None = None


class TenantRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    slug: str
    config: dict
    is_active: bool
    created_at: datetime
    updated_at: datetime
