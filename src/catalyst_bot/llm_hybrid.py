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
"""

from __future__ import annotations

import asyncio
import logging
import os
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
            try:
                result = await self._call_gemini(prompt)
                if result:
                    self.gemini_quota_remaining -= 1
                    _logger.debug(
                        "llm_route provider=gemini success=True quota=%d",
                        self.gemini_quota_remaining,
                    )
                    return result
            except Exception as e:
                _logger.warning("llm_gemini_failed err=%s", str(e))

        # Decision 3: Fallback to Anthropic Claude (reliable, paid)
        if self.config.anthropic_enabled:
            try:
                result = await self._call_anthropic(prompt)
                if result:
                    _logger.debug("llm_route provider=anthropic success=True")
                    return result
            except Exception as e:
                _logger.warning("llm_anthropic_failed err=%s", str(e))

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
