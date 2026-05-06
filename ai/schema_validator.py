"""
Schema Validator — Preflight checks to prevent 400 Bad Request API failures.
"""

import logging

logger = logging.getLogger("presence.ai.schema")

# Whitelist of explicitly supported/tested Groq models
GROQ_ALLOWED_MODELS = {
    "llama-3.3-70b-versatile",
    "llama-3.1-8b-instant",
    "llama3-8b-8192",
    "gemma2-9b-it",
    "mixtral-8x7b-32768",
}

def validate_groq_schema(model: str, temperature: float, max_tokens: int) -> tuple[bool, str]:
    """Validate parameters before sending to Groq to prevent 400s."""
    
    if model not in GROQ_ALLOWED_MODELS:
        if not model.startswith("llama") and not model.startswith("gemma") and not model.startswith("mixtral"):
            return False, f"Model {model} is not recognized by Groq registry."
        logger.warning(f"Groq model {model} not in strict whitelist, but matches expected prefix.")

    if not (0.0 <= temperature <= 2.0):
        return False, f"Temperature {temperature} out of bounds [0, 2]"
        
    if max_tokens > 8192 or max_tokens < 1:
        return False, f"max_tokens {max_tokens} out of bounds"
        
    return True, "OK"
