"""
Shutdown Manager — Graceful system termination (Phase 2.1).

Handles:
  - Memory flush
  - Event bus stop
  - Reminder engine stop
  - UI cleanup
  - Process lock release
  - QApplication quit

All shutdown paths (tray quit, Ctrl+C, SIGTERM, close event) call shutdown().
"""

import logging
import os

logger = logging.getLogger("presence.system.shutdown_manager")

_shutting_down = False


def shutdown():
    """
    Graceful shutdown — flush state, stop services, release lock, exit.

    Safe to call multiple times (guarded by _shutting_down flag).
    """
    global _shutting_down
    if _shutting_down:
        return
    _shutting_down = True

    logger.info("=== SHUTDOWN INITIATED ===")

    # 1. Flush memory
    try:
        from memory.store import memory_store
        memory_store.save_all()
        logger.info("Memory flushed")
    except Exception as e:
        logger.error(f"Memory flush failed: {e}")

    # 2. Save session
    try:
        from memory.session_manager import session_manager
        session_manager.save_all()
        logger.info("Sessions saved")
    except Exception as e:
        logger.error(f"Session save failed: {e}")

    # 3. Save reminder state
    try:
        from memory.reminder_engine import reminder_engine
        reminder_engine.save()
        logger.info("Reminders saved")
    except Exception as e:
        logger.error(f"Reminder save failed: {e}")

    # 4. Stop event bus
    try:
        from core.event_bus import event_bus
        event_bus.stop()
        logger.info("Event bus stopped")
    except Exception as e:
        logger.error(f"Event bus stop failed: {e}")

    # 5. Release process lock
    try:
        from system.process_lock import release_lock
        release_lock()
    except Exception as e:
        logger.error(f"Lock release failed: {e}")

    # 6. Quit Qt application
    try:
        from PyQt6.QtWidgets import QApplication
        app = QApplication.instance()
        if app:
            app.quit()
            logger.info("QApplication quit")
    except Exception as e:
        logger.error(f"App quit failed: {e}")

    logger.info("=== SHUTDOWN COMPLETE ===")


def emergency_kill():
    """Force-kill the process immediately. Last resort only."""
    logger.warning("EMERGENCY KILL triggered")
    try:
        from system.process_lock import release_lock
        release_lock()
    except Exception:
        pass
    os._exit(1)


def is_shutting_down() -> bool:
    """Check if shutdown is in progress."""
    return _shutting_down
