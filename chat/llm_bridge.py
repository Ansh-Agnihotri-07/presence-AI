"""
LLM Bridge — Interface to the language model backend.

Supports OpenAI API (primary) with a local fallback stub.
All agents call through this single interface.
"""

import logging
from typing import Optional
from openai import AsyncOpenAI
from core.config import config

logger = logging.getLogger("presence.chat.llm_bridge")

# Initialize client
_client: Optional[AsyncOpenAI] = None


def _get_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        if config.OPENAI_API_KEY:
            kwargs = {"api_key": config.OPENAI_API_KEY}
            if config.OPENAI_API_BASE:
                kwargs["base_url"] = config.OPENAI_API_BASE
            _client = AsyncOpenAI(**kwargs)
        else:
            logger.warning("No OpenAI API key — using local fallback")
    return _client


async def call_llm(
    system_prompt: str,
    user_message: str,
    context: str = "",
    model: str | None = None,
    temperature: float | None = None,
    max_tokens: int | None = None,
) -> str:
    """
    Call the LLM with a system prompt, user message, and optional context.

    Returns the assistant's response text.
    """
    model = model or config.LLM_MODEL
    temperature = temperature if temperature is not None else config.LLM_TEMPERATURE
    max_tokens = max_tokens or config.LLM_MAX_TOKENS

    # Build messages
    messages = [{"role": "system", "content": system_prompt}]
    if context:
        messages.append({
            "role": "system",
            "content": f"[Context for this conversation]\n{context}",
        })
    messages.append({"role": "user", "content": user_message})

    client = _get_client()

    if client is None:
        # Local fallback — no API key configured
        return _local_fallback(user_message)

    try:
        response = await client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        text = response.choices[0].message.content.strip()
        logger.debug(f"LLM response ({model}): {text[:80]}...")
        return text

    except Exception as e:
        logger.error(f"LLM call failed: {e}", exc_info=True)
        return _local_fallback(user_message)


def _local_fallback(user_message: str) -> str:
    """Minimal fallback when no LLM is available."""
    return (
        "I'm running in offline mode right now, so my responses are limited. "
        "To unlock full capabilities, add your OpenAI API key to the .env file. "
        f"I heard you say: \"{user_message[:100]}\" — I'll be more helpful once connected."
    )