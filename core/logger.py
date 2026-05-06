"""
Logger — Structured logging for the Presence system.
"""

import io
import logging
import sys
from pathlib import Path


def setup_logging(level: int = logging.INFO):
    """Configure console + file logging for the entire system."""

    log_dir = Path(__file__).resolve().parent.parent / "logs"
    log_dir.mkdir(exist_ok=True)

    fmt = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-7s | %(name)-30s | %(message)s",
        datefmt="%H:%M:%S",
    )

    # Console handler with UTF-8 error-safe output (Windows cp1252 fix)
    safe_stdout = io.TextIOWrapper(
        sys.stdout.buffer, encoding="utf-8", errors="replace", line_buffering=True,
    )
    console = logging.StreamHandler(safe_stdout)
    console.setFormatter(fmt)
    console.setLevel(level)

    # File handler (UTF-8)
    file_handler = logging.FileHandler(log_dir / "presence.log", encoding="utf-8")
    file_handler.setFormatter(fmt)
    file_handler.setLevel(logging.DEBUG)

    root = logging.getLogger("presence")
    root.setLevel(logging.DEBUG)
    root.addHandler(console)
    root.addHandler(file_handler)

    return root
