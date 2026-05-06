"""
Learning Agent — Adaptive learning loop.

Analyzes task outcomes, identifies patterns, and adjusts future planning.
Never blames. Always seeks to understand and adapt.
"""

import logging
from typing import Any
from agents.base_agent import BaseAgent
from ai.ai_router import route_llm
from memory.store import memory_store

logger = logging.getLogger("presence.agents.learning")

LEARNING_SYSTEM_PROMPT = """You are the learning and reflection module of Presence, a growth-oriented AI companion.

When the user reflects on their progress, completed tasks, or failures, your job is to:

1. ACKNOWLEDGE honestly — name what happened without judgment
2. ANALYZE the factors:
   - Was it a time issue?
   - Energy / motivation?
   - Clarity problem?
   - Goal was too big?
   - External blockers?
   - Wrong strategy?
3. IDENTIFY PATTERNS from past data (provided as context)
4. SUGGEST ADAPTATIONS — concrete, small changes to try next time
5. REINFORCE what worked — if anything went well, name it specifically

Rules:
- NEVER blame or guilt the user
- NEVER say "you should have..."
- ALWAYS frame failures as learning signals, not character flaws
- Be warm, direct, and constructive
- Suggest ONE concrete next step, not a lecture

You speak like a thoughtful mentor who genuinely cares.
"""

LEARNING_INTENT_KEYWORDS = [
    "how am i doing", "reflect", "review", "progress",
    "i failed", "i didn't", "couldn't", "didn't finish",
    "i completed", "i finished", "i did it", "done with",
    "what's working", "what went wrong", "stuck",
    "struggling", "falling behind", "overwhelmed",
]


class LearningAgent(BaseAgent):
    name = "learning"

    async def can_handle(self, event: dict[str, Any]) -> bool:
        text = event.get("text", "").lower()
        return any(kw in text for kw in LEARNING_INTENT_KEYWORDS)

    async def handle(self, event: dict[str, Any]) -> dict[str, Any]:
        user_text = event.get("text", "")

        # Build rich context from learning memory
        context_parts = []

        # Active goals
        goals = memory_store.get_active_goals()
        if goals:
            goals_summary = "\n".join(
                f"- {g['title']} ({len(g.get('tasks', []))} tasks, status: {g['status']})"
                for g in goals
            )
            context_parts.append(f"Active goals:\n{goals_summary}")

        # Recent outcomes
        outcomes = memory_store.get_recent_outcomes(15)
        if outcomes:
            success = sum(1 for o in outcomes if o["outcome"] == "success")
            fail = sum(1 for o in outcomes if o["outcome"] == "failure")
            context_parts.append(f"Recent outcomes: {success} successes, {fail} failures out of {len(outcomes)} tasks")

            failures = [o for o in outcomes if o.get("failure_reason")]
            if failures:
                reasons = "\n".join(f"- {o['failure_reason']}" for o in failures[-5:])
                context_parts.append(f"Recent failure reasons:\n{reasons}")

        # Learning patterns
        patterns = memory_store.get_learning_patterns()
        if patterns.get("common_blockers"):
            context_parts.append(f"Known blockers: {', '.join(patterns['common_blockers'])}")
        if patterns.get("success_factors"):
            context_parts.append(f"Success factors: {', '.join(patterns['success_factors'])}")
        if patterns.get("peak_hours"):
            context_parts.append(f"Peak productivity hours: {patterns['peak_hours']}")

        context = "\n\n".join(context_parts) if context_parts else "No prior data yet."

        response, trace = await route_llm(
            system_prompt=LEARNING_SYSTEM_PROMPT,
            user_message=user_text,
            context=context,
            mode=event.get("cognitive_mode", "fact"),
        )

        memory_store.log_interaction(
            mode=event.get("mode", "chat"),
            user_input=user_text,
            ai_response=response,
            context="learning_reflection",
        )

        return {"text": response, "action": "learning_reflection", "metadata": {"runtime_trace": trace}}