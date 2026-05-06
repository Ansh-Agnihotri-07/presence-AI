"""
repair_loop.py - Iterative LLM-guided error repair with backup, rollback, and stall detection.

Rules:
  - max_attempts = config.BUILDER_MAX_REPAIR_ATTEMPTS (default 5)
  - Backs up file content in memory BEFORE applying each patch
  - Reverts immediately if patch introduces a worse or new error type
  - Stops early if the same error_type repeats STALL_THRESHOLD times
  - Escalates to cloud LLM (mode="tech") after attempt >= 3
  - requirements.txt repairs use deterministic rebuild, not LLM
  - HTML repairs demand standalone HTML5 documents (no Jinja inheritance)
"""

import logging
from pathlib import Path
from typing import Any, AsyncGenerator

from core.config import config
from builder.file_executor import read_file, update_file
from builder.terminal_runner import run_command
from builder.result_checker import check

logger = logging.getLogger("presence.builder.repair_loop")

STALL_THRESHOLD = 2


# ---------------------------------------------------------------------------
# File-type-aware repair prompt generation
# ---------------------------------------------------------------------------

def _repair_prompt(
    error_type: str,
    error_message: str,
    file_path: str,
    file_content: str,
    command: str,
    attempt: int,
) -> str:
    """Generate a targeted repair prompt based on file type and error."""
    ext = file_path.rsplit(".", 1)[-1].lower() if "." in file_path else ""

    type_rules = ""

    if ext == "html":
        type_rules = (
            "\n\nHTML REPAIR RULES:\n"
            "- Output MUST be a COMPLETE STANDALONE HTML5 document.\n"
            "- REQUIRED: <!DOCTYPE html>, <html>, <head> with <title> and <meta viewport>, <body>.\n"
            "- Include: <nav>, <main> with real content (cards, forms, tables), <footer>.\n"
            "- Link to /static/css/style.css and Google Fonts (Inter or Roboto).\n"
            "- Include <script src='/static/js/app.js'></script> before </body>.\n"
            "- DO NOT use {% extends %} or {% block %} - no Jinja2 template inheritance.\n"
            "- You CAN use {{ variable }}, {% for %}, {% if %} for dynamic data.\n"
            "- DO NOT output a fragment or placeholder page.\n"
            "- Include at least 3 real content elements (nav, forms, cards, tables, etc.).\n"
            "- Preserve all existing meaningful content.\n"
        )
    elif ext == "py":
        type_rules = (
            "\n\nPYTHON REPAIR RULES:\n"
            "- Fix syntax errors (unclosed strings, brackets, indentation).\n"
            "- DO NOT embed HTML/CSS/JS in triple-quoted strings.\n"
            "- Use render_template() for Flask HTML, not inline strings.\n"
            "- Preserve all existing logic, imports, and routes.\n"
            "- Ensure all render_template() calls reference files that actually exist.\n"
            "- Use JSON file persistence (data/*.json), not databases, unless explicitly requested.\n"
        )
    elif file_path.endswith("requirements.txt"):
        type_rules = (
            "\n\nREQUIREMENTS.TXT REPAIR RULES:\n"
            "- Output ONLY valid pip package names, one per line.\n"
            "- No shell commands, no python code, no markdown fences.\n"
            "- Example valid lines: flask, requests, gunicorn\n"
        )
    elif ext == "css":
        type_rules = (
            "\n\nCSS REPAIR RULES:\n"
            "- Output ONLY valid CSS code.\n"
            "- Must include CSS custom properties (variables), multiple selectors,\n"
            "  meaningful style rules, box-shadow, border-radius, responsive @media.\n"
            "- No Python code, no shell commands, no markdown fences.\n"
            "- Must have at least 5 selectors and 10 property declarations.\n"
        )
    elif ext == "js":
        type_rules = (
            "\n\nJS REPAIR RULES:\n"
            "- Output ONLY valid JavaScript code.\n"
            "- Must use modern JS (const/let, arrow functions, template literals).\n"
            "- Must contain real functional code (event listeners, DOM manipulation).\n"
            "- No Python code, no shell commands, no markdown fences.\n"
        )

    # Special handling for missing_template errors
    if error_type == "missing_template":
        type_rules += (
            "\n\nMANIFEST-AWARE REPAIR CRITICAL INSTRUCTION:\n"
            "- app.py references template files that DO NOT EXIST.\n"
            "- DO NOT create the missing template files.\n"
            "- You MUST rewrite the Python routes to use ONLY the existing templates "
            "cited in the error message.\n"
            "- If a route needs a page that doesn't exist, redirect to '/' or use "
            "the closest existing template (e.g., index.html).\n"
        )

    # Special handling for quality_floor errors
    if error_type == "quality_floor":
        type_rules += (
            "\n\nQUALITY FLOOR REPAIR:\n"
            "- The file was rejected because it was a placeholder stub.\n"
            "- You MUST output SUBSTANTIAL, real, functional content.\n"
            "- For HTML: multiple sections, real UI elements, forms, cards, navigation.\n"
            "- For CSS: many selectors, real properties, responsive design.\n"
            "- For JS: real event handlers, DOM manipulation, functional logic.\n"
        )

    return (
        f"You are a software repair engine. A build step failed.\n\n"
        f"Failed command: {command}\n"
        f"Error type: {error_type}\n"
        f"Error message: {error_message}\n\n"
        f"File to fix: {file_path}\n"
        f"Current file content:\n```\n{file_content}\n```\n\n"
        f"Attempt: {attempt}/{config.BUILDER_MAX_REPAIR_ATTEMPTS}\n"
        f"{type_rules}\n"
        "Output ONLY the corrected file content. No explanation. No markdown fences. "
        "Only the raw fixed file content."
    )


