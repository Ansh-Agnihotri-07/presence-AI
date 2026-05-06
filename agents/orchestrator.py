"""
Orchestrator — Mode-aware cognitive routing hub (Phase 2.1).

Routes incoming events through:
  1. Mode classification (SYSTEM, TECH, FACT, etc.)
  2. Task analysis (complexity, type)
  3. Agent selection (mode-appropriate)
  4. Memory context injection
  5. Response dispatch

Mode determines cognition. Persona is presentation only.
"""

import asyncio
import logging
from typing import Any

from core.event_bus import event_bus
from ai.mode_classifier import classify_mode, MODE_MEMORY, MODE_PLANNING
from agents.companion_agent import CompanionAgent
from agents.planner_agent import PlannerAgent
from agents.screen_agent import ScreenAgent
from agents.learning_agent import LearningAgent
from agents.builder_agent import BuilderAgent

logger = logging.getLogger("presence.agents.orchestrator")


class Orchestrator:
    """Central routing hub — mode-aware, memory-integrated."""

    def __init__(self):
        self.agents = [
            BuilderAgent(),   # ← first priority: project scaffolding
            ScreenAgent(),
            PlannerAgent(),
            LearningAgent(),
            CompanionAgent(),  # default fallback
        ]

    def register_all(self):
        """Subscribe to user_input events."""
        event_bus.subscribe("user_input", self._handle_input)
        logger.info(f"Orchestrator registered {len(self.agents)} agents")

    async def _handle_input(self, event: dict[str, Any]):
        """Route input: classify mode -> analyze task -> select agent -> respond."""
        text = event.get("text", "").strip()
        if not text:
            return

        # ── 1. Classify cognitive mode ──
        mode = classify_mode(text)
        event["cognitive_mode"] = mode

        # ── 2. Task analysis ──
        from ai.task_analyzer import analyze_task
        analysis = analyze_task(text)
        event["task_analysis"] = analysis

        # ── 3. Check for reminder intent ──
        if analysis["task_type"] == "reminder":
            await self._handle_reminder(text, event)
            return

        # ── 4. Signal thinking state ──
        await event_bus.publish("llm_thinking", {})

        # ── 5. Inject memory context ──
        from memory.recall_engine import recall_for_query
        memory_context = recall_for_query(text)
        if memory_context:
            existing = event.get("context", "")
            event["context"] = f"{existing}\n\n{memory_context}" if existing else memory_context

        # ── 5b. BUILDER INTERCEPT (before mode-binding) ──
        # Builder intent MUST be checked before direct-execution mode binding,
        # because "Build a Flask API" matches TECH patterns but must route to BuilderAgent.
        from agents.builder_agent import is_builder_request
        if is_builder_request(text):
            logger.info(f"[BUILDER] Intercepted BEFORE mode-binding. Mode was: {mode.upper()}")
            builder = None
            for agent in self.agents:
                if agent.name == "builder":
                    builder = agent
                    break
            if builder:
                try:
                    result = await builder.handle(event)
                except Exception as e:
                    logger.error(f"[BUILDER] Agent failed: {e}", exc_info=True)
                    result = {
                        "text": f"[ERROR] Builder execution failed: {e}",
                        "action": None,
                        "metadata": {"error": str(e)},
                    }
                response_text = result.get("text", "")
                from memory.recall_engine import store_interaction
                store_interaction(text, response_text, agent="builder")
                await event_bus.publish("agent_response", {
                    "text": response_text,
                    "agent": "builder",
                    "mode": mode,
                    "action": result.get("action"),
                    "metadata": result.get("metadata", {}),
                })
                await event_bus.publish("response_delivered", {})
                return

        # ── 6. Select execution path (Mode-Binding) ──
        if mode in ["system", "tech", "fact", "meta"]:
            # Direct engine execution for technical modes — NO companion wrapper
            logger.info(f"Direct Execution Binding: {mode.upper()} (bypassing agent wrappers)")
            from ai.ai_router import route_llm
            from agents.companion_agent import MODE_PROMPTS, CompanionAgent
            
            system_prompt = MODE_PROMPTS.get(mode, "")
            context_parts = []
            if mode == "system":
                context_parts.extend(CompanionAgent()._build_system_context())
            elif mode == "meta":
                context_parts.extend(CompanionAgent()._build_meta_context())
                
            context = "\n\n".join(context_parts) if context_parts else ""
            
            response_text, trace = await route_llm(
                system_prompt=system_prompt,
                user_message=text,
                context=context,
                mode=mode,
            )
            
            # Rule 9 Tripwire
            forbidden = ["i feel", "i think", "my friend", "we can ", "together", "let's ", "happy to", "i am a "]
            if any(f in response_text.lower() for f in forbidden):
                logger.error(f"CRITICAL SYSTEM ERROR (Rule 9): Persona language detected in {mode.upper()} mode.")
                response_text = f"[CRITICAL ERROR] Response nullified due to Cognitive Integrity violation (persona contamination in {mode.upper()} mode)."
                
            # Intercept and inject TRUE runtime trace if user requested a diagnostic report
            if "HYBRID EXECUTION" in text.upper() or "DIAGNOSTIC" in text.upper():
                real_report = "\n\n─── ACTUAL RUNTIME TRACE ───\n"
                real_report += f"Engines Called: {', '.join(trace.get('engines_called', [])) or 'None'}\n"
                real_report += f"Engines Responded: {', '.join(trace.get('engines_responded', [])) or 'None'}\n"
                real_report += f"Engines Succeeded: {', '.join(trace.get('engines_succeeded', [])) or 'None'}\n"
                real_report += f"Engines Failed: {trace.get('engines_failed', {})}\n"
                real_report += f"Hybrid Used: {trace.get('hybrid_used', False)}\n"
                real_report += f"Execution Mode: {trace.get('execution_mode', 'single')}\n"
                real_report += f"Quorum Reached: {trace.get('quorum_reached', False)}\n"
                real_report += f"OpenRouter Used: {'cloud' in trace.get('engines_called', [])}\n"
                real_report += f"Synthesis Applied: {trace.get('synthesis_executed', False)}\n"
                real_report += "────────────────────────────\n"
                
                if "─── HYBRID EXECUTION REPORT ───" in response_text:
                    response_text = response_text.split("─── HYBRID EXECUTION REPORT ───")[0] + real_report
                else:
                    response_text += real_report

            selected_name = "direct_router"
            action = None
            metadata = {"cognitive_mode": mode, "runtime_trace": trace}
            
        else:
            # Persona/Planning pipeline allowed
            selected = self.agents[-1]  # default: companion
            for agent in self.agents:
                if await agent.can_handle(event):
                    selected = agent
                    break
    
            logger.info(f"Routing: mode={mode.upper()}, agent={selected.name}, complexity={analysis['complexity']}")
    
            # ── 7. Execute Agent ──
            try:
                result = await selected.handle(event)
            except Exception as e:
                logger.error(f"Agent {selected.name} failed: {e}", exc_info=True)
                result = {
                    "text": "Something went wrong processing that request.",
                    "action": None,
                    "metadata": {"error": str(e)},
                }
    
            response_text = result.get("text", "")
            selected_name = selected.name
            action = result.get("action")
            metadata = result.get("metadata", {})

        # ── 8. Store interaction ──
        from memory.recall_engine import store_interaction
        store_interaction(text, response_text, agent=selected_name)

        # ── 9. Dispatch response ──
        await event_bus.publish("agent_response", {
            "text": response_text,
            "agent": selected_name,
            "mode": mode,
            "action": action,
            "metadata": metadata,
        })
        await event_bus.publish("response_delivered", {})

    async def _handle_reminder(self, text: str, event: dict[str, Any]):
        """Handle reminder creation."""
        from memory.reminder_engine import reminder_engine

        reminder = reminder_engine.parse_and_create(text)
        if reminder:
            response = f"Reminder set: \"{reminder.text}\" (due: {reminder.due_at[:16].replace('T', ' at ')})"
        else:
            response = "Couldn't parse that reminder. Try: 'remind me to X in 30 minutes'"

        from memory.recall_engine import store_interaction
        store_interaction(text, response, agent="reminder")

        await event_bus.publish("agent_response", {
            "text": response,
            "agent": "reminder",
            "mode": "memory",
            "action": "reminder_created",
            "metadata": {"reminder_id": reminder.id if reminder else None},
        })
        await event_bus.publish("response_delivered", {})


orchestrator = Orchestrator()