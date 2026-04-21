"""Auth Pydantic schemas."""

from __future__ import annotations

from pydantic import BaseModel, Field


class OTPRequest(BaseModel):
    email: str = Field(..., max_length=320)
    tenant_slug: str = Field(default="default", max_length=100)


class OTPVerify(BaseModel):
    email: str = Field(..., max_length=320)
    otp: str = Field(..., min_length=4, max_length=8)
    tenant_slug: str = Field(default="default", max_length=100)


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int  # seconds until access token expiry


class RefreshRequest(BaseModel):
    refresh_token: str


class GoogleTokenRequest(BaseModel):
    credential: str = Field(..., description="Google ID token from GIS callback")
    tenant_slug: str = Field(default="default", max_length=100)
