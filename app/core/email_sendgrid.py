"""
SendGrid transactional email client.

Used for all non-OTP outbound email: booking lifecycle, payment
confirmations/rejections, team invitations, tournament updates, etc.
OTP email continues to go through MSG91.

Failures are logged but never raise — transactional email should
never block the core business flow (a booking still succeeds even
if the confirmation mail can't be sent).
"""

from __future__ import annotations

import logging

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

SENDGRID_SEND_URL = "https://api.sendgrid.com/v3/mail/send"


class SendGridClient:
    """Sends email via SendGrid v3 /mail/send with inline HTML."""

    def __init__(
        self,
        http: httpx.AsyncClient,
        api_key: str,
        from_email: str,
        from_name: str,
    ):
        self._http = http
        self._api_key = api_key
        self._from_email = from_email
        self._from_name = from_name

    @property
    def configured(self) -> bool:
        return bool(self._api_key and self._from_email)

    async def send(
        self,
        to_email: str,
        to_name: str,
        subject: str,
        html: str,
        text: str | None = None,
        reply_to: str | None = None,
    ) -> bool:
        """Send a transactional email. Returns True on success, False on any failure."""
        if not self.configured:
            logger.warning("SendGrid not configured — skipping send to %s", to_email)
            return False

        payload: dict = {
            "personalizations": [
                {"to": [{"email": to_email, "name": to_name or to_email}]}
            ],
            "from": {"email": self._from_email, "name": self._from_name},
            "subject": subject,
            "content": [],
        }
        if text:
            payload["content"].append({"type": "text/plain", "value": text})
        payload["content"].append({"type": "text/html", "value": html})
        if reply_to:
            payload["reply_to"] = {"email": reply_to}

        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

        try:
            response = await self._http.post(
                SENDGRID_SEND_URL, json=payload, headers=headers
            )
        except httpx.TimeoutException as exc:
            logger.error("SendGrid timed out for %s: %s", to_email, exc)
            return False
        except httpx.HTTPError as exc:
            logger.error("SendGrid request failed for %s: %s", to_email, exc)
            return False

        if response.status_code >= 300:
            logger.error(
                "SendGrid rejected email to %s (status=%s body=%s)",
                to_email, response.status_code, response.text,
            )
            return False

        logger.info("SendGrid: sent '%s' to %s", subject, to_email)
        return True


# ─── Singletons (created lazily, closed via lifespan) ──

_http_client: httpx.AsyncClient | None = None
_sendgrid_client: SendGridClient | None = None


def _get_http_client() -> httpx.AsyncClient:
    global _http_client
    if _http_client is None:
        _http_client = httpx.AsyncClient(timeout=15.0)
    return _http_client


async def close_sendgrid_client() -> None:
    global _http_client, _sendgrid_client
    if _http_client is not None:
        await _http_client.aclose()
    _http_client = None
    _sendgrid_client = None


def get_sendgrid_client() -> SendGridClient:
    """Return the process-wide SendGridClient (safe to call from anywhere)."""
    global _sendgrid_client
    if _sendgrid_client is None:
        _sendgrid_client = SendGridClient(
            http=_get_http_client(),
            api_key=settings.sendgrid_api_key,
            from_email=settings.sendgrid_from_email,
            from_name=settings.sendgrid_from_name,
        )
    return _sendgrid_client
