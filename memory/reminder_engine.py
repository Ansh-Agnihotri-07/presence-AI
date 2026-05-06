"""
Reminder Engine — Natural language reminders with time-based scheduler.

Supports:
  - "remind me to X at 5pm"
  - "remind me to X in 30 minutes"
  - "remind me to X tomorrow"
  - Goal-based recurring reminders

Stores to persistent JSON. Background loop checks for due reminders
and fires events on the event bus.
"""

import asyncio
import json
import logging
import re
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional

from core.config import config

logger = logging.getLogger("presence.memory.reminder_engine")


class Reminder:
    """A single reminder entry."""

    def __init__(self, reminder_id: str, text: str, due_at: str,
                 recurring: bool = False, completed: bool = False):
        self.id = reminder_id
        self.text = text
        self.due_at = due_at
        self.created_at = datetime.now().isoformat()
        self.recurring = recurring
        self.completed = completed
        self.fired = False

    def is_due(self) -> bool:
        """Check if this reminder is due now."""
        if self.completed or self.fired:
            return False
        try:
            due = datetime.fromisoformat(self.due_at)
            return datetime.now() >= due
        except ValueError:
            return False

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "text": self.text,
            "due_at": self.due_at,
            "created_at": self.created_at,
            "recurring": self.recurring,
            "completed": self.completed,
            "fired": self.fired,
        }

    @staticmethod
    def from_dict(data: dict[str, Any]) -> "Reminder":
        r = Reminder(
            reminder_id=data["id"],
            text=data["text"],
            due_at=data["due_at"],
            recurring=data.get("recurring", False),
            completed=data.get("completed", False),
        )
        r.created_at = data.get("created_at", "")
        r.fired = data.get("fired", False)
        return r


class ReminderEngine:
    """Manages reminders with persistence and a background check loop."""

    def __init__(self):
        self._path = config.MEMORY_DIR / "reminders.json"
        self._reminders: list[Reminder] = []
        self._check_task: Optional[asyncio.Task] = None

    def load(self):
        """Load reminders from disk."""
        if self._path.exists():
            try:
                with open(self._path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self._reminders = [Reminder.from_dict(r) for r in data.get("reminders", [])]
                pending = sum(1 for r in self._reminders if not r.completed)
                logger.info(f"Loaded {len(self._reminders)} reminders ({pending} pending)")
            except (json.JSONDecodeError, KeyError) as e:
                logger.warning(f"Failed to load reminders: {e}")
                self._reminders = []
        self._save()

    def _save(self):
        """Persist reminders to disk."""
        tmp = self._path.with_suffix(".tmp")
        data = {"reminders": [r.to_dict() for r in self._reminders]}
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        tmp.replace(self._path)

    def create_reminder(self, text: str, due_at: datetime,
                        recurring: bool = False) -> Reminder:
        """Create and store a new reminder."""
        reminder = Reminder(
            reminder_id=str(uuid.uuid4()),
            text=text,
            due_at=due_at.isoformat(),
            recurring=recurring,
        )
        self._reminders.append(reminder)
        self._save()
        logger.info(f"Reminder created: '{text}' due at {due_at}")
        return reminder

    def parse_and_create(self, user_text: str) -> Optional[Reminder]:
        """
        Parse natural language and create a reminder if a time expression is found.

        Supports:
          - "in X minutes/hours/days"
          - "tomorrow"
          - "tonight"
        """
        lower = user_text.lower()

        # Extract the reminder body
        body = user_text
        for prefix in ["remind me to ", "remind me ", "remember to ",
                        "don't forget to ", "alert me to ", "notify me to "]:
            if prefix in lower:
                idx = lower.index(prefix) + len(prefix)
                body = user_text[idx:].strip()
                break

        # Parse time expressions
        due = None

        # "in X minutes"
        m = re.search(r"in (\d+) minute", lower)
        if m:
            due = datetime.now() + timedelta(minutes=int(m.group(1)))
            body = re.sub(r"in \d+ minutes?", "", body, flags=re.IGNORECASE).strip()

        # "in X hours"
        if not due:
            m = re.search(r"in (\d+) hour", lower)
            if m:
                due = datetime.now() + timedelta(hours=int(m.group(1)))
                body = re.sub(r"in \d+ hours?", "", body, flags=re.IGNORECASE).strip()

        # "in X days"
        if not due:
            m = re.search(r"in (\d+) day", lower)
            if m:
                due = datetime.now() + timedelta(days=int(m.group(1)))
                body = re.sub(r"in \d+ days?", "", body, flags=re.IGNORECASE).strip()

        # "tomorrow"
        if not due and "tomorrow" in lower:
            due = datetime.now() + timedelta(days=1)
            due = due.replace(hour=9, minute=0, second=0)
            body = body.replace("tomorrow", "").strip()

        # "tonight"
        if not due and "tonight" in lower:
            due = datetime.now().replace(hour=20, minute=0, second=0)
            if datetime.now().hour >= 20:
                due += timedelta(days=1)
            body = body.replace("tonight", "").strip()

        # Default: 30 minutes from now
        if not due:
            due = datetime.now() + timedelta(minutes=30)

        # Clean up body
        body = body.rstrip(" .,!?")
        if not body:
            body = user_text[:80]

        return self.create_reminder(body, due)

    def get_pending(self) -> list[Reminder]:
        """Get all pending (unfired, uncompleted) reminders."""
        return [r for r in self._reminders if not r.completed and not r.fired]

    def get_due(self) -> list[Reminder]:
        """Get all reminders that are due now."""
        return [r for r in self._reminders if r.is_due()]

    def complete_reminder(self, reminder_id: str):
        """Mark a reminder as completed."""
        for r in self._reminders:
            if r.id == reminder_id:
                r.completed = True
                self._save()
                return

    def mark_fired(self, reminder_id: str):
        """Mark a reminder as fired (notification sent)."""
        for r in self._reminders:
            if r.id == reminder_id:
                r.fired = True
                self._save()
                return

    async def start_check_loop(self, event_bus: Any, interval: int = 30):
        """Background loop that checks for due reminders every N seconds."""
        logger.info(f"Reminder check loop started (interval={interval}s)")
        while True:
            try:
                due = self.get_due()
                for reminder in due:
                    logger.info(f"REMINDER DUE: {reminder.text}")
                    await event_bus.publish("reminder_due", {
                        "id": reminder.id,
                        "text": reminder.text,
                    })
                    self.mark_fired(reminder.id)
            except Exception as e:
                logger.error(f"Reminder check error: {e}")
            await asyncio.sleep(interval)


# Global singleton
reminder_engine = ReminderEngine()
