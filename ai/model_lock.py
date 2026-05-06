"""
Model Lock — Whitelist of allowed AI models (Phase 2.0).

4-engine whitelist: Local (Ollama) + Groq + Gemini + OpenRouter.
No request is permitted with a model not on this list.
"""

import logging

logger = logging.getLogger("presence.ai.model_lock")

# ── Allowed model whitelist ──

ALLOWED_LOCAL_MODELS: set[str] = {
    "llama3:8b",
    "llama3.1:8b",
    "llama3:latest",
    "mistral:7b",
    "mistral:latest",
    "phi3:mini",
    "phi3:latest",
}

ALLOWED_GROQ_MODELS: set[str] = {
    "llama3-8b-8192",
    "mixtral-8x7b-32768",
    "llama-3.1-8b-instant",
}

ALLOWED_GEMINI_MODELS: set[str] = {
    "gemini-2.0-flash",
    "gemini-1.5-flash",
}

ALLOWED_CLOUD_MODELS: set[str] = {
    "meta-llama/llama-3.1-8b-instruct",
    "meta-llama/llama-3.1-8b-instruct:free",
}

# Combined set for quick lookup
ALL_ALLOWED_MODELS: set[str] = (
    ALLOWED_LOCAL_MODELS | ALLOWED_GROQ_MODELS |
    ALLOWED_GEMINI_MODELS | ALLOWED_CLOUD_MODELS
)


def is_model_allowed(model: str) -> bool:
    """Check if a model is in the allowed whitelist."""
    allowed = model in ALL_ALLOWED_MODELS
    if not allowed:
        logger.warning(f"MODEL BLOCKED: '{model}' is not in the allowed whitelist")
    return allowed


def is_local_model(model: str) -> bool:
    return model in ALLOWED_LOCAL_MODELS


def is_groq_model(model: str) -> bool:
    return model in ALLOWED_GROQ_MODELS


def is_gemini_model(model: str) -> bool:
    return model in ALLOWED_GEMINI_MODELS


def is_cloud_model(model: str) -> bool:
    return model in ALLOWED_CLOUD_MODELS


def get_default_local_model() -> str:
    return "llama3:8b"


def get_default_groq_model() -> str:
    return "llama3-8b-8192"


def get_default_gemini_model() -> str:
    return "gemini-2.0-flash"


def get_default_cloud_model() -> str:
    return "meta-llama/llama-3.1-8b-instruct:free"
