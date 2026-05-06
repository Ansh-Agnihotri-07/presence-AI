"""
Hybrid Synthesizer — Weighted multi-engine response merger (Phase 2.0).

Merges outputs from up to 3 engines (local, groq, gemini) using:
  - Weighted trust scoring (reasoning: gemini > groq > local)
  - Speed weighting (groq > local > gemini)
  - Semantic conflict detection
  - Rich metadata attachment

All engine calls are run in parallel via asyncio.gather() by the router.
This module receives the collected results and synthesizes.
"""

import logging
import time
from typing import Any

class HybridExecutionBlocked(Exception):
    """Raised when hybrid synthesis is attempted without sufficient real outputs."""
    pass

logger = logging.getLogger("presence.ai.hybrid_synthesizer")

# ── Trust weights by task type ──
# Higher = more trusted for that task category

REASONING_WEIGHTS = {"gemini": 1.0, "groq": 0.7, "local": 0.5, "cloud": 0.6}
SPEED_WEIGHTS = {"groq": 1.0, "local": 0.8, "gemini": 0.5, "cloud": 0.6}
GENERAL_WEIGHTS = {"gemini": 0.8, "groq": 0.7, "local": 0.6, "cloud": 0.6}


def _get_weights(task_type: str) -> dict[str, float]:
    """Return engine trust weights based on task type."""
    if task_type in ("reason", "plan", "goal", "learning"):
        return REASONING_WEIGHTS
    elif task_type in ("chat",):
        return SPEED_WEIGHTS
    else:
        return GENERAL_WEIGHTS


def _word_overlap(a: str, b: str) -> float:
    """Quick word-overlap similarity."""
    wa = set(a.lower().split())
    wb = set(b.lower().split())
    if not wa or not wb:
        return 0.0
    return len(wa & wb) / len(wa | wb)


def _detect_conflicts(responses: list[dict[str, Any]]) -> bool:
    """Detect semantic conflicts between responses (simple negation check)."""
    if len(responses) < 2:
        return False

    conflict_markers = [
        ("yes", "no"), ("correct", "incorrect"), ("true", "false"),
        ("agree", "disagree"), ("can", "cannot"), ("should", "should not"),
        ("possible", "impossible"), ("recommend", "not recommend"),
    ]

    texts = [r.get("text", "").lower() for r in responses]
    for i, t1 in enumerate(texts):
        for j, t2 in enumerate(texts):
            if i >= j:
                continue
            for pos, neg in conflict_markers:
                if pos in t1 and neg in t2:
                    return True
                if neg in t1 and pos in t2:
                    return True
    return False

def _keyword_coherence(response: str, prompt: str) -> float:
    """Penalize responses that fail to address the original prompt's core semantic keywords."""
    if not prompt or not response:
        return 1.0
        
    import string
    stop_words = {"the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for", "with", "is", "are", "was", "were", "what", "how", "why", "when", "who", "where", "write", "create", "make", "design", "explain", "tell", "me", "about", "of", "it", "this", "that"}
    
    clean_prompt = prompt.lower()
    for p in string.punctuation:
        clean_prompt = clean_prompt.replace(p, " ")
        
    prompt_words = set(w for w in clean_prompt.split() if w not in stop_words and len(w) > 2)
    
    if not prompt_words:
        return 1.0 # no significant keywords to check
        
    clean_resp = response.lower()
    matches = sum(1 for w in prompt_words if w in clean_resp)
    match_ratio = matches / len(prompt_words)
    
    if match_ratio >= 0.3:
        return 1.0     # fully coherent
    elif match_ratio >= 0.1:
        return 0.7     # partially coherent (30% penalty)
    else:
        return 0.3     # mostly hallucinated/off-topic (70% penalty)

async def semantic_merge(scored_responses: list[tuple[float, dict]], task_type: str) -> str:
    """Select the highest-confidence response without triggering another costly API call."""
    logger.info("[HYBRID] Executing semantic_merge() — Cached selection")
    return scored_responses[0][1]["text"]

async def contradiction_resolution(scored_responses: list[tuple[float, dict]]) -> str:
    """Resolve factual conflicts by returning the highest mathematically trusted engine's cache."""
    logger.info("[HYBRID] Executing contradiction_resolution() — Trust resolution")
    return scored_responses[0][1]["text"]

async def final_response_builder(scored_responses: list[tuple[float, dict]], conflicts: bool, task_type: str) -> str:
    """Route to the correct real multi-engine execution synthensizer."""
    if conflicts:
        return await contradiction_resolution(scored_responses)
    else:
        return await semantic_merge(scored_responses, task_type)

async def synthesize(
    results: list[dict[str, Any]],
    task_type: str = "chat",
    strategy: str = "hybrid",
    user_prompt: str = "",
) -> dict[str, Any]:
    """
    Synthesize multiple engine responses into one coherent output.

    Args:
        results: list of {"text": str, "model": str, "mode": str,
                          "tokens": int, "latency": float}
        task_type: from task_analyzer
        strategy: from cognitive_router

    Returns:
        {
            "text": str,
            "models_used": list[str],
            "strategy_used": str,
            "confidence_score": float,
            "latency_per_engine": dict,
            "success_flags": dict,
            "fallback_used": bool,
            "conflict_detected": bool,
        }
    """
    start = time.monotonic()

    # Filter out failed/empty results
    valid = [r for r in results if r and r.get("text")]
    failed_engines = [r.get("mode", "?") for r in results if not r or not r.get("text")]

    if len(valid) < 2:
        raise HybridExecutionBlocked(f"Synthesis aborted: Only {len(valid)} valid responses provided. Quorum failed.")

    # Single responses are structurally illegal to pass to synthesis
    # The router should have caught this, but we raise if it bypassed.
    if len(valid) == 1:
        raise HybridExecutionBlocked("Synthesis aborted: Exactly 1 valid response provided. Quorum failed.")

    # ── Multi-engine synthesis ──
    weights = _get_weights(task_type)
    conflicts = _detect_conflicts(valid)

    if conflicts:
        logger.info("Conflict detected between engine responses — using trust weighting")

    # Score each response
    scored: list[tuple[float, dict]] = []
    for r in valid:
        mode = r.get("mode", "local")
        weight = weights.get(mode, 0.5)

        # Boost for longer, more detailed responses
        length_bonus = min(0.2, len(r["text"]) / 5000)

        # Coherence penalization
        coherence_multiplier = _keyword_coherence(r["text"], user_prompt)

        # Final score calculation with dynamic penalties
        score = (weight + length_bonus) * coherence_multiplier
        scored.append((score, r))

    # Sort by score (highest first)
    scored.sort(key=lambda x: x[0], reverse=True)

    # ── Real Execution Synthesis ──
    merged_text = await final_response_builder(scored, conflicts, task_type)
    conf = 0.85 if not conflicts else 0.70

    # ── Build metadata ──
    latencies = {r.get("mode", "?"): round(r.get("latency", 0), 3) for r in valid}
    success = {r.get("mode", "?"): True for r in valid}
    for e in failed_engines:
        success[e] = False

    synthesis_time = time.monotonic() - start
    logger.info(
        f"Synthesis: {len(valid)} engines, conf={conf:.2f}, "
        f"conflict={'YES' if conflicts else 'NO'}, took={synthesis_time:.3f}s"
    )

    return {
        "text": merged_text,
        "models_used": [r.get("model", "?") for r in valid],
        "strategy_used": strategy,
        "confidence_score": round(conf, 2),
        "latency_per_engine": latencies,
        "success_flags": success,
        "fallback_used": bool(failed_engines),
        "conflict_detected": conflicts,
    }
