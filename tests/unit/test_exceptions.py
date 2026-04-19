"""Tests for custom exception hierarchy."""

from __future__ import annotations

from app.core.exceptions import AppError, ExternalServiceError


def test_external_service_error_defaults_to_502():
    exc = ExternalServiceError("boom")
    assert isinstance(exc, AppError)
    assert exc.status_code == 502
    assert exc.message == "boom"
