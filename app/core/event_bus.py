"""
Lightweight in-process event bus for domain events.

MVP approach: all handlers run in-process via asyncio.create_task().
Upgrade path: swap internals to Redis Streams or RabbitMQ without
changing the emit() / subscribe() API.
"""

from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from typing import Any, Callable, Coroutine

logger = logging.getLogger(__name__)

EventHandler = Callable[[dict[str, Any]], Coroutine[Any, Any, None]]


class EventBus:
    """
    Simple pub-sub event dispatcher.

    Usage:
        bus = EventBus()
        bus.subscribe("booking.created", send_confirmation_email)
        bus.subscribe("booking.created", invalidate_availability_cache)
        await bus.emit("booking.created", {"booking_id": "...", ...})
    """

    def __init__(self) -> None:
        self._handlers: dict[str, list[EventHandler]] = defaultdict(list)

    def subscribe(self, event_type: str, handler: EventHandler) -> None:
        """Register a handler for an event type."""
        self._handlers[event_type].append(handler)
        logger.debug(
            "Subscribed %s to event '%s'",
            handler.__name__,
            event_type,
        )

    async def emit(self, event_type: str, payload: dict[str, Any]) -> None:
        """
        Emit an event to all subscribed handlers.
        Handlers run as fire-and-forget tasks (non-blocking).
        """
        handlers = self._handlers.get(event_type, [])
        if not handlers:
            return

        logger.info(
            "Emitting event '%s' to %d handler(s)",
            event_type,
            len(handlers),
        )

        for handler in handlers:
            try:
                asyncio.create_task(
                    self._safe_handle(handler, event_type, payload)
                )
            except Exception:
                logger.exception(
                    "Failed to schedule handler %s for event '%s'",
                    handler.__name__,
                    event_type,
                )

    @staticmethod
    async def _safe_handle(
        handler: EventHandler,
        event_type: str,
        payload: dict[str, Any],
    ) -> None:
        """Execute a handler with error isolation."""
        try:
            await handler(payload)
        except Exception:
            logger.exception(
                "Event handler %s failed for '%s'",
                handler.__name__,
                event_type,
            )


# ─── Global singleton ───────────────────────────────
event_bus = EventBus()
