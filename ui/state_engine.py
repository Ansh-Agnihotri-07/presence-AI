"""
State Engine — Presence state management and automatic transitions.

Replaces the old state_animator. Maps events to presence states
with automatic timeout transitions (e.g., idle → dormant after 5 min).
"""

import asyncio
import logging
import time
from typing import Any

logger = logging.getLogger("presence.ui.state_engine")

# ── Presence States ──
STATES = {
    "idle",       # No interaction, calm presence
    "listening",  # Voice detected, awaiting input
    "thinking",   # Processing / AI call in progress
    "responding", # Output being delivered
    "focused",    # Task mode, deep work
    "dormant",    # No activity for extended period
    "active",     # General activity
    "observing",  # Context detected, passively aware
}

# ── Event → State mappings ──
EVENT_STATE_MAP = {
    "stt_active":         "listening",
    "llm_thinking":       "thinking",
    "response_ready":     "responding",
    "response_delivered": "active",
    "idle":               "idle",
    "waiting_input":      "idle",
    "task_started":       "focused",
    "context_detected":   "observing",
    "user_active":        "active",
}

# Timeout transitions (seconds)
STATE_TIMEOUTS = {
    "active":     30,     # active → idle after 30s
    "responding": 3,      # responding → active after 3s
    "observing":  15,     # observing → idle after 15s
    "idle":       300,    # idle → dormant after 5 min
}


class StateEngine:
    """Manages presence states with event-driven and timeout transitions."""

    def __init__(self, orb):
        self._orb = orb
        self._state = "idle"
        self._last_transition = time.time()
        self._timeout_task: asyncio.Task | None = None

    @property
    def state(self) -> str:
        return self._state

    def set_state(self, new_state: str):
        """Transition to a new state."""
        if new_state not in STATES:
            logger.warning(f"Unknown state: {new_state}")
            return
        if new_state == self._state:
            return

        prev = self._state
        self._state = new_state
        self._last_transition = time.time()

        self._orb.set_state(new_state)
        logger.debug(f"State: {prev} → {new_state}")

        # Schedule timeout transition
        self._schedule_timeout()

    def _schedule_timeout(self):
        """Schedule automatic state timeout transition."""
        if self._timeout_task and not self._timeout_task.done():
            self._timeout_task.cancel()

        timeout = STATE_TIMEOUTS.get(self._state)
        if timeout:
            try:
                loop = asyncio.get_event_loop()
                self._timeout_task = loop.create_task(
                    self._timeout_transition(timeout)
                )
            except RuntimeError:
                pass

    async def _timeout_transition(self, seconds: float):
        """After timeout, transition to the next logical state."""
        await asyncio.sleep(seconds)
        transitions = {
            "active": "idle",
            "responding": "active",
            "observing": "idle",
            "idle": "dormant",
        }
        next_state = transitions.get(self._state)
        if next_state:
            logger.debug(f"Timeout: {self._state} → {next_state} (after {seconds}s)")
            self.set_state(next_state)

    def wake_up(self):
        """Wake from dormant state on any user interaction."""
        if self._state == "dormant":
            self.set_state("active")

    def bind_events(self, event_bus):
        """Subscribe to state-changing events on the event bus."""
        for event_name, visual_state in EVENT_STATE_MAP.items():
            async def handler(data: dict[str, Any], state: str = visual_state):
                self.wake_up() if state != "dormant" else None
                self.set_state(state)
            event_bus.subscribe(event_name, handler)

        # Special: after response, briefly show "responding" then return to active
        async def response_flow(data: dict[str, Any]):
            self.set_state("responding")
            # timeout will handle responding → active → idle → dormant

        event_bus.subscribe("agent_response", response_flow)

        logger.info(f"State engine bound — {len(EVENT_STATE_MAP)} event mappings")
