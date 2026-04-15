"""
Redis connection pool and helper utilities.

Used for: OTP storage, rate limiting, slot availability caching,
session blacklisting.
"""

from __future__ import annotations

from typing import AsyncGenerator

import redis.asyncio as aioredis

from app.config import settings

redis_pool = aioredis.ConnectionPool.from_url(
    settings.redis_url,
    decode_responses=True,
    max_connections=20,
)


async def get_redis() -> AsyncGenerator[aioredis.Redis, None]:
    """FastAPI dependency that yields a Redis client."""
    client = aioredis.Redis(connection_pool=redis_pool)
    try:
        yield client
    finally:
        await client.aclose()


class RedisCache:
    """High-level cache operations for domain logic."""

    def __init__(self, client: aioredis.Redis):
        self.client = client

    # ─── OTP ────────────────────────────────────────

    async def store_otp(self, email: str, otp: str, ttl: int | None = None) -> None:
        key = f"otp:{email}"
        await self.client.setex(key, ttl or settings.otp_expire_seconds, otp)

    async def get_otp(self, email: str) -> str | None:
        return await self.client.get(f"otp:{email}")

    async def delete_otp(self, email: str) -> None:
        await self.client.delete(f"otp:{email}")

    # ─── Rate limiting ──────────────────────────────

    async def check_rate_limit(
        self, key: str, max_attempts: int, window_seconds: int
    ) -> bool:
        """Returns True if rate limit is NOT exceeded."""
        current = await self.client.get(f"rate:{key}")
        if current and int(current) >= max_attempts:
            return False
        pipe = self.client.pipeline()
        pipe.incr(f"rate:{key}")
        pipe.expire(f"rate:{key}", window_seconds)
        await pipe.execute()
        return True

    # ─── Generic cache ──────────────────────────────

    async def get_cached(self, key: str) -> str | None:
        return await self.client.get(f"cache:{key}")

    async def set_cached(self, key: str, value: str, ttl: int = 60) -> None:
        await self.client.setex(f"cache:{key}", ttl, value)

    async def invalidate(self, pattern: str) -> None:
        """Delete all keys matching a glob pattern."""
        async for key in self.client.scan_iter(f"cache:{pattern}"):
            await self.client.delete(key)
