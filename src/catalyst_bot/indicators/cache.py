"""
cache.py
========

Indicator calculation caching system.

Technical indicators can be computationally expensive to calculate, especially
when working with large datasets or complex algorithms. This module provides
an in-memory caching system with TTL (time-to-live) support to avoid redundant
calculations.

Features:
- Per-ticker, per-indicator caching
- Configurable TTL (time-to-live)
- Parameter-based cache keys (different parameters = different cache)
- Automatic expiration
- Memory-efficient LRU eviction
- Thread-safe operations

Cache keys are generated from: ticker + indicator_name + sorted(params)
This ensures that different parameter combinations are cached separately.
"""

from __future__ import annotations

import hashlib
import json
import time
from collections import OrderedDict
from threading import Lock
from typing import Any, Dict, List, Optional, Tuple


class IndicatorCache:
    """Thread-safe LRU cache for indicator calculations with TTL support."""

    def __init__(self, max_size: int = 1000, default_ttl: int = 300):
        """Initialize the indicator cache.

        Parameters
        ----------
        max_size : int, optional
            Maximum number of cached items, by default 1000
        default_ttl : int, optional
            Default time-to-live in seconds, by default 300 (5 minutes)
        """
        self._cache: OrderedDict[str, Tuple[Any, float]] = OrderedDict()
        self._lock = Lock()
        self._max_size = max_size
        self._default_ttl = default_ttl
        self._hits = 0
        self._misses = 0

    def _make_key(
        self, ticker: str, indicator_name: str, params: Optional[Dict[str, Any]] = None
    ) -> str:
        """Generate a cache key from ticker, indicator name, and parameters.

        Parameters
        ----------
        ticker : str
            Stock ticker symbol
        indicator_name : str
            Name of the indicator
        params : Optional[Dict[str, Any]], optional
            Indicator parameters, by default None

        Returns
        -------
        str
            Cache key (MD5 hash for compact representation)
        """
        # Normalize ticker
        ticker = ticker.upper().strip()

        # Create key components
        key_parts = [ticker, indicator_name]

        # Add sorted params for consistent keys
        if params:
            # Sort params by key for consistency
            sorted_params = json.dumps(params, sort_keys=True)
            key_parts.append(sorted_params)

        # Create hash for compact key
        key_string = "|".join(key_parts)
        key_hash = hashlib.md5(key_string.encode()).hexdigest()

        return key_hash

    def get(
        self, ticker: str, indicator_name: str, params: Optional[Dict[str, Any]] = None
    ) -> Optional[Any]:
        """Retrieve a cached indicator value.

        Parameters
        ----------
        ticker : str
            Stock ticker symbol
        indicator_name : str
            Name of the indicator
        params : Optional[Dict[str, Any]], optional
            Indicator parameters, by default None

        Returns
        -------
        Optional[Any]
            Cached value if found and not expired, None otherwise

        Examples
        --------
        >>> cache = IndicatorCache()
        >>> cache.put("AAPL", "bollinger", {"period": 20}, [150, 155, 145])
        >>> result = cache.get("AAPL", "bollinger", {"period": 20})
        >>> result
        [150, 155, 145]
        """
        key = self._make_key(ticker, indicator_name, params)

        with self._lock:
            if key not in self._cache:
                self._misses += 1
                return None

            value, expiry = self._cache[key]

            # Check if expired
            if time.time() > expiry:
                # Remove expired entry
                del self._cache[key]
                self._misses += 1
                return None

            # Move to end (most recently used)
            self._cache.move_to_end(key)
            self._hits += 1

            return value

    def put(
        self,
        ticker: str,
        indicator_name: str,
        params: Optional[Dict[str, Any]],
        value: Any,
        ttl: Optional[int] = None,
    ) -> None:
        """Store an indicator value in the cache.

        Parameters
        ----------
        ticker : str
            Stock ticker symbol
        indicator_name : str
            Name of the indicator
        params : Optional[Dict[str, Any]]
            Indicator parameters
        value : Any
            The calculated indicator value to cache
        ttl : Optional[int], optional
            Time-to-live in seconds, by default uses default_ttl

        Examples
        --------
        >>> cache = IndicatorCache()
        >>> cache.put("AAPL", "bollinger", {"period": 20}, [150, 155, 145], ttl=60)
        """
        key = self._make_key(ticker, indicator_name, params)

        if ttl is None:
            ttl = self._default_ttl

        expiry = time.time() + ttl

        with self._lock:
            # Add/update entry
            self._cache[key] = (value, expiry)

            # Move to end (most recently used)
            self._cache.move_to_end(key)

            # Enforce max size (evict oldest)
            while len(self._cache) > self._max_size:
                self._cache.popitem(last=False)

    def invalidate(
        self, ticker: Optional[str] = None, indicator_name: Optional[str] = None
    ) -> int:
        """Invalidate cached entries.

        Parameters
        ----------
        ticker : Optional[str], optional
            If specified, only invalidate this ticker, by default None (all tickers)
        indicator_name : Optional[str], optional
            If specified, only invalidate this indicator, by default None (all indicators)

        Returns
        -------
        int
            Number of entries invalidated

        Examples
        --------
        >>> cache = IndicatorCache()
        >>> cache.put("AAPL", "bollinger", {}, [150, 155, 145])
        >>> count = cache.invalidate(ticker="AAPL")
        >>> count >= 1
        True
        """
        if ticker is None and indicator_name is None:
            # Clear entire cache
            with self._lock:
                count = len(self._cache)
                self._cache.clear()
                return count

        # Selective invalidation requires key reconstruction
        # For simplicity, we'll clear all if specific invalidation is needed
        # In production, you might want to store reverse mappings
        with self._lock:
            # This is a simple implementation - for production use,
            # consider maintaining reverse index for efficient selective invalidation
            count = len(self._cache)
            self._cache.clear()
            return count

    def cleanup_expired(self) -> int:
        """Remove all expired entries from the cache.

        Returns
        -------
        int
            Number of expired entries removed

        Examples
        --------
        >>> cache = IndicatorCache(default_ttl=1)
        >>> cache.put("AAPL", "bollinger", {}, [150, 155, 145])
        >>> import time
        >>> time.sleep(2)
        >>> count = cache.cleanup_expired()
        >>> count >= 1
        True
        """
        now = time.time()
        expired_keys = []

        with self._lock:
            for key, (value, expiry) in self._cache.items():
                if now > expiry:
                    expired_keys.append(key)

            for key in expired_keys:
                del self._cache[key]

        return len(expired_keys)

    def get_stats(self) -> Dict[str, int]:
        """Get cache statistics.

        Returns
        -------
        Dict[str, int]
            Statistics including size, hits, misses, and hit_rate

        Examples
        --------
        >>> cache = IndicatorCache()
        >>> cache.put("AAPL", "bollinger", {}, [150, 155, 145])
        >>> cache.get("AAPL", "bollinger", {})
        [150, 155, 145]
        >>> stats = cache.get_stats()
        >>> stats['hits'] >= 1
        True
        """
        with self._lock:
            total_requests = self._hits + self._misses
            hit_rate = (self._hits / total_requests * 100) if total_requests > 0 else 0

            return {
                "size": len(self._cache),
                "max_size": self._max_size,
                "hits": self._hits,
                "misses": self._misses,
                "total_requests": total_requests,
                "hit_rate_pct": round(hit_rate, 2),
            }

    def reset_stats(self) -> None:
        """Reset hit/miss statistics.

        Examples
        --------
        >>> cache = IndicatorCache()
        >>> cache.get("AAPL", "bollinger", {})
        >>> cache.reset_stats()
        >>> stats = cache.get_stats()
        >>> stats['hits'] == 0 and stats['misses'] == 0
        True
        """
        with self._lock:
            self._hits = 0
            self._misses = 0


