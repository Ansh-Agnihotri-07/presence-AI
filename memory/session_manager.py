"""
Session Manager — Multi-session conversation management.

Each session has its own conversation history, metadata, and persistence.
Sessions are stored as individual JSON files in memory/data/sessions/.
"""

import json
import logging
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from core.config import config

logger = logging.getLogger("presence.memory.session_manager")


class Session:
    """A single conversation session."""

    def __init__(self, session_id: str, title: str = "New Session",
                 created_at: str = "", messages: list | None = None):
        self.id = session_id
        self.title = title
        self.created_at = created_at or datetime.now().isoformat()
        self.last_active = datetime.now().isoformat()
        self.messages: list[dict[str, Any]] = messages or []
        self.archived = False

    def add_message(self, role: str, text: str, metadata: dict | None = None):
        """Add a message to this session."""
        self.messages.append({
            "role": role,
            "text": text,
            "timestamp": datetime.now().isoformat(),
            "metadata": metadata or {},
        })
        self.last_active = datetime.now().isoformat()

    def get_recent(self, count: int = 10) -> list[dict[str, Any]]:
        """Get the last N messages."""
        return self.messages[-count:]

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "created_at": self.created_at,
            "last_active": self.last_active,
            "archived": self.archived,
            "messages": self.messages,
        }

    @staticmethod
    def from_dict(data: dict[str, Any]) -> "Session":
        s = Session(
            session_id=data["id"],
            title=data.get("title", "Untitled"),
            created_at=data.get("created_at", ""),
            messages=data.get("messages", []),
        )
        s.last_active = data.get("last_active", s.created_at)
        s.archived = data.get("archived", False)
        return s


class SessionManager:
    """Manages multiple conversation sessions with persistence."""

    def __init__(self):
        self._sessions_dir = config.SESSIONS_DIR
        self._sessions: dict[str, Session] = {}
        self._active_id: Optional[str] = None

    def load_all(self):
        """Load all sessions from disk."""
        self._sessions_dir.mkdir(parents=True, exist_ok=True)
        for path in self._sessions_dir.glob("*.json"):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                session = Session.from_dict(data)
                self._sessions[session.id] = session
            except (json.JSONDecodeError, KeyError) as e:
                logger.warning(f"Failed to load session {path.name}: {e}")

        # Set active to most recent, or create default
        if self._sessions:
            most_recent = max(self._sessions.values(), key=lambda s: s.last_active)
            self._active_id = most_recent.id
            logger.info(f"Loaded {len(self._sessions)} sessions, active: {most_recent.title}")
        else:
            self.create_session("Default")
            logger.info("No sessions found — created default session")

    def _save_session(self, session: Session):
        """Persist a session to disk."""
        path = self._sessions_dir / f"{session.id}.json"
        tmp = path.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(session.to_dict(), f, indent=2, ensure_ascii=False)
        tmp.replace(path)

    # ── Session CRUD ──

    def create_session(self, title: str = "New Session") -> Session:
        """Create a new session and set it as active."""
        session = Session(session_id=str(uuid.uuid4()), title=title)
        self._sessions[session.id] = session
        self._active_id = session.id
        self._save_session(session)
        logger.info(f"Created session: {title} ({session.id[:8]})")
        return session

    def get_active_session(self) -> Optional[Session]:
        """Get the currently active session."""
        if self._active_id and self._active_id in self._sessions:
            return self._sessions[self._active_id]
        return None

    def switch_session(self, session_id: str) -> Optional[Session]:
        """Switch to a different session."""
        if session_id in self._sessions:
            self._active_id = session_id
            session = self._sessions[session_id]
            logger.info(f"Switched to session: {session.title}")
            return session
        return None

    def delete_session(self, session_id: str) -> bool:
        """Delete a session."""
        if session_id in self._sessions:
            session = self._sessions.pop(session_id)
            path = self._sessions_dir / f"{session_id}.json"
            if path.exists():
                path.unlink()
            if self._active_id == session_id:
                if self._sessions:
                    self._active_id = list(self._sessions.keys())[0]
                else:
                    self.create_session("Default")
            logger.info(f"Deleted session: {session.title}")
            return True
        return False

    def archive_session(self, session_id: str) -> bool:
        """Archive a session (hidden but preserved)."""
        if session_id in self._sessions:
            self._sessions[session_id].archived = True
            self._save_session(self._sessions[session_id])
            return True
        return False

    def list_sessions(self, include_archived: bool = False) -> list[dict[str, Any]]:
        """List all sessions (metadata only, no messages)."""
        result = []
        for s in sorted(self._sessions.values(), key=lambda x: x.last_active, reverse=True):
            if not include_archived and s.archived:
                continue
            result.append({
                "id": s.id,
                "title": s.title,
                "created_at": s.created_at,
                "last_active": s.last_active,
                "message_count": len(s.messages),
                "archived": s.archived,
            })
        return result

    # ── Message operations ──

    def add_message(self, role: str, text: str, metadata: dict | None = None):
        """Add a message to the active session and persist."""
        session = self.get_active_session()
        if session:
            session.add_message(role, text, metadata)
            self._save_session(session)

    def get_context(self, count: int = 10) -> list[dict[str, Any]]:
        """Get recent messages from the active session for context injection."""
        session = self.get_active_session()
        if session:
            return session.get_recent(count)
        return []

    def auto_title(self, first_message: str):
        """Auto-generate a session title from the first message."""
        session = self.get_active_session()
        if session and session.title in ("New Session", "Default") and first_message:
            title = first_message[:50].strip()
            if len(first_message) > 50:
                title += "…"
            session.title = title
            self._save_session(session)


# Global singleton
session_manager = SessionManager()
