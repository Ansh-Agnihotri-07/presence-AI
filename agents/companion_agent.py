"""
Companion Agent — Mode-switched cognitive agent (Phase 2.1.1).

Security: API keys are MASKED in all prompts. Never raw secrets.
Telemetry: Performance stats only injected if data exists. No fake data.
SYSTEM/META modes: zero persona, zero emotion, zero companionship.
"""

import logging
from typing import Any
from agents.base_agent import BaseAgent
from ai.ai_router import route_llm
from ai.mode_classifier import is_persona_disabled
from memory.store import memory_store

logger = logging.getLogger("presence.agents.companion")

# ── Mode-switched system prompts ──

PROMPT_SYSTEM = """You are a technical system status reporter.
Report ONLY: engine states, model names, routing config, masked credentials, system health.
No persona. No warmth. No encouragement. No emotional framing. No growth language.
Pure technical output. If asked about API keys, show MASKED form only (e.g. gsk_****82F)."""

PROMPT_TECH = """You are a technical debugging assistant.
Analyze errors, crashes, bugs, and code issues.
Diagnostic and structured. Concrete fixes only.
No persona. No encouragement. No emotional framing."""

PROMPT_FACT = """You are a factual Q&A system.
Short, exact answers. No preamble. No personality. No elaboration unless asked.
If you don't know, say so."""

PROMPT_PLANNING = """You are a planning and task structuring assistant.
Organize tasks, create schedules, break down projects.
Structured output: lists, steps, priorities. Minimal personality."""

PROMPT_MEMORY = """You are a memory-aware assistant.
Reference the user's stored context, preferences, and history when relevant.
Be helpful and context-aware."""

PROMPT_META = """You are a system architecture analyst.
Explain your own routing logic, cognition architecture, engine structure, and mode system.
Only report real data. If performance telemetry exists, report it. If not, say so.
No persona. No warmth. No companionship. Analytical only."""

PROMPT_CHAT = """You are a helpful AI assistant.
Respond naturally and conversationally. Be concise but thorough.
Adapt tone to the user's message. Focus on being useful."""

PROMPT_PRESENCE = """You are a calm, intelligent AI companion.
Warm, supportive, and honest. Speak like a thoughtful friend.
Remember what the user has told you. Celebrate small wins.
Conversational and concise."""

MODE_PROMPTS = {
    "system":   PROMPT_SYSTEM,
    "tech":     PROMPT_TECH,
    "fact":     PROMPT_FACT,
    "planning": PROMPT_PLANNING,
    "memory":   PROMPT_MEMORY,
    "meta":     PROMPT_META,
    "chat":     PROMPT_CHAT,
    "presence": PROMPT_PRESENCE,
}


def _mask_key(key: str) -> str:
    """Mask an API key: show first 4 + last 3 chars only."""
    if not key or len(key) < 10:
        return "not configured"
    return f"{key[:4]}****{key[-3:]}"


