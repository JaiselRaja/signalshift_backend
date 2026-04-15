"""
Auth service: OTP generation/verification and JWT issuance.

Flow:
1. User requests OTP → we generate + store in Redis + send email
2. User submits OTP → we verify against Redis → issue JWT pair
3. Refresh token → validate + issue new pair (rotation)
"""

from __future__ import annotations

import logging
import uuid

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.schemas import TokenPair
from app.config import settings
from app.core.exceptions import AuthenticationError, RateLimitError
from app.core.redis import RedisCache
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    generate_otp,
)
from app.tenants.models import Tenant
from app.users.service import UserService

logger = logging.getLogger(__name__)


class AuthService:
    def __init__(self, db: AsyncSession, cache: RedisCache):
        self.db = db
        self.cache = cache
        self.user_service = UserService(db)

    async def send_otp(self, email: str, tenant_slug: str = "default") -> None:
        """Generate OTP, store in Redis, send via email."""
        # Rate limit: 3 OTP requests per email per 10 minutes
        allowed = await self.cache.check_rate_limit(
            f"otp_send:{email}", max_attempts=3, window_seconds=600
        )
        if not allowed:
            raise RateLimitError("Too many OTP requests. Please wait before retrying.")

        otp = generate_otp()
        await self.cache.store_otp(email, otp)

        # In development, log OTP instead of sending email
        if settings.is_development:
            logger.info("DEV OTP for %s: %s", email, otp)
        else:
            await self._send_otp_email(email, otp)

    async def verify_otp_and_issue_tokens(
        self, email: str, otp: str, tenant_slug: str = "default"
    ) -> TokenPair:
        """Verify OTP and return JWT access + refresh tokens."""
        # Rate limit: 5 verification attempts per email per 15 min
        allowed = await self.cache.check_rate_limit(
            f"otp_verify:{email}", max_attempts=5, window_seconds=900
        )
        if not allowed:
            raise RateLimitError("Too many verification attempts. Account locked temporarily.")

        stored_otp = await self.cache.get_otp(email)
        if not stored_otp or stored_otp != otp:
            raise AuthenticationError("Invalid or expired OTP")

        # OTP valid → delete it (single use)
        await self.cache.delete_otp(email)

        # Resolve tenant
        tenant = await self._resolve_tenant(tenant_slug)

        # Get or create user
        user = await self.user_service.get_or_create_by_email(tenant.id, email)

        return self._create_token_pair(user.id, tenant.id, user.role)

    async def dev_login(self, email: str, tenant_slug: str = "default") -> TokenPair:
        """Dev-only: get-or-create a user by email and return tokens. No password check."""
        if not settings.is_development:
            raise AuthenticationError("Dev login is only available in development mode.")
        tenant = await self._resolve_tenant(tenant_slug)
        user = await self.user_service.get_or_create_by_email(tenant.id, email)
        logger.info("DEV login for %s", email)
        return self._create_token_pair(user.id, tenant.id, user.role)

    async def google_sign_in(self, credential: str, tenant_slug: str = "default") -> TokenPair:
        """Verify a Google ID token and issue Signal Shift JWT tokens."""
        if not settings.google_client_id:
            raise AuthenticationError("Google Sign-In is not configured on this server.")

        # Verify token with Google's tokeninfo endpoint
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                "https://oauth2.googleapis.com/tokeninfo",
                params={"id_token": credential},
            )

        if resp.status_code != 200:
            raise AuthenticationError("Invalid Google token.")

        payload = resp.json()

        # Validate audience matches our client ID
        if payload.get("aud") != settings.google_client_id:
            raise AuthenticationError("Google token audience mismatch.")

        email = payload.get("email")
        if not email or not payload.get("email_verified"):
            raise AuthenticationError("Google account email not verified.")

        tenant = await self._resolve_tenant(tenant_slug)
        user = await self.user_service.get_or_create_by_email(tenant.id, email)

        # Optionally backfill full_name if the user was just created
        if not user.full_name:
            given = payload.get("given_name", "")
            family = payload.get("family_name", "")
            full = f"{given} {family}".strip()
            if full:
                user.full_name = full
                await self.db.commit()

        logger.info("Google sign-in for %s (tenant=%s)", email, tenant_slug)
        return self._create_token_pair(user.id, tenant.id, user.role)

    async def refresh(self, refresh_token: str) -> TokenPair:
        """Validate refresh token and issue a new token pair (rotation)."""
        payload = decode_token(refresh_token)
        if not payload or payload.get("type") != "refresh":
            raise AuthenticationError("Invalid refresh token")

        user_id = uuid.UUID(payload["sub"])
        tenant_id = uuid.UUID(payload["tenant_id"])

        # Verify user still exists and is active
        user = await self.db.get(
            __import__("app.users.models", fromlist=["User"]).User,
            user_id,
        )
        if not user or not user.is_active:
            raise AuthenticationError("User account is deactivated")

        return self._create_token_pair(user_id, tenant_id, user.role)

    def _create_token_pair(
        self, user_id: uuid.UUID, tenant_id: uuid.UUID, role: str
    ) -> TokenPair:
        access = create_access_token(user_id, tenant_id, role)
        refresh = create_refresh_token(user_id, tenant_id)
        return TokenPair(
            access_token=access,
            refresh_token=refresh,
            expires_in=settings.jwt_access_token_expire_minutes * 60,
        )

    async def _resolve_tenant(self, slug: str) -> Tenant:
        result = await self.db.execute(
            select(Tenant).where(Tenant.slug == slug, Tenant.is_active.is_(True))
        )
        tenant = result.scalar_one_or_none()
        if not tenant:
            raise AuthenticationError(f"Tenant '{slug}' not found or inactive")
        return tenant

    async def _send_otp_email(self, email: str, otp: str) -> None:
        """Send OTP via SMTP. Placeholder for real email service."""
        # TODO: Integrate with email provider (SES, SendGrid, etc.)
        logger.info("Sending OTP email to %s", email)
