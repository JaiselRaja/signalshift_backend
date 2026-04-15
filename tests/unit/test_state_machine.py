"""Unit tests for booking state machine."""

import pytest

from app.bookings.state_machine import BookingStateMachine
from app.core.exceptions import InvalidStateTransitionError


class TestBookingStateMachine:
    def test_pending_to_confirmed(self):
        BookingStateMachine.validate_transition("pending", "confirmed")

    def test_pending_to_cancelled(self):
        BookingStateMachine.validate_transition("pending", "cancelled")

    def test_confirmed_to_completed(self):
        BookingStateMachine.validate_transition("confirmed", "completed")

    def test_confirmed_to_no_show(self):
        BookingStateMachine.validate_transition("confirmed", "no_show")

    def test_confirmed_to_cancelled(self):
        BookingStateMachine.validate_transition("confirmed", "cancelled")

    def test_cancelled_to_refund_pending(self):
        BookingStateMachine.validate_transition("cancelled", "refund_pending")

    def test_refund_pending_to_refunded(self):
        BookingStateMachine.validate_transition("refund_pending", "refunded")

    def test_invalid_pending_to_completed(self):
        with pytest.raises(InvalidStateTransitionError):
            BookingStateMachine.validate_transition("pending", "completed")

    def test_invalid_completed_to_anything(self):
        with pytest.raises(InvalidStateTransitionError):
            BookingStateMachine.validate_transition("completed", "cancelled")

    def test_invalid_refunded_to_anything(self):
        with pytest.raises(InvalidStateTransitionError):
            BookingStateMachine.validate_transition("refunded", "pending")

    def test_is_terminal(self):
        assert BookingStateMachine.is_terminal("completed") is True
        assert BookingStateMachine.is_terminal("refunded") is True
        assert BookingStateMachine.is_terminal("no_show") is True
        assert BookingStateMachine.is_terminal("pending") is False

    def test_is_cancellable(self):
        assert BookingStateMachine.is_cancellable("pending") is True
        assert BookingStateMachine.is_cancellable("confirmed") is True
        assert BookingStateMachine.is_cancellable("completed") is False
