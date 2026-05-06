"""
Base Agent — Abstract interface all agents implement.
"""

import logging
from abc import ABC, abstractmethod
from typing import Any

logger = logging.getLogger("presence.agents.base")


class BaseAgent(ABC):
    """Abstract base for all Presence AI agents."""

    name: str = "base"

    @abstractmethod
    async def handle(self, event: dict[str, Any]) -> dict[str, Any]:
        """
        Process an event and return a response dict.

        Returns:
            {
                "text": str,        # response text
                "action": str,      # optional follow-up action
                "metadata": dict,   # optional metadata
            }
        """
        raise NotImplementedError

    async def can_handle(self, event: dict[str, Any]) -> bool:
        """Return True if this agent should handle the event."""
        return False