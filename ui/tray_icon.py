"""
Tray Icon — System tray icon with shutdown-aware quit (Phase 2.1).
"""

import logging
from PyQt6.QtWidgets import QSystemTrayIcon, QMenu
from PyQt6.QtGui import QIcon, QPixmap, QPainter, QColor, QRadialGradient
from system.shutdown_manager import shutdown

logger = logging.getLogger("presence.ui.tray_icon")


def _generate_icon() -> QIcon:
    """Generate a small orb icon programmatically."""
    size = 64
    pix = QPixmap(size, size)
    pix.fill(QColor(0, 0, 0, 0))
    painter = QPainter(pix)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    grad = QRadialGradient(size / 2, size / 2, size / 2)
    grad.setColorAt(0.0, QColor("#7c6ef0"))
    grad.setColorAt(1.0, QColor("#5c4db7"))
    painter.setBrush(grad)
    painter.setPen(QColor(0, 0, 0, 0))
    painter.drawEllipse(4, 4, size - 8, size - 8)
    painter.end()
    return QIcon(pix)


def create_tray_icon(app, orb) -> QSystemTrayIcon:
    """Create the system tray icon with a context menu."""
    tray = QSystemTrayIcon(_generate_icon(), app)
    tray.setToolTip("Presence AI")

    menu = QMenu()
    menu.setStyleSheet("""
        QMenu {
            background: #1a1a2e; color: #d0d0d0;
            border: 1px solid #333; border-radius: 8px;
            padding: 4px;
        }
        QMenu::item { padding: 6px 24px; }
        QMenu::item:selected { background: #5c4db7; border-radius: 4px; }
    """)

    show_action = menu.addAction("Show Orb")
    show_action.triggered.connect(orb.show)

    workspace_action = menu.addAction("Open Workspace")
    workspace_action.triggered.connect(lambda: orb._toggle_workspace())

    menu.addSeparator()

    quit_action = menu.addAction("Quit Presence")
    quit_action.triggered.connect(shutdown)  # graceful shutdown, not raw app.quit()

    tray.setContextMenu(menu)
    tray.activated.connect(lambda reason: orb._toggle_workspace()
                           if reason == QSystemTrayIcon.ActivationReason.DoubleClick
                           else None)
    tray.show()
    logger.info("Tray icon created")
    return tray