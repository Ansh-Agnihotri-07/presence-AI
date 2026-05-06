"""
Task Structurer — Breaks down goals into actionable tasks.

Provides utilities for task decomposition that agents can use
to create structured, time-estimated task lists.
"""

import logging
import uuid
from datetime import datetime
from memory.store import memory_store

logger = logging.getLogger("presence.planner.task_structurer")


def add_task_to_goal(goal_id: str, title: str, estimate_minutes: int = 30, priority: int = 3) -> dict:
    """
    Add a task to an existing goal.

    Args:
        goal_id: The goal ID to add the task to
        title: Task title
        estimate_minutes: Estimated time in minutes
        priority: 1 (highest) to 5 (lowest)

    Returns:
        The created task dict
    """
    task = {
        "id": str(uuid.uuid4()),
        "title": title,
        "estimate_minutes": estimate_minutes,
        "priority": priority,
        "status": "pending",
        "created_at": datetime.now().isoformat(),
        "completed_at": None,
    }

    goals_data = memory_store.get("goals")
    for goal in goals_data.get("goals", []):
        if goal["id"] == goal_id:
            goal.setdefault("tasks", []).append(task)
            break

    memory_store.set("goals", goals_data)
    logger.info(f"Task added to goal {goal_id[:8]}: {title}")
    return task


def complete_task(goal_id: str, task_id: str, outcome: str = "success", reason: str | None = None):
    """
    Mark a task as completed and record the outcome.

    Args:
        goal_id: Parent goal ID
        task_id: Task ID to complete
        outcome: 'success', 'failure', or 'partial'
        reason: Optional reason (especially for failures)
    """
    goals_data = memory_store.get("goals")
    for goal in goals_data.get("goals", []):
        if goal["id"] == goal_id:
            for task in goal.get("tasks", []):
                if task["id"] == task_id:
                    task["status"] = "completed"
                    task["completed_at"] = datetime.now().isoformat()
                    task["outcome"] = outcome
                    break
            break

    memory_store.set("goals", goals_data)
    memory_store.record_outcome(task_id, outcome, reason)
    logger.info(f"Task {task_id[:8]}: {outcome}")


def get_next_tasks(limit: int = 3) -> list[dict]:
    """
    Get the next tasks the user should work on, sorted by priority.

    Returns tasks across all active goals, highest priority first.
    """
    goals = memory_store.get_active_goals()
    pending = []
    for goal in goals:
        for task in goal.get("tasks", []):
            if task.get("status") == "pending":
                pending.append({**task, "goal_title": goal["title"], "goal_id": goal["id"]})

    pending.sort(key=lambda t: t.get("priority", 3))
    return pending[:limit]