"""
Keyword Performance Provider for Feedback Loop Integration.

This module provides a TTL-cached bridge between the feedback system
(which tracks keyword performance) and the SignalGenerator (which
uses performance data to adjust confidence scores).

Feature Flag: FEATURE_FEEDBACK_SIGNAL_INTEGRATION
"""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from threading import Lock
from typing import Dict, Optional

from ..config import get_settings
from ..logging_utils import get_logger

logger = get_logger(__name__)


@dataclass
class MultiplierCache:
    """TTL-based cache for keyword multipliers."""

    multipliers: Dict[str, float]
    expires_at: datetime


class KeywordPerformanceProvider:
    """
    Provides keyword performance multipliers with TTL caching.

    Bridges feedback system with signal generation. Fetches multipliers
    from weight_adjuster, applies bounds, and caches for TTL window.

    Usage:
        provider = KeywordPerformanceProvider()
        multiplier = provider.get_multiplier("fda")  # Returns 1.0-1.2 range
    """

    def __init__(
        self,
        cache_ttl_minutes: Optional[int] = None,
        min_bound: Optional[float] = None,
        max_bound: Optional[float] = None,
        min_samples: Optional[int] = None,
    ):
        """
        Initialize the provider.

        Args:
            cache_ttl_minutes: Cache TTL in minutes (default from config)
            min_bound: Minimum multiplier bound (default from config)
            max_bound: Maximum multiplier bound (default from config)
            min_samples: Minimum sample size before adjustment (default from config)
        """
        settings = get_settings()

        self.cache_ttl_minutes = (
            cache_ttl_minutes or settings.feedback_cache_ttl_minutes
        )
        self.min_bound = min_bound or settings.feedback_multiplier_min
        self.max_bound = max_bound or settings.feedback_multiplier_max
        self.min_samples = min_samples or settings.feedback_min_sample_size

        self._cache: Optional[MultiplierCache] = None
        self._lock = Lock()

    def get_multiplier(self, keyword: str) -> float:
        """
        Get performance multiplier for keyword.

        Args:
            keyword: Keyword category (e.g., "fda", "merger")

        Returns:
            Multiplier in range [min_bound, max_bound], default 1.0
        """
        settings = get_settings()

        # Feature disabled - return baseline
        if not settings.feature_feedback_signal_integration:
            return 1.0

        # Get cached multipliers
        multipliers = self._get_cached_multipliers()
        return multipliers.get(keyword.lower(), 1.0)

    def _get_cached_multipliers(self) -> Dict[str, float]:
        """Get multipliers from cache or refresh if expired."""
        with self._lock:
            now = datetime.now(timezone.utc)

            # Cache hit
            if self._cache and self._cache.expires_at > now:
                return self._cache.multipliers

            # Cache miss - refresh
            logger.info("refreshing_keyword_multiplier_cache")
            multipliers = self._fetch_multipliers()

            expires_at = now + timedelta(minutes=self.cache_ttl_minutes)
            self._cache = MultiplierCache(multipliers, expires_at)

            return multipliers

    def _fetch_multipliers(self) -> Dict[str, float]:
        """Fetch multipliers from feedback system."""
        try:
            from ..feedback.weight_adjuster import analyze_keyword_performance

            perf_data = analyze_keyword_performance(lookback_days=7)
            multipliers = {}

            for keyword, data in perf_data.items():
                # Skip low sample size
                if data.get("alert_count", 0) < self.min_samples:
                    continue

                # Calculate raw multiplier from performance
                win_rate = data.get("win_rate", 0.5)
                avg_score = data.get("avg_score", 0.0)

                if win_rate > 0.60 and avg_score > 0.3:
                    raw_multiplier = 1.2
                elif win_rate > 0.55 and avg_score > 0.2:
                    raw_multiplier = 1.1
                elif win_rate < 0.35 and avg_score < -0.2:
                    raw_multiplier = 0.7
                elif win_rate < 0.40 and avg_score < 0.0:
                    raw_multiplier = 0.85
                else:
                    raw_multiplier = 1.0

                # Apply bounds
                bounded = max(self.min_bound, min(self.max_bound, raw_multiplier))
                multipliers[keyword.lower()] = bounded

                logger.debug(
                    "keyword_multiplier_calculated keyword=%s win_rate=%.2f "
                    "avg_score=%.2f raw=%.2f bounded=%.2f",
                    keyword,
                    win_rate,
                    avg_score,
                    raw_multiplier,
                    bounded,
                )

            logger.info(
                "keyword_multipliers_fetched count=%d min=%.2f max=%.2f",
                len(multipliers),
                min(multipliers.values()) if multipliers else 1.0,
                max(multipliers.values()) if multipliers else 1.0,
            )

            return multipliers

        except Exception as e:
            logger.error("failed_to_fetch_multipliers error=%s", str(e))
            # Graceful degradation - return empty dict (all keywords get 1.0)
            return {}

    def refresh_cache(self) -> None:
        """Force refresh cache (for testing/admin commands)."""
        with self._lock:
            self._cache = None
        logger.info("keyword_multiplier_cache_cleared")

    def get_all_multipliers(self) -> Dict[str, float]:
        """Get all cached multipliers (for debugging/health endpoint)."""
        settings = get_settings()
        if not settings.feature_feedback_signal_integration:
            return {}
        return self._get_cached_multipliers()

    def get_cache_info(self) -> Dict:
        """Get cache status information."""
        with self._lock:
            if self._cache:
                return {
                    "cached": True,
                    "expires_at": self._cache.expires_at.isoformat(),
                    "multiplier_count": len(self._cache.multipliers),
                    "ttl_minutes": self.cache_ttl_minutes,
                }
            return {
                "cached": False,
                "ttl_minutes": self.cache_ttl_minutes,
            }


# Module-level singleton for efficiency
_provider_instance: Optional[KeywordPerformanceProvider] = None
_provider_lock = Lock()


def get_keyword_performance_provider() -> KeywordPerformanceProvider:
    """Get or create the singleton KeywordPerformanceProvider."""
    global _provider_instance
    with _provider_lock:
        if _provider_instance is None:
            _provider_instance = KeywordPerformanceProvider()
        return _provider_instance
