"""
Application middleware: tenant resolution, request ID injection, timing.
"""

from __future__ import annotations

import logging
import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

logger = logging.getLogger(__name__)


class RequestIDMiddleware(BaseHTTPMiddleware):
    """Inject a unique request ID into every request/response for tracing."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        request_id = str(uuid.uuid4())
        request.state.request_id = request_id

        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response


class TimingMiddleware(BaseHTTPMiddleware):
    """Log and expose request processing duration."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        start = time.perf_counter()
        response = await call_next(request)
        duration_ms = (time.perf_counter() - start) * 1000

        response.headers["X-Process-Time-Ms"] = f"{duration_ms:.1f}"
        logger.info(
            "%s %s completed in %.1fms (status=%d)",
            request.method,
            request.url.path,
            duration_ms,
            response.status_code,
        )
        return response


class TenantMiddleware(BaseHTTPMiddleware):
    """
    Resolve tenant_id from the authenticated user's JWT claims
    and attach it to request.state for downstream use.

    Public routes (auth, webhooks) bypass tenant resolution.
    """

    SKIP_PATHS = {"/api/v1/auth", "/api/v1/payments/webhook", "/health", "/docs", "/openapi.json"}

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        path = request.url.path

        # Skip tenant resolution for public endpoints
        if any(path.startswith(skip) for skip in self.SKIP_PATHS):
            request.state.tenant_id = None
            return await call_next(request)

        # Tenant ID will be set by auth dependency (get_current_user)
        # This middleware just ensures the attribute exists on state
        if not hasattr(request.state, "tenant_id"):
            request.state.tenant_id = None

        return await call_next(request)
