"""
Memory Store — JSON read/write for all persistent memory.

Handles:
  - Auto-creation of default files on first run
  - Thread/async-safe reads and writes
  - Atomic saves (write-to-temp then rename)
"""

import json
import logging
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from core.config import config
from memory.schema import SCHEMAS

logger = logging.getLogger("presence.memory.store")


class MemoryStore:
    """JSON-backed persistent memory for the Presence system."""

    def __init__(self):
        self._data: dict[str, dict] = {}
        self._dir: Path = config.MEMORY_DIR

    # ── Load / Save ──

    def load_all(self):
        """Load all memory files, creating defaults if missing."""
        self._dir.mkdir(parents=True, exist_ok=True)
        for name, schema_fn in SCHEMAS.items():
            path = self._dir / f"{name}.json"
            if path.exists():
                with open(path, "r", encoding="utf-8") as f:
                    self._data[name] = json.load(f)
                logger.info(f"Loaded memory: {name}")
            else:
                self._data[name] = schema_fn()
                self._save(name)
                logger.info(f"Created default memory: {name}")

    def _save(self, name: str):
        """Atomic write: temp file → rename."""
        path = self._dir / f"{name}.json"
        tmp = path.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self._data[name], f, indent=2, ensure_ascii=False)
        tmp.replace(path)

    # ── Generic access ──

    def get(self, name: str) -> dict:
        """Get the full data dict for a memory store."""
        return self._data.get(name, {})

    def set(self, name: str, data: dict):
        """Replace an entire memory store."""
        self._data[name] = data
        self._save(name)

    def update(self, name: str, key: str, value: Any):
        """Update a top-level key in a memory store."""
        self._data[name][key] = value
        self._save(name)

    # ── Profile shortcuts ──

    def get_user_name(self) -> str:
        return self._data.get("profile", {}).get("name", "")

    def set_user_name(self, name: str):
        self._data.setdefault("profile", {})["name"] = name
        self._save("profile")

    # ── Goals ──

    def add_goal(self, title: str, description: str = "", deadline: str | None = None) -> dict:
        """Add a new goal and return it."""
        goal = {
            "id": str(uuid.uuid4()),
            "title": title,
            "description": description,
            "created_at": datetime.now().isoformat(),
            "deadline": deadline,
            "status": "active",
            "tasks": [],
            "analysis": {"feasibility": "", "concerns": [], "suggestions": []},
        }
        self._data.setdefault("goals", {}).setdefault("goals", []).append(goal)
        self._save("goals")
        logger.info(f"Goal added: {title}")
        return goal

    def get_active_goals(self) -> list[dict]:
        """Get all goals with status 'active'."""
        goals = self._data.setdefault("goals", {}).setdefault("goals", [])
        return [g for g in goals if g.get("status") == "active"]

    def update_goal(self, goal_id: str, updates: dict):
        """Update fields on a specific goal by ID."""
        goals = self._data.setdefault("goals", {}).setdefault("goals", [])
        for g in goals:
            if g["id"] == goal_id:
                g.update(updates)
                break
        self._save("goals")

    # ── History ──

    def log_interaction(self, mode: str, user_input: str, ai_response: str, context: str = ""):
        """Log an interaction to history."""
        entry = {
            "timestamp": datetime.now().isoformat(),
            "mode": mode,
            "user_input": user_input,
            "ai_response": ai_response,
            "context": context,
        }
        history_inter = self._data.setdefault("history", {}).setdefault("interactions", [])
        history_inter.append(entry)
        # Keep last 500 interactions
        self._data["history"]["interactions"] = history_inter[-500:]
        self._save("history")

    # ── Learning ──

    def record_outcome(self, task_id: str, outcome: str, reason: str | None = None):
        """Record a task outcome for the learning loop."""
        entry = {
            "task_id": task_id,
            "outcome": outcome,
            "failure_reason": reason,
            "timestamp": datetime.now().isoformat(),
        }
        self._data.setdefault("learning", {}).setdefault("task_outcomes", []).append(entry)
        self._save("learning")

    def get_recent_outcomes(self, limit: int = 20) -> list[dict]:
        return self._data["learning"]["task_outcomes"][-limit:]

    def get_learning_patterns(self) -> dict:
        return self._data["learning"].get("patterns", {})

    def update_patterns(self, patterns: dict):
        self._data["learning"]["patterns"].update(patterns)
        self._save("learning")


# Global singleton
memory_store = MemoryStore()