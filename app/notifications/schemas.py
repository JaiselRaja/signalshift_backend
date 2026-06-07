"""Admin notification recipient Pydantic schemas."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class AdminRecipientCreate(BaseModel):
    email: EmailStr
    label: str | None = Field(default=None, max_length=120)
    is_active: bool = True


class AdminRecipientUpdate(BaseModel):
    label: str | None = Field(default=None, max_length=120)
    is_active: bool | None = None


class AdminRecipientRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    email: str
    label: str | None
    is_active: bool
    created_at: datetime
    updated_at: datetime
