"""
project_planner.py - Generate a structured build plan from a parsed goal.

Input:  parsed goal dict from goal_parser
Output: {
    "folder_structure": list[str],
    "files_to_create": [{"path": str, "description": str}],
    "commands": list[str],
    "success_criteria": list[str],
    "manifest": {"routes": [...], "pages": [...], "assets": [...]},
}

Templates used for known stacks; LLM-assisted for custom ones.
Commands are pre-filtered through the safety allowlist.
"""

import json
import logging
import re
from typing import Any

logger = logging.getLogger("presence.builder.project_planner")

# -- Allowed command prefixes (must match terminal_runner) --
_ALLOWED_PREFIXES = ("npm", "node", "python", "pip", "yarn", "npx")
_BLOCKED_PATTERNS = (
    "rm -rf", "del /s", "del /f", "rmdir /s", "format ",
    "shutdown", "mkfs", "dd if=", "> /dev/", "rd /s",
    "taskkill", "kill -9", "&&", "||", ";",
)


def _is_safe_command(cmd: str) -> bool:
    cl = cmd.lower().strip()
    for bp in _BLOCKED_PATTERNS:
        if bp in cl:
            return False
    first_token = cl.split()[0] if cl.split() else ""
    return first_token in _ALLOWED_PREFIXES


def _filter_commands(commands: list[str]) -> list[str]:
    safe = []
    for cmd in commands:
        if _is_safe_command(cmd):
            safe.append(cmd)
        else:
            logger.warning(f"[BUILDER] Planner stripped unsafe command: {cmd!r}")
    return safe


# ---------------------------------------------------------------------------
# Premium standalone HTML description blocks
# ---------------------------------------------------------------------------

_HTML_PAGE_QUALITY = (
    "This file MUST be a COMPLETE standalone HTML5 document. "
    "REQUIRED structure: <!DOCTYPE html>, <html lang='en'>, "
    "<head> with <meta charset>, <meta viewport>, <title>, "
    "link to /static/css/style.css, link to Google Fonts (Inter or Roboto), "
    "</head>, <body> with real content, <script src='/static/js/app.js'></script>. "
    "REQUIRED UI elements: a modern <nav> bar with app name and navigation links, "
    "a <main> container with real page content using card-based layouts, "
    "a <footer> with copyright. "
    "DO NOT use {% extends %} or {% block %} or any Jinja2 template inheritance. "
    "DO NOT output a fragment. DO NOT output placeholder text. "
    "Use semantic HTML5: <header>, <nav>, <main>, <section>, <footer>. "
    "Use proper form elements with labels, inputs with types, styled buttons. "
    "Use Jinja2 ONLY for dynamic data: {{ variable }}, {% for %}, {% if %}. "
)

_CSS_QUALITY = (
    "Premium-quality modern CSS stylesheet. "
    "MUST include: CSS custom properties (--primary-color, --bg-color, --text-color, etc.), "
    "a professional color palette (not raw red/blue/green), "
    "* { box-sizing: border-box; margin: 0; padding: 0; }, "
    "body with font-family from Google Fonts (Inter or Roboto), line-height, bg-color, "
    "container with max-width: 1200px and margin: 0 auto, "
    "nav styling with background, padding, flexbox layout, "
    "card components with background, border-radius: 12px, box-shadow, padding, "
    "button styling with padding, border-radius, background gradient or solid, "
    "button:hover and button:focus states with transitions, "
    "input/select styling with border, border-radius, padding, focus outline, "
    "responsive @media queries for mobile (<768px), "
    "table styling if tables are used (striped rows, padding, borders), "
    "form layout with proper spacing, "
    "section headers with font-size hierarchy, "
    "footer styling, "
    "smooth transition: all 0.2s ease on interactive elements. "
    "DO NOT use browser defaults. DO NOT output placeholder CSS. "
    "Output MUST be substantial (300+ lines of real CSS)."
)

_JS_QUALITY = (
    "Frontend JavaScript for client-side interactivity. "
    "Handle form submissions, DOM manipulation, dynamic updates, "
    "fetch API calls to Flask routes if needed, "
    "event listeners for buttons and form elements, "
    "input validation where appropriate, "
    "smooth UI transitions and feedback. "
    "Use modern JS (const/let, arrow functions, template literals, async/await). "
    "DO NOT output placeholder comments only. Write real functional code."
)

