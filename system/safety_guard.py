"""
Safety Guard — Pre-request validation (Phase 1.7).

Validates model existence + cost guard checks.
No manual mode validation — system is autonomous.
"""

import logging
from typing import Any

logger = logging.getLogger("presence.system.safety_guard")


class SafetyGuard:
    """Top-level safety check — wraps cost guard with model validation."""

    def __init__(self, config: Any, cost_guard: Any):
        self._config = config
        self._cost_guard = cost_guard

    def validate_request(self, model: str, mode: str = "local") -> dict[str, Any]:
        """
        Full pre-request validation.
        Returns {"safe": True, "model": model, "mode": mode}
        or {"safe": False, "reason": "..."}.
        """
        # 1. Model must be explicitly provided
        if not model or not model.strip():
            return {
                "safe": False,
                "reason": "No model specified. Every request must include a model field.",
            }

        # 2. Cost guard checks (daily limit, whitelist, paid blocking)
        cost_result = self._cost_guard.check(model, mode)
        if not cost_result["allowed"]:
            return {"safe": False, "reason": cost_result["reason"]}

        logger.debug(f"Safety: PASS model={model}, mode={mode}")
        return {"safe": True, "model": model, "mode": mode}
