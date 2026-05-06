"""
file_validator.py - File-type-aware pre-execution validation.

Validates generated files before any commands are run to catch LLM hallucination
like shell commands in requirements.txt, broken HTML fragments, or invalid Python syntax.

Validation philosophy:
  - Structure-based checks, not just character counts
  - HTML must be a complete standalone document (no Jinja inheritance)
  - CSS must contain real selectors and rules
  - JS must contain real logic if present
  - requirements.txt must pass strict format rules
  - Python must pass py_compile
"""

import logging
import re
from pathlib import Path
from builder.terminal_runner import run_command

logger = logging.getLogger("presence.builder.file_validator")

# Suspicious patterns in non-shell files
_SHELL_PATTERNS = ["mkdir ", "cd ", "echo ", "touch ", "pip install ", "python "]
_PYTHON_PATTERNS = ["def ", "class ", "import ", "from ", "print("]


# ---------------------------------------------------------------------------
# Python validation
# ---------------------------------------------------------------------------

def _check_python(file_path: Path, project_root: Path) -> dict:
    """Validate Python syntax using py_compile."""
    logger.info(f"[VALIDATOR] Checking Python syntax: {file_path.name}")
    cmd = f'python -m py_compile "{file_path.name}"'
    result = run_command(cmd, file_path.parent)
    if result["exit_code"] != 0:
        # Capture full output (stderr usually contains the syntax error details)
        full_msg = (result["stderr"] + "\n" + result["stdout"]).strip()
        msg = full_msg if full_msg else "Python syntax validation failed"
        logger.error(f"[VALIDATOR] Python syntax FAILED for {file_path.name}:\n{msg}")
        return {
            "status": "error",
            "error_type": "syntax_error",
            "error_message": msg,
        }
    logger.info(f"[VALIDATOR] Python syntax OK: {file_path.name}")
    return {"status": "success"}


# ---------------------------------------------------------------------------
# Requirements validation
# ---------------------------------------------------------------------------

def _check_requirements(content: str) -> dict:
    """Validate requirements.txt contains only valid pip package lines."""
    logger.info("[VALIDATOR] Checking requirements.txt format")

    if "```" in content:
        return {
            "status": "error",
            "error_type": "invalid_format",
            "error_message": "Found markdown fences in requirements.txt.",
        }

    lines = content.splitlines()
    if len(lines) > 50:
        return {
            "status": "error",
            "error_type": "invalid_format",
            "error_message": f"requirements.txt is abnormally long ({len(lines)} lines). Possible LLM looping.",
        }

    for line in lines:
        line = line.strip()
        if not line or line.startswith("#"):
            continue

        if " " in line:
            return {
                "status": "error",
                "error_type": "invalid_format",
                "error_message": f"Invalid requirement '{line}'. Package names cannot contain spaces.",
            }

        bad_starts = [
            "mkdir ", "cd ", "echo ", "touch ", "python ", "pip ",
            "yarn ", "npm ", "from ", "import ", "def ", "class ",
            "print(", "if ", "for ", "while ", "return ",
        ]
        if any(line.startswith(b) for b in bad_starts):
            return {
                "status": "error",
                "error_type": "invalid_format",
                "error_message": f"Found non-package content in requirements.txt: {line}",
            }

        if "&&" in line or "||" in line:
            return {
                "status": "error",
                "error_type": "invalid_format",
                "error_message": f"Found shell-like syntax in requirements.txt: {line}",
            }

        invalid_packages = {"python", "node", "npm", "yarn", "json", "os", "sys", "re", "io", "math"}
        pkg_name = line.split("==")[0].split(">=")[0].split("<=")[0].split(">")[0].split("<")[0].strip().lower()
        if pkg_name in invalid_packages:
            return {
                "status": "error",
                "error_type": "invalid_format",
                "error_message": f"'{pkg_name}' is not a valid pip package (runtime or builtin).",
            }

    logger.info("[VALIDATOR] requirements.txt OK")
    return {"status": "success"}


# ---------------------------------------------------------------------------
# HTML validation - structure-based, standalone only
# ---------------------------------------------------------------------------

