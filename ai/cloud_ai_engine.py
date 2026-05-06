"""
Cloud AI Engine — OpenRouter integration (model-locked, OFF by default).

Refactored from chat/llm_bridge.py. Only activates if explicitly enabled
by the user AND local AI is unavailable.
"""

import logging
from typing import Any, Optional

logger = logging.getLogger("presence.ai.cloud_engine")

_client: Optional[Any] = None


def _get_client(api_key: str, base_url: str):
    """Get or create the AsyncOpenAI client for cloud."""
    global _client
    if _client is None:
        from openai import AsyncOpenAI
        _client = AsyncOpenAI(api_key=api_key, base_url=base_url)
    return _client


async def chat(
    system_prompt: str,
    user_message: str,
    context: str = "",
    model: str = "meta-llama/llama-3.1-8b-instruct:free",
    temperature: float = 0.7,
    max_tokens: int = 1024,
    api_key: str = "",
    base_url: str = "https://openrouter.ai/api/v1",
) -> dict[str, Any]:
    """
    Send a chat completion request to the cloud (OpenRouter).

    The model field is MANDATORY and always sent explicitly.
    No auto-routing; no implicit model selection.

    Returns {"text": str, "model": str, "mode": "cloud", "tokens": int}.
    """
    if not api_key:
        raise ValueError("Cloud AI requires an API key (OPENAI_API_KEY).")

    client = _get_client(api_key, base_url)

    messages: list[dict[str, str]] = [{"role": "system", "content": system_prompt}]
    if context:
        messages.append({
            "role": "system",
            "content": f"[Context]\n{context}",
        })
    messages.append({"role": "user", "content": user_message})

    logger.info(f"[OPENROUTER] Request sent → model={model}")
    logger.info(f"CLOUD REQUEST → model={model} (explicit, no auto-routing)")

    try:
        response = await client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        text = response.choices[0].message.content or ""
        text = text.strip()
        tokens = getattr(response.usage, "total_tokens", 0) if response.usage else 0

        logger.info(f"CLOUD RESPONSE ← model={model}, tokens={tokens}")
        return {
            "text": text,
            "model": model,
            "mode": "cloud",
            "tokens": tokens,
        }

    except Exception as e:
        logger.error(f"Cloud AI error: {e}")
        raise
