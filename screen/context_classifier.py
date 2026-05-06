"""
Context Classifier — Detect the type of active window/application.

Uses the active window title to classify what the user is looking at
(browser, PDF, code editor, video player, document, etc.).
"""

import logging
import re

logger = logging.getLogger("presence.screen.context_classifier")

# Window title patterns → context type
PATTERNS = [
    (r"(chrome|firefox|edge|brave|opera|safari|vivaldi)", "browser"),
    (r"\.(pdf)$", "pdf"),
    (r"(visual studio code|vs ?code|code\.exe|pycharm|intellij|sublime|atom|neovim|vim)", "code_editor"),
    (r"(word|docs|libreoffice writer|google docs|\.docx?)", "document"),
    (r"(excel|sheets|\.xlsx?|calc)", "spreadsheet"),
    (r"(powerpoint|slides|\.pptx?|impress)", "presentation"),
    (r"(vlc|mpv|media player|youtube|netflix|prime video|plex)", "video_player"),
    (r"(spotify|music|audacity|soundcloud)", "audio_player"),
    (r"(terminal|cmd|powershell|bash|wt\.exe|windows terminal)", "terminal"),
    (r"(explorer|file manager|files)", "file_manager"),
    (r"(discord|slack|teams|telegram|whatsapp|signal)", "messaging"),
    (r"(outlook|gmail|thunderbird|mail)", "email"),
    (r"(notion|obsidian|onenote|evernote|logseq)", "notes"),
]


def classify_context(window_title: str | None = None) -> str:
    """
    Classify the context type from the active window title.

    If no title is provided, attempts to get the foreground window title.
    """
    if window_title is None:
        window_title = _get_active_window_title()

    if not window_title:
        return "unknown"

    title_lower = window_title.lower()

    for pattern, context_type in PATTERNS:
        if re.search(pattern, title_lower):
            logger.debug(f"Context: '{window_title}' → {context_type}")
            return context_type

    logger.debug(f"Context: '{window_title}' → unknown")
    return "unknown"


def _get_active_window_title() -> str:
    """Get the title of the currently active window (Windows)."""
    try:
        import ctypes
        user32 = getattr(ctypes, "windll").user32
        hwnd = user32.GetForegroundWindow()
        length = user32.GetWindowTextLengthW(hwnd)
        buf = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buf, length + 1)
        return buf.value
    except Exception as e:
        logger.warning(f"Could not get window title: {e}")
        return ""