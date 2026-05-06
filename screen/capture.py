"""
Screen Capture — On-demand screenshot of the active window.

IMPORTANT: This module ONLY captures when explicitly called by user action.
NO passive monitoring. NO background capture. NO surveillance.
"""

import logging
import tempfile
from pathlib import Path

logger = logging.getLogger("presence.screen.capture")


def capture_active_window() -> str:
    """
    Capture a screenshot of the currently active window.

    Returns the path to the saved screenshot file.
    """
    try:
        import mss
        import mss.tools

        with mss.mss() as sct:
            # Capture the primary monitor (full screen)
            # In Phase 2, we can use win32gui to get the active window rect
            monitor = sct.monitors[1]  # Primary monitor
            screenshot = sct.grab(monitor)

            # Save to temp file
            tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
            mss.tools.to_png(screenshot.rgb, screenshot.size, output=tmp.name)
            logger.info(f"Screen captured: {tmp.name}")
            return tmp.name

    except ImportError:
        logger.warning("mss not installed — using Pillow fallback")
        return _capture_pillow()
    except Exception as e:
        logger.error(f"Screen capture failed: {e}")
        return ""


def _capture_pillow() -> str:
    """Fallback screen capture using Pillow."""
    try:
        from PIL import ImageGrab
        img = ImageGrab.grab()
        tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
        img.save(tmp.name)
        logger.info(f"Screen captured (Pillow): {tmp.name}")
        return tmp.name
    except Exception as e:
        logger.error(f"Pillow capture failed: {e}")
        return ""


def capture_region(x: int, y: int, width: int, height: int) -> str:
    """Capture a specific screen region."""
    try:
        import mss
        import mss.tools

        with mss.mss() as sct:
            region = {"left": x, "top": y, "width": width, "height": height}
            screenshot = sct.grab(region)
            tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
            mss.tools.to_png(screenshot.rgb, screenshot.size, output=tmp.name)
            return tmp.name
    except Exception as e:
        logger.error(f"Region capture failed: {e}")
        return ""