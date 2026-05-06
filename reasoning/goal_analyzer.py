"""
Goal Analyzer — Feasibility, overload, and conflict analysis.

Provides structured analysis helpers that the PlannerAgent uses
to enrich its LLM context before generating advice.
"""

import logging
from memory.store import memory_store

logger = logging.getLogger("presence.reasoning.goal_analyzer")


def analyze_workload() -> dict:
    """
    Analyze the user's current workload.

    Returns a summary dict with:
      - active_count: number of active goals
      - overloaded: True if >5 active goals
      - total_tasks: total number of tasks across all goals
    """
    goals = memory_store.get_active_goals()
    total_tasks = sum(len(g.get("tasks", [])) for g in goals)

    return {
        "active_count": len(goals),
        "overloaded": len(goals) > 5,
        "total_tasks": total_tasks,
        "goal_titles": [g["title"] for g in goals],
    }


def check_conflicts(new_goal_title: str) -> list[str]:
    """
    Check if a new goal might conflict with existing goals.

    Returns a list of potential conflict descriptions.
    """
    goals = memory_store.get_active_goals()
    conflicts = []

    # Simple keyword overlap check (enhanced by LLM in agent)
    new_words = set(new_goal_title.lower().split())
    for g in goals:
        existing_words = set(g["title"].lower().split())
        overlap = new_words & existing_words
        if overlap and overlap - {"a", "the", "to", "and", "or", "in", "on", "for"}:
            conflicts.append(f"Possible overlap with: '{g['title']}'")

    return conflicts


def success_rate() -> float:
    """Calculate the user's recent task success rate."""
    outcomes = memory_store.get_recent_outcomes(20)
    if not outcomes:
        return 0.0
    successes = sum(1 for o in outcomes if o["outcome"] == "success")
    return successes / len(outcomes)


def common_failure_reasons() -> list[str]:
    """Extract the most common failure reasons from recent outcomes."""
    outcomes = memory_store.get_recent_outcomes(30)
    reasons = [o["failure_reason"] for o in outcomes if o.get("failure_reason")]
    # Simple frequency count
    from collections import Counter
    counter = Counter(reasons)
    return [reason for reason, _ in counter.most_common(5)]