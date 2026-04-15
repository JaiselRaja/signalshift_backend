"""
Custom exception hierarchy for the application.

All domain-specific exceptions inherit from AppError so they
can be caught uniformly by the global exception handler in main.py.
"""

from __future__ import annotations

from fastapi import HTTPException, status


class AppError(Exception):
    """Base application error."""

    def __init__(self, message: str, status_code: int = 500, detail: dict | None = None):
        self.message = message
        self.status_code = status_code
        self.detail = detail or {}
        super().__init__(message)


class NotFoundError(AppError):
    """Resource not found."""

    def __init__(self, resource: str, identifier: str | None = None):
        msg = f"{resource} not found"
        if identifier:
            msg += f": {identifier}"
        super().__init__(msg, status_code=404)


class ConflictError(AppError):
    """Resource conflict (e.g. duplicate, overlap)."""

    def __init__(self, message: str):
        super().__init__(message, status_code=409)


class BookingConflictError(ConflictError):
    """Booking time slot overlaps with an existing booking."""
    pass


class InvalidStateTransitionError(AppError):
    """Attempted an invalid status transition (state machine violation)."""

    def __init__(self, message: str):
        super().__init__(message, status_code=422)


class AuthenticationError(AppError):
    """Authentication failed."""

    def __init__(self, message: str = "Authentication failed"):
        super().__init__(message, status_code=401)


class AuthorizationError(AppError):
    """Insufficient permissions."""

    def __init__(self, message: str = "Insufficient permissions"):
        super().__init__(message, status_code=403)


class RateLimitError(AppError):
    """Rate limit exceeded."""

    def __init__(self, message: str = "Too many requests"):
        super().__init__(message, status_code=429)


class ValidationError(AppError):
    """Business rule validation failed."""

    def __init__(self, message: str, detail: dict | None = None):
        super().__init__(message, status_code=422, detail=detail)


class PaymentError(AppError):
    """Payment processing failure."""

    def __init__(self, message: str, detail: dict | None = None):
        super().__init__(message, status_code=402, detail=detail)
