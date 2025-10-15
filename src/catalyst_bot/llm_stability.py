"""
LLM Stability Enhancements - Wave 0.2

This module provides stability improvements for LLM operations:
- Intelligent rate limiting with sliding windows
- Smart batching with pre-filtering
- Enhanced error handling with graceful degradation
- GPU memory monitoring and cleanup
- Request throttling with exponential backoff

Environment Variables:
* ``LLM_BATCH_SIZE`` – Items per batch (default: 5)
* ``LLM_BATCH_DELAY_SEC`` – Delay between batches (default: 2.0)
* ``LLM_MIN_PRESCALE_SCORE`` – Pre-filter threshold (default: 0.20)
* ``LLM_RATE_LIMIT_RPM`` – Requests per minute (default: 10 for Gemini free tier)
* ``LLM_MIN_INTERVAL_SEC`` – Minimum seconds between requests (default: 3.0)
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Deque, Dict, List, Optional

_logger = logging.getLogger(__name__)


@dataclass
class RateLimitConfig:
    """Rate limit configuration for a provider."""

    max_requests_per_minute: int = 60
    max_requests_per_hour: int = 3600
    max_requests_per_day: int = 86400
    min_interval_sec: float = 0.0  # Minimum time between requests


@dataclass
class RateLimiter:
    """
    Rate limiter with sliding window tracking.

    Tracks request timestamps to enforce per-minute, per-hour, and per-day limits.
    Provides intelligent throttling with exponential backoff.
    """

    config: RateLimitConfig
    request_history: Deque[datetime] = field(default_factory=deque)
    last_request_time: float = 0.0
    consecutive_failures: int = 0

    def can_make_request(self) -> tuple[bool, float]:
        """
        Check if a request can be made now.

        Returns:
            (allowed, wait_time_sec) - If not allowed, returns recommended wait time
        """
        now = datetime.now(timezone.utc)
        current_time = time.time()

        # Check minimum interval between requests
        time_since_last = current_time - self.last_request_time
        if (
            self.config.min_interval_sec > 0
            and time_since_last < self.config.min_interval_sec
        ):
            wait_time = self.config.min_interval_sec - time_since_last
            return False, wait_time

        # Clean old entries (keep only last 24 hours)
        cutoff = now - timedelta(hours=24)
        while self.request_history and self.request_history[0] < cutoff:
            self.request_history.popleft()

        # Count requests in different windows
        one_min_ago = now - timedelta(minutes=1)
        one_hour_ago = now - timedelta(hours=1)

        requests_last_min = sum(1 for t in self.request_history if t >= one_min_ago)
        requests_last_hour = sum(1 for t in self.request_history if t >= one_hour_ago)
        requests_last_day = len(self.request_history)

        # Check limits
        if requests_last_min >= self.config.max_requests_per_minute:
            _logger.debug(
                "rate_limit_hit window=minute count=%d limit=%d",
                requests_last_min,
                self.config.max_requests_per_minute,
            )
            return False, 60.0

        if requests_last_hour >= self.config.max_requests_per_hour:
            _logger.debug(
                "rate_limit_hit window=hour count=%d limit=%d",
                requests_last_hour,
                self.config.max_requests_per_hour,
            )
            return False, 300.0

        if requests_last_day >= self.config.max_requests_per_day:
            _logger.warning(
                "rate_limit_hit window=day count=%d limit=%d",
                requests_last_day,
                self.config.max_requests_per_day,
            )
            return False, 3600.0

        return True, 0.0

    async def wait_if_needed(self) -> None:
        """Wait if rate limit requires it."""
        can_proceed, wait_time = self.can_make_request()
        if not can_proceed and wait_time > 0:
            _logger.info("rate_limit_throttle wait_sec=%.1f", wait_time)
            await asyncio.sleep(wait_time)

    def record_request(self, success: bool = True) -> None:
        """Record a request in the history."""
        now = datetime.now(timezone.utc)
        self.request_history.append(now)
        self.last_request_time = time.time()

        if success:
            self.consecutive_failures = 0
        else:
            self.consecutive_failures += 1

    def get_backoff_delay(self) -> float:
        """Get exponential backoff delay based on consecutive failures."""
        if self.consecutive_failures == 0:
            return 0.0
        # Exponential backoff: 2^failures seconds, capped at 60s
        return min(2**self.consecutive_failures, 60.0)

    def get_stats(self) -> Dict[str, int]:
        """Get current rate limit statistics."""
        now = datetime.now(timezone.utc)
        one_min_ago = now - timedelta(minutes=1)
        one_hour_ago = now - timedelta(hours=1)

        return {
            "requests_last_min": sum(
                1 for t in self.request_history if t >= one_min_ago
            ),
            "requests_last_hour": sum(
                1 for t in self.request_history if t >= one_hour_ago
            ),
            "requests_last_day": len(self.request_history),
            "consecutive_failures": self.consecutive_failures,
        }


class BatchProcessor:
    """
    Smart batch processor with pre-filtering and rate limiting.

    Processes items in batches with delays to prevent GPU/API overload.
    Applies pre-filtering to reduce load on expensive LLMs.
    """

    def __init__(
        self,
        batch_size: int = 5,
        batch_delay_sec: float = 2.0,
        min_prescale_score: float = 0.20,
        rate_limiter: Optional[RateLimiter] = None,
    ):
        """
        Initialize batch processor.

        Args:
            batch_size: Number of items per batch
            batch_delay_sec: Delay between batches in seconds
            min_prescale_score: Minimum score threshold for processing
            rate_limiter: Optional rate limiter for throttling
        """
        self.batch_size = batch_size
        self.batch_delay_sec = batch_delay_sec
        self.min_prescale_score = min_prescale_score
        self.rate_limiter = rate_limiter

        _logger.info(
            "batch_processor_init batch_size=%d delay=%.1fs min_score=%.2f",
            batch_size,
            batch_delay_sec,
            min_prescale_score,
        )

    def pre_filter(self, items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Pre-filter items based on prescale score.

        Only sends high-potential items to expensive LLM.

        Args:
            items: List of items with prescale_score field

        Returns:
            Filtered list of items
        """
        if self.min_prescale_score <= 0:
            return items

        filtered = [
            item
            for item in items
            if item.get("prescale_score", 0) >= self.min_prescale_score
        ]

        reduction_pct = (1 - len(filtered) / max(len(items), 1)) * 100 if items else 0
        _logger.info(
            "batch_prefilter original=%d filtered=%d reduction=%.0f%%",
            len(items),
            len(filtered),
            reduction_pct,
        )

        return filtered

    async def process_batch(
        self,
        items: List[Dict[str, Any]],
        process_fn: Any,  # async callable
        filter_items: bool = True,
    ) -> List[Dict[str, Any]]:
        """
        Process items in batches with delays.

        Args:
            items: List of items to process
            process_fn: Async function to process each item
            filter_items: Whether to pre-filter items

        Returns:
            Processed items
        """
        # Pre-filter items if enabled
        items_to_process = self.pre_filter(items) if filter_items else items

        if not items_to_process:
            _logger.debug("batch_process skipped_all items=0")
            return []

        total_batches = (len(items_to_process) + self.batch_size - 1) // self.batch_size
        processed_items = []

        for i in range(0, len(items_to_process), self.batch_size):
            batch = items_to_process[i : i + self.batch_size]
            batch_num = (i // self.batch_size) + 1

            _logger.info(
                "batch_processing batch=%d/%d items=%d",
                batch_num,
                total_batches,
                len(batch),
            )

            # Process each item in the batch
            for item in batch:
                try:
                    # Rate limit if configured
                    if self.rate_limiter:
                        await self.rate_limiter.wait_if_needed()

                    # Process the item
                    result = await process_fn(item)
                    processed_items.append(result)

                    # Record success
                    if self.rate_limiter:
                        self.rate_limiter.record_request(success=True)

                except Exception as e:
                    _logger.warning("batch_item_failed err=%s", str(e))
                    if self.rate_limiter:
                        self.rate_limiter.record_request(success=False)
                    processed_items.append(item)  # Return unprocessed item

            # Delay between batches (except last batch)
            if i + self.batch_size < len(items_to_process):
                _logger.debug("batch_delay sec=%.1f", self.batch_delay_sec)
                await asyncio.sleep(self.batch_delay_sec)

        _logger.info(
            "batch_complete processed=%d/%d success_rate=%.1f%%",
            len(processed_items),
            len(items_to_process),
            (len(processed_items) / max(len(items_to_process), 1)) * 100,
        )

        return processed_items


class ErrorHandler:
    """
    Enhanced error handling with graceful degradation.

    Tracks error patterns and provides intelligent fallback strategies.
    """

    def __init__(self):
        self.error_counts: Dict[str, int] = {}
        self.last_errors: Deque[tuple[str, datetime]] = deque(maxlen=100)

    def record_error(self, error_type: str, error_msg: str) -> None:
        """Record an error occurrence."""
        self.error_counts[error_type] = self.error_counts.get(error_type, 0) + 1
        self.last_errors.append((error_type, datetime.now(timezone.utc)))
        _logger.warning(
            "error_recorded type=%s msg=%s count=%d",
            error_type,
            error_msg,
            self.error_counts[error_type],
        )

    def should_retry(self, error_type: str, max_retries: int = 3) -> bool:
        """Determine if an operation should be retried."""
        count = self.error_counts.get(error_type, 0)
        return count < max_retries

    def get_error_stats(self) -> Dict[str, Any]:
        """Get error statistics."""
        now = datetime.now(timezone.utc)
        recent_errors = [e for e in self.last_errors if (now - e[1]).seconds < 3600]

        return {
            "total_errors": len(self.last_errors),
            "recent_errors_1h": len(recent_errors),
            "error_types": dict(self.error_counts),
        }


# Global instances
_rate_limiters: Dict[str, RateLimiter] = {}
_error_handler = ErrorHandler()


def get_rate_limiter(provider: str = "default") -> RateLimiter:
    """
    Get or create a rate limiter for a provider.

    Args:
        provider: Provider name (e.g., "gemini", "anthropic", "local")

    Returns:
        RateLimiter instance
    """
    if provider not in _rate_limiters:
        # Load provider-specific config from environment
        rpm = int(os.getenv(f"LLM_{provider.upper()}_RPM", "10"))
        rph = int(os.getenv(f"LLM_{provider.upper()}_RPH", "600"))
        rpd = int(os.getenv(f"LLM_{provider.upper()}_RPD", "1500"))
        min_interval = float(os.getenv("LLM_MIN_INTERVAL_SEC", "3.0"))

        config = RateLimitConfig(
            max_requests_per_minute=rpm,
            max_requests_per_hour=rph,
            max_requests_per_day=rpd,
            min_interval_sec=min_interval,
        )

        _rate_limiters[provider] = RateLimiter(config=config)
        _logger.info(
            "rate_limiter_created provider=%s rpm=%d rph=%d rpd=%d interval=%.1fs",
            provider,
            rpm,
            rph,
            rpd,
            min_interval,
        )

    return _rate_limiters[provider]


def get_error_handler() -> ErrorHandler:
    """Get the global error handler instance."""
    return _error_handler


def get_batch_processor() -> BatchProcessor:
    """
    Get a batch processor with configuration from environment.

    Returns:
        BatchProcessor instance
    """
    batch_size = int(os.getenv("LLM_BATCH_SIZE", "5"))
    batch_delay = float(os.getenv("LLM_BATCH_DELAY_SEC", "2.0"))
    min_score = float(os.getenv("LLM_MIN_PRESCALE_SCORE", "0.20"))

    # Use default rate limiter
    rate_limiter = get_rate_limiter("default")

    return BatchProcessor(
        batch_size=batch_size,
        batch_delay_sec=batch_delay,
        min_prescale_score=min_score,
        rate_limiter=rate_limiter,
    )
