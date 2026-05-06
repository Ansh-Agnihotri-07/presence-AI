"""
Gemini Engine — Google Gemini API integration for deep reasoning.

Uses the google-generativeai SDK for reasoning, planning, synthesis.
Model: gemini-2.0-flash.
Future-ready for vision integration.
"""

import logging
import time
from typing import Any

logger = logging.getLogger("presence.ai.gemini_engine")

# Track temporal spacing between calls to avoid hard API burst limits
_last_gemini_call = 0.0


async def probe_gemini(api_key: str, timeout: float = 1.5) -> bool:
    """Check if Gemini API key is valid."""
    if not api_key or api_key.startswith("PASTE"):
        return False
    try:
        import httpx
        url = f"https://generativelanguage.googleapis.com/v1beta/models?key={api_key}"
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.get(url)
            available = resp.status_code == 200
            if available:
                logger.info("✓ Gemini API AVAILABLE")
            
            global _last_gemini_call
            _last_gemini_call = time.monotonic()
            
            return available
    except Exception as e:
        logger.debug(f"Gemini probe failed: {e}")
        return False


async def chat(
    system_prompt: str,
    user_message: str,
    context: str = "",
    model: str = "gemini-2.0-flash",
    temperature: float = 0.7,
    max_tokens: int = 1024,
    api_key: str = "",
) -> dict[str, Any]:
    """
    Send a request to Gemini API via REST.

    Returns: {"text": str, "model": str, "mode": "gemini", "tokens": int, "latency": float}
    """
    import httpx

    # Build the prompt parts
    parts = []
    if system_prompt:
        parts.append({"text": f"System: {system_prompt}"})
    if context:
        parts.append({"text": f"Context:\n{context}"})
    parts.append({"text": user_message})

    payload = {
        "contents": [{"parts": parts}],
        "generationConfig": {
            "temperature": temperature,
            "maxOutputTokens": max_tokens,
        },
    }

    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{model}:generateContent?key={api_key}"
    )

    global _last_gemini_call
    start = time.monotonic()
    
    # ── Strict 2.0s Minimum Temporal Gap ──
    elapsed_since_last = start - _last_gemini_call
    if elapsed_since_last < 2.0:
        sleep_time = 2.0 - elapsed_since_last
        logger.debug(f"Throttling Gemini call by {sleep_time:.2f}s")
        import asyncio
        await asyncio.sleep(sleep_time)

    # ── Exponential Backoff Loop ──
    max_retries = 3
    base_delay = 2.0
    
    for attempt in range(max_retries + 1):
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                resp = await client.post(url, json=payload)
                resp.raise_for_status()
                data = resp.json()
                _last_gemini_call = time.monotonic()  # Mark precise success time
                break # Success
                
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 429 and attempt < max_retries:
                delay = base_delay * (2 ** attempt)
                logger.warning(f"GEMINI 429 Rate Limit hit. Retrying in {delay}s... (Attempt {attempt+1}/{max_retries})")
                import asyncio
                await asyncio.sleep(delay)
                continue
            
            _last_gemini_call = time.monotonic() # Advance clock even on failure
            raise # Re-raise if retries exhausted or not a 429 error
        except Exception:
            _last_gemini_call = time.monotonic()
            raise

    latency = time.monotonic() - start

    # Extract response text
    try:
        text = data["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError):
        text = "Gemini returned an empty response."

    # Extract token counts
    usage = data.get("usageMetadata", {})
    tokens = usage.get("totalTokenCount", 0)

    logger.info(f"GEMINI RESPONSE ← model={model}, tokens={tokens}, latency={latency:.2f}s")

    return {
        "text": text,
        "model": model,
        "mode": "gemini",
        "tokens": tokens,
        "latency": latency,
    }
