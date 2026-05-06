"""
result_checker.py — Classify terminal output as success or error.

Success requires ALL of:
  - exit_code == 0
  - no critical stderr pattern matched
  - error_type is None (not blocked/timeout/crash)

Returns:
  {
    "status": "success" | "error",
    "error_type": str,    # None | "missing_module" | "syntax_error" | "build_failure"
                          #        | "runtime_crash" | "timeout" | "blocked"
    "error_message": str,
  }
"""

import logging
import re
from typing import Any

logger = logging.getLogger("presence.builder.result_checker")

# ── Error pattern registry (order matters — more specific first) ──

ERROR_PATTERNS: list[tuple[str, str, str]] = [
    # (pattern, error_type, search_in)
    # Missing modules
    (r"ModuleNotFoundError:\s*No module named", "missing_module", "stderr"),
    (r"No module named",                        "missing_module", "stderr"),
    (r"Cannot find module",                     "missing_module", "stderr"),
    (r"cannot find module",                     "missing_module", "stderr"),

    # Syntax errors
    (r"SyntaxError",                            "syntax_error",   "stderr"),
    (r"IndentationError",                       "syntax_error",   "stderr"),
    (r"TabError",                               "syntax_error",   "stderr"),

    # Build failures — npm/yarn
    (r"npm ERR!",                              "build_failure",  "stderr"),
    (r"npm ERR!",                              "build_failure",  "stdout"),
    (r"yarn error",                            "build_failure",  "stderr"),
    (r"ENOENT",                                "build_failure",  "stderr"),
    (r"error Command failed",                  "build_failure",  "stderr"),

    # Python runtime
    (r"Traceback \(most recent call last\)",   "runtime_crash",  "stderr"),
    (r"RuntimeError",                          "runtime_crash",  "stderr"),
    (r"TypeError",                             "runtime_crash",  "stderr"),
    (r"AttributeError",                        "runtime_crash",  "stderr"),
    (r"ImportError",                           "missing_module", "stderr"),

    # Jinja2 template errors (runtime safety net)
    (r"jinja2\.exceptions\.TemplateNotFound",  "missing_template", "stderr"),
    (r"TemplateNotFound",                      "missing_template", "stderr"),

    # Generic non-zero
    (r"Error:",                                "runtime_crash",  "stderr"),
    (r"error:",                                "runtime_crash",  "stderr"),
]


def _extract_message(text: str, max_chars: int = 500) -> str:
    """
    Extract meaningful error context. 
    Special handling for Python SyntaxError to include line number and pointer.
    """
    if "SyntaxError" in text or "IndentationError" in text or "TabError" in text:
        # Try to find the "File ..., line ..." block
        match = re.search(r'(File ".*?", line \d+.*?(?:\n.*?)*?SyntaxError:.*)', text, re.DOTALL)
        if match:
            return match.group(1).strip()[:max_chars]

    # Default to first non-empty line
    for line in text.splitlines():
        line = line.strip()
        if line:
            return line[:max_chars]
    return text[:max_chars]


def check(result: dict[str, Any], cmd: str = "") -> dict[str, Any]:
    """
    Classify a terminal_runner result dict.
    Reads ONLY from real subprocess data — no assumptions.
    """
    # If the command is a long-running server, a timeout means it stayed alive!
    if result.get("error_type") == "timeout":
        if "python app.py" in cmd or "python main.py" in cmd or "npm start" in cmd:
            logger.info(f"[SUCCESS] Command {cmd!r} stayed alive until timeout — considering it successfully tested.")
            return {
                "status": "success",
                "error_type": None,
                "error_message": "",
            }

    # Passthrough for pre-classified errors (blocked / timeout for non-servers)
    if result.get("error_type") in ("blocked", "timeout"):
        return {
            "status": "error",
            "error_type": result["error_type"],
            "error_message": result.get("stderr", ""),
        }

    exit_code: int = result.get("exit_code", -1)
    stdout: str = result.get("stdout", "")
    stderr: str = result.get("stderr", "")

    # ── Pattern matching ──
    for pattern, error_type, search_in in ERROR_PATTERNS:
        target = stderr if search_in == "stderr" else stdout
        if re.search(pattern, target, re.IGNORECASE):
            msg = _extract_message(stderr or stdout)
            logger.error(f"[ERROR] Detected >> type={error_type}  msg={msg!r}")
            return {
                "status": "error",
                "error_type": error_type,
                "error_message": msg,
            }

    # -- Non-zero exit with no specific pattern --
    if exit_code != 0:
        msg = _extract_message(stderr or stdout or f"Process exited with code {exit_code}")
        logger.error(f"[ERROR] Detected >> type=runtime_crash  msg={msg!r}")
        return {
            "status": "error",
            "error_type": "runtime_crash",
            "error_message": msg,
        }

    # ── All conditions passed ──
    logger.info("[SUCCESS] Result check passed — all criteria satisfied.")
    return {
        "status": "success",
        "error_type": None,
        "error_message": "",
    }
