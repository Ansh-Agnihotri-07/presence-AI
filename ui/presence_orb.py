"""
Presence Orb — Volumetric living entity (Phase 2.0).

Not a widget. Not a button. A spatial presence — ambient intelligence
made visual. Responds to system state, mouse proximity, and cognitive load.

Rendering layers (inside → out):
  1. Inner core light
  2. Core orb with gradient
  3. Mid halo ring
  4. Outer ambient glow
  5. Micro-particles
  6. Focus aura
  7. Parallax depth (mouse-based core shift)

Delta-time animation, 30fps cap, no fixed phase increments.
8 unique visual states: IDLE, LISTENING, THINKING, FOCUSED,
OBSERVING, DORMANT, REMINDER, ERROR.
"""

import math
import random
import time
import logging
from typing import Optional

from PyQt6.QtCore import (
    Qt, QTimer, QPropertyAnimation, QEasingCurve,
    pyqtProperty, QElapsedTimer, QPoint,
)
from PyQt6.QtGui import QPainter, QColor, QRadialGradient, QPen, QCursor
from PyQt6.QtWidgets import QWidget, QApplication

logger = logging.getLogger("presence.ui.orb")


# ═════════════════════════════════════════════
# ── Visual state palette (8 unique states)
# ═════════════════════════════════════════════

STATE_VISUALS = {
    "idle": {
        "core": "#7c6ef0", "glow": "#b8b0ff", "ring": "#6558cc", "inner": "#a090ff",
        "breath_amp": 0.035, "breath_freq": 1.0,
        "glow_alpha": 40, "particle_speed": 0.3, "particle_count": 8,
        "halo_pulse": False, "ring_expand": False,
    },
    "listening": {
        "core": "#4fc3f7", "glow": "#81d4fa", "ring": "#0288d1", "inner": "#b3e5fc",
        "breath_amp": 0.05, "breath_freq": 1.5,
        "glow_alpha": 65, "particle_speed": 0.6, "particle_count": 12,
        "halo_pulse": True, "ring_expand": True,
    },
    "thinking": {
        "core": "#ffa726", "glow": "#ffcc80", "ring": "#ef6c00", "inner": "#ffe0b2",
        "breath_amp": 0.06, "breath_freq": 2.0,
        "glow_alpha": 75, "particle_speed": 1.2, "particle_count": 16,
        "halo_pulse": False, "ring_expand": False,
    },
    "focused": {
        "core": "#e040fb", "glow": "#ea80fc", "ring": "#aa00ff", "inner": "#f3e5f5",
        "breath_amp": 0.02, "breath_freq": 0.6,
        "glow_alpha": 85, "particle_speed": 0.15, "particle_count": 6,
        "halo_pulse": True, "ring_expand": False,
    },
    "observing": {
        "core": "#26c6da", "glow": "#80deea", "ring": "#00838f", "inner": "#b2ebf2",
        "breath_amp": 0.04, "breath_freq": 1.2,
        "glow_alpha": 55, "particle_speed": 0.5, "particle_count": 10,
        "halo_pulse": False, "ring_expand": True,
    },
    "dormant": {
        "core": "#546e7a", "glow": "#78909c", "ring": "#37474f", "inner": "#90a4ae",
        "breath_amp": 0.012, "breath_freq": 0.3,
        "glow_alpha": 15, "particle_speed": 0.08, "particle_count": 3,
        "halo_pulse": False, "ring_expand": False,
    },
    "reminder": {
        "core": "#ffab40", "glow": "#ffd180", "ring": "#ff6d00", "inner": "#fff3e0",
        "breath_amp": 0.07, "breath_freq": 3.0,
        "glow_alpha": 90, "particle_speed": 1.5, "particle_count": 14,
        "halo_pulse": True, "ring_expand": False,
    },
    "error": {
        "core": "#ef5350", "glow": "#ef9a9a", "ring": "#c62828", "inner": "#ffcdd2",
        "breath_amp": 0.04, "breath_freq": 2.5,
        "glow_alpha": 80, "particle_speed": 0.9, "particle_count": 10,
        "halo_pulse": True, "ring_expand": False,
    },
}