def _css_full_regeneration_prompt(project_name: str, user_request: str) -> str:
    """Dedicated prompt for full CSS regeneration. Discards old content, demands real CSS."""
    return (
        f"Generate a complete, premium-quality CSS stylesheet for a web application.\n\n"
        f"Project: {project_name}\n"
        f"Application purpose: {user_request[:300]}\n\n"
        "REQUIREMENTS - you MUST include ALL of these:\n"
        "1. CSS custom properties at :root (--primary-color, --bg-color, --text-color, --card-bg, --border-radius, --shadow)\n"
        "2. Global reset: * { box-sizing: border-box; margin: 0; padding: 0; }\n"
        "3. Body styles: font-family from Google Fonts (Inter or Roboto), background, text color, line-height\n"
        "4. .container class: max-width: 1200px, margin: 0 auto, padding\n"
        "5. Nav bar: background, padding, flexbox layout, link styles\n"
        "6. Card component: background, border-radius, box-shadow, padding\n"
        "7. Button styles: padding, border-radius, background, color, border: none, cursor: pointer\n"
        "8. button:hover and button:focus states with transition\n"
        "9. Form input and select styles: border, border-radius, padding, focus outline\n"
        "10. Typography hierarchy: h1, h2, h3 with font-size and font-weight\n"
        "11. At least one @media query for mobile (<768px)\n"
        "12. Footer styles\n"
        "13. Table styles if relevant\n"
        "14. Meaningful color palette - NOT raw red/blue/green\n\n"
        "MINIMUM: 8 distinct selectors, 20 property declarations.\n"
        "Output ONLY valid CSS code. No markdown fences. No explanation. No placeholder comments."
    )


def _js_full_regeneration_prompt(project_name: str, user_request: str) -> str:
    """Dedicated prompt for full JS regeneration. Discards old content, demands real JS."""
    return (
        f"Generate complete frontend JavaScript for a web application.\n\n"
        f"Project: {project_name}\n"
        f"Application purpose: {user_request[:300]}\n\n"
        "REQUIREMENTS:\n"
        "1. Use modern JavaScript (const/let, arrow functions, template literals)\n"
        "2. Include DOMContentLoaded event listener as entry point\n"
        "3. Handle form submissions with validation\n"
        "4. Add interactive UI feedback (button states, loading indicators, alerts)\n"
        "5. Use fetch() for any API calls to Flask routes if needed\n"
        "6. Add at least 3 event listeners (click, submit, input, etc.)\n"
        "7. Include helper functions for DOM manipulation\n\n"
        "Output ONLY valid JavaScript code. No markdown fences. No explanation."
    )


