"""
State Animator — Binds event bus events to orb visual states.
"""

import logging

logger = logging.getLogger("presence.ui.state_animator")

# Maps internal event names to orb visual states
EVENT_STATE_MAP = {
    "stt_active":     "listening",
    "llm_thinking":   "thinking",
    "response_ready": "acting",
    "idle":           "idle",
    "waiting_input":  "waiting",
}


def bind_state_events(orb, event_bus):
    """Subscribe the orb to state-changing events on the bus."""

    for event_name, visual_state in EVENT_STATE_MAP.items():
        # Capture visual_state in closure
        async def handler(data, state=visual_state):
            orb.set_state(state)
        event_bus.subscribe(event_name, handler)

    # After response is shown, return to idle after a short delay
    async def acting_to_idle(data):
        import asyncio
        orb.set_state("acting")
        await asyncio.sleep(1.5)
        orb.set_state("idle")

    event_bus.subscribe("response_delivered", acting_to_idle)

    logger.info("State animator bound to orb")