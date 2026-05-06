"""
Presence AI — Phase 2.1 Entry Point.

Multi-mode cognitive system with OS-level lifecycle control.
Single-instance lock. Signal handling. Graceful shutdown.
"""

import sys
import os
import signal

# Ensure project root is on path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def _handle_signal(signum, frame):
    """Handle SIGINT/SIGTERM -> graceful shutdown."""
    from system.shutdown_manager import shutdown
    shutdown()


def main():
    # ── Signal handlers ──
    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    # ── Single instance lock ──
    from core.config import config
    from system.process_lock import acquire_lock

    if not acquire_lock(config.MEMORY_DIR):
        print("[ABORT] Another instance of Presence AI is already running.")
        sys.exit(1)

    # ── Boot ──
    from core.startup import run
    run()


if __name__ == "__main__":
    main()