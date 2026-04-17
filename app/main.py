"""
Signal Shift — FastAPI Application Entrypoint.

Wires together all routers, middleware, exception handlers,
and lifecycle events.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.database import get_async_session
from app.core.exceptions import AppError
from app.core.middleware import RateLimitMiddleware, RequestIDMiddleware, TenantMiddleware, TimingMiddleware

# ─── Import routers ─────────────────────────────────
from app.auth.router import router as auth_router
from app.tenants.router import router as tenants_router
from app.users.router import router as users_router
from app.turfs.router import router as turfs_router
from app.bookings.router import router as bookings_router
from app.teams.router import router as teams_router
from app.tournaments.router import router as tournaments_router
from app.payments.router import router as payments_router
from app.coupons.router import router as coupons_router

# ─── Logging ─────────────────────────────────────────
logging.basicConfig(
    level=logging.DEBUG if settings.debug else logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("signal_shift")


# ─── Lifecycle ───────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup / shutdown hooks."""
    logger.info("🚀 Signal Shift API starting up (%s)", settings.app_env)

    # Import models to register them with SQLAlchemy metadata
    import app.tenants.models  # noqa: F401
    import app.users.models  # noqa: F401
    import app.turfs.models  # noqa: F401
    import app.bookings.models  # noqa: F401
    import app.teams.models  # noqa: F401
    import app.tournaments.models  # noqa: F401
    import app.payments.models  # noqa: F401
    import app.coupons.models  # noqa: F401

    # Register event bus handlers
    from app.core.event_handlers import register_all_handlers
    register_all_handlers()

    yield

    logger.info("🛬 Signal Shift API shutting down")


# ─── App Factory ─────────────────────────────────────

app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    description="Turf Management & Booking Platform API",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# ─── Middleware (LIFO order — first added = outermost) ─

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(RequestIDMiddleware)
app.add_middleware(TimingMiddleware)
app.add_middleware(RateLimitMiddleware)
app.add_middleware(TenantMiddleware)


# ─── Global Exception Handler ───────────────────────

@app.exception_handler(AppError)
async def app_error_handler(request: Request, exc: AppError):
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": type(exc).__name__,
            "message": exc.message,
            "detail": exc.detail,
        },
    )


# ─── Health Check ────────────────────────────────────

@app.get("/health", tags=["Health"])
async def health_check(
    db: AsyncSession = Depends(get_async_session),
):
    checks: dict[str, str] = {}
    healthy = True

    # Database check
    try:
        await db.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception as exc:
        checks["database"] = f"error: {exc}"
        healthy = False

    # Redis check
    try:
        import redis.asyncio as aioredis
        from app.core.redis import redis_pool
        r = aioredis.Redis(connection_pool=redis_pool)
        await r.ping()
        checks["redis"] = "ok"
        await r.aclose()
    except Exception as exc:
        checks["redis"] = f"error: {exc}"
        healthy = False

    status_code = 200 if healthy else 503
    return JSONResponse(
        status_code=status_code,
        content={
            "status": "healthy" if healthy else "degraded",
            "service": settings.app_name,
            "environment": settings.app_env,
            "checks": checks,
        },
    )


# ─── Mount Routers ──────────────────────────────────

API_PREFIX = settings.api_prefix

app.include_router(auth_router, prefix=API_PREFIX)
app.include_router(tenants_router, prefix=API_PREFIX)
app.include_router(users_router, prefix=API_PREFIX)
app.include_router(turfs_router, prefix=API_PREFIX)
app.include_router(bookings_router, prefix=API_PREFIX)
app.include_router(teams_router, prefix=API_PREFIX)
app.include_router(tournaments_router, prefix=API_PREFIX)
app.include_router(payments_router, prefix=API_PREFIX)
app.include_router(coupons_router, prefix=API_PREFIX)
