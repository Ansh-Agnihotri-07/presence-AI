"""
Process Lock — Single instance enforcement (Phase 2.1).

Prevents duplicate orbs by using a PID-based lock file.
If lock exists and PID is alive -> refuse to start.
On shutdown -> release lock.
"""

import os
import logging
from pathlib import Path

logger = logging.getLogger("presence.system.process_lock")

_LOCK_FILE: Path | None = None


def acquire_lock(lock_dir: Path) -> bool:
    """
    Attempt to acquire the process lock.

    Returns True if lock acquired (safe to start).
    Returns False if another instance is running.
    """
    global _LOCK_FILE
    lock_dir.mkdir(parents=True, exist_ok=True)
    _LOCK_FILE = lock_dir / "app.lock"

    if _LOCK_FILE.exists():
        try:
            stored_pid = int(_LOCK_FILE.read_text().strip())
            if _is_pid_alive(stored_pid):
                logger.warning(f"Another instance is running (PID {stored_pid}). Refusing to start.")
                return False
            else:
                logger.info(f"Stale lock found (PID {stored_pid} dead). Overwriting.")
        except (ValueError, OSError):
            logger.info("Corrupt lock file found. Overwriting.")

    # Write our PID
    _LOCK_FILE.write_text(str(os.getpid()))
    logger.info(f"Process lock acquired (PID {os.getpid()})")
    return True


def release_lock():
    """Release the process lock."""
    global _LOCK_FILE
    if _LOCK_FILE and _LOCK_FILE.exists():
        try:
            stored_pid = int(_LOCK_FILE.read_text().strip())
            if stored_pid == os.getpid():
                _LOCK_FILE.unlink()
                logger.info("Process lock released")
        except (ValueError, OSError):
            try:
                _LOCK_FILE.unlink()
            except OSError:
                pass


def _is_pid_alive(pid: int) -> bool:
    """Check if a process with the given PID is still running."""
    try:
        os.kill(pid, 0)
        return True
    except (OSError, ProcessLookupError):
        return False
