"""
Cognitive Router — 4-engine strategy selection (Phase 2.0).

Maps task analysis → routing strategy across Local, Groq, Gemini, OpenRouter.
Uses confidence threshold, ambiguity, and task type for decisions.
Cloud engines are boosters — never the default.
"""

import logging
from typing import Any

logger = logging.getLogger("presence.ai.cognitive_router")

# ── Strategies ──
STRATEGY_LOCAL_ONLY = "local_only"
STRATEGY_GROQ_FAST = "groq_fast"       # speed verification (no Gemini blocking)
STRATEGY_GEMINI_DEEP = "gemini_deep"     # deep reasoning (Gemini leads)
STRATEGY_HYBRID_FULL = "hybrid_full"     # parallel local + groq + gemini → synthesis
STRATEGY_MEMORY_LOCAL = "memory_local"   # local + memory enrichment
STRATEGY_CLOUD_FALLBACK = "cloud_fallback"  # OpenRouter legacy

CONFIDENCE_THRESHOLD = 0.65  # below this → escalate to cloud verification


def select_strategy(
    analysis: dict[str, Any],
    local_available: bool,
    groq_available: bool,
    gemini_available: bool,
    cloud_available: bool = False,
) -> dict[str, Any]:
    """
    Select routing strategy based on task analysis and engine availability.

    Returns:
        {
            "strategy": str,
            "engines": list[str],  # which engines to use
            "execution_mode": str, # "parallel", "sequential", or "single"
            "reason": str,
        }
    """
    complexity = analysis.get("complexity", "low")
    task_type = analysis.get("task_type", "chat")
    confidence = analysis.get("confidence", 0.5)
    ambiguity = analysis.get("ambiguity", False)
    multi_step = analysis.get("multi_step", False)
    memory_relevance = analysis.get("memory_relevance", False)
    vision_required = analysis.get("vision_required", False)

    # ── No engines at all ──
    available = []
    if local_available:
        available.append("local")
    if groq_available:
        available.append("groq")
    if gemini_available:
        available.append("gemini")
    if cloud_available:
        available.append("cloud")

    if not available:
        return {
            "strategy": "offline",
            "engines": [],
            "execution_mode": "none",
            "reason": "No AI engines available",
        }

    # ── Only one engine → use it ──
    if len(available) == 1:
        engine = available[0]
        return {
            "strategy": f"{engine}_only",
            "engines": [engine],
            "execution_mode": "single",
            "reason": f"Only {engine} available",
        }

    # ── Vision tasks → Gemini (if available) ──
    if vision_required and gemini_available:
        return {
            "strategy": STRATEGY_GEMINI_DEEP,
            "engines": ["gemini"],
            "execution_mode": "single",
            "reason": "Vision task — Gemini pipeline",
        }

    # ── Memory tasks → local + memory engine ──
    if memory_relevance and task_type == "memory" and local_available:
        return {
            "strategy": STRATEGY_MEMORY_LOCAL,
            "engines": ["local"],
            "execution_mode": "single",
            "reason": "Memory task — local + recall",
        }

    # ── LOW complexity → local only ──
    if complexity == "low" and local_available:
        return {
            "strategy": STRATEGY_LOCAL_ONLY,
            "engines": ["local"],
            "execution_mode": "single",
            "reason": "Low complexity — local sufficient",
        }

    # ── MEDIUM complexity ──
    if complexity == "medium":
        # Ambiguity or low confidence → Groq speed verification
        if (ambiguity or confidence < CONFIDENCE_THRESHOLD) and groq_available:
            engines = ["local", "groq"] if local_available else ["groq"]
            return {
                "strategy": STRATEGY_GROQ_FAST,
                "engines": engines,
                "execution_mode": "parallel",
                "reason": f"Medium + {'ambiguity' if ambiguity else 'low confidence'} — Groq verify",
            }
        # Normal medium → local only
        if local_available:
            return {
                "strategy": STRATEGY_LOCAL_ONLY,
                "engines": ["local"],
                "execution_mode": "single",
                "reason": "Medium complexity — local sufficient",
            }
        # No local → Groq
        if groq_available:
            return {
                "strategy": STRATEGY_GROQ_FAST,
                "engines": ["groq"],
                "execution_mode": "single",
                "reason": "Medium — Groq (local unavailable)",
            }

    # ── HIGH complexity ──
    if complexity == "high":
        # Plan/reason/goal → full hybrid (parallel)
        if task_type in ("plan", "reason", "goal", "learning"):
            engines = [e for e in ["local", "groq", "gemini"] if e in available]
            if len(engines) >= 2:
                return {
                    "strategy": STRATEGY_HYBRID_FULL,
                    "engines": engines,
                    "execution_mode": "parallel",
                    "reason": f"High {task_type} — parallel hybrid reasoning",
                }
            elif gemini_available:
                return {
                    "strategy": STRATEGY_GEMINI_DEEP,
                    "engines": ["gemini"],
                    "execution_mode": "single",
                    "reason": f"High {task_type} — Gemini deep reasoning",
                }

        # High non-plan → local + groq verify
        if local_available and groq_available:
            return {
                "strategy": STRATEGY_GROQ_FAST,
                "engines": ["local", "groq"],
                "execution_mode": "parallel",
                "reason": f"High {task_type} — local + Groq boost",
            }

        # High with Gemini only
        if gemini_available:
            return {
                "strategy": STRATEGY_GEMINI_DEEP,
                "engines": ["gemini"],
                "execution_mode": "single",
                "reason": f"High {task_type} — Gemini reasoning",
            }

    # ── Fallback: best available engine ──
    if local_available:
        return {"strategy": STRATEGY_LOCAL_ONLY, "engines": ["local"],
                "execution_mode": "single", "reason": "Fallback — local"}
    if groq_available:
        return {"strategy": STRATEGY_GROQ_FAST, "engines": ["groq"],
                "execution_mode": "single", "reason": "Fallback — Groq"}
    if gemini_available:
        return {"strategy": STRATEGY_GEMINI_DEEP, "engines": ["gemini"],
                "execution_mode": "single", "reason": "Fallback — Gemini"}
    if cloud_available:
        return {"strategy": STRATEGY_CLOUD_FALLBACK, "engines": ["cloud"],
                "execution_mode": "single", "reason": "Fallback — OpenRouter"}

    return {"strategy": "offline", "engines": [], "execution_mode": "none",
            "reason": "No engines available"}
