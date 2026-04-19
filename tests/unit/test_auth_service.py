"""Unit tests for AuthService.send_otp — EmailClient integration."""

from __future__ import annotations

import pytest

from app.auth.service import AuthService
from app.core.exceptions import ExternalServiceError


class _FakeCache:
    def __init__(self):
        self.stored: dict[str, str] = {}

    async def check_rate_limit(self, *_args, **_kwargs) -> bool:
        return True

    async def store_otp(self, email: str, otp: str, ttl: int | None = None) -> None:
        self.stored[email] = otp


class _RecordingEmailClient:
    def __init__(self):
        self.calls: list[dict] = []

    async def send(self, **kwargs) -> None:
        self.calls.append(kwargs)


class _FailingEmailClient:
    async def send(self, **_kwargs) -> None:
        raise ExternalServiceError("boom")


@pytest.mark.asyncio
async def test_send_otp_calls_email_client_with_template_and_otp_variable(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "msg91_otp_template_id", "global_otp")

    cache = _FakeCache()
    email_client = _RecordingEmailClient()
    svc = AuthService(db=None, cache=cache, email_client=email_client)  # type: ignore[arg-type]

    await svc.send_otp("user@example.com")

    assert len(email_client.calls) == 1
    call = email_client.calls[0]
    assert call["to_email"] == "user@example.com"
    assert call["template_id"] == "global_otp"
    stored_otp = cache.stored["user@example.com"]
    assert call["variables"]["otp"] == stored_otp


@pytest.mark.asyncio
async def test_send_otp_propagates_email_failure():
    cache = _FakeCache()
    email_client = _FailingEmailClient()
    svc = AuthService(db=None, cache=cache, email_client=email_client)  # type: ignore[arg-type]

    with pytest.raises(ExternalServiceError):
        await svc.send_otp("user@example.com")
