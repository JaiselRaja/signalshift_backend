"""Auth API routes — OTP send/verify, token refresh."""

from __future__ import annotations

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.schemas import GoogleTokenRequest, OTPRequest, OTPVerify, RefreshRequest, TokenPair
from app.auth.service import AuthService
from app.core.database import get_async_session
from app.core.email import EmailClient, get_email_client
from app.core.redis import RedisCache, get_redis

router = APIRouter(prefix="/auth", tags=["Authentication"])


def _get_service(
    db: AsyncSession = Depends(get_async_session),
    redis_client: aioredis.Redis = Depends(get_redis),
    email_client: EmailClient = Depends(get_email_client),
) -> AuthService:
    return AuthService(db, RedisCache(redis_client), email_client)


@router.post("/otp/send", status_code=202)
async def send_otp(
    body: OTPRequest,
    svc: AuthService = Depends(_get_service),
):
    """
    Send an OTP to the user's email address.

    Rate limited: 3 requests per email per 10 minutes.
    No authentication required.
    Response is intentionally vague to prevent email enumeration.
    """
    await svc.send_otp(body.email, body.tenant_slug)
    return {"message": "If this email is registered, an OTP has been sent."}


@router.post("/otp/verify", response_model=TokenPair)
async def verify_otp(
    body: OTPVerify,
    svc: AuthService = Depends(_get_service),
):
    """
    Verify OTP and receive JWT access + refresh tokens.

    Rate limited: 5 attempts per email per 15 minutes.
    OTP expires after 5 minutes.
    Auto-creates a player account if email is new.
    """
    return await svc.verify_otp_and_issue_tokens(
        body.email, body.otp, body.tenant_slug
    )


@router.post("/google", response_model=TokenPair)
async def google_sign_in(
    body: GoogleTokenRequest,
    svc: AuthService = Depends(_get_service),
):
    """
    Verify a Google ID token (from Google Identity Services) and return JWT tokens.
    Auto-creates a player account if the email is new.
    """
    return await svc.google_sign_in(body.credential, body.tenant_slug)


@router.post("/refresh", response_model=TokenPair)
async def refresh_token(
    body: RefreshRequest,
    svc: AuthService = Depends(_get_service),
):
    """
    Exchange a valid refresh token for a new access + refresh pair.
    Implements token rotation for security.
    """
    return await svc.refresh(body.refresh_token)
