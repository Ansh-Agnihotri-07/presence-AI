"""
Groq Engine — Groq API integration for speed-optimized inference.

Uses Groq's OpenAI-compatible API for ultra-fast LLM calls.
Models: llama-3.1-8b-instant, mixtral-8x7b-32768.
"""

import logging
from typing import Any

logger = logging.getLogger("presence.ai.groq_engine")

GROQ_API_BASE = "https://api.groq.com/openai/v1"


async def probe_groq(api_key: str, timeout: float = 1.5) -> bool:
    """Check if Groq API is reachable and key is valid."""
    if not api_key or api_key.startswith("PASTE"):
        return False
    try:
        import httpx
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.get(
                f"{GROQ_API_BASE}/models",
                headers={"Authorization": f"Bearer {api_key}"},
            )
            available = resp.status_code == 200
            if available:
                logger.info("✓ Groq API AVAILABLE")
            return available
    except Exception as e:
        logger.debug(f"Groq probe failed: {e}")
        return False


async def chat(
    system_prompt: str,
    user_message: str,
    context: str = "",
    model: str = "llama-3.1-8b-instant",
    temperature: float = 0.7,
    max_tokens: int = 1024,
    api_key: str = "",
) -> dict[str, Any]:
    """
    Send a chat completion request to Groq API.

    Returns: {"text": str, "model": str, "mode": "groq", "tokens": int}
    """
    import httpx
    import time

    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    if context:
        messages.append({"role": "system", "content": f"Context:\n{context}"})
    messages.append({"role": "user", "content": user_message})

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }

    start = time.monotonic()
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            f"{GROQ_API_BASE}/chat/completions",
            headers=headers,
            json=payload,
        )
        resp.raise_for_status()
        data = resp.json()

    latency = time.monotonic() - start
    text = data["choices"][0]["message"]["content"]
    tokens = data.get("usage", {}).get("total_tokens", 0)

    logger.info(f"GROQ RESPONSE ← model={model}, tokens={tokens}, latency={latency:.2f}s")

    return {
        "text": text,
        "model": model,
        "mode": "groq",
        "tokens": tokens,
        "latency": latency,
    }


if __name__ == "__main__":
    import asyncio
    import os
    import httpx
    from dotenv import load_dotenv

    async def test_groq():
        load_dotenv()
        api_key = os.getenv("GROQ_API_KEY")
        if not api_key:
            print("No GROQ_API_KEY found in .env")
            return

        print("Testing Groq Engine (llama-3.1-8b-instant)...")
        try:
            res = await chat(
                system_prompt="You are a helpful test assistant.",
                user_message="Respond with 'Hello, Groq is working!'",
                model="llama-3.1-8b-instant",
                api_key=api_key,
            )
            print("\nResponse Match:")
            print(res)
        except httpx.HTTPStatusError as e:
            print(f"HTTP Error {e.response.status_code}")
            print(e.response.text)
        except Exception as e:
            print(f"Error testing Groq: {e}")

    asyncio.run(test_groq())