# ═════════════════════════════════════════════
# ── Micro-particle
# ═════════════════════════════════════════════

class Particle:
    __slots__ = ("angle", "radius", "speed", "size", "alpha", "drift")

    def __init__(self, base_radius: float):
        self.angle = random.uniform(0, 2 * math.pi)
        self.radius = base_radius * random.uniform(0.4, 1.3)
        self.speed = random.uniform(0.2, 1.0)
        self.size = random.uniform(1.5, 3.5)
        self.alpha = random.randint(40, 120)
        self.drift = random.uniform(-0.02, 0.02)

    def update(self, dt: float, speed_mult: float):
        self.angle += self.speed * speed_mult * dt
        self.radius += self.drift * dt * 60
        if self.angle > 2 * math.pi:
            self.angle -= 2 * math.pi


# ═════════════════════════════════════════════
# ── Presence Orb
# ═════════════════════════════════════════════

class PresenceOrb(QWidget):
    """Volumetric living orb — ambient intelligence made visual."""

    def __init__(self, size: int = 80, parent=None):
        super().__init__(parent)
        self._size = size
        self._state = "idle"
        self._phase = 0.0
        self._ring_radius = 0.0
        self._input_overlay = None
        self._workspace_panel = None

        # Delta-time animation
        self._clock = QElapsedTimer()
        self._clock.start()
        self._last_frame = self._clock.elapsed() / 1000.0

        # Parallax (mouse-based depth)
        self._parallax_x = 0.0
        self._parallax_y = 0.0
        self.setMouseTracking(True)

        # Micro-particles
        self._particles: list[Particle] = []
        self._init_particles()

        # Frameless, transparent, always-on-top
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(size + 80, size + 80)  # room for glow + particles

        # Position: bottom-right
        screen = QApplication.primaryScreen().geometry()
        self.move(screen.width() - self.width() - 30, screen.height() - self.height() - 80)

        # Animation timer — 30fps cap
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(33)  # ~30fps

        # Ring animation
        self._ring_anim = QPropertyAnimation(self, b"ring_radius")
        self._ring_anim.setDuration(1400)
        self._ring_anim.setStartValue(0.0)
        self._ring_anim.setEndValue(float(size * 1.2))
        self._ring_anim.setEasingCurve(QEasingCurve.Type.OutQuad)
        self._ring_anim.setLoopCount(-1)

        # Edge snap threshold
        self._snap_threshold = 20
        self._drag_pos = None

        logger.info(f"Orb 2.0 created — size={size}, state=idle")

    def _init_particles(self):
        """Generate initial particle field."""
        count = STATE_VISUALS[self._state]["particle_count"]
        self._particles = [Particle(self._size / 2) for _ in range(count)]

    # ── Properties ──

    def get_ring_radius(self):
        return self._ring_radius

    def set_ring_radius(self, val):
        self._ring_radius = val

    ring_radius = pyqtProperty(float, fget=get_ring_radius, fset=set_ring_radius)

    # ── State management ──

    def set_state(self, state: str):
        if state not in STATE_VISUALS:
            return
        prev = self._state
        self._state = state
        logger.debug(f"Orb state: {prev} → {state}")

        # Rebuild particles for new count
        target = STATE_VISUALS[state]["particle_count"]
        while len(self._particles) < target:
            self._particles.append(Particle(self._size / 2))
        while len(self._particles) > target:
            self._particles.pop()

        # Ring animation
        vis = STATE_VISUALS[state]
        if vis["ring_expand"] and self._ring_anim.state() != QPropertyAnimation.State.Running:
            self._ring_anim.start()
        elif not vis["ring_expand"]:
            self._ring_anim.stop()
            self._ring_radius = 0.0

    def get_state(self) -> str:
        return self._state

    # ── Delta-time tick ──

    def _tick(self):
        now = self._clock.elapsed() / 1000.0
        dt = now - self._last_frame
        self._last_frame = now

        # Clamp delta to avoid jumps
        dt = min(dt, 0.1)

        vis = STATE_VISUALS[self._state]

        # Advance phase using delta-time (not fixed increment)
        self._phase += dt * vis["breath_freq"] * 2.0
        if self._phase > 2 * math.pi * 100:
            self._phase -= 2 * math.pi * 100

        # Update parallax from mouse position
        self._update_parallax()

        # Update particles
        for p in self._particles:
            p.update(dt, vis["particle_speed"])

        self.update()

    def _update_parallax(self):
        """Calculate core offset based on mouse cursor position."""
        try:
            cursor = QCursor.pos()
            orb_center = self.mapToGlobal(QPoint(self.width() // 2, self.height() // 2))
            dx = cursor.x() - orb_center.x()
            dy = cursor.y() - orb_center.y()
            dist = math.sqrt(dx * dx + dy * dy)
            max_shift = 4.0
            if dist > 0 and dist < 500:
                factor = max_shift / max(dist, 50)
                self._parallax_x = dx * factor
                self._parallax_y = dy * factor
            else:
                self._parallax_x *= 0.9
                self._parallax_y *= 0.9
        except Exception:
            pass

    # ═════════════════════════════════════════════
    # ── Painting
    # ═════════════════════════════════════════════

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        cx = self.width() / 2
        cy = self.height() / 2
        vis = STATE_VISUALS[self._state]

        # Breathing scale
        breath = math.sin(self._phase)
        scale = 1.0 + vis["breath_amp"] * breath
        r = (self._size / 2) * scale

        # Parallax-shifted center
        pcx = cx + self._parallax_x
        pcy = cy + self._parallax_y

        # ── Layer 1: Outer ambient glow ──
        glow_alpha = vis["glow_alpha"]
        glow_pulse = int(12 * math.sin(self._phase * 0.6))
        glow_alpha = max(5, min(100, glow_alpha + glow_pulse))
        glow_size = r + 30

        glow = QRadialGradient(cx, cy, glow_size)
        gc = QColor(vis["glow"])
        gc.setAlpha(glow_alpha)
        glow.setColorAt(0.0, gc)
        glow.setColorAt(0.4, QColor(gc.red(), gc.green(), gc.blue(), glow_alpha // 2))
        glow.setColorAt(0.75, QColor(gc.red(), gc.green(), gc.blue(), glow_alpha // 5))
        glow.setColorAt(1.0, QColor(0, 0, 0, 0))
        painter.setBrush(glow)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(
            int(cx - glow_size), int(cy - glow_size),
            int(glow_size * 2), int(glow_size * 2),
        )

        # ── Layer 2: Halo ring (pulsing states) ──
        if vis["halo_pulse"]:
            halo_r = r + 14 + 4 * math.sin(self._phase * 0.45)
            halo_c = QColor(vis["ring"])
            halo_c.setAlpha(35 + int(15 * math.sin(self._phase * 0.3)))
            painter.setPen(QPen(halo_c, 2.0))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawEllipse(
                int(cx - halo_r), int(cy - halo_r),
                int(halo_r * 2), int(halo_r * 2),
            )

        # ── Layer 3: Expanding ring (listening/observing) ──
        if vis["ring_expand"] and self._ring_radius > 0:
            ring_c = QColor(vis["ring"])
            alpha = max(0, int(120 * (1.0 - self._ring_radius / (self._size * 1.2))))
            ring_c.setAlpha(alpha)
            painter.setPen(QPen(ring_c, 2))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            rr = self._ring_radius
            painter.drawEllipse(
                int(cx - rr), int(cy - rr), int(rr * 2), int(rr * 2),
            )

        # ── Layer 4: Core orb (depth gradient + parallax shift) ──
        grad = QRadialGradient(pcx - r * 0.25, pcy - r * 0.25, r * 1.4)
        core_c = QColor(vis["core"])
        ring_c = QColor(vis["ring"])

        if self._state == "dormant":
            core_c.setAlpha(150)
            ring_c.setAlpha(130)

        grad.setColorAt(0.0, QColor(vis["inner"]))
        grad.setColorAt(0.3, core_c)
        grad.setColorAt(1.0, ring_c)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(grad)
        painter.drawEllipse(int(pcx - r), int(pcy - r), int(r * 2), int(r * 2))

        # ── Layer 5: Inner core light ──
        inner_r = r * 0.35
        inner_alpha = 60 + int(30 * math.sin(self._phase * 1.5))
        inner_grad = QRadialGradient(pcx, pcy, inner_r)
        inner_c = QColor(vis["inner"])
        inner_c.setAlpha(inner_alpha)
        inner_grad.setColorAt(0.0, inner_c)
        inner_grad.setColorAt(1.0, QColor(0, 0, 0, 0))
        painter.setBrush(inner_grad)
        painter.drawEllipse(
            int(pcx - inner_r), int(pcy - inner_r),
            int(inner_r * 2), int(inner_r * 2),
        )

        # ── Layer 6: Micro-particles ──
        particle_c = QColor(vis["glow"])
        for p in self._particles:
            px = pcx + p.radius * math.cos(p.angle)
            py = pcy + p.radius * math.sin(p.angle)
            particle_c.setAlpha(p.alpha)
            painter.setBrush(particle_c)
            painter.setPen(Qt.PenStyle.NoPen)
            s = p.size
            painter.drawEllipse(int(px - s / 2), int(py - s / 2), int(s), int(s))

        # ── Layer 7: Thinking spinner dots ──
        if self._state == "thinking":
            for i in range(3):
                angle = self._phase * 2.5 + (i * 2 * math.pi / 3)
                dx = pcx + (r * 0.55) * math.cos(angle)
                dy = pcy + (r * 0.55) * math.sin(angle)
                dot_c = QColor(vis["glow"])
                dot_c.setAlpha(140)
                painter.setBrush(dot_c)
                painter.drawEllipse(int(dx - 3), int(dy - 3), 6, 6)

        # ── Layer 8: Error pulse ring ──
        if self._state == "error":
            pulse_r = r + 8 + 6 * abs(math.sin(self._phase * 2))
            err_c = QColor(vis["core"])
            err_c.setAlpha(50)
            painter.setPen(QPen(err_c, 3))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawEllipse(
                int(cx - pulse_r), int(cy - pulse_r),
                int(pulse_r * 2), int(pulse_r * 2),
            )

        painter.end()

    # ═════════════════════════════════════════════
    # ── Interaction
    # ═════════════════════════════════════════════

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.pos()
        elif event.button() == Qt.MouseButton.RightButton:
            self._toggle_input()
        elif event.button() == Qt.MouseButton.MiddleButton:
            self._toggle_workspace()

    def mouseMoveEvent(self, event):
        if self._drag_pos and event.buttons() & Qt.MouseButton.LeftButton:
            new_pos = event.globalPosition().toPoint() - self._drag_pos
            self.move(new_pos)

    def mouseReleaseEvent(self, event):
        if self._drag_pos:
            self._drag_pos = None
            self._snap_to_edge()

    def mouseDoubleClickEvent(self, event):
        self._toggle_workspace()

    def _snap_to_edge(self):
        """Snap orb to nearest screen edge if close enough."""
        screen = QApplication.primaryScreen().geometry()
        pos = self.pos()
        x, y = pos.x(), pos.y()

        if x < self._snap_threshold:
            x = 0
        elif x + self.width() > screen.width() - self._snap_threshold:
            x = screen.width() - self.width()

        if y < self._snap_threshold:
            y = 0
        elif y + self.height() > screen.height() - self._snap_threshold:
            y = screen.height() - self.height()

        self.move(x, y)

    def _toggle_input(self):
        if self._input_overlay:
            if self._input_overlay.isVisible():
                self._input_overlay.hide()
            else:
                self._input_overlay.position_near_orb(self)
                self._input_overlay.show()
                self._input_overlay.focus_input()

    def _toggle_workspace(self):
        if self._workspace_panel:
            if self._workspace_panel.isVisible():
                self._workspace_panel.hide()
            else:
                self._workspace_panel.show_workspace()

    def closeEvent(self, event):
        """Orb close -> graceful system shutdown."""
        from system.shutdown_manager import shutdown
        shutdown()
        event.accept()


def create_orb_window(size: int = 80) -> PresenceOrb:
    orb = PresenceOrb(size=size)
    orb.show()
    return orb