"""
Startup — Boot sequence orchestrator (Phase 2.1).

4-engine autonomous cognitive system with mode-aware routing.
Single-instance lock. Signal handling. Graceful shutdown.
"""

import asyncio
import logging

from core.config import config
from core.event_bus import event_bus
from core.logger import setup_logging

logger = logging.getLogger("presence.core.startup")


async def boot_headless():
    """Boot all non-UI systems."""
    config.ensure_dirs()

    # ── Memory ──
    from memory.store import memory_store
    memory_store.load_all()
    logger.info("Memory store loaded")

    from memory.session_manager import session_manager
    session_manager.load_all()
    logger.info("Session manager loaded")

    from memory.memory_index import memory_index
    memory_index.load()
    logger.info("Memory index loaded")

    from memory.reminder_engine import reminder_engine
    reminder_engine.load()
    logger.info("Reminder engine loaded")

    # ── AI Router (4-engine parallel probe) ──
    from ai.ai_router import init_router
    await init_router()
    logger.info("AI router 2.0 initialized (autonomous)")

    # ── Event Bus ──
    await event_bus.start()
    logger.info("Event bus started")

    # ── Agents ──
    from agents.orchestrator import orchestrator
    orchestrator.register_all()
    logger.info("Agents registered")

    # ── Scheduler ──
    from scheduler.follow_up import start_scheduler
    asyncio.create_task(start_scheduler(event_bus))
    logger.info("Scheduler started")

    # ── Reminder loop ──
    asyncio.create_task(reminder_engine.start_check_loop(event_bus, interval=30))
    logger.info("Reminder check loop started")

    # ── Boot event ──
    await event_bus.publish("system_ready", {})


def run():
    """Full boot: headless + UI (blocking)."""
    setup_logging()
    logger.info("═══ Presence AI — Phase 2.1 Booting ═══")

    import qasync
    from PyQt6.QtWidgets import QApplication
    from ui.presence_orb import create_orb_window
    from ui.tray_icon import create_tray_icon
    from ui.chat_panel import create_input_overlay
    from workspace.workspace_panel import create_workspace_panel

    app = QApplication([])
    app.setQuitOnLastWindowClosed(False)

    loop = qasync.QEventLoop(app)
    asyncio.set_event_loop(loop)

    # UI components
    orb = create_orb_window()
    tray = create_tray_icon(app, orb)
    overlay = create_input_overlay(orb)
    workspace = create_workspace_panel()  # singleton

    # Wire workspace to orb
    orb._workspace_panel = workspace

    # State engine
    from ui.state_engine import StateEngine
    state_engine = StateEngine(orb)
    state_engine.bind_events(event_bus)

    # Output renderer → overlay + workspace
    from chat.output_renderer import set_input_overlay, set_workspace_panel, register_output_handler
    set_input_overlay(overlay)
    set_workspace_panel(workspace)
    register_output_handler()

    # Boot headless
    loop.run_until_complete(boot_headless())

    # Voice pipeline (optional)
    if config.VOICE_ENABLED:
        from voice.pipeline import voice_pipeline
        loop.run_until_complete(voice_pipeline.start())
        logger.info("Voice pipeline started")

    logger.info("═══ Presence AI — Phase 2.1 Running ═══")

    with loop:
        loop.run_forever()