_APP_PY_QUALITY = (
    "Flask application with complete routing and logic. "
    "MUST implement ALL requested features with real backend logic. "
    "Use render_template() for every route - NEVER inline HTML strings. "
    "Use JSON file persistence (data/*.json) for storing/loading data. "
    "Include proper error handling with try/except. "
    "Include Flask flash messages for user feedback. "
    "All routes must return proper HTTP responses. "
    "Import: Flask, render_template, request, redirect, url_for, jsonify, flash. "
    "Create app = Flask(__name__) with app.secret_key set. "
    "Add if __name__ == '__main__': app.run(debug=True). "
    "DO NOT use a database unless explicitly requested - use JSON files. "
    "DO NOT embed HTML/CSS/JS in Python strings."
)

# ---------------------------------------------------------------------------
# Static templates for known stacks
# ---------------------------------------------------------------------------

_TEMPLATES: dict[str, dict] = {
    "python": {
        "folder_structure": ["."],
        "files_to_create": [
            {"path": "main.py", "description": "Entry point Python script implementing the logic."},
            {"path": "requirements.txt", "description": "[SYSTEM_GENERATED_DETERMINISTIC]"},
        ],
        "commands": ["python main.py"],
        "success_criteria": ["regex:main.py:def"],
    },
    "react": {
        "folder_structure": ["src", "public"],
        "files_to_create": [
            {"path": "package.json", "description": "npm package manifest"},
            {"path": "src/index.js", "description": "React entry point"},
            {
                "path": "src/App.jsx",
                "description": (
                    "Root React component. Must use modern UI aesthetics, "
                    "flexbox/grid layouts, card components, and interactive elements."
                ),
            },
            {
                "path": "public/index.html",
                "description": "HTML shell for React with Google Fonts link (Inter or Roboto).",
            },
            {
                "path": "src/styles.css",
                "description": _CSS_QUALITY,
            },
        ],
        "commands": ["npm install", "npm run build"],
        "success_criteria": ["regex:src/App.jsx:function", "regex:src/styles.css:var\\(--"],
    },
    "flask": {
        "folder_structure": ["templates", "static", "static/css", "static/js", "data"],
        "files_to_create": [
            {
                "path": "app.py",
                "description": _APP_PY_QUALITY,
            },
            {
                "path": "requirements.txt",
                "description": "[SYSTEM_GENERATED_DETERMINISTIC]",
            },
            {
                "path": "templates/index.html",
                "description": (
                    "Main dashboard/home page. " + _HTML_PAGE_QUALITY
                    + "This is the primary page users see. Include summary cards, "
                    "main action buttons, and overview of all features."
                ),
            },
            {
                "path": "static/css/style.css",
                "description": _CSS_QUALITY,
            },
            {
                "path": "static/js/app.js",
                "description": _JS_QUALITY,
            },
            {
                "path": "data/store.json",
                "description": "[SYSTEM_GENERATED_DETERMINISTIC] Initial empty JSON data store.",
            },
            {
                "path": "README.md",
                "description": "Project README with setup and run instructions.",
            },
        ],
        "commands": ["pip install -r requirements.txt", "python app.py"],
        "success_criteria": [
            "regex:app.py:@app.route",
            "regex:app.py:render_template",
            "regex:templates/index.html:<!DOCTYPE",
            "regex:templates/index.html:<html",
            "regex:templates/index.html:<nav",
            "regex:templates/index.html:<main",
            "regex:static/css/style.css:var(--",
            "regex:static/css/style.css:box-shadow",
            "regex:static/css/style.css:border-radius",
            "regex:static/css/style.css:@media",
        ],
    },
}


# ---------------------------------------------------------------------------
# Deterministic requirements builder
# ---------------------------------------------------------------------------