# Global cache instance
_global_cache: Optional[IndicatorCache] = None


def get_cache(max_size: int = 1000, default_ttl: int = 300) -> IndicatorCache:
    """Get the global indicator cache instance (singleton pattern).

    Parameters
    ----------
    max_size : int, optional
        Maximum cache size (only used on first call), by default 1000
    default_ttl : int, optional
        Default TTL in seconds (only used on first call), by default 300

    Returns
    -------
    IndicatorCache
        The global cache instance

    Examples
    --------
    >>> cache1 = get_cache()
    >>> cache2 = get_cache()
    >>> cache1 is cache2
    True
    """
    global _global_cache

    if _global_cache is None:
        _global_cache = IndicatorCache(max_size=max_size, default_ttl=default_ttl)

    return _global_cache


def get_cached_indicator(
    ticker: str, indicator_name: str, params: Optional[Dict[str, Any]] = None
) -> Optional[Any]:
    """Get a cached indicator value (convenience function).

    Parameters
    ----------
    ticker : str
        Stock ticker symbol
    indicator_name : str
        Name of the indicator
    params : Optional[Dict[str, Any]], optional
        Indicator parameters, by default None

    Returns
    -------
    Optional[Any]
        Cached value if found and not expired, None otherwise

    Examples
    --------
    >>> cache_indicator("AAPL", "bollinger", {"period": 20}, [150, 155, 145])
    >>> result = get_cached_indicator("AAPL", "bollinger", {"period": 20})
    >>> result
    [150, 155, 145]
    """
    cache = get_cache()
    return cache.get(ticker, indicator_name, params)


