"""
builder_agent.py — Agent that routes project build requests to BuilderController.

PRIORITY: This agent is checked BEFORE cognitive mode routing.
If can_handle() returns True, the orchestrator routes exclusively here —
no fallback to CompanionAgent or direct route_llm.

Triggers on keywords: build, create, make, generate, scaffold, etc.
Collects streamed status lines and returns them as a single formatted response.
"""

import logging
from typing import Any

from agents.base_agent import BaseAgent
from core.event_bus import event_bus

logger = logging.getLogger("presence.agents.builder")

# Broad keyword list to reliably catch builder-intent prompts
_TRIGGER_KEYWORDS = [
    # Explicit build commands
    "build me", "build a ", "build an ",
    # Create patterns — broad ("create a" catches "create a react app", etc.)
    "create a ", "create an ", "create app",
    "create project", "create script", "create website", "create server",
    # Make patterns — broad
    "make a ", "make an ", "make me a",
    "make website", "make project", "make script", "make server",
    # Generate patterns
    "generate project", "generate a ", "generate an ",
    "generate app",
    # Scaffold
    "scaffold",
    # "build X" shorthand
    "build a simple", "build a basic",
]


def is_builder_request(text: str) -> bool:
    """
    Exported function for use by orchestrator to check builder intent
    BEFORE cognitive mode routing.
    """
    tl = text.lower()
    return any(kw in tl for kw in _TRIGGER_KEYWORDS)


class BuilderAgent(BaseAgent):
    name = "builder"

    async def can_handle(self, event: dict[str, Any]) -> bool:
        text = event.get("text", "")
        result = is_builder_request(text)
        if result:
            logger.info(f"[BUILDER_AGENT] can_handle=True for: {text[:80]!r}")
        return result

    async def handle(self, event: dict[str, Any]) -> dict[str, Any]:
        from builder.builder_controller import BuilderController

        user_text = event.get("text", "")
        logger.info(f"[BUILDER_AGENT] ACTIVE")
        logger.info(f"[BUILDER_AGENT] intercepted request: {user_text[:80]!r}")
        logger.info(f"[BUILDER_AGENT] calling builder_controller.execute()")

        controller = BuilderController()
        lines: list[str] = ["[BUILDER_AGENT] ACTIVE"]

        logger.info(f"[BUILDER_AGENT] builder execution started")

        async for status_line in controller.execute(user_text):
            lines.append(status_line)
            # Emit incremental progress through event bus so the UI can stream it
            await event_bus.publish("builder_progress", {"line": status_line})

        logger.info(f"[BUILDER_AGENT] builder execution finished")

        response_text = "\n".join(lines)

        return {
            "text": response_text,
            "action": "project_built",
            "metadata": {"agent": "builder"},
        }
