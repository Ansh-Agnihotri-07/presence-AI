"""
Presence Input Overlay + Persistent Ambient Responses (Phase 1.7).

NOT a chat UI. NOT a messenger. NOT a chat feed.

Responses are PERSISTENT — they never auto-fade, never auto-delete,
never self-destruct. They persist until the user manually deletes them
via the workspace/session UI. Each response is appended to session history.
"""

import asyncio
import logging
from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QFont, QColor, QPainter
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QLineEdit, QLabel, QFrame, QScrollArea,
)

logger = logging.getLogger("presence.ui.input_overlay")


class AmbientResponse(QFrame):
    """A persistent floating response entry.
    Never fades. Never auto-deletes. Persists until manual removal."""

    def __init__(self, text: str, is_user: bool = False, parent=None):
        super().__init__(parent)
        self.setObjectName("ambient_response")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 10)

        # Role indicator
        role = "You" if is_user else "Presence"
        role_label = QLabel(role)
        role_label.setFont(QFont("Segoe UI", 8))
        role_color = "#9080e0" if not is_user else "#6a9fd8"
        role_label.setStyleSheet(f"color: {role_color}; margin-bottom: 2px;")
        layout.addWidget(role_label)

        # Message text
        self._label = QLabel(text)
        self._label.setWordWrap(True)
        self._label.setFont(QFont("Segoe UI", 10))
        self._label.setStyleSheet("color: #d0d0e8;")
        self._label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self._label)

        bg = "rgba(30, 26, 52, 0.92)" if not is_user else "rgba(35, 40, 55, 0.88)"
        border = "rgba(120, 100, 220, 0.15)" if not is_user else "rgba(100, 160, 220, 0.15)"
        self.setStyleSheet(f"""
            QFrame#ambient_response {{
                background: {bg};
                border-radius: 12px;
                border: 1px solid {border};
                margin: 2px 0px;
            }}
        """)


class PresenceInputOverlay(QWidget):
    """Minimal presence input + persistent response history.
    Appears on demand. Responses never disappear."""

    message_sent = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_window()
        self._build_ui()
        self._connect_signals()
        logger.info("Presence input overlay created")

    def _setup_window(self):
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(400, 420)

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)

        # Wrapper with background
        wrapper = QFrame(self)
        wrapper.setObjectName("overlayWrapper")
        wrapper.setStyleSheet("""
            QFrame#overlayWrapper {
                background: rgba(14, 12, 28, 0.93);
                border-radius: 18px;
                border: 1px solid rgba(120, 100, 220, 0.18);
            }
        """)
        layout = QVBoxLayout(wrapper)
        layout.setContentsMargins(8, 10, 8, 8)
        layout.setSpacing(4)

        # Header
        header = QLabel("Presence")
        header.setFont(QFont("Segoe UI", 11, QFont.Weight.DemiBold))
        header.setStyleSheet("color: #9080e0; padding-left: 6px; margin-bottom: 2px;")
        layout.addWidget(header)

        # Scrollable response area
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll.setStyleSheet("""
            QScrollArea { background: transparent; border: none; }
            QScrollBar:vertical {
                background: rgba(30,30,50,0.3); width: 5px; border-radius: 2px;
            }
            QScrollBar::handle:vertical {
                background: rgba(120,100,220,0.4); border-radius: 2px; min-height: 25px;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
        """)

        self._messages_widget = QWidget()
        self._messages_layout = QVBoxLayout(self._messages_widget)
        self._messages_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self._messages_layout.setSpacing(4)
        self._messages_layout.setContentsMargins(2, 2, 2, 2)

        self._scroll.setWidget(self._messages_widget)
        layout.addWidget(self._scroll, stretch=1)

        # Input line
        self._input = QLineEdit()
        self._input.setPlaceholderText("speak to presence…")
        self._input.setFont(QFont("Segoe UI", 10))
        self._input.setStyleSheet("""
            QLineEdit {
                background: rgba(40, 40, 60, 0.6);
                color: #e0e0e0;
                border: none;
                border-radius: 16px;
                padding: 8px 18px;
            }
            QLineEdit:focus {
                background: rgba(50, 50, 70, 0.7);
                border: 1px solid rgba(120, 100, 220, 0.3);
            }
        """)
        layout.addWidget(self._input)

        root.addWidget(wrapper)

    def _connect_signals(self):
        self._input.returnPressed.connect(self._on_send)

    def _on_send(self):
        text = self._input.text().strip()
        if not text:
            return
        self._input.clear()
        self.add_message(text, is_user=True)
        self.message_sent.emit(text)

    # ── Public API ──

    def add_message(self, text: str, is_user: bool = False):
        """Add a persistent message entry. Never auto-deletes."""
        entry = AmbientResponse(text, is_user=is_user, parent=self._messages_widget)
        self._messages_layout.addWidget(entry)
        # Scroll to bottom
        QTimer.singleShot(50, lambda: self._scroll.verticalScrollBar().setValue(
            self._scroll.verticalScrollBar().maximum()
        ))

    def show_response(self, text: str):
        """Show an AI response — persistent, appended to history."""
        self.add_message(text, is_user=False)
        # Auto-show the overlay when a response arrives
        if not self.isVisible():
            self.show()

    def position_near_orb(self, orb):
        """Position the overlay to the left of the orb."""
        orb_pos = orb.pos()
        x = orb_pos.x() - self.width() - 10
        y = orb_pos.y() + orb.height() - self.height()
        if x < 0:
            x = orb_pos.x() + orb.width() + 10
        if y < 0:
            y = 10
        self.move(x, y)

    def focus_input(self):
        self._input.setFocus()
        self.activateWindow()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.hide()
        super().keyPressEvent(event)


def create_input_overlay(orb) -> PresenceInputOverlay:
    """Create the input overlay and wire it to the orb."""
    overlay = PresenceInputOverlay()
    orb._input_overlay = overlay

    async def dispatch_message(text: str):
        from core.event_bus import event_bus
        await event_bus.publish("user_input", {"text": text, "mode": "chat"})

    def on_message_sent(text: str):
        loop = asyncio.get_event_loop()
        asyncio.ensure_future(dispatch_message(text), loop=loop)

    overlay.message_sent.connect(on_message_sent)

    return overlay