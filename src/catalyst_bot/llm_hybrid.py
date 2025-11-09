"""
Hybrid LLM router: Local Mistral → Gemini Flash/Pro → Anthropic Claude

This module provides a three-tier fallback architecture for LLM queries with
automatic routing based on availability, performance, and quota limits.

Routing Logic:
1. Local Mistral (70%): Fast, free, handles short articles
2. Gemini Flash/Pro (25%): Tiered based on complexity (Wave 3B)
   - Flash: Simple filings, fast, cheap ($0.075/1M tokens input)
   - Pro: Complex filings (M&A, earnings), deep analysis ($1.25/1M tokens)
3. Anthropic Claude (5%): Highest accuracy fallback, paid

Environment Variables:
* ``LLM_LOCAL_ENABLED`` – Enable local Mistral (default: 1)
* ``LLM_LOCAL_MAX_LENGTH`` – Max article length for local (default: 1000)
* ``GEMINI_API_KEY`` – Gemini API key (free tier: 1500 req/day)
* ``ANTHROPIC_API_KEY`` – Anthropic Claude key (paid fallback)
* ``LLM_TIER_STRATEGY`` – Tiering strategy: auto, flash, pro, adaptive (default: auto)
* ``LLM_COMPLEXITY_THRESHOLD`` – Pro threshold for auto mode (default: 0.7)
* ``LLM_COST_TRACKING`` – Enable cost logging (default: true)

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


# ============================================================================
# Gemini Model Costs (Wave 3B - Cost Tracking)
# ============================================================================

GEMINI_COSTS = {
    "gemini-1.5-flash-002": {
        "input": 0.075 / 1_000_000,  # $0.075 per 1M tokens
        "output": 0.30 / 1_000_000,  # $0.30 per 1M tokens
    },
    "gemini-2.5-flash": {
        "input": 0.075 / 1_000_000,
        "output": 0.30 / 1_000_000,
    },
    "gemini-2.0-flash-lite": {
        "input": 0.02 / 1_000_000,  # $0.02 per 1M tokens (73% cheaper than Flash)
        "output": 0.10 / 1_000_000,  # $0.10 per 1M tokens (67% cheaper than Flash)
    },
    "gemini-1.5-pro-002": {
        "input": 1.25 / 1_000_000,  # $1.25 per 1M tokens
        "output": 5.00 / 1_000_000,  # $5.00 per 1M tokens
    },
    "gemini-2.5-pro": {
        "input": 1.25 / 1_000_000,
        "output": 5.00 / 1_000_000,
    },
}


# ============================================================================
# SEC Filing Complexity Scoring (Wave 3B)
# ============================================================================


def is_simple_operation(
    operation: str,
    text_length: int = 0,
    complexity_threshold: float = 0.3,
) -> bool:
    """
    Determine if an operation is simple enough for Flash-Lite model.

    Flash-Lite is suitable for:
    - Short text analysis (<500 chars)
    - Simple classification tasks
    - Keyword extraction from brief content
    - Quick sentiment analysis

    Parameters
    ----------
    operation : str
        Type of operation (e.g., 'sentiment', 'classification', 'sec_analysis')
    text_length : int
        Length of text to analyze in characters
    complexity_threshold : float
        Complexity score threshold (0.0-1.0), operations below this use Flash-Lite

    Returns
    -------
    bool
        True if operation is simple enough for Flash-Lite

    Examples
    --------
    >>> is_simple_operation('sentiment', text_length=200)
    True
    >>> is_simple_operation('sec_analysis', text_length=5000)
    False
    """
    # Short text is always simple
    if text_length < 500:
        return True

    # Medium text (500-2000 chars) depends on operation type
    if text_length < 2000:
        simple_operations = {
            'sentiment',
            'classification',
            'keyword_extraction',
            'duplicate_check',
        }
        return operation.lower() in simple_operations

    # Long text (>2000 chars) requires Flash/Pro
    return False


def calculate_filing_complexity(
    filing_section=None,
    numeric_metrics=None,
    guidance_analysis=None,
    filing_text: str = "",
) -> float:
    """
    Calculate SEC filing complexity score (0.0-1.0).

    Determines whether to use Gemini Flash (simple) or Pro (complex) based on:
    - Filing type and item code (8-K Item 1.01 M&A = complex)
    - Text length (>5000 chars = complex)
    - Numeric density (>10 metrics = complex)
    - Forward guidance presence (raises/lowers = complex)

    Parameters
    ----------
    filing_section : FilingSection, optional
        Parsed SEC filing section from sec_parser.py
    numeric_metrics : NumericMetrics, optional
        Extracted numeric data from numeric_extractor.py
    guidance_analysis : GuidanceAnalysis, optional
        Forward guidance from guidance_extractor.py
    filing_text : str
        Raw filing text (fallback if filing_section unavailable)

    Returns
    -------
    float
        Complexity score: 0.0-0.3 (simple), 0.3-0.7 (medium), 0.7-1.0 (complex)

    Examples
    --------
    >>> from sec_parser import FilingSection
    >>> filing = FilingSection(item_code="1.01", filing_type="8-K", text="M&A announcement...")
    >>> complexity = calculate_filing_complexity(filing_section=filing)
    >>> complexity >= 0.7  # M&A is complex
    True
    """
    score = 0.0

    # Factor 1: Filing type impact (0.0-0.3)
    if filing_section:
        high_impact_items = ["1.01", "1.03", "2.02"]  # M&A, bankruptcy, earnings
        if filing_section.item_code in high_impact_items:
            score += 0.3
        elif filing_section.filing_type in ("10-Q", "10-K"):
            score += 0.25

    # Factor 2: Text length (0.0-0.2)
    text = filing_section.text if filing_section else filing_text
    if len(text) > 10000:
        score += 0.2
    elif len(text) > 5000:
        score += 0.15
    elif len(text) > 2000:
        score += 0.1

    # Factor 3: Numeric density (0.0-0.2)
    if numeric_metrics:
        total_metrics = (
            len(numeric_metrics.revenue)
            + len(numeric_metrics.eps)
            + len(numeric_metrics.margins)
            + len(numeric_metrics.guidance_ranges)
        )
        if total_metrics > 15:
            score += 0.2
        elif total_metrics > 10:
            score += 0.15
        elif total_metrics > 5:
            score += 0.1

    # Factor 4: Forward guidance presence (0.0-0.3)
    if guidance_analysis and guidance_analysis.has_guidance:
        # Raised/lowered guidance is more complex than maintained
        if any(
            g.change_direction in ("raised", "lowered")
            for g in guidance_analysis.guidance_items
        ):
            score += 0.3
        elif guidance_analysis.overall_direction == "mixed":
            score += 0.25
        else:
            score += 0.15

    return min(1.0, score)


def select_model_tier(
    complexity: float,
    strategy: Optional[str] = None,
    confidence_threshold: float = 0.6,
    text_length: int = 0,
    operation: str = "",
) -> str:
    """
    Select Gemini model based on filing complexity and strategy.

    Now includes Flash-Lite routing for simple operations (Agent 1).

    Parameters
    ----------
    complexity : float
        Complexity score from calculate_filing_complexity (0.0-1.0)
    strategy : str, optional
        Tiering strategy: "auto", "flash", "flash-lite", "pro", "adaptive"
        Defaults to LLM_TIER_STRATEGY env var or "auto"
    confidence_threshold : float
        For adaptive strategy: upgrade to Pro if confidence < threshold
    text_length : int
        Length of text being analyzed (for flash-lite routing)
    operation : str
        Operation type (for flash-lite routing)

    Returns
    -------
    str
        Model name: "gemini-2.0-flash-lite", "gemini-2.5-flash", or "gemini-2.5-pro"

    Examples
    --------
    >>> select_model_tier(0.1, strategy="auto", text_length=200, operation="sentiment")
    'gemini-2.0-flash-lite'
    >>> select_model_tier(0.3, strategy="auto")  # Simple filing
    'gemini-2.5-flash'
    >>> select_model_tier(0.8, strategy="auto")  # Complex M&A
    'gemini-2.5-pro'
    >>> select_model_tier(0.5, strategy="flash-lite")  # Force Flash-Lite
    'gemini-2.0-flash-lite'
    """
    if strategy is None:
        strategy = os.getenv("LLM_TIER_STRATEGY", "auto").lower()

    complexity_threshold = float(os.getenv("LLM_COMPLEXITY_THRESHOLD", "0.7"))
    flash_lite_enabled = os.getenv("FEATURE_FLASH_LITE", "1") in ("1", "true", "yes", "on")
    flash_lite_threshold = float(os.getenv("LLM_FLASH_LITE_THRESHOLD", "0.3"))

    # Strategy overrides
    if strategy == "flash-lite":
        return "gemini-2.0-flash-lite"
    elif strategy == "flash":
        return "gemini-2.5-flash"
    elif strategy == "pro":
        return "gemini-2.5-pro"
    elif strategy == "auto":
        # Agent 1: Flash-Lite routing for simple operations
        if flash_lite_enabled and complexity < flash_lite_threshold:
            # Check if operation is simple enough for Flash-Lite
            if is_simple_operation(operation, text_length, flash_lite_threshold):
                return "gemini-2.0-flash-lite"

        # Standard Flash/Pro routing
        if complexity >= complexity_threshold:
            return "gemini-2.5-pro"
        else:
            return "gemini-2.5-flash"
    elif strategy == "adaptive":
        # Start with Flash-Lite for simple ops, Flash otherwise
        if flash_lite_enabled and is_simple_operation(operation, text_length, flash_lite_threshold):
            return "gemini-2.0-flash-lite"
        return "gemini-2.5-flash"
    else:
        _logger.warning(f"Unknown tier strategy: {strategy}, defaulting to auto")
        return select_model_tier(complexity, strategy="auto", text_length=text_length, operation=operation)


def log_llm_cost(
    model: str,
    input_tokens: int,
    output_tokens: int,
    operation: str = "sec_analysis",
) -> float:
    """
    Calculate and log LLM cost for a request.

    Parameters
    ----------
    model : str
        Model name (e.g., "gemini-2.5-flash", "gemini-2.5-pro")
    input_tokens : int
        Number of input tokens
    output_tokens : int
        Number of output tokens
    operation : str
        Operation type for logging context

    Returns
    -------
    float
        Total cost in USD

    Examples
    --------
    >>> cost = log_llm_cost("gemini-2.5-flash", 1000, 200)
    >>> cost
    0.000135  # (1000 * 0.075 + 200 * 0.30) / 1M
    """
    if model not in GEMINI_COSTS:
        _logger.warning(f"Unknown model for cost tracking: {model}")
        return 0.0

    costs = GEMINI_COSTS[model]
    input_cost = input_tokens * costs["input"]
    output_cost = output_tokens * costs["output"]
    total_cost = input_cost + output_cost

    cost_tracking_enabled = os.getenv("LLM_COST_TRACKING", "true").lower() in (
        "true",
        "1",
        "yes",
    )

    if cost_tracking_enabled:
        _logger.info(
            f"llm_cost model={model} operation={operation} "
            f"tokens_in={input_tokens} tokens_out={output_tokens} "
            f"cost_usd=${total_cost:.6f}"
        )

    return total_cost


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
        # Agent 1: Flash-Lite has higher rate limits (500 RPM)
        self.flash_lite_rate_limiter = RateLimitTracker(
            requests_per_minute=500,
            requests_per_hour=10000,
            backoff_threshold=0.9,  # Higher threshold for generous limits
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
        model_override: Optional[str] = None,
    ) -> Optional[str]:
        """
        Route request through fallback chain.

        Args:
            prompt: User prompt
            article_length: Length of article in chars (for routing decisions)
            priority: "high", "normal", "low" - affects retry behavior
            model_override: Optional model override (e.g., "gemini-2.5-pro" for complex filings)

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

        # Decision 2: Try Gemini Flash/Flash-Lite (medium/low complexity, free)
        if self.config.gemini_enabled and self.gemini_quota_remaining > 100:
            # Agent 1: Determine model (Flash-Lite vs Flash vs override)
            if model_override:
                model = model_override
                rate_limiter = self.flash_lite_rate_limiter if "lite" in model else self.gemini_rate_limiter
            else:
                # Auto-select based on complexity and text length
                flash_lite_enabled = os.getenv("FEATURE_FLASH_LITE", "1") in ("1", "true", "yes", "on")
                if flash_lite_enabled and is_simple_operation("llm_query", len(prompt), 0.3):
                    model = "gemini-2.0-flash-lite"
                    rate_limiter = self.flash_lite_rate_limiter
                else:
                    model = "gemini-2.5-flash"
                    rate_limiter = self.gemini_rate_limiter

            # CRITICAL FIX: Check rate limits before calling Gemini
            should_wait, wait_time = rate_limiter.should_backoff()
            if should_wait:
                _logger.info(
                    "llm_gemini_rate_limit_backoff model=%s wait_sec=%.2f stats=%s",
                    model,
                    wait_time,
                    rate_limiter.get_stats(),
                )
                # Wait if backoff time is reasonable (<5s)
                if wait_time < 5.0:
                    await asyncio.sleep(wait_time)
                else:
                    # Skip Gemini and try Claude instead
                    _logger.warning("llm_gemini_skipped reason=rate_limit_backoff_too_long model=%s wait_sec=%.2f", model, wait_time)
                    pass  # Fall through to Claude

            if not should_wait or wait_time < 5.0:
                try:
                    rate_limiter.record_request()
                    result = await self._call_gemini(prompt, model=model)
                    if result:
                        rate_limiter.record_success()
                        self.gemini_quota_remaining -= 1
                        _logger.debug(
                            "llm_route provider=gemini model=%s success=True quota=%d rate_stats=%s",
                            model,
                            self.gemini_quota_remaining,
                            rate_limiter.get_stats(),
                        )
                        return result
                    else:
                        rate_limiter.record_failure(is_rate_limit=False)
                except Exception as e:
                    # Check if it's a rate limit error (429 or quota exceeded)
                    error_msg = str(e).lower()
                    is_rate_limit = "429" in error_msg or "rate limit" in error_msg or "quota" in error_msg
                    rate_limiter.record_failure(is_rate_limit=is_rate_limit)
                    _logger.warning(
                        "llm_gemini_failed model=%s err=%s is_rate_limit=%s",
                        model,
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

    async def _call_gemini(self, prompt: str, model: str = "gemini-2.5-flash") -> Optional[str]:
        """
        Call Gemini API with usage monitoring and cost tracking.

        Args:
            prompt: User prompt
            model: Gemini model to use ("gemini-2.5-flash" or "gemini-2.5-pro")

        Returns:
            Response text or None on failure
        """
        if not GEMINI_AVAILABLE:
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
            # Create model-specific client dynamically for tiering support
            gemini_model = genai.GenerativeModel(model)

            # Gemini API is synchronous, run in thread pool
            response = await asyncio.to_thread(
                gemini_model.generate_content, prompt
            )

            if response and hasattr(response, "text"):
                result_text = response.text.strip()

                # Estimate output tokens
                output_tokens = estimate_tokens(result_text) if monitor else 0

                # Log cost (Wave 3B)
                log_llm_cost(model, input_tokens, output_tokens, operation="sec_analysis")

                # Log usage if monitor available
                if monitor:
                    monitor.log_usage(
                        provider="gemini",
                        model=model,
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
                    model=model,
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
                    model=model,
                    operation="llm_query",
                    input_tokens=input_tokens,
                    output_tokens=0,
                    success=False,
                    error=str(e),
                )
            _logger.warning("gemini_api_error model=%s err=%s", model, str(e))
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
    prompt: str,
    article_length: Optional[int] = None,
    priority: str = "normal",
    model_override: Optional[str] = None,
) -> Optional[str]:
    """
    Main entry point for hybrid LLM routing.

    Automatically routes through: Local → Gemini (Flash/Pro) → Anthropic

    Args:
        prompt: User prompt
        article_length: Optional article length for routing decisions
        priority: "high", "normal", "low" - affects retry behavior
        model_override: Optional Gemini model override (e.g., "gemini-2.5-pro")

    Returns:
        LLM response or None if all providers failed

    Example:
        >>> result = await query_hybrid_llm("Analyze this headline: Apple announces record earnings")  # noqa: E501
        >>> if result:
        ...     print(f"LLM response: {result}")

        >>> # Use Pro model for complex SEC filing
        >>> result = await query_hybrid_llm(prompt, model_override="gemini-2.5-pro")
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

    return await _router.route_request(prompt, article_length, priority, model_override)


def get_router() -> Optional[HybridLLMRouter]:
    """
    Get the global router instance.

    Returns:
        Router instance or None if not initialized
    """
    return _router
