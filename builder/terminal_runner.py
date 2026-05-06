"""
terminal_runner.py — Real subprocess execution with strict safety enforcement.

Safety layers (applied in order before any subprocess call):
  1. Shell chaining block  — rejects &&, ||, ;
  2. Blocklist check       — rejects destructive patterns
  3. Allowlist check       — rejects commands not starting with approved tokens
  4. Timeout enforcement   — kills process after BUILDER_COMMAND_TIMEOUT seconds

DRY_RUN mode: prints the command instead of executing it.

Returns:
  {
    "success": bool,
    "stdout": str,
    "stderr": str,
    "exit_code": int,
    "error_type": str | None,   # None | "blocked" | "timeout" | "crash"
  }
"""

import logging
import subprocess
from pathlib import Path

from core.config import config

logger = logging.getLogger("presence.builder.terminal_runner")

# ── Safety configuration ──

ALLOWED_PREFIXES = frozenset(["npm", "node", "python", "pip", "yarn", "npx"])

BLOCKED_PATTERNS = [
    # Shell chaining (must come first — these are zero-tolerance)
    "&&", "||", ";",
    # Destructive file system
    "rm -rf", "del /s", "del /f", "rmdir /s", "rd /s",
    # Format / wipe
    "format ", "mkfs", "dd if=",
    # System control
    "shutdown", "reboot", "halt",
    # Output redirection to dangerous targets
    "> /dev/",
    # Process killing
    "taskkill", "kill -9",
]


def _safety_check(cmd: str) -> tuple[bool, str]:
    """
    Returns (is_safe, reason).
    Checks chaining, blocklist, then allowlist — in that order.
    """
    cl = cmd.strip().lower()

    # 1. Shell chaining
    for chain in ("&&", "||", ";"):
        if chain in cl:
            return False, f"Shell chaining character {chain!r} is not allowed."

    # 2. Blocklist
    for pattern in BLOCKED_PATTERNS:
        if pattern in cl:
            return False, f"Blocked destructive pattern: {pattern!r}"

    # 3. Allowlist — first token must be an approved prefix
    tokens = cl.split()
    if not tokens:
        return False, "Empty command."
    first = tokens[0]
    # Strip path prefix (e.g., /usr/bin/python → python)
    first_base = Path(first).name.split(".")[0]  # handles python.exe → python
    if first_base not in ALLOWED_PREFIXES:
        return False, f"Command prefix {first!r} is not in the allowed list."

    return True, ""


def run_command(cmd: str, cwd: Path) -> dict:
    """
    Execute cmd inside cwd with strict safety enforcement.
    Returns a result dict — never raises.
    """
    is_safe, reason = _safety_check(cmd)

    if not is_safe:
        logger.error(f"[TERMINAL] BLOCKED → {cmd!r}  Reason: {reason}")
        return {
            "success": False,
            "stdout": "",
            "stderr": reason,
            "exit_code": -1,
            "error_type": "blocked",
        }

    if config.BUILDER_DRY_RUN:
        logger.info(f"[DRY-RUN] Would run: {cmd}  CWD={cwd}")
        return {
            "success": True,
            "stdout": f"[DRY-RUN] Command not executed: {cmd}",
            "stderr": "",
            "exit_code": 0,
            "error_type": None,
        }

    # Resolve to absolute path — critical for Windows paths with spaces
    resolved_cwd = str(cwd.resolve())
    logger.info(f"[TERMINAL] Running >> {cmd}  CWD={resolved_cwd}")

    try:
        result = subprocess.run(
            cmd,
            shell=True,         # required for npm/npx on Windows
            cwd=resolved_cwd,
            capture_output=True,
            text=True,
            timeout=config.BUILDER_COMMAND_TIMEOUT,
            encoding="utf-8",
            errors="replace",
        )

        stdout = result.stdout.strip()
        stderr = result.stderr.strip()
        exit_code = result.returncode

        logger.info(
            f"[TERMINAL] exit_code={exit_code}  "
            f"stdout={len(stdout)} chars  stderr={len(stderr)} chars"
        )
        if stderr:
            logger.debug(f"[TERMINAL] stderr preview: {stderr[:200]}")

        return {
            "success": exit_code == 0,
            "stdout": stdout,
            "stderr": stderr,
            "exit_code": exit_code,
            "error_type": None if exit_code == 0 else "crash",
        }

    except subprocess.TimeoutExpired as e:
        # Kill the process group
        if e.process:
            try:
                e.process.kill()
            except Exception:
                pass
        logger.error(
            f"[TERMINAL] Process killed after {config.BUILDER_COMMAND_TIMEOUT}s timeout → {cmd!r}"
        )
        return {
            "success": False,
            "stdout": "",
            "stderr": f"Process exceeded {config.BUILDER_COMMAND_TIMEOUT}s timeout.",
            "exit_code": -1,
            "error_type": "timeout",
        }

    except Exception as e:
        logger.error(f"[TERMINAL] Unexpected error running {cmd!r}: {e}")
        return {
            "success": False,
            "stdout": "",
            "stderr": str(e),
            "exit_code": -1,
            "error_type": "crash",
        }
