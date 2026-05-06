"""
Config — Global configuration loader (Phase 2.0).

Autonomous system — all routing is self-deciding.
4-engine configuration: Local + Groq + Gemini + OpenRouter.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_ENV_PATH = _PROJECT_ROOT / ".env"
load_dotenv(_ENV_PATH)


class Config:
    """Centralized configuration for the Presence system."""

    # ── Paths ──
    PROJECT_ROOT: Path = _PROJECT_ROOT
    MEMORY_DIR: Path = _PROJECT_ROOT / "memory" / "data"
    SESSIONS_DIR: Path = _PROJECT_ROOT / "memory" / "data" / "sessions"

    # ── Cost Safety ──
    FREE_MODE: bool = os.getenv("FREE_MODE", "true").lower() == "true"
    ALLOW_PAID_MODELS: bool = os.getenv("ALLOW_PAID_MODELS", "false").lower() == "true"
    MAX_CALLS_PER_DAY: int = int(os.getenv("MAX_CALLS_PER_DAY", "100"))

    # ── Local AI (Ollama) ──
    LOCAL_MODEL: str = os.getenv("LOCAL_MODEL", "llama3:8b")
    OLLAMA_HOST: str = os.getenv("OLLAMA_HOST", "http://localhost:11434")

    # ── Groq ──
    GROQ_API_KEY: str = os.getenv("GROQ_API_KEY", "")
    GROQ_MODEL: str = os.getenv("GROQ_MODEL", "llama-3.1-8b-instant")

    # ── Gemini ──
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
    GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")

    # ── Cloud AI (OpenRouter — legacy fallback) ──
    MODEL_LOCK: str = os.getenv("MODEL_LOCK", "meta-llama/llama-3.1-8b-instruct:free")
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
    OPENAI_API_BASE: str = os.getenv("OPENAI_API_BASE", "https://openrouter.ai/api/v1")

    # ── LLM Defaults ──
    LLM_TEMPERATURE: float = float(os.getenv("LLM_TEMPERATURE", "0.7"))
    LLM_MAX_TOKENS: int = int(os.getenv("LLM_MAX_TOKENS", "1024"))

    # ── Voice ──
    VOICE_ENABLED: bool = os.getenv("VOICE_ENABLED", "false").lower() == "true"
    WHISPER_MODEL: str = os.getenv("WHISPER_MODEL", "base")
    TTS_VOICE: str = os.getenv("TTS_VOICE", "en-US-AriaNeural")

    # ── UI ──
    ORB_SIZE: int = int(os.getenv("ORB_SIZE", "80"))
    ORB_OPACITY: float = float(os.getenv("ORB_OPACITY", "0.85"))
    CHAT_HOTKEY: str = os.getenv("CHAT_HOTKEY", "ctrl+space")

    # ── Scheduler ──
    CHECKIN_INTERVAL_MINUTES: int = int(os.getenv("CHECKIN_INTERVAL_MINUTES", "60"))
    NUDGE_ENABLED: bool = os.getenv("NUDGE_ENABLED", "true").lower() == "true"

    # ── Tesseract ──
    TESSERACT_PATH: str = os.getenv(
        "TESSERACT_PATH",
        r"C:\Program Files\Tesseract-OCR\tesseract.exe"
    )

    # ── Project Builder ──
    BUILDER_PROJECTS_DIR: Path = Path(
        os.getenv("BUILDER_PROJECTS_DIR", str(_PROJECT_ROOT / "projects"))
    ).resolve()
    BUILDER_DRY_RUN: bool = os.getenv("BUILDER_DRY_RUN", "false").lower() == "true"
    BUILDER_MAX_REPAIR_ATTEMPTS: int = int(os.getenv("BUILDER_MAX_REPAIR_ATTEMPTS", "5"))
    BUILDER_COMMAND_TIMEOUT: int = int(os.getenv("BUILDER_COMMAND_TIMEOUT", "120"))

    @classmethod
    def ensure_dirs(cls):
        cls.MEMORY_DIR.mkdir(parents=True, exist_ok=True)
        cls.SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
        cls.BUILDER_PROJECTS_DIR.mkdir(parents=True, exist_ok=True)


config = Config()