"""
Booking state machine — explicit status transition rules.

All allowed transitions are defined here. Any code that
changes a booking status MUST go through this machine.
"""

from __future__ import annotations

from app.core.exceptions import InvalidStateTransitionError


class BookingStateMachine:
    """
    pending ──→ confirmed ──→ completed     (happy path)
       │            │
       │            ├───→ cancelled ──→ refund_pending ──→ refunded
       │            │
       │            └───→ no_show
       │
       └───→ cancelled
    """

    TRANSITIONS: dict[str, set[str]] = {
        "pending":        {"confirmed", "cancelled"},
        "confirmed":      {"completed", "cancelled", "no_show"},
        "cancelled":      {"refund_pending"},
        "completed":      set(),           # terminal
        "no_show":        set(),           # terminal
        "refund_pending": {"refunded"},
        "refunded":       set(),           # terminal
    }

    @classmethod
    def validate_transition(cls, current: str, target: str) -> None:
        """Raise if the transition is not allowed."""
        allowed = cls.TRANSITIONS.get(current, set())
        if target not in allowed:
            raise InvalidStateTransitionError(
                f"Cannot transition from '{current}' → '{target}'. "
                f"Allowed transitions: {allowed or '(terminal state)'}"
            )

    @classmethod
    def is_terminal(cls, status: str) -> bool:
        return len(cls.TRANSITIONS.get(status, set())) == 0

    @classmethod
    def is_cancellable(cls, status: str) -> bool:
        return "cancelled" in cls.TRANSITIONS.get(status, set())

    @classmethod
    def allowed_transitions(cls, status: str) -> set[str]:
        return cls.TRANSITIONS.get(status, set())