def build_deterministic_requirements(goal: dict[str, Any]) -> str:
    """Deterministically map project features and tech stack to known PyPI packages."""
    stack = goal.get("tech_stack", "").lower()
    features_raw = goal.get("features", [])
    features_str = (" ".join(features_raw)).lower()

    reqs = set()

    if stack == "flask":
        reqs.add("flask")

        if any(kw in features_str for kw in ["env", "config", "dotenv", "environment"]):
            reqs.add("python-dotenv")
        if any(kw in features_str for kw in ["db", "database", "sql", "sqlite"]):
            reqs.add("flask-sqlalchemy")
        if any(kw in features_str for kw in ["auth", "login", "register", "user", "account"]):
            reqs.update(["flask-login", "flask-wtf", "flask-bcrypt", "wtforms"])
        if any(kw in features_str for kw in ["api", "rest", "endpoint"]):
            reqs.add("requests")
        if any(kw in features_str for kw in ["chart", "plot", "graph", "visualization"]):
            reqs.update(["plotly", "matplotlib"])

    elif stack == "fastapi":
        reqs.update(["fastapi", "uvicorn"])
        if any(kw in features_str for kw in ["db", "database", "sql"]):
            reqs.add("sqlalchemy")

    if not reqs:
        return ""

    return "\n".join(sorted(reqs)) + "\n"


def build_deterministic_json_store() -> str:
    """Return an empty JSON data store."""
    return "{}\n"


# ---------------------------------------------------------------------------
# Multi-page detection and generation
# ---------------------------------------------------------------------------

# Keywords that suggest additional pages beyond index.html
_PAGE_KEYWORDS = {
    "add": "add",
    "create": "add",
    "new": "add",
    "edit": "edit",
    "update": "edit",
    "detail": "detail",
    "details": "detail",
    "view": "detail",
    "history": "history",
    "log": "history",
    "report": "report",
    "reports": "report",
    "summary": "summary",
    "analytics": "analytics",
    "dashboard": "dashboard",
    "settings": "settings",
    "profile": "profile",
    "about": "about",
}


def _detect_extra_pages(features: list[str]) -> list[dict]:
    """Detect if features imply multiple pages and return extra page specs."""
    features_str = " ".join(features).lower()
    extra_pages = []
    seen_types = set()

    for keyword, page_type in _PAGE_KEYWORDS.items():
        if keyword in features_str and page_type not in seen_types:
            seen_types.add(page_type)
            page_name = f"templates/{page_type}.html"
            extra_pages.append({
                "path": page_name,
                "description": (
                    f"Page for '{page_type}' functionality. " + _HTML_PAGE_QUALITY
                    + f"This page handles the {page_type} feature with appropriate "
                    "forms, displays, and interactive elements."
                ),
            })

    return extra_pages


# ---------------------------------------------------------------------------
# Build manifest (routes, pages, assets)
# ---------------------------------------------------------------------------

def _build_manifest(plan: dict, goal: dict) -> dict:
    """Build an explicit manifest tracking routes, pages, and assets."""
    pages = []
    assets = []
    routes = ["/"]  # Always have index route

    for f in plan.get("files_to_create", []):
        path = f["path"]
        if path.startswith("templates/") and path.endswith(".html"):
            page_name = path.replace("templates/", "").replace(".html", "")
            pages.append(path)
            if page_name != "index":
                routes.append(f"/{page_name}")
        elif path.startswith("static/"):
            assets.append(path)

    # Add feature-implied routes
    features_str = " ".join(goal.get("features", [])).lower()
    if any(kw in features_str for kw in ["add", "create", "new"]):
        if "/add" not in routes:
            routes.append("/add")
    if any(kw in features_str for kw in ["delete", "remove"]):
        if "/delete" not in routes:
            routes.append("/delete/<id>")
    if any(kw in features_str for kw in ["edit", "update"]):
        if "/edit" not in routes:
            routes.append("/edit/<id>")

    return {
        "routes": routes,
        "pages": pages,
        "assets": assets,
    }


# ---------------------------------------------------------------------------
# LLM planner fallback
# ---------------------------------------------------------------------------

