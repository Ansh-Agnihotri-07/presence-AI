"""
Local AI Engine — Ollama integration.

Connects to a locally running Ollama instance via its OpenAI-compatible API.
Supports LLaMA 3, Mistral, Phi-3. Auto-detects availability.
"""

import logging
from typing import Any, Optional

logger = logging.getLogger("presence.ai.local_engine")

_client: Optional[Any] = None
_available: Optional[bool] = None


async def probe_local() -> bool:
    """Check if Ollama is running and reachable."""
    global _available
    try:
        import httpx
        async with httpx.AsyncClient(timeout=3.0) as client:
            resp = await client.get("http://localhost:11434/api/tags")
            if resp.status_code == 200:
                models = resp.json().get("models", [])
                names = [m.get("name", "") for m in models]
                logger.info(f"Ollama detected — models available: {names}")
                _available = True
                return True
    except Exception as e:
        logger.info(f"Ollama not available: {e}")
    _available = False
    return False


def is_available() -> bool:
    """Return cached availability status."""
    return _available is True


def _get_client(host: str = "http://localhost:11434"):
    """Get or create the OpenAI-compatible client for Ollama."""
    global _client
    if _client is None:
        from openai import AsyncOpenAI
        _client = AsyncOpenAI(
            base_url=f"{host}/v1",
            api_key="ollama",  # Ollama doesn't need a real key
        )
    return _client


async def chat(
    system_prompt: str,
    user_message: str,
    context: str = "",
    model: str = "llama3:8b",
    temperature: float = 0.7,
    max_tokens: int = 1024,
    host: str = "http://localhost:11434",
) -> dict[str, Any]:
    """
    Send a chat completion request to the local Ollama instance.

    Returns {"text": str, "model": str, "mode": "local", "tokens": int}.
    """
    client = _get_client(host)

    messages: list[dict[str, str]] = [{"role": "system", "content": system_prompt}]
    if context:
        messages.append({
            "role": "system",
            "content": f"[Context]\n{context}",
        })
    messages.append({"role": "user", "content": user_message})

    logger.info(f"LOCAL REQUEST → model={model}")

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

        logger.info(f"LOCAL RESPONSE ← model={model}, tokens={tokens}")
        return {
            "text": text,
            "model": model,
            "mode": "local",
            "tokens": tokens,
        }

    except Exception as e:
        logger.error(f"Local AI error: {e}")
        raise
