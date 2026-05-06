"""
Input Handler — Processes raw text input before dispatching to agents.

Normalizes whitespace, detects empty input, and publishes to event bus.
"""

import logging
from core.event_bus import event_bus

logger = logging.getLogger("presence.chat.input_handler")


async def handle_text_input(text: str, mode: str = "chat"):
    """
    Process a raw text input and publish it as a user_input event.

    Args:
        text: Raw input string
        mode: 'chat' or 'voice'
    """
    text = text.strip()
    if not text:
        return

    logger.debug(f"Input ({mode}): {text[:80]}")

    await event_bus.publish("user_input", {
        "text": text,
        "mode": mode,
    })