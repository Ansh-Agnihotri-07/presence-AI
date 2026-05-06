"""
Animation Engine — Centralized visual effect controller.

Drives breathing, pulse, glow, voice wave ring, focus halo,
and all ambient animations from a single engine.
"""

import math
import logging
from typing import Optional

from PyQt6.QtCore import QTimer, QPropertyAnimation, QEasingCurve

logger = logging.getLogger("presence.ui.animation_engine")


class AnimationEngine:
    """Drives all presence orb visual animations."""

    def __init__(self, orb, fps: int = 20):
        self._orb = orb
        self._phase = 0.0
        self._glow_intensity = 0.0
        self._dormant_drift = 0.0

        # Main tick timer
        self._timer = QTimer(orb)
        self._timer.timeout.connect(self._tick)
        self._timer.start(1000 // fps)

        # Ring animation (for listening state)
        self._ring_anim = QPropertyAnimation(orb, b"ring_radius")
        self._ring_anim.setDuration(1200)
        self._ring_anim.setStartValue(0.0)
        self._ring_anim.setEndValue(float(orb._size))
        self._ring_anim.setEasingCurve(QEasingCurve.Type.OutQuad)
        self._ring_anim.setLoopCount(-1)

        logger.info("Animation engine initialized")

    def _tick(self):
        """Main animation tick — updates phase and triggers repaint."""
        self._phase += 0.07
        if self._phase > 2 * math.pi:
            self._phase -= 2 * math.pi

        # Dormant drift (very slow oscillation)
        self._dormant_drift += 0.01
        if self._dormant_drift > 2 * math.pi:
            self._dormant_drift -= 2 * math.pi

        self._orb.update()

    def get_breathing_scale(self, state: str) -> float:
        """Return the current breathing scale factor based on state."""
        if state == "idle":
            return 1.0 + 0.04 * math.sin(self._phase)
        elif state == "listening":
            return 1.0 + 0.05 * math.sin(self._phase * 1.5)
        elif state == "thinking":
            return 1.0 + 0.06 * math.sin(self._phase * 2)
        elif state == "responding":
            return 1.0 + 0.04 * math.sin(self._phase * 1.2)
        elif state == "focused":
            return 1.0 + 0.02 * math.sin(self._phase * 0.8)
        elif state == "dormant":
            return 1.0 + 0.015 * math.sin(self._phase * 0.3)
        elif state == "observing":
            return 1.0 + 0.03 * math.sin(self._phase * 1.1)
        elif state == "active":
            return 1.0 + 0.05 * math.sin(self._phase * 1.8)
        else:
            return 1.0 + 0.03 * math.sin(self._phase)

    def get_glow_alpha(self, state: str) -> int:
        """Return glow alpha based on state — ambient presence effect."""
        base = {
            "idle": 35,
            "listening": 60,
            "thinking": 70,
            "responding": 55,
            "focused": 80,
            "dormant": 15,
            "observing": 50,
            "active": 65,
        }.get(state, 35)

        # Pulsing glow
        pulse = int(15 * math.sin(self._phase * 0.7))
        return max(5, min(100, base + pulse))

    def get_dormant_offset(self) -> tuple[float, float]:
        """Return subtle X/Y drift for dormant state."""
        dx = 2.0 * math.sin(self._dormant_drift)
        dy = 1.5 * math.cos(self._dormant_drift * 0.7)
        return dx, dy

    def start_ring(self):
        """Start the expanding ring animation (listening/voice)."""
        if not self._ring_anim.state():
            self._ring_anim.start()

    def stop_ring(self):
        """Stop the ring animation."""
        self._ring_anim.stop()
        self._orb._ring_radius = 0.0

    @property
    def phase(self) -> float:
        return self._phase