def _python_full_regeneration_prompt(project_name: str, user_request: str, manifest: dict = None) -> str:
    """Dedicated prompt for full Python/Flask regeneration. Discards old code, preserves manifest."""
    routes_str = ""
    if manifest and manifest.get("routes"):
        routes_str = f"REQUIRED ROUTES to implement: {manifest['routes']}"
        
    pages_str = ""
    if manifest and manifest.get("pages"):
        pages_str = f"REQUIRED PAGES to render via render_template(): {manifest['pages']}"

    return (
        f"Generate a complete, production-ready Flask application (app.py).\n\n"
        f"Project: {project_name}\n"
        f"Purpose: {user_request[:500]}\n\n"
        f"{routes_str}\n"
        f"{pages_str}\n\n"
        "REQUIREMENTS - you MUST include:\n"
        "1. All necessary imports (flask, os, json, etc.).\n"
        "2. A secret key and app configuration.\n"
        "3. Routes that match the project manifest above exactly.\n"
        "4. Error handlers for 404 and 500.\n"
        "5. Clean, modular Python code with comments.\n"
        "6. JSON-based persistence (data/*.json) if data storage is needed.\n"
        "7. DO NOT use inline HTML - use render_template() for all UI routes.\n"
        "8. Ensure all templates cited in manifest are rendered.\n\n"
        "Output ONLY valid Python code. No markdown. No explanation. No placeholder stubs."
    )


# ---------------------------------------------------------------------------
# LLM patch retrieval
# ---------------------------------------------------------------------------

async def _get_llm_patch(prompt: str, attempt: int) -> str | None:
    """Call LLM for a patch. Escalates to tech/cloud mode on later attempts."""
    try:
        from ai.ai_router import route_llm
        import re
        mode = "tech" if attempt >= 3 else "chat"
        response, _ = await route_llm(
            system_prompt="You are a software repair engine. Output only corrected file content. No markdown fences.",
            user_message=prompt,
            mode=mode,
        )
        content = response.strip()
        # Strip markdown fences if LLM wrapped the output
        if "```" in content:
            match = re.search(r"```[\w]*\n(.*?)```", content, re.DOTALL)
            if match:
                content = match.group(1).strip()
            else:
                content = re.sub(r"```[\w]*\n?", "", content)
                content = content.replace("```", "").strip()
        logger.info(f"[REPAIR] LLM patch received: {len(content)} chars")
        return content
    except Exception as e:
        logger.error(f"[REPAIR] LLM patch request failed: {e}")
        return None


# ---------------------------------------------------------------------------
# Error comparison
# ---------------------------------------------------------------------------

def _is_worse(old_check: dict, new_check: dict) -> bool:
    """Returns True if the new error is the same type or a new distinct type was introduced."""
        
    # Block rollback to known-invalid placeholder stubs if we are fixing quality_floor
    if old_check["error_type"] == "quality_floor" and new_check["error_type"] != "quality_floor":
        # Any error that isn't quality_floor is technically progress from a placeholder
        return False

    # Universal syntax gate: Never rollback to a version that fails py_compile / node --check
    # if the previous version also failed or if we are fixing a syntax error.
    if old_check["error_type"] == "syntax_error" and new_check["error_type"] == "syntax_error":
        return True # Attempting a syntax fix that resulted in another syntax error is a "stall" or worse

    return new_check["error_type"] == old_check["error_type"] or (
        new_check["error_type"] is not None
        and old_check["error_type"] != new_check["error_type"]
    )


# ---------------------------------------------------------------------------
# Main repair loop
# ---------------------------------------------------------------------------

