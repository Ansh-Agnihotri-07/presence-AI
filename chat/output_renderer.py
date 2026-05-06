"""
Output Renderer — Dispatches agent responses to presence UI + workspace (Phase 1.7).

Subscribes to agent_response events and pushes text to:
  1. PresenceInputOverlay (ambient display)
  2. WorkspacePanel (persistent session history)
Also triggers TTS if voice is active.
"""

import asyncio
import logging
from core.event_bus import event_bus

logger = logging.getLogger("presence.chat.output_renderer")

_input_overlay = None
_workspace_panel = None


def set_input_overlay(overlay):
    """Wire the input overlay reference."""
    global _input_overlay
    _input_overlay = overlay


def set_workspace_panel(panel):
    """Wire the workspace panel reference."""
    global _workspace_panel
    _workspace_panel = panel


async def _on_agent_response(data: dict):
    """Handle agent_response events — push to overlay + workspace."""
    text = data.get("text", "")
    if not text:
        return

    agent = data.get("agent", "unknown")
    logger.debug(f"Rendering {agent} response: {text[:60]}...")

    # Push to ambient overlay
    if _input_overlay is not None:
        _input_overlay.show_response(text)

    # Push to workspace panel
    if _workspace_panel is not None:
        _workspace_panel.add_response(text)

    # Trigger TTS if voice is enabled
    from core.config import config
    if config.VOICE_ENABLED:
        await event_bus.publish("tts_request", {"text": text})


async def _on_reminder_due(data: dict):
    """Handle reminder notifications — show as ambient response."""
    text = data.get("text", "")
    if text and _input_overlay is not None:
        _input_overlay.show_response(f"⏰ Reminder: {text}")
    if text and _workspace_panel is not None:
        _workspace_panel.add_response(f"⏰ Reminder: {text}")


def register_output_handler():
    """Subscribe to output events on the bus."""
    event_bus.subscribe("agent_response", _on_agent_response)
    event_bus.subscribe("reminder_due", _on_reminder_due)
    logger.info("Output renderer registered")