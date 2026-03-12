"""Typed pub/sub event bus for decoupled communication.

NOTE: This module is currently not wired into either UI (TUI or Web).
It is reserved for future unified event handling. The Web UI uses direct
WebSocket broadcasts and the TUI uses Textual's event system.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from typing import Any, Callable
from threading import Lock

from opendev.core.events.types import Event, EventType

logger = logging.getLogger(__name__)

# Type for event handlers
EventHandler = Callable[[Event], None]

_global_bus: EventBus | None = None


class EventBus:
    """Thread-safe typed event bus with topic-based subscriptions."""

    def __init__(self) -> None:
        self._handlers: dict[EventType, list[EventHandler]] = defaultdict(list)
        self._wildcard_handlers: list[EventHandler] = []
        self._lock = Lock()

    def subscribe(
        self,
        event_type: EventType | str,
        handler: EventHandler,
    ) -> Callable[[], None]:
        """Subscribe to events of a specific type.

        Args:
            event_type: The event type to subscribe to, or "*" for all events.
            handler: Callback function that receives the Event.

        Returns:
            Unsubscribe function.
        """
        with self._lock:
            if event_type == "*":
                self._wildcard_handlers.append(handler)

                def unsub_wildcard() -> None:
                    with self._lock:
                        try:
                            self._wildcard_handlers.remove(handler)
                        except ValueError:
                            pass

                return unsub_wildcard

            if isinstance(event_type, str):
                event_type = EventType(event_type)

            self._handlers[event_type].append(handler)

            # Capture for closure
            captured_type = event_type

            def unsub() -> None:
                with self._lock:
                    try:
                        self._handlers[captured_type].remove(handler)
                    except ValueError:
                        pass

            return unsub

    def publish(self, event: Event) -> None:
        """Publish an event to all subscribed handlers.

        Handlers are called synchronously in registration order.
        Exceptions in handlers are logged but don't stop delivery.
        """
        with self._lock:
            handlers = list(self._handlers.get(event.type, []))
            wildcards = list(self._wildcard_handlers)

        for handler in handlers + wildcards:
            try:
                handler(event)
            except Exception:
                logger.warning("Event handler failed for %s", event.type.value, exc_info=True)

    def emit(self, event_type: EventType, source: str = "", **data: Any) -> None:
        """Convenience method to create and publish an event."""
        self.publish(Event(type=event_type, data=data, source=source))

    def clear(self) -> None:
        """Remove all subscriptions."""
        with self._lock:
            self._handlers.clear()
            self._wildcard_handlers.clear()


def get_bus() -> EventBus:
    """Get the global event bus singleton."""
    global _global_bus
    if _global_bus is None:
        _global_bus = EventBus()
    return _global_bus
