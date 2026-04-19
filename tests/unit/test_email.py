"""Tests for the MSG91 EmailClient."""

from __future__ import annotations

import httpx
import pytest

from app.core.email import EmailClient
from app.core.exceptions import ExternalServiceError


def _handler_factory(captured: dict):
    def _handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["headers"] = dict(request.headers)
        captured["json"] = request.read().decode()
        return httpx.Response(200, json={"message": "ok"})

    return _handler


def _make_client(
    handler, *, auth_key="test-key", domain="msg.signalshift.in",
    from_email="no-reply@msg.signalshift.in", from_name="Signal Shift",
) -> EmailClient:
    transport = httpx.MockTransport(handler)
    http = httpx.AsyncClient(transport=transport, timeout=10.0)
    return EmailClient(
        http=http,
        auth_key=auth_key,
        domain=domain,
        from_email=from_email,
        from_name=from_name,
    )


@pytest.mark.asyncio
async def test_send_builds_correct_msg91_request():
    captured: dict = {}
    client = _make_client(_handler_factory(captured))

    await client.send(
        to_email="user@example.com",
        to_name="Test User",
        template_id="global_otp",
        variables={"otp": "123456"},
    )

    import json
    body = json.loads(captured["json"])

    assert captured["url"] == "https://control.msg91.com/api/v5/email/send"
    assert captured["headers"]["authkey"] == "test-key"
    assert captured["headers"]["content-type"].startswith("application/json")

    assert body["from"] == {"name": "Signal Shift", "email": "no-reply@msg.signalshift.in"}
    assert body["domain"] == "msg.signalshift.in"
    assert body["template_id"] == "global_otp"
    assert body["recipients"] == [
        {
            "to": [{"name": "Test User", "email": "user@example.com"}],
            "variables": {"otp": "123456"},
        }
    ]
    assert "subject" not in body
    assert "body" not in body


@pytest.mark.asyncio
async def test_send_raises_external_service_error_on_non_2xx():
    def _handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"message": "bad request"})

    client = _make_client(_handler)
    with pytest.raises(ExternalServiceError) as excinfo:
        await client.send(
            to_email="user@example.com",
            to_name="Test",
            template_id="global_otp",
            variables={"otp": "1"},
        )
    assert excinfo.value.status_code == 502


@pytest.mark.asyncio
async def test_send_raises_external_service_error_on_timeout():
    def _handler(request: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("slow")

    client = _make_client(_handler)
    with pytest.raises(ExternalServiceError) as excinfo:
        await client.send(
            to_email="user@example.com",
            to_name="Test",
            template_id="global_otp",
            variables={"otp": "1"},
        )
    assert excinfo.value.status_code == 502
