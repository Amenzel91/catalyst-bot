"""
Hybrid LLM router: Local Mistral → Gemini Flash → Anthropic Claude

This module provides a three-tier fallback architecture for LLM queries with
automatic routing based on availability, performance, and quota limits.

Routing Logic:
1. Local Mistral (70%): Fast, free, handles short articles
2. Gemini Flash (25%): Medium complexity, free tier covers typical volume
3. Anthropic Claude (5%): Highest accuracy fallback, paid

Environment Variables:
* ``LLM_LOCAL_ENABLED`` – Enable local Mistral (default: 1)
* ``LLM_LOCAL_MAX_LENGTH`` – Max article length for local (default: 1000)
* ``GEMINI_API_KEY`` – Gemini API key (free tier: 1500 req/day)
* ``ANTHROPIC_API_KEY`` – Anthropic Claude key (paid fallback)

CRITICAL FIX: Added rate limit tracking with exponential backoff to prevent
API quota exhaustion and rate limit errors.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from collections import deque
from dataclasses import dataclass
from typing import Optional

# Optional Anthropic support
try:
    from anthropic import AsyncAnthropic

    ANTHROPIC_AVAILABLE = True
except ImportError:
    ANTHROPIC_AVAILABLE = False
    AsyncAnthropic = None

# Optional Gemini support
try:
    import google.generativeai as genai

    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False
    genai = None

_logger = logging.getLogger(__name__)


# Rate limit tracking for Gemini and Claude
class RateLimitTracker:
    """
    Track API calls per minute/hour and implement exponential backoff.

    Prevents quota exhaustion by monitoring request rates and applying
    backoff when approaching limits.
    """

    def __init__(
        self,
        requests_per_minute: int = 60,
        requests_per_hour: int = 1500,
        backoff_threshold: float = 0.8,
    ):
        """
        Initialize rate limit tracker.

        Args:
            requests_per_minute: Max requests per minute (default: 60)
            requests_per_hour: Max requests per hour (default: 1500)
            backoff_threshold: Start backoff at this fraction of limit (default: 0.8 = 80%)
        """
        self.requests_per_minute = requests_per_minute
        self.requests_per_hour = requests_per_hour
        self.backoff_threshold = backoff_threshold

        # Track recent requests with timestamps
        self.minute_window: deque[float] = deque(maxlen=requests_per_minute)
        self.hour_window: deque[float] = deque(maxlen=requests_per_hour)

        # Backoff state
        self.backoff_until = 0.0  # Timestamp when backoff ends
        self.consecutive_failures = 0

    def record_request(self) -> None:
        """Record a new API request."""
        now = time.time()
        self.minute_window.append(now)
        self.hour_window.append(now)

    def record_success(self) -> None:
        """Record a successful request (resets failure counter)."""
        self.consecutive_failures = 0
        self.backoff_until = 0.0

    def record_failure(self, is_rate_limit: bool = False) -> None:
        """
        Record a failed request.

        Args:
            is_rate_limit: True if failure was due to rate limiting (429 error)
        """
        self.consecutive_failures += 1

        if is_rate_limit:
            # Exponential backoff: 2^failures seconds (max 300s = 5 min)
            backoff_seconds = min(2 ** self.consecutive_failures, 300)
            self.backoff_until = time.time() + backoff_seconds
            _logger.warning(
                "rate_limit_backoff failures=%d backoff_sec=%d",
                self.consecutive_failures,
                backoff_seconds,
            )

    def should_backoff(self) -> tuple[bool, float]:
        """
        Check if we should apply backoff before making a request.

        Returns:
            Tuple of (should_wait, wait_seconds)
        """
        now = time.time()

        # Check if we're in active backoff period
        if now < self.backoff_until:
            wait = self.backoff_until - now
            return True, wait

        # Clean up old requests outside time windows
        minute_cutoff = now - 60
        hour_cutoff = now - 3600

        # Remove old requests (deque is FIFO, so oldest are at front)
        while self.minute_window and self.minute_window[0] < minute_cutoff:
            self.minute_window.popleft()
        while self.hour_window and self.hour_window[0] < hour_cutoff:
            self.hour_window.popleft()

        # Check if we're approaching rate limits
        minute_usage = len(self.minute_window) / self.requests_per_minute
        hour_usage = len(self.hour_window) / self.requests_per_hour

        # Apply soft backoff when approaching limits
        if minute_usage >= self.backoff_threshold:
            # Calculate wait time to stay under limit
            # If at 80% of limit, wait proportionally longer
            wait = (minute_usage - self.backoff_threshold) * 2.0
            _logger.info(
                "rate_limit_soft_backoff window=minute usage=%.1f%% wait=%.2fs",
                minute_usage * 100,
                wait,
            )
            return True, wait

        if hour_usage >= self.backoff_threshold:
            # Hourly limit approaching - apply small delay
            wait = (hour_usage - self.backoff_threshold) * 5.0
            _logger.info(
                "rate_limit_soft_backoff window=hour usage=%.1f%% wait=%.2fs",
                hour_usage * 100,
                wait,
            )
            return True, wait

        return False, 0.0

    def get_stats(self) -> dict:
        """Get current rate limit statistics."""
        now = time.time()
        minute_cutoff = now - 60
        hour_cutoff = now - 3600

        # Count requests in windows
        minute_count = sum(1 for ts in self.minute_window if ts >= minute_cutoff)
        hour_count = sum(1 for ts in self.hour_window if ts >= hour_cutoff)

        return {
            "requests_last_minute": minute_count,
            "requests_last_hour": hour_count,
            "minute_limit": self.requests_per_minute,
            "hour_limit": self.requests_per_hour,
            "minute_usage_pct": round((minute_count / self.requests_per_minute) * 100, 1),
            "hour_usage_pct": round((hour_count / self.requests_per_hour) * 100, 1),
            "consecutive_failures": self.consecutive_failures,
            "in_backoff": now < self.backoff_until,
        }


@dataclass
class HybridConfig:
    """Configuration for hybrid LLM router."""

    local_enabled: bool = True
    gemini_enabled: bool = False
    anthropic_enabled: bool = False

    gemini_api_key: str = ""
    anthropic_api_key: str = ""

    # Routing thresholds
    local_max_article_length: int = 1000  # chars

    @classmethod
    def from_env(cls) -> "HybridConfig":
        """Load configuration from environment variables."""
        gemini_key = os.getenv("GEMINI_API_KEY", "")
        anthropic_key = os.getenv("ANTHROPIC_API_KEY", "")

        return cls(
            local_enabled=os.getenv("LLM_LOCAL_ENABLED", "1") == "1",
            gemini_enabled=bool(gemini_key and GEMINI_AVAILABLE),
            anthropic_enabled=bool(anthropic_key and ANTHROPIC_AVAILABLE),
            gemini_api_key=gemini_key,
            anthropic_api_key=anthropic_key,
            local_max_article_length=int(os.getenv("LLM_LOCAL_MAX_LENGTH", "1000")),
        )


class HybridLLMRouter:
    """
    Three-tier routing with automatic fallback.

    Provides resilient LLM access with graceful degradation:
    - Primary: Local Mistral via Ollama (fast, free)
    - Secondary: Google Gemini Flash (free tier 1500 req/day)
    - Tertiary: Anthropic Claude (paid, highest accuracy)

    Health tracking ensures failed providers are skipped until recovery.
    """

    def __init__(self, config: Optional[HybridConfig] = None):
        self.config = config or HybridConfig.from_env()

        # Track health status
        self.local_healthy = True
        self.gemini_quota_remaining = 1500  # Daily free tier

        # CRITICAL FIX: Initialize rate limit trackers
        # Gemini free tier: 15 RPM, 1500 RPD (requests per day)
        self.gemini_rate_limiter = RateLimitTracker(
            requests_per_minute=15,
            requests_per_hour=1500,
            backoff_threshold=0.8,
        )
        # Claude paid tier: 50 RPM typical, adjust based on your tier
        self.claude_rate_limiter = RateLimitTracker(
            requests_per_minute=50,
            requests_per_hour=5000,
            backoff_threshold=0.8,
        )

        # Initialize clients
        self.gemini_client = None
        self.anthropic_client = None

        if self.config.gemini_enabled and GEMINI_AVAILABLE:
            try:
                genai.configure(api_key=self.config.gemini_api_key)
                # Using stable gemini-2.5-flash (1000 RPM with Tier 1 billing)
                # 100x better than experimental model (10 RPM limit)
                self.gemini_client = genai.GenerativeModel("gemini-2.5-flash")
                _logger.info("gemini_client_initialized model=gemini-2.5-flash")
            except Exception as e:
                _logger.warning("gemini_init_failed err=%s", str(e))
                self.config.gemini_enabled = False

        if self.config.anthropic_enabled and ANTHROPIC_AVAILABLE:
            try:
                self.anthropic_client = AsyncAnthropic(
                    api_key=self.config.anthropic_api_key
                )
                _logger.info("anthropic_client_initialized model=claude-3-haiku")
            except Exception as e:
                _logger.warning("anthropic_init_failed err=%s", str(e))
                self.config.anthropic_enabled = False

    async def route_request(
        self,
        prompt: str,
        article_length: Optional[int] = None,
        priority: str = "normal",
    ) -> Optional[str]:
        """
        Route request through fallback chain.

        Args:
            prompt: User prompt
            article_length: Length of article in chars (for routing decisions)
            priority: "high", "normal", "low" - affects retry behavior

        Returns:
            LLM response or None if all providers failed
        """
        # Decision 1: Try local Mistral for short articles
        if (
            self.config.local_enabled
            and self.local_healthy
            and (
                article_length is None
                or article_length < self.config.local_max_article_length
            )
        ):
            try:
                # Import here to avoid circular dependency
                from .llm_client import query_llm

                result = await asyncio.wait_for(
                    asyncio.to_thread(query_llm, prompt, timeout=15.0), timeout=20.0
                )
                if result:
                    _logger.debug("llm_route provider=local success=True")
                    return result
                else:
                    _logger.warning("llm_route provider=local success=False")
                    self.local_healthy = False  # Mark unhealthy
            except asyncio.TimeoutError:
                _logger.warning("llm_local_timeout")
                self.local_healthy = False
            except Exception as e:
                _logger.warning("llm_local_failed err=%s", str(e))
                self.local_healthy = False

        # Decision 2: Try Gemini Flash (medium complexity, free)
        if self.config.gemini_enabled and self.gemini_quota_remaining > 100:
            # CRITICAL FIX: Check rate limits before calling Gemini
            should_wait, wait_time = self.gemini_rate_limiter.should_backoff()
            if should_wait:
                _logger.info(
                    "llm_gemini_rate_limit_backoff wait_sec=%.2f stats=%s",
                    wait_time,
                    self.gemini_rate_limiter.get_stats(),
                )
                # Wait if backoff time is reasonable (<5s)
                if wait_time < 5.0:
                    await asyncio.sleep(wait_time)
                else:
                    # Skip Gemini and try Claude instead
                    _logger.warning("llm_gemini_skipped reason=rate_limit_backoff_too_long wait_sec=%.2f", wait_time)
                    pass  # Fall through to Claude

            if not should_wait or wait_time < 5.0:
                try:
                    self.gemini_rate_limiter.record_request()
                    result = await self._call_gemini(prompt)
                    if result:
                        self.gemini_rate_limiter.record_success()
                        self.gemini_quota_remaining -= 1
                        _logger.debug(
                            "llm_route provider=gemini success=True quota=%d rate_stats=%s",
                            self.gemini_quota_remaining,
                            self.gemini_rate_limiter.get_stats(),
                        )
                        return result
                    else:
                        self.gemini_rate_limiter.record_failure(is_rate_limit=False)
                except Exception as e:
                    # Check if it's a rate limit error (429 or quota exceeded)
                    error_msg = str(e).lower()
                    is_rate_limit = "429" in error_msg or "rate limit" in error_msg or "quota" in error_msg
                    self.gemini_rate_limiter.record_failure(is_rate_limit=is_rate_limit)
                    _logger.warning(
                        "llm_gemini_failed err=%s is_rate_limit=%s",
                        str(e),
                        is_rate_limit,
                    )

        # Decision 3: Fallback to Anthropic Claude (reliable, paid)
        if self.config.anthropic_enabled:
            # CRITICAL FIX: Check rate limits before calling Claude
            should_wait, wait_time = self.claude_rate_limiter.should_backoff()
            if should_wait:
                _logger.info(
                    "llm_claude_rate_limit_backoff wait_sec=%.2f stats=%s",
                    wait_time,
                    self.claude_rate_limiter.get_stats(),
                )
                # Always wait for Claude (it's our last resort)
                if wait_time > 0:
                    await asyncio.sleep(wait_time)

            try:
                self.claude_rate_limiter.record_request()
                result = await self._call_anthropic(prompt)
                if result:
                    self.claude_rate_limiter.record_success()
                    _logger.debug(
                        "llm_route provider=anthropic success=True rate_stats=%s",
                        self.claude_rate_limiter.get_stats(),
                    )
                    return result
                else:
                    self.claude_rate_limiter.record_failure(is_rate_limit=False)
            except Exception as e:
                # Check if it's a rate limit error (429)
                error_msg = str(e).lower()
                is_rate_limit = "429" in error_msg or "rate limit" in error_msg
                self.claude_rate_limiter.record_failure(is_rate_limit=is_rate_limit)
                _logger.warning(
                    "llm_anthropic_failed err=%s is_rate_limit=%s",
                    str(e),
                    is_rate_limit,
                )

        # All providers failed
        _logger.error(
            "llm_all_providers_failed local=%s gemini=%s anthropic=%s",
            self.local_healthy,
            self.config.gemini_enabled,
            self.config.anthropic_enabled,
        )
        return None

    async def _call_gemini(self, prompt: str) -> Optional[str]:
        """
        Call Gemini Flash API with usage monitoring.

        Args:
            prompt: User prompt

        Returns:
            Response text or None on failure
        """
        if not self.gemini_client:
            return None

        # Import usage monitor
        try:
            from .llm_usage_monitor import estimate_tokens, get_monitor

            monitor = get_monitor()
        except ImportError:
            monitor = None

        # Estimate input tokens
        input_tokens = estimate_tokens(prompt) if monitor else 0

        try:
            # Gemini API is synchronous, run in thread pool
            response = await asyncio.to_thread(
                self.gemini_client.generate_content, prompt
            )

            if response and hasattr(response, "text"):
                result_text = response.text.strip()

                # Log usage if monitor available
                if monitor:
                    output_tokens = estimate_tokens(result_text)
                    monitor.log_usage(
                        provider="gemini",
                        model="gemini-2.5-flash",
                        operation="llm_query",
                        input_tokens=input_tokens,
                        output_tokens=output_tokens,
                        success=True,
                        article_length=len(prompt),
                    )

                return result_text

            # Empty response - log as failure
            if monitor:
                monitor.log_usage(
                    provider="gemini",
                    model="gemini-2.5-flash",
                    operation="llm_query",
                    input_tokens=input_tokens,
                    output_tokens=0,
                    success=False,
                    error="empty_response",
                )
            return None

        except Exception as e:
            # Log failed request
            if monitor:
                monitor.log_usage(
                    provider="gemini",
                    model="gemini-2.5-flash",
                    operation="llm_query",
                    input_tokens=input_tokens,
                    output_tokens=0,
                    success=False,
                    error=str(e),
                )
            _logger.warning("gemini_api_error err=%s", str(e))
            return None

    async def _call_anthropic(self, prompt: str) -> Optional[str]:
        """
        Call Anthropic Claude API with usage monitoring.

        Args:
            prompt: User prompt

        Returns:
            Response text or None on failure
        """
        if not self.anthropic_client:
            return None

        # Import usage monitor
        try:
            from .llm_usage_monitor import get_monitor

            monitor = get_monitor()
        except ImportError:
            monitor = None

        try:
            # Using Claude 3 Haiku for cost-effective keyword extraction
            # 91% cheaper than Sonnet ($0.44 vs $3.30/month for 5% fallback traffic)
            message = await self.anthropic_client.messages.create(
                model="claude-3-haiku-20240307",
                max_tokens=1024,
                messages=[{"role": "user", "content": prompt}],
            )

            if message.content and len(message.content) > 0:
                result_text = message.content[0].text

                # Log usage with actual token counts from API response
                if monitor and hasattr(message, "usage"):
                    monitor.log_usage(
                        provider="anthropic",
                        model="claude-3-haiku-20240307",
                        operation="llm_query",
                        input_tokens=message.usage.input_tokens,
                        output_tokens=message.usage.output_tokens,
                        success=True,
                        article_length=len(prompt),
                    )

                return result_text

            # Empty response - log as failure
            if monitor:
                from .llm_usage_monitor import estimate_tokens

                monitor.log_usage(
                    provider="anthropic",
                    model="claude-3-haiku-20240307",
                    operation="llm_query",
                    input_tokens=estimate_tokens(prompt),
                    output_tokens=0,
                    success=False,
                    error="empty_response",
                )
            return None

        except Exception as e:
            # Log failed request
            if monitor:
                from .llm_usage_monitor import estimate_tokens

                monitor.log_usage(
                    provider="anthropic",
                    model="claude-3-haiku-20240307",
                    operation="llm_query",
                    input_tokens=estimate_tokens(prompt),
                    output_tokens=0,
                    success=False,
                    error=str(e),
                )
            _logger.warning("anthropic_api_error err=%s", str(e))
            return None

    def reset_local_health(self) -> None:
        """Reset local LLM health status (call after successful warmup)."""
        self.local_healthy = True
        _logger.info("local_llm_health_reset")


# Global router instance (lazy initialization)
_router: Optional[HybridLLMRouter] = None


async def query_hybrid_llm(
    prompt: str, article_length: Optional[int] = None, priority: str = "normal"
) -> Optional[str]:
    """
    Main entry point for hybrid LLM routing.

    Automatically routes through: Local → Gemini → Anthropic

    Args:
        prompt: User prompt
        article_length: Optional article length for routing decisions
        priority: "high", "normal", "low" - affects retry behavior

    Returns:
        LLM response or None if all providers failed

    Example:
        >>> result = await query_hybrid_llm("Analyze this headline: Apple announces record earnings")  # noqa: E501
        >>> if result:
        ...     print(f"LLM response: {result}")
    """
    global _router

    if _router is None:
        _router = HybridLLMRouter()
        _logger.info(
            "hybrid_router_initialized local=%s gemini=%s anthropic=%s",
            _router.config.local_enabled,
            _router.config.gemini_enabled,
            _router.config.anthropic_enabled,
        )

    return await _router.route_request(prompt, article_length, priority)


def get_router() -> Optional[HybridLLMRouter]:
    """
    Get the global router instance.

    Returns:
        Router instance or None if not initialized
    """
    return _router
