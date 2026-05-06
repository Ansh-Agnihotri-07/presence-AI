"""
Mode Classifier — 8-mode cognitive intent detection (Phase 2.1.1).

Priority order (checked first wins on ties):
  1. SYSTEM  — configs, APIs, keys, engines, infrastructure
  2. TECH    — bugs, crashes, errors, debugging
  3. META    — self-analysis, system status, architecture
  4. FACT    — direct questions, short factual queries
  5. PLANNING — scheduling, tasks, structuring
  6. MEMORY  — remember, recall, reminders, context
  7. PRESENCE — ambient personality
  8. CHAT    — default fallback

Mode > Persona > Style. Task > Identity.
"""

import re
import logging

logger = logging.getLogger("presence.ai.mode_classifier")

# ── Mode constants ──
MODE_SYSTEM = "system"
MODE_TECH = "tech"
MODE_META = "meta"
MODE_FACT = "fact"
MODE_PLANNING = "planning"
MODE_MEMORY = "memory"
MODE_CHAT = "chat"
MODE_PRESENCE = "presence"

# Modes where persona is DISABLED
NO_PERSONA_MODES = {MODE_SYSTEM, MODE_TECH, MODE_FACT, MODE_META}

# ── Priority order — first match wins on tie ──
PRIORITY_ORDER = [
    MODE_SYSTEM,
    MODE_TECH,
    MODE_META,
    MODE_FACT,
    MODE_PLANNING,
    MODE_MEMORY,
    MODE_PRESENCE,
]

# ── Pattern banks ──

SYSTEM_PATTERNS = [
    r"\b(api.?key|api key|openrouter|groq|gemini|ollama|model lock)\b",
    r"\b(config|configuration|\.env|environment|setting|settings)\b",
    r"\b(engine|router|routing|model|models|backend|endpoint)\b",
    r"\b(which (model|engine|api|key)|what model|what engine)\b",
    r"\b(free.?tier|paid model|cost guard|usage tracker|rate limit)\b",
    r"\b(local ai|cloud ai|hybrid|fallback chain|probe)\b",
    r"\b(install|setup|dependency|dependencies|pip|package)\b",
    r"\b(port|host|url|base.?url|server)\b",
]

TECH_PATTERNS = [
    r"\b(bug|crash|error|exception|traceback|stack trace)\b",
    r"\b(debug|debugging|fix|broken|not working|won't work)\b",
    r"\b(log|logs|logging|stderr|stdout|output)\b",
    r"\b(import error|module not found|attribute error|type error)\b",
    r"\b(memory leak|hang|freeze|stuck|timeout|slow)\b",
    r"\b(code|function|class|method|variable|file|script)\b",
    r"\b(syntax|runtime|compile|build|test|unit test)\b",
    r"\b(git|commit|branch|merge|pull|push|deploy)\b",
]

META_PATTERNS = [
    r"\b(system status|router status|engine status|health)\b",
    r"\b(how (are|do) you work|your architecture|your design)\b",
    r"\b(what (are|is) your|about yourself|self.?analysis)\b",
    r"\b(stats|statistics|performance|metrics|uptime)\b",
    r"\b(version|phase|build|current mode)\b",
    r"\b(which engines|active engines|available engines)\b",
    r"\b(how .+ internally|your (system|code|logic|brain))\b",
    r"\b(tell me about (yourself|your|the system))\b",
    r"\b(explain (your|the) (routing|cognition|architecture|engine|mode))\b",
    r"\bexplain .*(your|yourself|how you)\b",
    r"\byour (routing|cognition|mode|engine|architecture)\b",
]

FACT_PATTERNS = [
    r"^(what is|what's|who is|when is|where is|how many|how much)\b",
    r"^(define|meaning of|what does .+ mean)\b",
    r"\b(capital of|population of|distance|temperature|formula)\b",
    r"\b(convert|calculate|translate|spell|list all)\b",
]

PLANNING_PATTERNS = [
    r"\b(plan|planning|schedule|organize|structure|roadmap)\b",
    r"\b(task|tasks|todo|to.?do|checklist|action items)\b",
    r"\b(step.by.step|break down|breakdown|phases|milestones)\b",
    r"\b(timeline|deadline|priority|prioritize|order)\b",
    r"\b(project|sprint|workflow|pipeline|process)\b",
]

MEMORY_PATTERNS = [
    r"\b(remember|recall|remind|reminder|don't forget)\b",
    r"\b(you said|i told you|last time|previously|earlier)\b",
    r"\b(my name|my goal|my preference|my habit)\b",
    r"\b(save this|store this|note this|keep this|log this)\b",
    r"\b(what did (i|we)|history|context|session)\b",
]

PRESENCE_PATTERNS = [
    r"\b(how are you|good morning|good night|good evening)\b",
    r"\b(feeling|mood|lonely|sad|happy|anxious|stressed)\b",
    r"\b(motivate|inspire|encourage|support|comfort)\b",
    r"\b(thank you|thanks|appreciate|grateful)\b",
    r"\b(i need someone|talk to me|be with me|listen)\b",
]

# Mode -> patterns map
_MODE_PATTERNS = {
    MODE_SYSTEM:   SYSTEM_PATTERNS,
    MODE_TECH:     TECH_PATTERNS,
    MODE_META:     META_PATTERNS,
    MODE_FACT:     FACT_PATTERNS,
    MODE_PLANNING: PLANNING_PATTERNS,
    MODE_MEMORY:   MEMORY_PATTERNS,
    MODE_PRESENCE: PRESENCE_PATTERNS,
}


def _score_patterns(text: str, patterns: list[str]) -> int:
    """Count matching patterns in text."""
    count = 0
    for p in patterns:
        if re.search(p, text, re.IGNORECASE):
            count += 1
    return count


def classify_mode(text: str) -> str:
    """
    Classify cognitive mode using priority-ordered scoring.

    On ties, the higher-priority mode wins (SYSTEM > TECH > META > FACT > ...).
    """
    lower = text.lower().strip()

    scores = {}
    for mode_name, patterns in _MODE_PATTERNS.items():
        scores[mode_name] = _score_patterns(lower, patterns)

    best_score = max(scores.values())

    # No patterns matched -> CHAT
    if best_score == 0:
        logger.info(f"Mode: CHAT (no patterns matched)")
        return MODE_CHAT

    # Priority-ordered tie resolution: first mode in PRIORITY_ORDER with best_score wins
    for mode_name in PRIORITY_ORDER:
        if scores.get(mode_name, 0) == best_score:
            logger.info(f"Mode: {mode_name.upper()} (score={best_score}, scores={scores})")
            return mode_name

    # Fallback (shouldn't reach)
    best_mode = max(scores, key=scores.get)
    logger.info(f"Mode: {best_mode.upper()} (fallback)")
    return best_mode


def is_persona_disabled(mode: str) -> bool:
    """Return True if persona/presence styling should be off for this mode."""
    return mode in NO_PERSONA_MODES
