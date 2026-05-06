"""
Memory Index — Multi-layer memory indexing and retrieval.

Layers:
  - Short-term: current context window (last 10 messages)
  - Session: full current session history
  - Workspace: cross-session important facts, preferences, goals
  - Long-term: persistent user knowledge and patterns
  - Task: active/completed tasks
  - Reminder: pending/completed reminders
  - Preference: user habits, settings, communication style
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from core.config import config

logger = logging.getLogger("presence.memory.memory_index")


class MemoryIndex:
    """Multi-layer memory system for cognitive continuity."""

    def __init__(self):
        self._workspace_path = config.MEMORY_DIR / "workspace.json"
        self._workspace: dict[str, Any] = {
            "facts": [],
            "preferences": {},
            "knowledge": [],
            "updated_at": datetime.now().isoformat(),
        }

    def load(self):
        """Load workspace memory from disk."""
        if self._workspace_path.exists():
            try:
                with open(self._workspace_path, "r", encoding="utf-8") as f:
                    self._workspace = json.load(f)
                logger.info(f"Workspace memory loaded: {len(self._workspace.get('facts', []))} facts")
            except (json.JSONDecodeError, KeyError):
                self._workspace = self._default_workspace()
        else:
            self._workspace = self._default_workspace()
            self._save()

    def _default_workspace(self) -> dict[str, Any]:
        return {
            "facts": [],           # important facts about the user
            "preferences": {},     # user preferences (style, habits)
            "knowledge": [],       # persistent knowledge entries
            "updated_at": datetime.now().isoformat(),
        }

    def _save(self):
        """Persist workspace memory."""
        self._workspace["updated_at"] = datetime.now().isoformat()
        tmp = self._workspace_path.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self._workspace, f, indent=2, ensure_ascii=False)
        tmp.replace(self._workspace_path)

    # ── Facts (workspace-level, cross-session) ──

    def add_fact(self, fact: str, source: str = "conversation"):
        """Store an important fact about the user."""
        self._workspace["facts"].append({
            "text": fact,
            "source": source,
            "timestamp": datetime.now().isoformat(),
        })
        # Keep last 200 facts
        if len(self._workspace["facts"]) > 200:
            self._workspace["facts"] = self._workspace["facts"][-200:]
        self._save()
        logger.info(f"Fact stored: {fact[:50]}")

    def get_facts(self, limit: int = 20) -> list[dict[str, Any]]:
        """Get recent facts."""
        return self._workspace["facts"][-limit:]

    def search_facts(self, query: str) -> list[dict[str, Any]]:
        """Simple keyword search across facts."""
        words = set(query.lower().split())
        results = []
        for fact in self._workspace["facts"]:
            fact_words = set(fact["text"].lower().split())
            if words & fact_words:
                results.append(fact)
        return results[-10:]

    # ── Preferences ──

    def set_preference(self, key: str, value: Any):
        """Set a user preference."""
        self._workspace["preferences"][key] = value
        self._save()

    def get_preference(self, key: str, default: Any = None) -> Any:
        return self._workspace["preferences"].get(key, default)

    def get_all_preferences(self) -> dict[str, Any]:
        return self._workspace["preferences"]

    # ── Knowledge entries ──

    def add_knowledge(self, topic: str, content: str):
        """Store a persistent knowledge entry."""
        self._workspace["knowledge"].append({
            "topic": topic,
            "content": content,
            "timestamp": datetime.now().isoformat(),
        })
        if len(self._workspace["knowledge"]) > 100:
            self._workspace["knowledge"] = self._workspace["knowledge"][-100:]
        self._save()

    def search_knowledge(self, query: str) -> list[dict[str, Any]]:
        """Keyword search across knowledge entries."""
        words = set(query.lower().split())
        results = []
        for entry in self._workspace["knowledge"]:
            entry_words = set(entry["topic"].lower().split()) | set(entry["content"].lower().split())
            if words & entry_words:
                results.append(entry)
        return results[-5:]

    # ── Context building (for agent injection) ──

    def build_context(self, session_messages: list[dict], query: str = "") -> str:
        """Build a rich context string from all memory layers for agent injection."""
        parts = []

        # Short-term: last few messages from session
        if session_messages:
            recent = session_messages[-6:]
            convo = "\n".join(f"  {m['role']}: {m['text'][:200]}" for m in recent)
            parts.append(f"[Recent conversation]\n{convo}")

        # Workspace facts
        relevant_facts = self.search_facts(query) if query else self.get_facts(5)
        if relevant_facts:
            facts_str = "\n".join(f"  - {f['text']}" for f in relevant_facts[-5:])
            parts.append(f"[Known facts about user]\n{facts_str}")

        # Preferences
        prefs = self.get_all_preferences()
        if prefs:
            prefs_str = ", ".join(f"{k}={v}" for k, v in list(prefs.items())[:8])
            parts.append(f"[User preferences] {prefs_str}")

        # Relevant knowledge
        if query:
            knowledge = self.search_knowledge(query)
            if knowledge:
                k_str = "\n".join(f"  - {k['topic']}: {k['content'][:150]}" for k in knowledge)
                parts.append(f"[Relevant knowledge]\n{k_str}")

        return "\n\n".join(parts) if parts else ""


# Global singleton
memory_index = MemoryIndex()
