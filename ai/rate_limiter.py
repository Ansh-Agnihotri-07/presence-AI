"""
Rate Limiter — API protection and token bucket to prevent 429 Too Many Requests.
"""

import time
import logging
from dataclasses import dataclass

logger = logging.getLogger("presence.ai.ratelimit")

@dataclass
class TokenBucket:
    capacity: int
    fill_rate: float  # tokens per second
    tokens: float
    last_fill: float

class ApiRateLimiter:
    def __init__(self):
        # Gemini Flash free tier has limits: ~15 RPM
        self.buckets = {
            "gemini": TokenBucket(capacity=15, fill_rate=15.0/60.0, tokens=15.0, last_fill=time.monotonic()),
            "groq": TokenBucket(capacity=30, fill_rate=30.0/60.0, tokens=30.0, last_fill=time.monotonic())
        }
        
    def _refill(self, engine: str):
        bucket = self.buckets.get(engine)
        if not bucket: return
        
        now = time.monotonic()
        elapsed = now - bucket.last_fill
        new_tokens = elapsed * bucket.fill_rate
        
        bucket.tokens = min(float(bucket.capacity), bucket.tokens + new_tokens)
        bucket.last_fill = now
        
    def check_and_consume(self, engine: str, tokens_needed: int = 1) -> bool:
        """Check if request can proceed, and consume a token if so. True = OK"""
        if engine not in self.buckets:
            return True # Not tracked by rate limiter
            
        self._refill(engine)
        bucket = self.buckets[engine]
        
        if bucket.tokens >= tokens_needed:
            bucket.tokens -= tokens_needed
            return True
            
        logger.warning(f"Runtime rate limiter block applied to {engine} (burst/RPM limits).")
        return False
        
    def register_429(self, engine: str):
        """Immediately drain tokens on 429 to force a physical delay."""
        if engine in self.buckets:
            self.buckets[engine].tokens = 0
            
rate_limiter = ApiRateLimiter()