async def run(
    initial_check: dict[str, Any],
    failed_command: str,
    project_root: Path,
    files_to_create: list[dict],
    target_path_override: str = None,
    goal: dict = None,
) -> AsyncGenerator[str, Any]:
    """
    Iterative repair loop. Yields status strings for each action taken.

    Args:
        initial_check:   result from result_checker.check() that triggered repair
        failed_command:  the command string that failed
        project_root:    absolute path to the project directory
        files_to_create: list of {"path": str, "description": str}
        target_path_override: specific file path to repair, overrides heuristic
        goal: parsed goal dict for deterministic rebuilds
    """
    error_type = initial_check["error_type"]
    error_message = initial_check["error_message"]
    previous_errors: list[str] = []
    current_check = initial_check

    # -- Select the most relevant file to patch based on error type --
    if target_path_override:
        target_file_entry = {"path": target_path_override}
    else:
        target_file_entry = files_to_create[-1] if files_to_create else None

        # Command-aware targeting
        if "requirements.txt" in failed_command:
            for f in files_to_create:
                if f["path"] == "requirements.txt":
                    target_file_entry = f
                    logger.info("[REPAIR] Command references requirements.txt >> targeting it")
                    break
        elif "package.json" in failed_command or failed_command.startswith("npm"):
            for f in files_to_create:
                if f["path"] == "package.json":
                    target_file_entry = f
                    logger.info("[REPAIR] Command references package.json >> targeting it")
                    break
        elif error_type in ("missing_module", "invalid_format"):
            for f in files_to_create:
                if f["path"] in ("requirements.txt", "package.json"):
                    target_file_entry = f
                    break
        elif error_type in ("syntax_error", "runtime_crash", "empty_file", "quality_floor"):
            # Target main script files, not dependency manifests
            dep_files = {"requirements.txt", "package.json"}
            for f in files_to_create:
                if f["path"] not in dep_files:
                    target_file_entry = f
                    break

    if not target_file_entry:
        yield "[REPAIR] No target file available for repair. Aborting."
        return

    target_path = target_file_entry["path"]

    for attempt in range(1, config.BUILDER_MAX_REPAIR_ATTEMPTS + 1):
        yield f"[REPAIR] Attempt {attempt}/{config.BUILDER_MAX_REPAIR_ATTEMPTS} >> targeting {target_path}"

        # -- Stall detection --
        previous_errors.append(current_check.get("error_type", "unknown"))
        recent = previous_errors[-STALL_THRESHOLD:]
        if len(recent) >= STALL_THRESHOLD and len(set(recent)) == 1:
            yield f"[REPAIR] Stall detected -- same error ({recent[0]!r}) repeated {STALL_THRESHOLD}x. Aborting."
            return

        # -- Read + backup --
        try:
            backup_content = read_file(project_root, target_path)
        except FileNotFoundError:
            backup_content = ""

        patched_content = None
        is_css = target_path.endswith(".css")
        is_js  = target_path.endswith(".js")
        is_py  = target_path.endswith(".py")
        is_readme = target_path.lower() == "readme.md"
        is_quality_floor = current_check.get("error_type") == "quality_floor"
        is_syntax_error = current_check.get("error_type") == "syntax_error"

        if target_path == "requirements.txt" and goal:
            from builder.project_planner import build_deterministic_requirements
            det_content = build_deterministic_requirements(goal)
            if det_content:
                yield "[REPAIR] Re-generating requirements.txt deterministically..."
                patched_content = det_content

        elif (is_css or is_js or is_readme) and is_quality_floor:
            # Full regeneration - discard stub, call LLM with a strong dedicated prompt
            file_type = "CSS" if is_css else ("JS" if is_js else "README")
            yield f"[REPAIR] {file_type} quality floor failure - DISCARDING stub, running full regeneration..."
            project_name = goal.get("project_name", "app") if goal else "app"
            user_request = goal.get("user_request", "") if goal else ""
            
            from builder.builder_controller import (
                _FALLBACK_CSS, _FALLBACK_JS, _FALLBACK_README, _validate_frontend_content
            )

            if is_css:
                regen_prompt = _css_full_regeneration_prompt(project_name, user_request)
            elif is_js:
                regen_prompt = _js_full_regeneration_prompt(project_name, user_request)
            else:
                regen_prompt = _repair_prompt(
                    error_type="quality_floor",
                    error_message="File is a placeholder stub",
                    file_path=target_path,
                    file_content="",
                    command=f"Full regeneration of {target_path}",
                    attempt=attempt,
                )

            patched_content = await _get_llm_patch(regen_prompt, attempt)
            
            # Validate the new content
            if patched_content:
                if not _validate_frontend_content(patched_content, target_path):
                    yield f"[REPAIR] {file_type} regeneration output failed validation. Using DETERMINISTIC FALLBACK."
                    if is_css: patched_content = _FALLBACK_CSS
                    elif is_js: patched_content = _FALLBACK_JS
                    else: patched_content = _FALLBACK_README
            else:
                yield f"[REPAIR] {file_type} regeneration returned NO content. Using DETERMINISTIC FALLBACK."
                if is_css: patched_content = _FALLBACK_CSS
                elif is_js: patched_content = _FALLBACK_JS
                else: patched_content = _FALLBACK_README

        elif is_py and (is_syntax_error or current_check["error_type"] == "runtime_crash"):
            project_name = goal.get("project_name", "app") if goal else "app"
            user_request = goal.get("user_request", "") if goal else ""
            
            if attempt == 2:
                # Stage 2: Full Python Regeneration
                yield f"[REPAIR] Python fix attempt {attempt} - Patching failed. Starting FULL REGENERATION..."
            
            # Use manifest if available (passed via project_planner context usually, but we need to find it)
            # For now, we assume if goal is present, we have intent. 
            # We can try to reconstruct manifest-like info from goal's routes if they were added.
            
            # Reconstruct manifest from goal if possible (planner might have stored it there)
            manifest = goal.get("manifest", {})
            regen_prompt = _python_full_regeneration_prompt(project_name, user_request, manifest)
            
            if attempt == 2:
                patched_content = await _get_llm_patch(regen_prompt, attempt)
            if not patched_content:
                yield "[REPAIR] Python full regeneration returned NO content. Using DETERMINISTIC FLASK FALLBACK."
                from builder.builder_controller import build_deterministic_flask_app
                patched_content = build_deterministic_flask_app(manifest)
            elif attempt >= 3:
                # Stage 3: Deterministic Fallback
                yield f"[REPAIR] Python fix attempt {attempt} - Forcing DETERMINISTIC FLASK FALLBACK to stop stalling."
                from builder.builder_controller import build_deterministic_flask_app
                patched_content = build_deterministic_flask_app(manifest)

        if patched_content is None:
            prompt = _repair_prompt(
                error_type=current_check["error_type"],
                error_message=current_check["error_message"],
                file_path=target_path,
                file_content=backup_content,
                command=failed_command,
                attempt=attempt,
            )
            patched_content = await _get_llm_patch(prompt, attempt)

        if not patched_content:
            yield f"[REPAIR] Engine returned no patch on attempt {attempt}. Skipping."
            continue

        # -- Apply patch --
        update_file(project_root, target_path, patched_content)
        yield f"[REPAIR] Patch applied to {target_path}"

        # -- Re-run command or validation --
        yield f"[REPAIR] Re-running: {failed_command}"
        if failed_command.startswith("Validation of "):
            v_path = failed_command.replace("Validation of ", "").strip()
            from builder.file_validator import validate_file
            v_res = validate_file(project_root, v_path)
            new_check = {
                "status": v_res["status"],
                "error_type": v_res.get("error_type"),
                "error_message": v_res.get("error_message", ""),
            }
        elif failed_command == "Cross-file template reference validation":
            # Re-check cross-file consistency
            import re
            try:
                app_content = read_file(project_root, "app.py")
                found_refs = set(re.findall(r"render_template\(['\"]([^'\"]+)['\"]", app_content))
                templates_dir = project_root / "templates"
                actual_templates = set()
                if templates_dir.exists():
                    for f in templates_dir.iterdir():
                        if f.suffix == ".html":
                            actual_templates.add(f.name)
                missing = found_refs - actual_templates
                if missing:
                    new_check = {
                        "status": "error",
                        "error_type": "missing_template",
                        "error_message": f"Still missing: {sorted(missing)}",
                    }
                else:
                    new_check = {"status": "success", "error_type": None, "error_message": ""}
            except Exception as e:
                new_check = {"status": "error", "error_type": "runtime_crash", "error_message": str(e)}
        else:
            can_run = True
            if target_path.endswith(".py"):
                from builder.file_validator import validate_file
                v_res = validate_file(project_root, target_path)
                if v_res["status"] != "success":
                    yield f"  [PY_GATE] Syntax invalid after patch for {target_path}. Skipping runtime retry."
                    new_check = {
                        "status": "error",
                        "error_type": "syntax_error",
                        "error_message": v_res.get("error_message", "Syntax error after patch"),
                    }
                    can_run = False
            
            if can_run:
                new_result = run_command(failed_command, project_root)
                new_check = check(new_result, failed_command)

        current_check = new_check

        if new_check["status"] == "success":
            yield f"[SUCCESS] Repair succeeded on attempt {attempt} >> {failed_command}"
            return

        if _is_worse(initial_check, new_check):
            yield f"[REPAIR] Patch worsened error -- reverting {target_path}"
            update_file(project_root, target_path, backup_content)
            logger.warning(f"[REPAIR] Reverted {target_path} -- patch made things worse")
            current_check["error_type"] = initial_check["error_type"]
            current_check["error_message"] = initial_check["error_message"]
        else:
            yield f"[REPAIR] Error changed: was={initial_check['error_type']} now={new_check['error_type']}"
            error_type = new_check["error_type"]
            error_message = new_check["error_message"]

    yield f"[REPAIR] Max attempts ({config.BUILDER_MAX_REPAIR_ATTEMPTS}) reached without success."