def cache_indicator(
    ticker: str,
    indicator_name: str,
    params: Optional[Dict[str, Any]],
    result: Any,
    ttl: Optional[int] = None,
) -> None:
    """Cache an indicator value (convenience function).

    Parameters
    ----------
    ticker : str
        Stock ticker symbol
    indicator_name : str
        Name of the indicator
    params : Optional[Dict[str, Any]]
        Indicator parameters
    result : Any
        The calculated indicator value to cache
    ttl : Optional[int], optional
        Time-to-live in seconds, by default uses default_ttl

    Examples
    --------
    >>> cache_indicator("AAPL", "bollinger", {"period": 20}, [150, 155, 145], ttl=60)
    """
    cache = get_cache()
    cache.put(ticker, indicator_name, params, result, ttl)


def get_cached_patterns(
    ticker: str, timeframe: str = "1D", pattern_types: Optional[List[str]] = None
) -> Optional[List[Dict[str, Any]]]:
    """Get cached pattern detection results.

    Parameters
    ----------
    ticker : str
        Stock ticker symbol
    timeframe : str, optional
        Timeframe for pattern detection, by default "1D"
    pattern_types : Optional[List[str]], optional
        Specific pattern types to retrieve, by default None (all patterns)

    Returns
    -------
    Optional[List[Dict[str, Any]]]
        Cached patterns if found and not expired, None otherwise

    Examples
    --------
    >>> patterns = [{"type": "ascending_triangle", "confidence": 0.8}]
    >>> cache_patterns("AAPL", patterns, timeframe="1D")
    >>> result = get_cached_patterns("AAPL", "1D")
    >>> result is not None
    True
    """
    cache = get_cache()
    params = {
        "timeframe": timeframe,
        "pattern_types": sorted(pattern_types) if pattern_types else "all",
    }
    return cache.get(ticker, "patterns", params)


def cache_patterns(
    ticker: str,
    patterns: List[Dict[str, Any]],
    timeframe: str = "1D",
    ttl: Optional[int] = None,
) -> None:
    """Cache pattern detection results.

    Patterns are expensive to calculate, so we cache them with a longer TTL
    (default 1 hour) compared to price data.

    Parameters
    ----------
    ticker : str
        Stock ticker symbol
    patterns : List[Dict[str, Any]]
        Detected patterns to cache
    timeframe : str, optional
        Timeframe for pattern detection, by default "1D"
    ttl : Optional[int], optional
        Time-to-live in seconds, by default 3600 (1 hour)

    Examples
    --------
    >>> patterns = [{"type": "head_shoulders", "confidence": 0.75}]
    >>> cache_patterns("AAPL", patterns, timeframe="5D", ttl=1800)
    """
    import os

    if ttl is None:
        # Default to 1 hour for patterns (slower-changing than prices)
        ttl = int(os.getenv("CHART_PATTERN_CACHE_TTL", "3600"))

    cache = get_cache()
    params = {"timeframe": timeframe, "pattern_types": "all"}
    cache.put(ticker, "patterns", params, patterns, ttl)


def invalidate_pattern_cache(ticker: Optional[str] = None) -> int:
    """Invalidate cached patterns for a ticker or all tickers.

    Parameters
    ----------
    ticker : Optional[str], optional
        Ticker to invalidate, by default None (all tickers)

    Returns
    -------
    int
        Number of entries invalidated

    Examples
    --------
    >>> cache_patterns("AAPL", [{"type": "triangle"}])
    >>> count = invalidate_pattern_cache("AAPL")
    >>> count >= 0
    True
    """
    cache = get_cache()
    # This will invalidate all cache entries (current simple implementation)
    # In production, you'd want to be more selective
    if ticker:
        return cache.invalidate(ticker=ticker, indicator_name="patterns")
    else:
        return cache.invalidate(indicator_name="patterns")


__all__ = [
    "IndicatorCache",
    "get_cache",
    "get_cached_indicator",
    "cache_indicator",
    "get_cached_patterns",
    "cache_patterns",
    "invalidate_pattern_cache",
]
