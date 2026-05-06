"""
Memory Schema — Default structures for all memory files.
"""

from datetime import datetime


def default_profile() -> dict:
    return {
        "name": "",
        "created_at": datetime.now().isoformat(),
        "preferences": {
            "interaction_mode": "chat",
            "voice_enabled": False,
            "theme": "dark",
        },
        "personality_calibration": {},
    }


def default_goals() -> dict:
    return {"goals": []}


def default_history() -> dict:
    return {"interactions": []}


def default_learning() -> dict:
    return {
        "patterns": {
            "peak_hours": [],
            "productive_session_length": None,
            "common_blockers": [],
            "success_factors": [],
        },
        "adaptations": [],
        "task_outcomes": [],
    }


SCHEMAS = {
    "profile": default_profile,
    "goals": default_goals,
    "history": default_history,
    "learning": default_learning,
}