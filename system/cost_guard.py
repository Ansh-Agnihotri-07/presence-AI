"""
Cost Guard — Rate limiting and model validation (Phase 1.7).

Blocks paid models, unknown models, and requests after daily limit.
No manual mode checks — system is autonomous.
"""

import logging
from typing import Any

logger = logging.getLogger("presence.system.cost_guard")


class CostGuard:
    """Validates every AI request before it's sent."""

    def __init__(self, config: Any, usage_tracker: Any):
        self._config = config
        self._usage = usage_tracker

    def check(self, model: str, mode: str = "local") -> dict[str, Any]:
        """
        Pre-flight check before an AI call.
        Returns {"allowed": True} or {"allowed": False, "reason": "..."}.
        """
        from ai.model_lock import is_model_allowed

        # 1. Block if daily limit reached
        if self._usage.calls_today >= self._config.MAX_CALLS_PER_DAY:
            reason = (
                f"Daily limit reached ({self._config.MAX_CALLS_PER_DAY} calls). "
                "Resets at midnight."
            )
            self._usage.record_blocked(reason)
            return {"allowed": False, "reason": reason}

        # 2. Block unknown/unlisted models
        if not is_model_allowed(model):
            reason = f"Model '{model}' is not on the allowed whitelist."
            self._usage.record_blocked(reason)
            return {"allowed": False, "reason": reason}

        # 3. Block paid models if not allowed
        if not self._config.ALLOW_PAID_MODELS:
            from ai.model_lock import is_cloud_model
            if is_cloud_model(model) and not model.endswith(":free"):
                if model != "meta-llama/llama-3.1-8b-instruct":
                    reason = f"Paid model '{model}' blocked."
                    self._usage.record_blocked(reason)
                    return {"allowed": False, "reason": reason}

        return {"allowed": True}

    def get_status(self) -> dict[str, Any]:
        """Return current cost-safe status."""
        return {
            "free_mode": self._config.FREE_MODE,
            "allow_paid": self._config.ALLOW_PAID_MODELS,
            "calls_today": self._usage.calls_today,
            "daily_limit": self._config.MAX_CALLS_PER_DAY,
            "remaining": max(0, self._config.MAX_CALLS_PER_DAY - self._usage.calls_today),
        }
