"""
Task Analyzer — Enhanced heuristic cognitive classifier (Phase 2.0).

Classifies messages by complexity, type, confidence, ambiguity,
multi-step detection, memory relevance, and vision requirements.
Used by cognitive_router for routing priority decisions.
"""

import logging
import re
from typing import Any

logger = logging.getLogger("presence.ai.task_analyzer")

# ── Complexity signals ──

HIGH_PATTERNS = [
    r"\b(analyze|architect|design|implement|refactor|debug|optimize)\b",
    r"\b(compare .+ (with|to|vs|versus))\b",
    r"\b(trade.?offs?|pros? and cons?|advantages? and disadvantages?)\b",
    r"\b(step.by.step|in detail|explain .+ thoroughly|deep dive)\b",
    r"\b(create a plan|build a system|write a program)\b",
    r"\b(why does .+ (happen|work|fail|break))\b",
    r"\b(how (would|should|could) (I|we|you) .{20,})\b",
    r"\b(multiple|several|many|complex|complicated|difficult)\b",
    r"\b(strategy|framework|methodology|pipeline|architecture)\b",
]

MEDIUM_PATTERNS = [
    r"\b(explain|describe|summarize|what is|how does|help me)\b",
    r"\b(suggest|recommend|advice|opinion|think about)\b",
    r"\b(plan|goal|task|schedule|organize|remind)\b",
    r"\b(improve|better|change|update|modify)\b",
    r"\?.*\?",
]

LOW_PATTERNS = [
    r"^(hi|hello|hey|yo|sup|thanks|ok|yes|no|sure|cool|nice|great)\b",
    r"^.{1,25}$",
    r"\b(what time|weather|how are you|good morning|good night)\b",
]

# ── Ambiguity signals ──
AMBIGUITY_PATTERNS = [
    r"\b(maybe|perhaps|might|not sure|could be|possibly)\b",
    r"\b(something like|kind of|sort of|I think)\b",
    r"\b(what do you think|what would you|any idea)\b",
    r"\b(or something|whatever|anything)\b",
]

# ── Multi-step signals ──
MULTI_STEP_PATTERNS = [
    r"\b(first|then|after that|next|finally|step \d)\b",
    r"\b(also|additionally|and then|followed by)\b",
    r"\band\b.*\band\b",  # multiple "and" connectors
    r"\b\d+\)\s",  # numbered lists: 1) 2) 3)
]

# ── Memory-relevant signals ──
MEMORY_PATTERNS = [
    r"\b(remember|last time|before|previously|earlier|you said)\b",
    r"\b(my name|my job|my goal|my habit|i told you)\b",
    r"\b(what did I|when did I|did I mention)\b",
    r"\b(history|past|context|conversation)\b",
]

# ── Vision signals ──
VISION_PATTERNS = [
    r"\b(screen|screenshot|image|picture|photo|look at|see this)\b",
    r"\b(what's on my|read this|explain this|what is this)\b",
    r"\b(visual|diagram|chart|graph|UI|interface)\b",
]

# ── Task type keywords ──
PLAN_KEYWORDS = {"goal", "goals", "plan", "planning", "task", "tasks", "schedule",
                 "organize", "track", "improve", "learn", "start", "begin", "achieve", "build"}
REASON_KEYWORDS = {"why", "because", "analyze", "think", "reason", "logic", "evaluate",
                   "assess", "consider", "reflect", "compare", "argue"}
SCREEN_KEYWORDS = {"screen", "explain this", "read this", "summarize this",
                   "what's on my screen", "look at this", "what is this"}
REMINDER_KEYWORDS = {"remind", "reminder", "remember to", "don't forget",
                     "in 5 minutes", "in an hour", "tomorrow", "later",
                     "wake me", "alert me", "notify me"}
MEMORY_KEYWORDS = {"remember", "recall", "what did i", "previously", "last time",
                   "you said", "my name", "my goal"}
