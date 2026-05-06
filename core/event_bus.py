"""
Event Bus — Async pub/sub backbone for all inter-module communication.

Every module publishes and subscribes to typed events.
No modules talk to each other directly — everything flows through the bus.
"""

import asyncio
import logging
from collections import defaultdict
from typing import Any, Callable, Coroutine

logger = logging.getLogger("presence.core.event_bus")


class EventBus:
    """Central async event bus. All system communication is routed here."""

    def __init__(self):
        self._listeners: dict[str, list[Callable[..., Coroutine]]] = defaultdict(list)
        self._queue: asyncio.Queue = asyncio.Queue()
        self._running = False

    def subscribe(self, event_type: str, handler: Callable[..., Coroutine]):
        """Subscribe an async handler to an event type."""
        self._listeners[event_type].append(handler)
        logger.debug(f"Subscribed {handler.__qualname__} to '{event_type}'")

    def unsubscribe(self, event_type: str, handler: Callable[..., Coroutine]):
        """Remove a handler from an event type."""
        if handler in self._listeners[event_type]:
            self._listeners[event_type].remove(handler)

    async def publish(self, event_type: str, data: dict[str, Any] | None = None):
        """Publish an event to all subscribed handlers."""
        data = data or {}
        data["_event_type"] = event_type
        logger.debug(f"Event published: '{event_type}' → {len(self._listeners[event_type])} handlers")

        tasks = []
        for handler in self._listeners[event_type]:
            tasks.append(asyncio.create_task(self._safe_call(handler, data)))

        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _safe_call(self, handler: Callable, data: dict):
        """Call a handler with error isolation."""
        try:
            await handler(data)
        except Exception as e:
            logger.error(f"Handler {handler.__qualname__} failed: {e}", exc_info=True)

    async def start(self):
        """Start processing queued events (for deferred dispatch if needed)."""
        self._running = True
        logger.info("EventBus started")

    async def stop(self):
        """Stop the event bus."""
        self._running = False
        logger.info("EventBus stopped")


# Global singleton
event_bus = EventBus()