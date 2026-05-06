"""
Screen Agent — On-demand screen understanding.

IMPORTANT: Only activates when the user explicitly asks.
No passive surveillance. No always-on monitoring.
"""

import logging
from typing import Any
from agents.base_agent import BaseAgent
from ai.ai_router import route_llm
from memory.store import memory_store

logger = logging.getLogger("presence.agents.screen")

SCREEN_SYSTEM_PROMPT = """You are the screen understanding module of Presence, a calm AI companion.

The user has asked you to look at their screen. You've been given OCR-extracted text
from the active window.

Your job:
- If they said "explain this": provide a clear, concise explanation of what's on screen
- If they said "read this": read and summarize the visible content
- If they said "summarize this": provide a focused summary
- If they said "make notes": extract key points as structured notes

Be concise. Don't repeat the entire screen text back. Synthesize and explain.
If the OCR text is garbled or unclear, say so honestly.
"""

SCREEN_INTENT_KEYWORDS = [
    "explain this", "read this", "summarize this", "make notes",
    "what's on my screen", "what am i looking at", "screen",
    "what is this", "analyze this", "look at this",
]


class ScreenAgent(BaseAgent):
    name = "screen"

    async def can_handle(self, event: dict[str, Any]) -> bool:
        text = event.get("text", "").lower()
        return any(kw in text for kw in SCREEN_INTENT_KEYWORDS)

    async def handle(self, event: dict[str, Any]) -> dict[str, Any]:
        user_text = event.get("text", "")

        # Capture + OCR
        from screen.capture import capture_active_window
        from screen.ocr import extract_text
        from screen.context_classifier import classify_context

        screenshot_path = capture_active_window()
        ocr_text = extract_text(screenshot_path)
        context_type = classify_context()

        context = f"Window type: {context_type}\n\nExtracted text from screen:\n{ocr_text[:3000]}"

        response, trace = await route_llm(
            system_prompt=SCREEN_SYSTEM_PROMPT,
            user_message=user_text,
            context=context,
            mode=event.get("cognitive_mode", "tech"),
        )

        memory_store.log_interaction(
            mode=event.get("mode", "chat"),
            user_input=user_text,
            ai_response=response,
            context=f"screen:{context_type}",
        )

        return {"text": response, "action": "screen_analysis", "metadata": {"context_type": context_type, "runtime_trace": trace}}