"""
MSG91 transactional email client.

A thin wrapper around MSG91's /api/v5/email/send endpoint. All outbound
email from the backend goes through `EmailClient.send`, which accepts a
template id and variable map (MSG91 renders the final HTML from a
template configured in the dashboard).
"""

from __future__ import annotations

import logging

import httpx

from app.config import settings
from app.core.exceptions import ExternalServiceError

logger = logging.getLogger(__name__)

MSG91_SEND_URL = "https://control.msg91.com/api/v5/email/send"


class EmailClient:
    """Sends email via MSG91 using a pre-built template."""

    def __init__(
        self,
        http: httpx.AsyncClient,
        auth_key: str,
        domain: str,
        from_email: str,
        from_name: str,
    ):
        self._http = http
        self._auth_key = auth_key
        self._domain = domain
        self._from_email = from_email
        self._from_name = from_name

    async def send(
        self,
        to_email: str,
        to_name: str,
        template_id: str,
        variables: dict[str, str],
    ) -> None:
        payload = {
            "recipients": [
                {
                    "to": [{"name": to_name, "email": to_email}],
                    "variables": variables,
                }
            ],
            "from": {"name": self._from_name, "email": self._from_email},
            "domain": self._domain,
            "template_id": template_id,
        }
        headers = {
            "Authkey": self._auth_key,
            "Content-Type": "application/json",
        }

        try:
            response = await self._http.post(
                MSG91_SEND_URL, json=payload, headers=headers
            )
        except httpx.TimeoutException as exc:
            logger.error("MSG91 email send timed out for %s: %s", to_email, exc)
            raise ExternalServiceError("Failed to send verification email") from exc
        except httpx.HTTPError as exc:
            logger.error("MSG91 email send failed for %s: %s", to_email, exc)
            raise ExternalServiceError("Failed to send verification email") from exc

        if response.status_code >= 300:
            logger.error(
                "MSG91 rejected email to %s (status=%s body=%s)",
                to_email,
                response.status_code,
                response.text,
            )
            raise ExternalServiceError("Failed to send verification email")


# Module-scoped singletons (created lazily on first dependency call,
# closed on app shutdown via app.main lifespan hooks).
_http_client: httpx.AsyncClient | None = None
_email_client: EmailClient | None = None


def _get_http_client() -> httpx.AsyncClient:
    global _http_client
    if _http_client is None:
        _http_client = httpx.AsyncClient(timeout=10.0)
    return _http_client


async def close_email_client() -> None:
    """Called from FastAPI shutdown to release the shared httpx client."""
    global _http_client, _email_client
    if _http_client is not None:
        await _http_client.aclose()
    _http_client = None
    _email_client = None


async def get_email_client() -> EmailClient:
    """FastAPI dependency that returns a process-wide EmailClient."""
    global _email_client
    if _email_client is None:
        _email_client = EmailClient(
            http=_get_http_client(),
            auth_key=settings.msg91_auth_key,
            domain=settings.msg91_email_domain,
            from_email=settings.msg91_from_email,
            from_name=settings.msg91_from_name,
        )
    return _email_client