async def _llm_plan(goal: dict[str, Any]) -> dict[str, Any] | None:
    """Use LLM to generate a plan for unknown tech stacks."""
    try:
        from ai.ai_router import route_llm

        system = (
            "You are a software project planner. Given a project goal, output ONLY a JSON object "
            "with fields: folder_structure (list of dir paths), "
            "files_to_create (list of {path, description}), "
            "commands (list of shell commands using only npm/node/python/pip/yarn/npx), "
            "success_criteria (list of strings formatted as 'regex:filepath:pattern').\n"
            "IMPORTANT: Every HTML file must be a complete standalone HTML5 document. "
            "Do NOT use Jinja2 template inheritance (extends/block).\n"
            "File descriptions MUST explicitly demand premium-quality modern aesthetics "
            "and explicitly command the implementation of the requested features.\n"
            "No markdown. No explanation. Pure JSON only."
        )
        prompt = (
            f"Project name: {goal['project_name']}\n"
            f"Type: {goal['project_type']}\n"
            f"Tech stack: {goal['tech_stack']}\n"
            f"Features: {', '.join(goal.get('features', []) or ['full implementation'])}"
        )
        response, _ = await route_llm(system_prompt=system, user_message=prompt, mode="tech")
        clean = re.sub(r"```(?:json)?", "", response).strip().strip("`")
        return json.loads(clean)
    except Exception as e:
        logger.warning(f"[BUILDER] LLM plan generation failed: {e}")
        return None


# ---------------------------------------------------------------------------
# Main planner entry point
# ---------------------------------------------------------------------------

async def plan(goal: dict[str, Any]) -> dict[str, Any]:
    """
    Create a build plan from a parsed goal.
    Raises ValueError if plan has no files or no commands (or commands are all unsafe).
    """
    tech = goal.get("tech_stack", "python").lower()
    logger.info(f"[BUILDER] Planning project >> stack={tech} name={goal.get('project_name')}")

    result = _TEMPLATES.get(tech)

    if not result:
        logger.info(f"[BUILDER] No template for stack={tech!r} -- using LLM planner")
        result = await _llm_plan(goal)

    if not result:
        raise ValueError(f"[BUILDER] Could not generate a plan for stack: {tech!r}")

    # Deep copy to avoid mutating templates
    result = {
        k: ([dict(item) if isinstance(item, dict) else item for item in v] if isinstance(v, list) else v)
        for k, v in result.items()
    }

    # -- Inject dynamic features into file descriptions --
    features = goal.get("features", [])
    if features and tech == "flask":
        feature_str = ", ".join(features)
        for f in result["files_to_create"]:
            if f["path"] == "app.py":
                f["description"] += f" MUST explicitly implement backend logic for ALL of these features: {feature_str}."
            elif f["path"].startswith("templates/") and f["path"].endswith(".html"):
                f["description"] += f" MUST contain UI elements for: {feature_str}."
            elif f["path"] == "static/css/style.css":
                f["description"] += f" Style all UI components for: {feature_str}."
            elif f["path"] == "static/js/app.js":
                f["description"] += f" Handle client-side interactions for: {feature_str}."
    elif features and tech == "react":
        feature_str = ", ".join(features)
        for f in result["files_to_create"]:
            if f["path"] == "src/App.jsx":
                f["description"] += f" MUST implement React components for: {feature_str}."

    # -- Multi-page detection: add extra pages if features imply them --
    if tech == "flask" and features:
        extra_pages = _detect_extra_pages(features)
        existing_paths = {f["path"] for f in result["files_to_create"]}
        for page in extra_pages:
            if page["path"] not in existing_paths:
                result["files_to_create"].append(page)
                logger.info(f"[BUILDER] Added extra page: {page['path']}")

    # -- Deduplication: Single Source of Truth --
    unique_files = []
    seen_paths = set()
    duplicates = []
    for f in result.get("files_to_create", []):
        if f["path"] not in seen_paths:
            seen_paths.add(f["path"])
            unique_files.append(f)
        else:
            duplicates.append(f["path"])

    if duplicates:
        logger.info(f"[VALIDATION] Duplicate file entries removed: {duplicates}")
    result["files_to_create"] = unique_files

    # -- Safety filter on commands --
    result["commands"] = _filter_commands(result.get("commands", []))

    # -- Build explicit manifest --
    result["manifest"] = _build_manifest(result, goal)
    logger.info(f"[BUILDER] Manifest >> routes={result['manifest']['routes']} "
                f"pages={result['manifest']['pages']} assets={result['manifest']['assets']}")

    # -- Validation gate --
    if not result.get("files_to_create"):
        raise ValueError("[BUILDER] Plan validation failed: no files to create.")

    file_paths = [f["path"] for f in result["files_to_create"]]
    logger.info(
        f"[BUILDER] Plan created >> {len(file_paths)} files: {file_paths} | "
        f"{len(result['commands'])} commands: {result['commands']}"
    )
    return result