def _check_html(content: str, file_path: Path) -> dict:
    """
    Validate HTML files are complete standalone HTML5 documents.
    Rejects: Jinja inheritance fragments, empty files, placeholder stubs.
    """
    logger.info(f"[VALIDATOR] Checking HTML structure: {file_path.name}")

    stripped = content.strip()
    if not stripped:
        return {
            "status": "error",
            "error_type": "empty_file",
            "error_message": f"HTML file is empty: {file_path.name}",
        }

    lower = stripped.lower()

    # -- Reject Jinja inheritance (we use standalone pages now) --
    if "{% extends" in lower:
        return {
            "status": "error",
            "error_type": "invalid_format",
            "error_message": (
                f"HTML file {file_path.name} uses Jinja2 template inheritance "
                "(extends). Builder requires standalone HTML5 documents."
            ),
        }

    # -- Require complete document structure --
    has_doctype = "<!doctype" in lower
    has_html = "<html" in lower
    has_head = "<head" in lower
    has_body = "<body" in lower
    has_title = "<title" in lower

    missing = []
    if not has_doctype and not has_html:
        missing.append("<!DOCTYPE html> or <html>")
    if not has_head:
        missing.append("<head>")
    if not has_body:
        missing.append("<body>")
    if not has_title:
        missing.append("<title>")

    if missing:
        return {
            "status": "error",
            "error_type": "invalid_format",
            "error_message": (
                f"HTML file {file_path.name} is missing required structural tags: "
                f"{', '.join(missing)}. Must be a complete standalone HTML5 document."
            ),
        }

    # -- Require real content (not just empty structure) --
    # Count meaningful content tags
    content_tags = 0
    for tag in ["<nav", "<main", "<section", "<div", "<form", "<table",
                "<ul", "<ol", "<article", "<header", "<footer", "<h1",
                "<h2", "<h3", "<p", "<button", "<input", "<a "]:
        if tag in lower:
            content_tags += 1

    if content_tags < 3:
        return {
            "status": "error",
            "error_type": "quality_floor",
            "error_message": (
                f"HTML file {file_path.name} has too few content elements "
                f"(found {content_tags} content tags, need at least 3). "
                "File appears to be a placeholder stub."
            ),
        }

    # -- Reject accidental Python code in HTML --
    python_count = sum(1 for p in _PYTHON_PATTERNS if p in content and "<script" not in lower)
    if python_count >= 3:
        return {
            "status": "error",
            "error_type": "invalid_format",
            "error_message": f"HTML file appears to contain Python code: {file_path.name}",
        }

    logger.info(f"[VALIDATOR] HTML structure OK: {file_path.name}")
    return {"status": "success"}


# ---------------------------------------------------------------------------
# CSS validation - structure-based
# ---------------------------------------------------------------------------

def _check_css(content: str, file_path: Path) -> dict:
    """Validate CSS files contain real selectors and meaningful rules."""
    logger.info(f"[VALIDATOR] Checking CSS structure: {file_path.name}")

    stripped = content.strip()
    if not stripped:
        return {
            "status": "error",
            "error_type": "empty_file",
            "error_message": f"CSS file is empty: {file_path.name}",
        }

    # -- Reject accidental Python in CSS --
    python_matches = sum(1 for p in _PYTHON_PATTERNS if p in content)
    if python_matches > 2:
        return {
            "status": "error",
            "error_type": "invalid_format",
            "error_message": f"CSS file appears to contain Python code: {file_path.name}",
        }

    # -- Reject shell content --
    if any(stripped.startswith(p) for p in _SHELL_PATTERNS):
        return {
            "status": "error",
            "error_type": "invalid_format",
            "error_message": f"CSS file appears to contain shell commands: {file_path.name}",
        }

    # -- Reject markdown fences --
    if "```" in content:
        return {
            "status": "error",
            "error_type": "invalid_format",
            "error_message": f"CSS file contains markdown fences: {file_path.name}",
        }

    # -- Structure check: must have multiple selectors with rules --
    selector_count = len(re.findall(r"[a-zA-Z.#\[\]:*@][^{]*\{", content))
    if selector_count < 5:
        return {
            "status": "error",
            "error_type": "quality_floor",
            "error_message": (
                f"CSS file {file_path.name} has too few selectors "
                f"(found {selector_count}, need at least 5). "
                "File appears to be a placeholder stub."
            ),
        }

    # -- Must contain meaningful property declarations --
    property_count = len(re.findall(r":\s*[^;]+;", content))
    if property_count < 10:
        return {
            "status": "error",
            "error_type": "quality_floor",
            "error_message": (
                f"CSS file {file_path.name} has too few style rules "
                f"(found {property_count} declarations, need at least 10). "
                "File appears to be a placeholder."
            ),
        }

    logger.info(f"[VALIDATOR] CSS structure OK: {file_path.name}")
    return {"status": "success"}


# ---------------------------------------------------------------------------
# JS validation - structure-based
# ---------------------------------------------------------------------------

