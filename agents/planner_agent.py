"""
Planner Agent — Goal analysis, task structuring, and intelligent planning.

This agent does NOT blindly accept goals. It analyzes feasibility,
detects overload, and suggests better structuring.
"""

import logging
from typing import Any
from agents.base_agent import BaseAgent
from ai.ai_router import route_llm
from memory.store import memory_store

logger = logging.getLogger("presence.agents.planner")

PLANNER_SYSTEM_PROMPT = """You are the planning intelligence of Presence, a growth-oriented AI companion.

Your job is to help the user set, analyze, and structure goals and tasks.

You must NEVER blindly accept a goal. For each goal, you must:

1. ASSESS FEASIBILITY
   - Is it achievable with the stated time and energy?
   - Are there hidden dependencies?

2. CHECK FOR OVERLOAD
   - How many other active goals does the user have?
   - Is adding this realistic right now?

3. DETECT CONFLICTS
   - Does this new goal compete with existing ones?

4. ANALYZE PATTERNS (use provided learning data)
   - Has the user attempted similar goals before?
   - What blocked them last time?

5. STRUCTURE THE PLAN
   - Break the goal into concrete, small, actionable tasks
   - Suggest a realistic timeline (daily/weekly)
   - Prioritize ruthlessly

6. ASK CLARIFYING QUESTIONS
   - "What's your daily availability for this?"
   - "Have you tried this before? What happened?"
   - "What usually gets in the way?"

Keep your tone supportive but honest. If a goal seems unrealistic, say so gently and suggest alternatives.

Respond conversationally, not as a bullet-point machine — though structured breakdowns are welcome when analyzing.

When you create a plan, format tasks as a simple numbered list with realistic time estimates.
"""

PLAN_INTENT_KEYWORDS = [
    "goal", "goals", "plan", "planning", "task", "tasks",
    "i want to", "i need to", "i'm going to", "help me with",
    "how can i", "what should i", "i should", "i want",
    "schedule", "organize", "track", "improve", "learn",
    "start", "begin", "commit", "achieve", "build",
]


class PlannerAgent(BaseAgent):
    name = "planner"

    async def can_handle(self, event: dict[str, Any]) -> bool:
        text = event.get("text", "").lower()
        return any(kw in text for kw in PLAN_INTENT_KEYWORDS)

    async def handle(self, event: dict[str, Any]) -> dict[str, Any]:
        user_text = event.get("text", "")

        # Build context
        context_parts = []

        # Active goals
        goals = memory_store.get_active_goals()
        if goals:
            goals_summary = "\n".join(
                f"- {g['title']} (status: {g['status']}, tasks: {len(g.get('tasks', []))})"
                for g in goals
            )
            context_parts.append(f"Current active goals:\n{goals_summary}")
        else:
            context_parts.append("User has no active goals yet.")

        # Learning patterns
        patterns = memory_store.get_learning_patterns()
        if any(patterns.values()):
            context_parts.append(f"Known patterns: {patterns}")

        # Recent outcomes
        outcomes = memory_store.get_recent_outcomes(10)
        if outcomes:
            outcomes_text = "\n".join(
                f"- Task {o['task_id'][:8]}: {o['outcome']}" +
                (f" (reason: {o['failure_reason']})" if o.get('failure_reason') else "")
                for o in outcomes
            )
            context_parts.append(f"Recent task outcomes:\n{outcomes_text}")

        context = "\n\n".join(context_parts)

        response, trace = await route_llm(
            system_prompt=PLANNER_SYSTEM_PROMPT,
            user_message=user_text,
            context=context,
            mode=event.get("cognitive_mode", "planning"),
        )

        # Log the interaction
        memory_store.log_interaction(
            mode=event.get("mode", "chat"),
            user_input=user_text,
            ai_response=response,
            context="planner",
        )

        return {"text": response, "action": "plan_analysis", "metadata": {}}