GOAL_KEYWORDS = {"goal", "achieve", "target", "milestone", "progress", "accomplish"}
LEARNING_KEYWORDS = {"learn", "study", "practice", "improve", "skill", "habit", "routine"}


def _count_matches(text: str, patterns: list[str]) -> int:
    """Count how many patterns match in the text."""
    count = 0
    for p in patterns:
        if re.search(p, text, re.IGNORECASE):
            count += 1
    return count


def analyze_task(text: str) -> dict[str, Any]:
    """
    Analyze a message with enhanced cognitive classification.

    Returns:
        {
            "complexity": "low"|"medium"|"high",
            "task_type": "chat"|"plan"|"reason"|"screen"|"memory"|"goal"|"learning"|"reminder",
            "confidence": 0.0-1.0,
            "ambiguity": bool,
            "multi_step": bool,
            "memory_relevance": bool,
            "vision_required": bool,
        }
    """
    lower = text.lower().strip()
    word_count = len(text.split())
    sentence_count = len(re.split(r'[.!?]+', text))

    # ── Score complexity ──
    high_score = _count_matches(lower, HIGH_PATTERNS)
    med_score = _count_matches(lower, MEDIUM_PATTERNS)
    low_score = _count_matches(lower, LOW_PATTERNS)

    if word_count > 50:
        high_score += 2
    elif word_count > 20:
        med_score += 1
    if sentence_count > 4:
        high_score += 1

    if high_score >= 2:
        complexity = "high"
    elif high_score >= 1 or med_score >= 2:
        complexity = "medium"
    else:
        complexity = "low"

    # ── Ambiguity detection ──
    ambiguity_score = _count_matches(lower, AMBIGUITY_PATTERNS)
    ambiguity = ambiguity_score >= 1

    # ── Multi-step detection ──
    multi_step_score = _count_matches(lower, MULTI_STEP_PATTERNS)
    multi_step = multi_step_score >= 1

    # Multi-step boosts complexity
    if multi_step:
        med_score += 1
        if multi_step_score >= 2:
            high_score += 1

    # ── Memory relevance ──
    memory_score = _count_matches(lower, MEMORY_PATTERNS)
    memory_relevance = memory_score >= 1

    # ── Vision required ──
    vision_score = _count_matches(lower, VISION_PATTERNS)
    vision_required = vision_score >= 1

    # ── Confidence scoring (0.0-1.0) ──
    # High confidence = clear intent, low ambiguity, strong pattern matches
    total_signals = high_score + med_score + low_score
    if total_signals == 0:
        confidence = 0.4  # no patterns matched — uncertain
    elif ambiguity:
        confidence = min(0.6, 0.3 + total_signals * 0.1)
    elif complexity == "low" and low_score >= 1:
        confidence = 0.9  # very clear simple intent
    elif complexity == "high" and high_score >= 3:
        confidence = 0.85
    else:
        confidence = min(0.8, 0.5 + total_signals * 0.1)

    # ── Classify task type ──
    task_type = "chat"
    if any(kw in lower for kw in REMINDER_KEYWORDS):
        task_type = "reminder"
    elif vision_required:
        task_type = "screen"
    elif any(kw in lower for kw in MEMORY_KEYWORDS):
        task_type = "memory"
    elif any(kw in lower for kw in GOAL_KEYWORDS):
        task_type = "goal"
    elif any(kw in lower for kw in LEARNING_KEYWORDS):
        task_type = "learning"
    elif any(kw in lower for kw in REASON_KEYWORDS):
        task_type = "reason"
    elif any(kw in lower for kw in PLAN_KEYWORDS):
        task_type = "plan"

    result = {
        "complexity": complexity,
        "task_type": task_type,
        "confidence": round(confidence, 2),
        "ambiguity": ambiguity,
        "multi_step": multi_step,
        "memory_relevance": memory_relevance,
        "vision_required": vision_required,
    }

    logger.info(
        f"Task analysis: {complexity}/{task_type} "
        f"conf={confidence:.2f} amb={ambiguity} multi={multi_step}"
    )
    return result