def _check_js(content: str, file_path: Path, project_root: Path) -> dict:
    """Validate JS files contain real logic if present."""
    logger.info(f"[VALIDATOR] Checking JS: {file_path.name}")

    stripped = content.strip()

    # Empty JS is acceptable (optional file)
    if not stripped:
        logger.info(f"[VALIDATOR] JS file is empty (optional), accepting: {file_path.name}")
        return {"status": "success"}

    # -- Reject markdown fences --
    if "```" in content:
        return {
            "status": "error",
            "error_type": "invalid_format",
            "error_message": f"JS file contains markdown fences: {file_path.name}",
        }

    # -- Reject shell content --
    if any(stripped.startswith(p) for p in _SHELL_PATTERNS):
        return {
            "status": "error",
            "error_type": "invalid_format",
            "error_message": f"JS file appears to contain shell commands: {file_path.name}",
        }

    # -- Structure check: must contain real JS constructs --
    js_constructs = 0
    for pattern in ["function ", "const ", "let ", "var ", "=>", "document.",
                     "addEventListener", "querySelector", "fetch(", "async ",
                     "class ", "export ", "import ", "window.", "console."]:
        if pattern in content:
            js_constructs += 1

    if js_constructs < 2:
        return {
            "status": "error",
            "error_type": "quality_floor",
            "error_message": (
                f"JS file {file_path.name} has too few JS constructs "
                f"(found {js_constructs}, need at least 2). "
                "File appears to be placeholder comments only."
            ),
        }

    # -- Syntax check with node --check --
    cmd = f'node --check "{file_path.name}"'
    result = run_command(cmd, file_path.parent)
    if result["exit_code"] != 0:
        full_msg = (result["stderr"] + "\n" + result["stdout"]).strip()
        msg = full_msg if full_msg else "JS syntax validation failed"
        logger.error(f"[VALIDATOR] JS syntax FAILED for {file_path.name}:\n{msg}")
        return {
            "status": "error",
            "error_type": "syntax_error",
            "error_message": msg,
        }

    logger.info(f"[VALIDATOR] JS OK: {file_path.name}")
    return {"status": "success"}


# ---------------------------------------------------------------------------
# JSON validation
# ---------------------------------------------------------------------------

def _check_json(content: str, file_path: Path) -> dict:
    """Validate JSON files are parseable."""
    import json as json_mod

    logger.info(f"[VALIDATOR] Checking JSON: {file_path.name}")
    try:
        json_mod.loads(content)
        logger.info(f"[VALIDATOR] JSON OK: {file_path.name}")
        return {"status": "success"}
    except json_mod.JSONDecodeError as e:
        logger.error(f"[VALIDATOR] JSON parse error in {file_path.name}: {e}")
        return {
            "status": "error",
            "error_type": "invalid_format",
            "error_message": f"Invalid JSON in {file_path.name}: {e}",
        }


# ---------------------------------------------------------------------------
# Main validation dispatcher
# ---------------------------------------------------------------------------

def validate_file(project_root: Path, rel_path: str) -> dict:
    """
    Validate a file based on its extension.
    Returns: {"status": "success"} or {"status": "error", "error_type": ..., "error_message": ...}
    """
    file_path = (project_root / rel_path).resolve()

    # Protect bounded access
    if not str(file_path).startswith(str(project_root.resolve())):
        return {
            "status": "error",
            "error_type": "path_traversal",
            "error_message": "Path traversal detected.",
        }

    if not file_path.exists():
        logger.error(f"[VALIDATOR] File does not exist: {rel_path}")
        return {
            "status": "error",
            "error_type": "missing_file",
            "error_message": f"File does not exist: {rel_path}",
        }

    ext = file_path.suffix.lower()
    name = file_path.name.lower()

    # Read content for text files
    content = None
    if ext in (".py", ".txt", ".html", ".css", ".js", ".json", ".md"):
        try:
            content = file_path.read_text(encoding="utf-8")
        except Exception as e:
            logger.error(f"[VALIDATOR] Cannot read {rel_path}: {e}")
            return {
                "status": "error",
                "error_type": "read_error",
                "error_message": str(e),
            }

    if ext == ".py":
        return _check_python(file_path, project_root)
    elif name == "requirements.txt":
        return _check_requirements(content)
    elif ext == ".html":
        return _check_html(content, file_path)
    elif ext == ".css":
        return _check_css(content, file_path)
    elif ext == ".js":
        return _check_js(content, file_path, project_root)
    elif ext == ".json":
        return _check_json(content, file_path)

    # .md and unknown extensions pass by default
    logger.info(f"[VALIDATOR] Skipping validation for {rel_path} (ext={ext})")
    return {"status": "success"}