class CompanionAgent(BaseAgent):
    name = "companion"

    async def can_handle(self, event: dict[str, Any]) -> bool:
        return True

    async def handle(self, event: dict[str, Any]) -> dict[str, Any]:
        user_text = event.get("text", "")
        mode = event.get("cognitive_mode", "chat")
        system_prompt = MODE_PROMPTS.get(mode, PROMPT_CHAT)

        context_parts = []

        # ── SYSTEM mode: engine metadata + masked keys (never raw) ──
        if mode == "system":
            context_parts.extend(self._build_system_context())

        # ── META mode: architecture + gated telemetry ──
        elif mode == "meta":
            context_parts.extend(self._build_meta_context())

        # ── Persona-enabled modes: inject personal context ──
        if not is_persona_disabled(mode):
            context_parts.extend(self._build_personal_context(event))

        context = "\n\n".join(context_parts) if context_parts else ""

        # ── SELF-CHECK (Rule 8) ──
        # 1. Verify mode correctness
        if mode not in MODE_PROMPTS:
            logger.error(f"Self-check fail: invalid mode '{mode}'")
            return {"text": "Internal Error: Invalid cognitive mode detected.", "action": None, "metadata": {}}
            
        # 2. Verify prompt isolation
        if system_prompt != MODE_PROMPTS[mode]:
            logger.error(f"Self-check fail: prompt isolation broken for '{mode}'")
            return {"text": "Internal Error: Prompt isolation failure.", "action": None, "metadata": {}}
            
        # 3. Verify persona flag correctness
        persona_disabled = is_persona_disabled(mode)
        if persona_disabled and bool([p for p in context_parts if "User's name:" in p]):
            logger.error(f"Self-check fail: persona context leaked into strictly technical mode '{mode}'")
            return {"text": "Internal Error: Persona context leak detected.", "action": None, "metadata": {}}

        response, trace = await route_llm(
            system_prompt=system_prompt,
            user_message=user_text,
            context=context,
            mode=mode,
        )

        # ── FAILURE PREVENTION / OUTPUT VALIDATION (Rule 9) ──
        if is_persona_disabled(mode):
            forbidden = ["i feel", "i think", "my friend", "we can ", "together", "let's ", "happy to", "i am a "]
            lower_resp = response.lower()
            if any(f in lower_resp for f in forbidden):
                logger.error(f"CRITICAL SYSTEM ERROR (Rule 9): Persona language detected in {mode.upper()} mode.")
                response = f"[CRITICAL ERROR] Response nullified due to Cognitive Integrity violation (persona contamination in {mode.upper()} mode)."

        if not is_persona_disabled(mode):
            memory_store.log_interaction(
                mode=event.get("mode", "chat"),
                user_input=user_text,
                ai_response=response,
            )

        return {"text": response, "action": None, "metadata": {"cognitive_mode": mode}}

    # ── Context builders ──

    def _build_system_context(self) -> list[str]:
        """Build SYSTEM mode context: engine state + masked credentials."""
        from core.config import config
        from ai.ai_router import get_router_status

        status = get_router_status()
        engines = status.get("engines", {})
        detected = status.get("detected_engines", [])
        available = status.get("active_engines", [])
        healthy = status.get("healthy_engines", [])
        unavailable = status.get("unavailable_engines", [])

        parts = [
            f"Detected Engines: {', '.join(detected) if detected else 'none'}",
            f"Available Engines: {', '.join(available) if available else 'none'}",
            f"Healthy Engines: {', '.join(healthy) if healthy else 'none'}",
            f"Unavailable Engines: {', '.join(unavailable) if unavailable else 'none'}",
            f"Engine details: {engines}",
            f"Local model: {config.LOCAL_MODEL}",
            f"Groq model: {config.GROQ_MODEL}",
            f"Gemini model: {config.GEMINI_MODEL}",
            f"Cloud model: {config.MODEL_LOCK}",
            f"Groq API key: {_mask_key(config.GROQ_API_KEY)}",
            f"Gemini API key: {_mask_key(config.GEMINI_API_KEY)}",
            f"OpenRouter key: {_mask_key(config.OPENAI_API_KEY)}",
            f"Free mode: {config.FREE_MODE}",
            f"Max calls/day: {config.MAX_CALLS_PER_DAY}",
        ]

        usage = status.get("usage", {})
        if usage:
            parts.append(f"Usage today: {usage}")

        return parts

    def _build_meta_context(self) -> list[str]:
        """Build META mode context: architecture + gated telemetry."""
        from ai.ai_router import get_router_status, get_engine_stats

        status = get_router_status()
        detected = status.get("detected_engines", [])
        available = status.get("active_engines", [])
        healthy = status.get("healthy_engines", [])
        unavailable = status.get("unavailable_engines", [])

        parts = [
            "System: Presence AI Phase 2.1.1",
            "Architecture: 4-engine autonomous cognitive routing (local/groq/gemini/cloud)",
            "Modes: 8 cognitive modes (SYSTEM, TECH, META, FACT, PLANNING, MEMORY, PRESENCE, CHAT)",
            "Routing: task_analyzer -> mode_classifier -> cognitive_router -> engine selection",
            f"Detected Engines: {', '.join(detected) if detected else 'none'}",
            f"Available Engines: {', '.join(available) if available else 'none'}",
            f"Healthy Engines: {', '.join(healthy) if healthy else 'none'}",
            f"Unavailable Engines: {', '.join(unavailable) if unavailable else 'none'}",
        ]

        # ── Gated telemetry: only inject if real data exists ──
        try:
            stats = get_engine_stats()
            has_data = any(v.get("total_calls", 0) > 0 for v in stats.values())
            if has_data:
                parts.append("Performance telemetry (real data):")
                for eng, data in stats.items():
                    if data.get("total_calls", 0) > 0:
                        parts.append(
                            f"  {eng}: avg_latency={data.get('avg_latency', '?')}s, "
                            f"success_rate={data.get('success_rate', '?')}, "
                            f"calls={data.get('total_calls', 0)}"
                        )
            else:
                parts.append("Performance telemetry: no calls recorded yet. No fake data to report.")
        except Exception:
            parts.append("Performance telemetry: module not available.")

        return parts

    def _build_personal_context(self, event: dict) -> list[str]:
        """Build persona context: name, history, goals. Only for persona-enabled modes."""
        parts = []
        user_name = memory_store.get_user_name()
        if user_name:
            parts.append(f"User's name: {user_name}")

        history = memory_store.get("history").get("interactions", [])[-6:]
        if history:
            history_text = "\n".join(
                f"User: {h['user_input']}\nAI: {h['ai_response']}"
                for h in history
            )
            parts.append(f"Recent conversation:\n{history_text}")

        goals = memory_store.get_active_goals()
        if goals:
            parts.append(f"Active goals: {', '.join(g['title'] for g in goals[:5])}")

        return parts