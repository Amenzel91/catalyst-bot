"""Google Trends sentiment source for Catalyst-Bot.

This module provides retail investor search volume analysis as a sentiment
indicator. Research shows that Google search volume spikes 12-48 hours before
significant price moves, making it a valuable leading indicator for retail
interest and potential volatility.

The module uses the pytrends library to fetch search interest data from Google
Trends and calculates sentiment based on search volume spikes relative to
baseline levels.

Rate Limiting & Caching:
    - Google Trends has strict rate limits (429 errors are common)
    - Implements exponential backoff on failures
    - Caches results for 4-6 hours (search trends don't change rapidly)
    - Handles connection errors gracefully without crashing the pipeline

Sentiment Calculation:
    - Baseline: 7-day average search interest
    - Current: Last 24-hour average search interest
    - Spike ratio: current / baseline
    - Sentiment mapping:
        * spike_ratio > 20: +0.8 (extreme hype - caution)
        * spike_ratio > 10: +0.6 (viral attention)
        * spike_ratio > 5: +0.4 (significant retail interest)
        * declining search: 0.0 (lack of interest ≠ negative)
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import time
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

log = logging.getLogger(__name__)

# Cache configuration
CACHE_TTL_HOURS = 4  # Cache results for 4 hours
CACHE_DIR = Path("data/cache/google_trends")

# Rate limiting configuration
MIN_REQUEST_INTERVAL = 2.0  # Minimum seconds between requests
MAX_RETRIES = 3
BACKOFF_FACTOR = 2.0  # Exponential backoff multiplier


def _get_cache_path(ticker: str) -> Path:
    """Get cache file path for a ticker.

    Args:
        ticker: Stock ticker symbol

    Returns:
        Path to cache file for this ticker
    """
    # Create cache directory if it doesn't exist
    CACHE_DIR.mkdir(parents=True, exist_ok=True)

    # Use ticker hash for filename to avoid filesystem issues
    ticker_hash = hashlib.md5(ticker.upper().encode()).hexdigest()
    return CACHE_DIR / f"{ticker_hash}.json"


def _get_cached_result(ticker: str) -> Optional[Dict[str, Any]]:
    """Retrieve cached Google Trends result if valid.

    Args:
        ticker: Stock ticker symbol

    Returns:
        Cached result dict or None if cache miss/expired
    """
    cache_path = _get_cache_path(ticker)

    if not cache_path.exists():
        return None

    try:
        with open(cache_path, 'r', encoding='utf-8') as f:
            cached = json.load(f)

        # Check if cache is still valid
        cached_time = cached.get("timestamp", 0)
        age_hours = (time.time() - cached_time) / 3600

        if age_hours < CACHE_TTL_HOURS:
            log.debug(
                "google_trends_cache_hit ticker=%s age_hours=%.1f",
                ticker,
                age_hours
            )
            return cached.get("result")
        else:
            log.debug(
                "google_trends_cache_expired ticker=%s age_hours=%.1f",
                ticker,
                age_hours
            )
            # Clean up expired cache
            cache_path.unlink(missing_ok=True)
            return None

    except Exception as e:
        log.debug(
            "google_trends_cache_read_error ticker=%s err=%s",
            ticker,
            e.__class__.__name__
        )
        return None


def _cache_result(ticker: str, result: Dict[str, Any]) -> None:
    """Cache Google Trends result for future use.

    Args:
        ticker: Stock ticker symbol
        result: Result dict to cache
    """
    cache_path = _get_cache_path(ticker)

    try:
        cached_data = {
            "timestamp": time.time(),
            "ticker": ticker.upper(),
            "result": result
        }

        with open(cache_path, 'w', encoding='utf-8') as f:
            json.dump(cached_data, f, indent=2)

        log.debug("google_trends_cached ticker=%s", ticker)

    except Exception as e:
        log.debug(
            "google_trends_cache_write_error ticker=%s err=%s",
            ticker,
            e.__class__.__name__
        )


def _calculate_sentiment_from_trends(
    trends_data: Any,
    ticker: str
) -> Tuple[float, Dict[str, Any]]:
    """Calculate sentiment score from Google Trends data.

    Args:
        trends_data: DataFrame from pytrends interest_over_time()
        ticker: Stock ticker symbol

    Returns:
        Tuple of (sentiment_score, metadata)
        - sentiment_score: -1.0 to +1.0 (0.0 for declining/neutral)
        - metadata: Dict with search_interest, spike_ratio, trend_direction
    """
    import pandas as pd

    if trends_data is None or trends_data.empty:
        log.debug("google_trends_no_data ticker=%s", ticker)
        return 0.0, {
            "search_interest": 0,
            "spike_ratio": 0.0,
            "trend_direction": "NO_DATA"
        }

    try:
        # Get ticker column (pytrends uses uppercase ticker as column name)
        ticker_col = ticker.upper()
        if ticker_col not in trends_data.columns:
            log.debug(
                "google_trends_ticker_not_in_columns ticker=%s columns=%s",
                ticker,
                list(trends_data.columns)
            )
            return 0.0, {
                "search_interest": 0,
                "spike_ratio": 0.0,
                "trend_direction": "NO_DATA"
            }

        # Get search interest values
        interest_values = trends_data[ticker_col].values

        # Filter out zero values for more accurate baseline
        non_zero_values = interest_values[interest_values > 0]

        if len(non_zero_values) == 0:
            log.debug("google_trends_all_zero ticker=%s", ticker)
            return 0.0, {
                "search_interest": 0,
                "spike_ratio": 0.0,
                "trend_direction": "NO_INTEREST"
            }

        # Calculate baseline (7-day average, excluding zeros)
        # For hourly data over 7 days, we have ~168 data points
        # Use all non-zero values for baseline
        baseline = float(non_zero_values.mean())

        # Calculate current interest (last 24 hours)
        # For hourly data, last 24 points = last 24 hours
        last_24h = interest_values[-24:] if len(interest_values) >= 24 else interest_values
        last_24h_nonzero = last_24h[last_24h > 0]

        if len(last_24h_nonzero) == 0:
            current_interest = 0.0
        else:
            current_interest = float(last_24h_nonzero.mean())

        # Calculate spike ratio
        if baseline > 0:
            spike_ratio = current_interest / baseline
        else:
            spike_ratio = 1.0

        # Determine trend direction
        if spike_ratio > 1.2:
            trend_direction = "RISING"
        elif spike_ratio < 0.8:
            trend_direction = "DECLINING"
        else:
            trend_direction = "STABLE"

        # Calculate sentiment based on spike ratio
        # We ONLY assign positive sentiment for rising trends
        # Declining search interest doesn't mean negative sentiment
        sentiment = 0.0

        if spike_ratio > 20:
            # Extreme hype - caution warranted
            sentiment = 0.8
        elif spike_ratio > 10:
            # Viral attention
            sentiment = 0.6
        elif spike_ratio > 5:
            # Significant retail interest
            sentiment = 0.4
        elif spike_ratio > 3:
            # Moderate interest increase
            sentiment = 0.2
        elif spike_ratio > 2:
            # Slight interest increase
            sentiment = 0.1
        # else: spike_ratio <= 2 or declining = 0.0 (neutral)

        metadata = {
            "search_interest": int(current_interest),
            "baseline_interest": int(baseline),
            "spike_ratio": round(spike_ratio, 2),
            "trend_direction": trend_direction
        }

        log.info(
            "google_trends_sentiment_calculated ticker=%s sentiment=%.2f "
            "spike_ratio=%.2fx current=%d baseline=%d direction=%s",
            ticker,
            sentiment,
            spike_ratio,
            int(current_interest),
            int(baseline),
            trend_direction
        )

        return sentiment, metadata

    except Exception as e:
        log.warning(
            "google_trends_calculation_failed ticker=%s err=%s",
            ticker,
            e.__class__.__name__
        )
        return 0.0, {
            "search_interest": 0,
            "spike_ratio": 0.0,
            "trend_direction": "ERROR"
        }


def _fetch_google_trends(
    ticker: str,
    retry_count: int = 0
) -> Optional[Any]:
    """Fetch Google Trends data with exponential backoff.

    Args:
        ticker: Stock ticker symbol
        retry_count: Current retry attempt (for exponential backoff)

    Returns:
        DataFrame from pytrends or None on error
    """
    try:
        from pytrends.request import TrendReq
    except ImportError:
        log.debug("google_trends_pytrends_not_installed ticker=%s", ticker)
        return None

    try:
        # Initialize pytrends with random delay to avoid rate limiting
        pytrend = TrendReq(hl='en-US', tz=360)

        # Build search query
        # For common word tickers (A, PLAY, etc.), add "stock" for disambiguation
        ticker_upper = ticker.upper()
        search_term = ticker_upper

        # Add "stock" suffix for single-letter tickers or common words
        if len(ticker_upper) <= 2 or ticker_upper in {
            'PLAY', 'BEST', 'TRUE', 'REAL', 'HOME', 'NICE'
        }:
            search_term = f"{ticker_upper} stock"

        # Build payload - last 7 days hourly data
        pytrend.build_payload([search_term], timeframe='now 7-d')

        # Add rate limiting delay
        time.sleep(MIN_REQUEST_INTERVAL)

        # Get interest over time
        trends_df = pytrend.interest_over_time()

        log.debug(
            "google_trends_fetched ticker=%s search_term=%s rows=%d",
            ticker,
            search_term,
            len(trends_df) if trends_df is not None else 0
        )

        return trends_df

    except Exception as e:
        error_msg = str(e)

        # Handle rate limiting (429)
        if "429" in error_msg or "too many requests" in error_msg.lower():
            if retry_count < MAX_RETRIES:
                # Exponential backoff
                backoff_delay = MIN_REQUEST_INTERVAL * (BACKOFF_FACTOR ** retry_count)
                log.warning(
                    "google_trends_rate_limited ticker=%s retry=%d delay=%.1fs",
                    ticker,
                    retry_count + 1,
                    backoff_delay
                )
                time.sleep(backoff_delay)
                return _fetch_google_trends(ticker, retry_count + 1)
            else:
                log.warning(
                    "google_trends_rate_limit_exceeded ticker=%s retries=%d",
                    ticker,
                    retry_count
                )
                return None

        # Handle other errors gracefully
        log.debug(
            "google_trends_fetch_error ticker=%s err=%s msg=%s",
            ticker,
            e.__class__.__name__,
            error_msg[:100]
        )
        return None


def get_google_trends_sentiment(
    ticker: str
) -> Optional[Tuple[float, str, Dict[str, Any]]]:
    """Get sentiment from Google Trends search volume.

    This function fetches Google search interest data for a ticker and
    calculates sentiment based on search volume spikes. Rising search
    volume indicates increasing retail interest and often precedes price
    moves by 12-48 hours.

    Args:
        ticker: Stock ticker symbol

    Returns:
        Tuple of (score, label, metadata) or None on error/no data
        - score: Sentiment score from 0.0 to 1.0 (never negative)
        - label: "Bullish", "Neutral", or "Bearish"
        - metadata: Dict with search_interest, spike_ratio, trend_direction

    Rate Limiting:
        - Implements exponential backoff on 429 errors
        - Caches results for 4 hours to minimize API calls
        - Adds delays between requests

    Edge Cases:
        - OTC tickers: Adds "stock" to search query
        - Common word tickers: Adds "stock" for disambiguation
        - No search data: Returns None (not all tickers are searched)
        - Low volume stocks: May return empty data
    """
    if not ticker:
        return None

    # Check if feature is enabled
    feature_enabled = os.getenv("FEATURE_GOOGLE_TRENDS", "0") == "1"
    if not feature_enabled:
        return None

    ticker_upper = ticker.upper().strip()

    # Check cache first
    cached = _get_cached_result(ticker_upper)
    if cached is not None:
        score = cached.get("score", 0.0)
        label = cached.get("label", "Neutral")
        metadata = cached.get("metadata", {})

        log.debug(
            "google_trends_using_cache ticker=%s score=%.2f",
            ticker_upper,
            score
        )
        return score, label, metadata

    # Fetch fresh data
    trends_data = _fetch_google_trends(ticker_upper)

    if trends_data is None:
        # Don't cache failures - allow retry on next cycle
        return None

    # Calculate sentiment
    sentiment, metadata = _calculate_sentiment_from_trends(trends_data, ticker_upper)

    # Map sentiment to label
    if sentiment >= 0.05:
        label = "Bullish"
    elif sentiment <= -0.05:
        label = "Bearish"
    else:
        label = "Neutral"

    # Prepare result for caching
    result = {
        "score": sentiment,
        "label": label,
        "metadata": metadata
    }

    # Cache the result
    _cache_result(ticker_upper, result)

    return sentiment, label, metadata


def clear_google_trends_cache(ticker: Optional[str] = None) -> None:
    """Clear Google Trends cache for a ticker or all tickers.

    Args:
        ticker: Optional ticker symbol. If None, clears all cache files.
    """
    if ticker:
        # Clear specific ticker
        cache_path = _get_cache_path(ticker)
        if cache_path.exists():
            cache_path.unlink()
            log.info("google_trends_cache_cleared ticker=%s", ticker)
    else:
        # Clear all cache files
        if CACHE_DIR.exists():
            for cache_file in CACHE_DIR.glob("*.json"):
                cache_file.unlink()
            log.info("google_trends_cache_cleared_all")
