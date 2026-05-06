"""
Follow-Up Scheduler — Proactive nudges, check-ins, and reminders.

Runs as a background async loop. The AI initiates interaction — it doesn't
just wait passively for the user.

Behaviors:
  - Session greeting (on startup)
  - Task reminders (upcoming/overdue)
  - Gentle check-ins after inactivity
  - Reflection prompts after goal milestones
"""

import asyncio
import logging
from datetime import datetime

from core.config import config
from memory.store import memory_store
from planner.task_structurer import get_next_tasks

logger = logging.getLogger("presence.scheduler.follow_up")


async def start_scheduler(event_bus):
    """Start the background follow-up loop."""

    # ── Session greeting ──
    await asyncio.sleep(3)  # Let UI settle
    user_name = memory_store.get_user_name()
    greeting = _build_greeting(user_name)
    await event_bus.publish("agent_response", {
        "text": greeting,
        "agent": "scheduler",
        "action": "greeting",
        "metadata": {},
    })
    await event_bus.publish("response_delivered", {})

    # ── Background check-in loop ──
    interval = config.CHECKIN_INTERVAL_MINUTES * 60

    while True:
        await asyncio.sleep(interval)

        if not config.NUDGE_ENABLED:
            continue

        nudge = _build_nudge()
        if nudge:
            # Signal the orb to pulse (waiting state)
            await event_bus.publish("waiting_input", {})
            await asyncio.sleep(1)

            await event_bus.publish("agent_response", {
                "text": nudge,
                "agent": "scheduler",
                "action": "nudge",
                "metadata": {},
            })
            await event_bus.publish("response_delivered", {})


def _build_greeting(user_name: str) -> str:
    """Build a warm session greeting."""
    hour = datetime.now().hour
    if hour < 12:
        time_word = "morning"
    elif hour < 17:
        time_word = "afternoon"
    else:
        time_word = "evening"

    name_part = f", {user_name}" if user_name else ""

    # Check for pending tasks
    next_tasks = get_next_tasks(2)
    task_part = ""
    if next_tasks:
        titles = " and ".join(f'"{t["title"]}"' for t in next_tasks[:2])
        task_part = f"\n\nYou've got {titles} on your list. Want to pick up where you left off?"

    return f"Good {time_word}{name_part}. I'm here whenever you need me.{task_part}"


def _build_nudge() -> str | None:
    """Build a gentle check-in nudge, or None if not needed."""
    next_tasks = get_next_tasks(1)

    if next_tasks:
        task = next_tasks[0]
        return (
            f"Hey — just checking in. You've got \"{task['title']}\" "
            f"from your \"{task['goal_title']}\" goal. "
            f"Want to work on it, or would you rather adjust the plan?"
        )

    goals = memory_store.get_active_goals()
    if not goals:
        return "It's been a while. If you've been thinking about any goals or projects, I'm here to help you think them through."

    return None