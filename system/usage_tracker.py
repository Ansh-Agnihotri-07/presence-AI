"""
Usage Tracker — Daily call counting and token tracking.

Persists usage data to memory/data/usage.json.
Resets daily at midnight.
"""

import json
import logging
from datetime import datetime, date
from pathlib import Path
from typing import Any

logger = logging.getLogger("presence.system.usage_tracker")


class UsageTracker:
    """Track daily AI usage: call count, tokens, routing decisions."""

    def __init__(self, data_dir: Path):
        self._path = data_dir / "usage.json"
        self._data: dict[str, Any] = self._load()

    def _load(self) -> dict[str, Any]:
        """Load usage data from disk or create defaults."""
        if self._path.exists():
            try:
                with open(self._path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                # Reset if it's a new day
                if data.get("date") != str(date.today()):
                    return self._default()
                return data
            except (json.JSONDecodeError, KeyError):
                return self._default()
        return self._default()

    def _default(self) -> dict[str, Any]:
        return {
            "date": str(date.today()),
            "calls_today": 0,
            "tokens_today": 0,
            "local_calls": 0,
            "cloud_calls": 0,
            "blocked_calls": 0,
            "log": [],
        }

    def _save(self):
        """Persist to disk."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._path.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self._data, f, indent=2)
        tmp.replace(self._path)

    def _check_day_reset(self):
        """Reset counters if it's a new day."""
        if self._data.get("date") != str(date.today()):
            self._data = self._default()
            self._save()

    @property
    def calls_today(self) -> int:
        self._check_day_reset()
        return self._data["calls_today"]

    def record_call(self, model: str, mode: str, tokens: int = 0):
        """Record a successful AI call."""
        self._check_day_reset()
        self._data["calls_today"] += 1
        self._data["tokens_today"] += tokens
        if mode == "local":
            self._data["local_calls"] += 1
        else:
            self._data["cloud_calls"] += 1

        # Keep last 100 log entries per day
        self._data["log"].append({
            "time": datetime.now().strftime("%H:%M:%S"),
            "model": model,
            "mode": mode,
            "tokens": tokens,
        })
        if len(self._data["log"]) > 100:
            self._data["log"] = self._data["log"][-100:]

        self._save()
        logger.info(
            f"Usage: call #{self._data['calls_today']} | "
            f"model={model} | mode={mode} | tokens={tokens}"
        )

    def record_blocked(self, reason: str):
        """Record a blocked call."""
        self._check_day_reset()
        self._data["blocked_calls"] += 1
        self._save()
        logger.warning(f"Usage: BLOCKED — {reason}")

    def get_summary(self) -> dict[str, Any]:
        """Get current day's usage summary."""
        self._check_day_reset()
        return {
            "date": self._data["date"],
            "calls": self._data["calls_today"],
            "tokens": self._data["tokens_today"],
            "local": self._data["local_calls"],
            "cloud": self._data["cloud_calls"],
            "blocked": self._data["blocked_calls"],
        }
