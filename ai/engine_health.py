"""
Engine Health Gate — Runtime truth provider scoring and cooldown management.
"""

import time
import logging
from typing import Any

logger = logging.getLogger("presence.ai.health")

class EngineHealthGate:
    def __init__(self):
        self.registry: dict[str, dict[str, Any]] = {
            "local": self._base_struct(),
            "groq": self._base_struct(),
            "gemini": self._base_struct(),
            "cloud": self._base_struct(),
        }

    def _base_struct(self) -> dict[str, Any]:
        return {
            "schema_valid": True,
            "auth_valid": True,
            "quota_ok": True,
            "rate_limit_ok": True,
            "model_valid": True,
            "last_success": 0.0,
            "failure_rate": 0.0,
            "success_count": 0,
            "failure_count": 0,
            "cooldown_until": 0.0,
            "latency_avg": 0.0,
        }

    def record_success(self, engine: str, latency: float):
        """Update metrics on success."""
        if engine not in self.registry: return
        reg = self.registry[engine]
        reg["success_count"] += 1
        reg["last_success"] = time.monotonic()
        total = reg["success_count"] + reg["failure_count"]
        reg["failure_rate"] = reg["failure_count"] / total
        
        # very naive rolling avg
        reg["latency_avg"] = (reg["latency_avg"] * 0.7) + (latency * 0.3)
        
        # Clear transient faults
        reg["rate_limit_ok"] = True
        reg["cooldown_until"] = 0.0

    def record_failure(self, engine: str, error_type: str, cooldown_seconds: float = 0):
        """Update metrics on failure and set specific flags."""
        if engine not in self.registry: return
        reg = self.registry[engine]
        reg["failure_count"] += 1
        total = reg["success_count"] + reg["failure_count"]
        reg["failure_rate"] = reg["failure_count"] / total
        
        if error_type == "rate_limit":
            reg["rate_limit_ok"] = False
            reg["cooldown_until"] = time.monotonic() + max(cooldown_seconds, 30.0)
            logger.warning(f"Engine {engine} enters rate limit cooldown for {max(cooldown_seconds, 30.0)}s.")
        elif error_type == "schema":
            reg["schema_valid"] = False
            logger.error(f"Engine {engine} disabled due to permanent schema invalidity.")
        elif error_type == "quota":
            reg["quota_ok"] = False
            reg["cooldown_until"] = time.monotonic() + 3600 # 1 hour backoff for quota
            logger.warning(f"Engine {engine} hit quota limits. Cooldown 1h.")
            
    def compute_score(self, engine: str) -> float:
        """
        score = (success_rate * 0.4) + (latency_score * 0.2) + (quota_health * 0.2) + (schema_validity * 0.2)
        """
        reg = self.registry.get(engine)
        if not reg: return 0.0
        
        # Absolute blockers
        if not reg["schema_valid"] or not reg["auth_valid"] or not reg["model_valid"]:
            return 0.0
            
        success_rate = 1.0 - reg["failure_rate"]
        # Basic latency scoring: < 1s is 1.0, 5s is 0.0
        lat_score = max(0.0, 1.0 - (reg["latency_avg"] / 5.0))
        quota_score = 1.0 if reg["quota_ok"] else 0.0
        schema_score = 1.0 if reg["schema_valid"] else 0.0
        
        return (success_rate * 0.4) + (lat_score * 0.2) + (quota_score * 0.2) + (schema_score * 0.2)

    def is_eligible(self, engine: str) -> bool:
        """Check if an engine is eligible for ANY routing (single or hybrid)."""
        reg = self.registry.get(engine)
        if not reg: return False
        
        if time.monotonic() < reg["cooldown_until"]:
            return False
        else:
            # Auto-clear temporal locks when cooldown gracefully expires
            reg["rate_limit_ok"] = True
            
        return reg["schema_valid"] and reg["auth_valid"] and reg["quota_ok"] and reg["rate_limit_ok"] and reg["model_valid"]

health_registry = EngineHealthGate()
