"""
goal_parser.py — Parse natural language into a structured project goal.

Input:  raw user string
Output: {
    "project_name": str,
    "project_type": str,   # "web" | "api" | "script" | "app" | "unknown"
    "tech_stack": str,     # "react" | "flask" | "express" | "python" | ...
    "features": list[str],
}

Uses heuristics first, LLM fallback for ambiguous inputs.
Never raises — returns {"error": str} on failure.
"""

import re
import logging
from typing import Any

logger = logging.getLogger("presence.builder.goal_parser")

# ── Heuristic keyword maps ──

TECH_STACK_HINTS: dict[str, list[str]] = {
    "react":   ["react", "jsx", "create-react-app", "vite react", "next.js", "nextjs"],
    "flask":   ["flask", "flask api", "python web", "python server"],
    "django":  ["django", "django rest"],
    "express": ["express", "node api", "nodejs api", "node.js server"],
    "python":  ["python script", "python program", "py script", "hello world python", "python"],
    "html":    ["html", "landing page", "static site", "static website", "plain html"],
    "fastapi": ["fastapi", "fast api"],
}

TYPE_HINTS: dict[str, list[str]] = {
    "web":    ["website", "landing page", "web app", "frontend", "ui"],
    "api":    ["api", "rest api", "backend", "server", "endpoint"],
    "script": ["script", "cli", "command line", "automation", "tool"],
    "app":    ["app", "application", "desktop", "cross-platform"],
}

# Words stripped from project name slugs — articles, verbs, filler
_FILLER_WORDS = {
    "a", "an", "the", "simple", "basic", "my", "with", "that",
    "and", "for", "to", "of", "in", "from", "this", "some",
    "please", "just", "me", "build", "create", "make", "generate",
    "scaffold", "using", "use", "it", "i", "want", "need",
    "responsive", "interactive", "new", "cool", "nice", "good",
    "complete", "full", "demo", "sample", "starter", "template",
    "project", "application", "web", "app", "site", "website",
    "api", "system", "tool", "software", "program",
    "intermediate", "level", "pro", "expert", "advanced", "beginner",
    "easy", "professional", "minimal", "basic", "simple",
}

_MIN_SLUG_LEN = 5  # minimum useful project name length


def _slugify(name: str, max_len: int = 32) -> str:
    """Convert free text into a short, clean folder name."""
    name = name.lower().strip()
    name = name.replace("-", " ")  # Convert hyphenated words to space-separated to filter components
    name = re.sub(r"[^\w\s]", "", name)  # remove special chars
    words = name.split()
    # Strip filler words
    meaningful = [w for w in words if w not in _FILLER_WORDS]
    
    # If no meaningful words remain, we'll try to use the raw words 
    # but the caller should usually handle this by falling back to stack_type
    if not meaningful:
        return ""
        
    slug = "_".join(meaningful)
    slug = re.sub(r"_+", "_", slug)  # collapse double underscores
    slug = slug[:max_len].strip("_")
    return slug


def _extract_heuristic(text: str) -> dict[str, Any] | None:
    """Try to extract goal from text using keyword matching alone."""
    tl = text.lower()

    tech_stack = "python"
    for tech, hints in TECH_STACK_HINTS.items():
        if any(h in tl for h in hints):
            tech_stack = tech
            break

    project_type = "script"
    for ptype, hints in TYPE_HINTS.items():
        if any(h in tl for h in hints):
            project_type = ptype
            break

    # Improved naming extraction: target the noun phrase after verbs/articles
    # Examples: "build a finance tracker" -> "finance tracker"
    project_name = ""
    # Regex 1: "build [a/me] {intent} [using/with/in...]"
    name_match = re.search(
        r"(?:build|create|make|generate|scaffold|want|need)\s+(?:a\s+|an\s+|me\s+a\s+|the\s+)?(.+?)(?:\s+using|\s+with|\s+in|\s+level|\s*(\.\s*|$))",
        tl,
    )
    if name_match:
        raw_name = name_match.group(1).strip()
        project_name = _slugify(raw_name)

    # Secondary check: if it's still generic or short, try another regex for "{intent} [app/website/site...]"
    if len(project_name) < _MIN_SLUG_LEN:
        sec_match = re.search(r"([\w\s-]+?)\s+(?:app|website|site|landing page|api|system|tool|program)", tl)
        if sec_match:
            raw_sec = sec_match.group(1).strip()
            # Filter out generic words from the match group itself
            project_name = _slugify(raw_sec)

    # Final guard: if slug is still too short, empty, or a known filler, use stack_type
    if not project_name or len(project_name) < _MIN_SLUG_LEN:
        project_name = f"{tech_stack}_{project_type}"
        logger.info(f"[BUILDER] Project name derived from stack/type: {project_name}")
    else:
        logger.info(f"[BUILDER] Intent-based project name extracted: {project_name}")

    # Extract feature-like phrases (simple: noun chunks after "with")
    features: list[str] = []
    feat_match = re.search(r"(?:with|including|featuring)\s+(.+)", tl)
    if feat_match:
        raw_feats = feat_match.group(1)
        features = [f.strip() for f in re.split(r",|and", raw_feats) if f.strip()]

    # Auto-promote: if tech_stack is flask but type is script, it's really a web app
    if tech_stack == "flask" and project_type == "script":
        project_type = "web"
        logger.info("[BUILDER] Auto-promoted flask script to web type")

    return {
        "project_name": project_name,
        "project_type": project_type,
        "tech_stack": tech_stack,
        "features": features,
    }


async def _extract_llm(text: str) -> dict[str, Any] | None:
    """Use LLM to extract goal when heuristics are ambiguous."""
    try:
        from ai.ai_router import route_llm
        import json

        system = (
            "You are a project goal extractor. Given a user request, output ONLY a JSON object "
            "with these fields: project_name (str, snake_case, descriptive, min 8 chars), "
            "project_type (one of: web/api/script/app), "
            "tech_stack (str, e.g. react/flask/python/express), features (list of strings). "
            "No explanation. No markdown. Pure JSON only."
        )
        response, _ = await route_llm(
            system_prompt=system,
            user_message=text,
            mode="tech",
        )
        # Strip markdown code fences if present
        clean = re.sub(r"```(?:json)?", "", response).strip().strip("`")
        data = json.loads(clean)
        data["project_name"] = _slugify(data.get("project_name", "project"))
        # Guard: if LLM also returned something too short
        if len(data["project_name"]) < _MIN_SLUG_LEN:
            data["project_name"] = f"{data.get('tech_stack', 'project')}_{data.get('project_type', 'app')}"
        return data
    except Exception as e:
        logger.warning(f"[BUILDER] LLM goal extraction failed: {e}")
        return None


async def parse(text: str) -> dict[str, Any]:
    """
    Parse user intent into a structured project goal.
    Returns {"error": str} if parsing completely fails.
    """
    logger.info(f"[BUILDER] Parsing goal from: {text[:80]!r}")

    result = _extract_heuristic(text)
    if not result or result.get("project_type") == "script" and "react" in text.lower():
        # Heuristic may have misfired — try LLM
        llm_result = await _extract_llm(text)
        if llm_result:
            result = llm_result

    if not result:
        return {"error": "Could not parse project goal from input."}

    logger.info(
        f"[BUILDER] Goal parsed >> name={result['project_name']} "
        f"type={result['project_type']} stack={result['tech_stack']} "
        f"features={result.get('features', [])}"
    )
    return result
