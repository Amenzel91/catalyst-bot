"""
RVOL (Relative Volume) Calculator
==================================

Real-time intraday RVol calculation for pre-catalyst signal detection.
RVol is the "strongest predictor of post-catalyst moves" per research.

RVOL Definition: Current intraday volume (extrapolated) / 20-day average volume
- RVOL > 5.0x = EXTREME (multiplier: 1.4x - very strong signal)
- RVOL 3.0-5.0x = HIGH (multiplier: 1.3x)
- RVOL 2.0-3.0x = ELEVATED (multiplier: 1.2x)
- RVOL 1.0-2.0x = NORMAL (multiplier: 1.0x - baseline)
- RVOL < 1.0x = LOW (multiplier: 0.8x - weak signal)

Features:
- Real-time intraday volume calculation with time-of-day adjustment
- 20-day average volume baseline (exclude today)
- 5-minute memory cache (TTL configurable)
- Historical backtesting support (MOA Agent 1 - legacy)
- Bulk fetching for multiple tickers
- Uses existing market.py data providers (yfinance, Tiingo, Alpha Vantage)

Key Insight: If it's 10:00 AM (30 min after open) and volume is already 50% of
average daily volume, that's actually 10x RVol when extrapolated to full trading day.

Author: Claude Code (Quick Win #4 + MOA Agent 1)
Date: 2025-10-13
"""

from __future__ import annotations

import hashlib
import pickle
import time
from datetime import datetime, time as dt_time, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import yfinance as yf

from .config import get_settings
from .logging_utils import get_logger

log = get_logger("rvol")

# Cache configuration - DUAL MODE
RVOL_CACHE_TTL_DAYS = 1  # Historical backtesting cache (1 day TTL)
RVOL_INTRADAY_CACHE_TTL_SEC = 300  # Real-time intraday cache (5 minutes)
RVOL_CACHE_DIR = Path("data/cache/rvol")

# Volume calculation parameters
VOLUME_LOOKBACK_DAYS = 20  # 20-day average volume
MIN_VOLUME_THRESHOLD = 10000  # Minimum daily volume to be considered valid

# Market hours (US Eastern Time)
MARKET_OPEN_TIME = dt_time(9, 30)  # 9:30 AM ET
MARKET_CLOSE_TIME = dt_time(16, 0)  # 4:00 PM ET
TRADING_HOURS = 6.5  # 6.5 hours in a full trading day


def _ensure_cache_dir() -> Path:
    """Ensure RVOL cache directory exists."""
    cache_dir = RVOL_CACHE_DIR
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir


def _get_cache_key(ticker: str, date: datetime) -> str:
    """
    Generate cache key for RVOL data.

    Args:
        ticker: Stock ticker
        date: Date for volume lookup

    Returns:
        Cache key string
    """
    date_str = date.strftime("%Y-%m-%d")
    return f"{ticker}_{date_str}"


def _get_disk_cache_path(ticker: str, date: datetime) -> Path:
    """
    Get disk cache file path for RVOL data.

    Args:
        ticker: Stock ticker
        date: Date for volume lookup

    Returns:
        Path to cache file
    """
    cache_dir = _ensure_cache_dir()
    cache_key = _get_cache_key(ticker, date)
    key_hash = hashlib.md5(cache_key.encode()).hexdigest()

    # Create 2-level directory structure: first 2 chars / next 2 chars
    subdir = cache_dir / key_hash[:2] / key_hash[2:4]
    subdir.mkdir(parents=True, exist_ok=True)

    return subdir / f"{cache_key}.pkl"


class RVOLCache:
    """Multi-level cache for RVOL data (memory + disk)."""

    def __init__(self):
        """Initialize RVOL cache."""
        self._memory_cache: Dict[Tuple[str, str], Dict] = {}
        self._cache_hits = 0
        self._cache_misses = 0
        self._disk_hits = 0

    def get(self, ticker: str, date: datetime) -> Optional[Dict]:
        """
        Get RVOL data from cache.

        Args:
            ticker: Stock ticker
            date: Date to fetch

        Returns:
            Cached RVOL data or None if not found
        """
        date_str = date.strftime("%Y-%m-%d")
        cache_key = (ticker, date_str)

        # Level 1: Memory cache
        if cache_key in self._memory_cache:
            self._cache_hits += 1
            return self._memory_cache[cache_key]

        # Level 2: Disk cache
        cache_path = _get_disk_cache_path(ticker, date)

        if cache_path.exists():
            try:
                with open(cache_path, "rb") as f:
                    cache_data = pickle.load(f)

                # Check TTL
                cached_date = cache_data.get("cached_at")
                if cached_date:
                    cache_age_days = (datetime.now(timezone.utc) - cached_date).days

                    if cache_age_days <= RVOL_CACHE_TTL_DAYS:
                        # Valid cache - load into memory and return
                        self._memory_cache[cache_key] = cache_data
                        self._disk_hits += 1
                        return cache_data

            except Exception as e:
                log.debug(f"disk_cache_load_failed ticker={ticker} err={e}")

        # Cache miss
        self._cache_misses += 1
        return None

    def put(self, ticker: str, date: datetime, data: Dict) -> None:
        """
        Put RVOL data in cache.

        Args:
            ticker: Stock ticker
            date: Date of data
            data: RVOL data dictionary
        """
        date_str = date.strftime("%Y-%m-%d")
        cache_key = (ticker, date_str)

        # Add timestamp
        data["cached_at"] = datetime.now(timezone.utc)

        # Store in memory cache
        self._memory_cache[cache_key] = data

        # Store in disk cache
        try:
            cache_path = _get_disk_cache_path(ticker, date)
            with open(cache_path, "wb") as f:
                pickle.dump(data, f)
        except Exception as e:
            log.debug(f"disk_cache_write_failed ticker={ticker} err={e}")

    def get_stats(self) -> Dict[str, int]:
        """Get cache statistics."""
        return {
            "memory_hits": self._cache_hits,
            "disk_hits": self._disk_hits,
            "misses": self._cache_misses,
            "total_requests": self._cache_hits + self._disk_hits + self._cache_misses,
        }


# Global cache instance
_rvol_cache = RVOLCache()


def calculate_rvol(
    ticker: str,
    date: datetime,
    *,
    use_cache: bool = True,
) -> Optional[Dict]:
    """
    Calculate RVOL (Relative Volume) for a ticker at a specific date.

    RVOL = Current volume / 20-day average volume

    Args:
        ticker: Stock ticker symbol
        date: Date to calculate RVOL for
        use_cache: Whether to use cached data (default: True)

    Returns:
        Dict with RVOL data:
        {
            "ticker": str,
            "date": str (ISO format),
            "current_volume": int,
            "avg_volume_20d": float,
            "rvol": float,
            "rvol_category": str ("HIGH", "MODERATE", "LOW"),
        }
        Returns None if insufficient data
    """
    ticker = ticker.strip().upper()

    # Check cache first
    if use_cache:
        cached_data = _rvol_cache.get(ticker, date)
        if cached_data is not None:
            return cached_data

    try:
        # Fetch historical data for lookback period
        start_date = date - timedelta(days=VOLUME_LOOKBACK_DAYS + 5)  # Add buffer
        end_date = date + timedelta(days=1)

        # Try Tiingo first if available
        settings = get_settings()
        hist_df = None

        if getattr(settings, "feature_tiingo", False) and getattr(
            settings, "tiingo_api_key", ""
        ):
            try:
                from .market import _tiingo_daily_history

                hist_df = _tiingo_daily_history(
                    ticker,
                    settings.tiingo_api_key,
                    start_date=start_date.strftime("%Y-%m-%d"),
                    end_date=end_date.strftime("%Y-%m-%d"),
                )
            except Exception as e:
                log.debug(f"tiingo_volume_fetch_failed ticker={ticker} err={e}")

        # Fallback to yfinance
        if hist_df is None or (hasattr(hist_df, "empty") and hist_df.empty):
            ticker_obj = yf.Ticker(ticker)
            hist_df = ticker_obj.history(
                start=start_date.strftime("%Y-%m-%d"),
                end=end_date.strftime("%Y-%m-%d"),
                interval="1d",
            )

        if hist_df is None or hist_df.empty:
            log.debug(f"rvol_no_data ticker={ticker} date={date.date()}")
            return None

        # Get volume data
        if "Volume" not in hist_df.columns:
            log.debug(f"rvol_no_volume_column ticker={ticker}")
            return None

        # Filter to get data up to and including target date
        hist_df = hist_df[hist_df.index <= date]

        if len(hist_df) < VOLUME_LOOKBACK_DAYS:
            log.debug(
                f"rvol_insufficient_data ticker={ticker} "
                f"rows={len(hist_df)} required={VOLUME_LOOKBACK_DAYS}"
            )
            return None

        # Get last 20 days of volume data
        volume_series = hist_df["Volume"].tail(VOLUME_LOOKBACK_DAYS)

        # Calculate average volume (excluding zero volume days)
        valid_volumes = volume_series[volume_series > MIN_VOLUME_THRESHOLD]

        if (
            len(valid_volumes) < VOLUME_LOOKBACK_DAYS * 0.5
        ):  # Need at least 50% valid days
            log.debug(
                f"rvol_insufficient_valid_days ticker={ticker} valid={len(valid_volumes)}"
            )
            return None

        avg_volume_20d = float(valid_volumes.mean())

        # Get current volume (most recent day)
        current_volume = int(volume_series.iloc[-1])

        # Calculate RVOL
        if avg_volume_20d == 0:
            log.debug(f"rvol_zero_avg_volume ticker={ticker}")
            return None

        rvol = current_volume / avg_volume_20d

        # Categorize RVOL
        if rvol >= 2.0:
            rvol_category = "HIGH"
        elif rvol >= 1.0:
            rvol_category = "MODERATE"
        else:
            rvol_category = "LOW"

        # Build result
        result = {
            "ticker": ticker,
            "date": date.strftime("%Y-%m-%d"),
            "current_volume": current_volume,
            "avg_volume_20d": round(avg_volume_20d, 2),
            "rvol": round(rvol, 2),
            "rvol_category": rvol_category,
        }

        # Cache result
        if use_cache:
            _rvol_cache.put(ticker, date, result)

        log.debug(
            f"rvol_calculated ticker={ticker} rvol={rvol:.2f} "
            f"category={rvol_category}"
        )

        return result

    except Exception as e:
        log.warning(
            f"rvol_calculation_failed ticker={ticker} date={date.date()} err={e}"
        )
        return None


def bulk_calculate_rvol(
    tickers: list[str],
    date: datetime,
    *,
    use_cache: bool = True,
) -> Dict[str, Optional[Dict]]:
    """
    Calculate RVOL for multiple tickers at once (bulk operation).

    Uses batch fetching for efficiency. Significantly faster than calling
    calculate_rvol() in a loop.

    Args:
        tickers: List of ticker symbols
        date: Date to calculate RVOL for
        use_cache: Whether to use cached data (default: True)

    Returns:
        Dict mapping ticker -> RVOL data (or None if calculation failed)

    Examples:
        >>> rvol_data = bulk_calculate_rvol(['AAPL', 'MSFT', 'GOOGL'], datetime.now())
        >>> rvol_data['AAPL']
        {'ticker': 'AAPL', 'rvol': 1.5, 'rvol_category': 'MODERATE', ...}
    """
    if not tickers:
        return {}

    results = {}
    to_fetch = []

    # Normalize tickers
    normalized_tickers = [t.strip().upper() for t in tickers if t and t.strip()]

    # Check cache first
    if use_cache:
        for ticker in normalized_tickers:
            cached_data = _rvol_cache.get(ticker, date)
            if cached_data is not None:
                results[ticker] = cached_data
            else:
                to_fetch.append(ticker)
    else:
        to_fetch = normalized_tickers

    if not to_fetch:
        return results

    # Fetch data for remaining tickers
    try:
        start_date = date - timedelta(days=VOLUME_LOOKBACK_DAYS + 5)
        end_date = date + timedelta(days=1)

        # Bulk fetch via yfinance (fastest for multiple tickers)
        data = yf.download(
            tickers=" ".join(to_fetch),
            start=start_date.strftime("%Y-%m-%d"),
            end=end_date.strftime("%Y-%m-%d"),
            interval="1d",
            threads=True,
            progress=False,
        )

        if data is None or data.empty:
            log.warning(f"bulk_rvol_no_data tickers={len(to_fetch)}")
            return results

        # Process each ticker
        for ticker in to_fetch:
            try:
                # Extract ticker data
                if len(to_fetch) == 1:
                    ticker_data = data
                else:
                    # Multi-ticker: data.columns is MultiIndex
                    try:
                        ticker_data = data.xs(ticker, level=1, axis=1, drop_level=True)
                    except (KeyError, AttributeError):
                        # Ticker not found in results
                        results[ticker] = None
                        continue

                if ticker_data.empty or "Volume" not in ticker_data.columns:
                    results[ticker] = None
                    continue

                # Filter to get data up to and including target date
                ticker_data = ticker_data[ticker_data.index <= date]

                if len(ticker_data) < VOLUME_LOOKBACK_DAYS:
                    results[ticker] = None
                    continue

                # Get last 20 days of volume data
                volume_series = ticker_data["Volume"].tail(VOLUME_LOOKBACK_DAYS)

                # Calculate average volume (excluding zero volume days)
                valid_volumes = volume_series[volume_series > MIN_VOLUME_THRESHOLD]

                if len(valid_volumes) < VOLUME_LOOKBACK_DAYS * 0.5:
                    results[ticker] = None
                    continue

                avg_volume_20d = float(valid_volumes.mean())
                current_volume = int(volume_series.iloc[-1])

                # Calculate RVOL
                if avg_volume_20d == 0:
                    results[ticker] = None
                    continue

                rvol = current_volume / avg_volume_20d

                # Categorize RVOL
                if rvol >= 2.0:
                    rvol_category = "HIGH"
                elif rvol >= 1.0:
                    rvol_category = "MODERATE"
                else:
                    rvol_category = "LOW"

                # Build result
                result = {
                    "ticker": ticker,
                    "date": date.strftime("%Y-%m-%d"),
                    "current_volume": current_volume,
                    "avg_volume_20d": round(avg_volume_20d, 2),
                    "rvol": round(rvol, 2),
                    "rvol_category": rvol_category,
                }

                results[ticker] = result

                # Cache result
                if use_cache:
                    _rvol_cache.put(ticker, date, result)

            except Exception as e:
                log.debug(f"bulk_rvol_ticker_failed ticker={ticker} err={e}")
                results[ticker] = None

        log.info(
            f"bulk_rvol_complete requested={len(normalized_tickers)} "
            f"cached={len(normalized_tickers) - len(to_fetch)} "
            f"fetched={len(to_fetch)} "
            f"successful={sum(1 for v in results.values() if v is not None)}"
        )

    except Exception as e:
        log.warning(f"bulk_rvol_failed tickers={len(to_fetch)} err={e}")
        # Fill in None for failed tickers
        for ticker in to_fetch:
            if ticker not in results:
                results[ticker] = None

    # Fill in results for all requested tickers
    for ticker in normalized_tickers:
        if ticker not in results:
            results[ticker] = None

    return results


def get_cache_stats() -> Dict[str, int]:
    """
    Get RVOL cache statistics.

    Returns:
        Dict with cache hit/miss counts
    """
    return _rvol_cache.get_stats()


# ==============================================================================
# REAL-TIME INTRADAY RVOL CALCULATION (Quick Win #4)
# ==============================================================================
# These functions provide real-time RVol calculation with time-of-day adjustment
# for detecting unusual volume spikes before price moves (pre-catalyst indicator).


# In-memory cache for real-time RVol (5-minute TTL)
_intraday_cache: Dict[str, Dict[str, Any]] = {}


def calculate_hours_since_market_open() -> float:
    """
    Calculate hours since 9:30 AM ET market open.

    Returns:
        Hours since market open (0.0 if pre-market, 6.5 if after close)
    """
    try:
        # Get current time in ET timezone
        try:
            from zoneinfo import ZoneInfo

            et_tz = ZoneInfo("America/New_York")
        except ImportError:
            try:
                from backports.zoneinfo import ZoneInfo  # type: ignore

                et_tz = ZoneInfo("America/New_York")
            except ImportError:
                # Fallback: assume UTC and apply -5 hour offset (EST)
                log.warning("zoneinfo_unavailable using_utc_fallback")
                et_tz = timezone.utc  # type: ignore

        now = datetime.now(et_tz)
        current_time = now.time()

        # Pre-market (before 9:30 AM)
        if current_time < MARKET_OPEN_TIME:
            return 0.0

        # After market close (after 4:00 PM)
        if current_time >= MARKET_CLOSE_TIME:
            return TRADING_HOURS

        # During market hours: calculate hours since 9:30 AM
        market_open_dt = datetime.combine(now.date(), MARKET_OPEN_TIME, tzinfo=et_tz)
        time_diff = now - market_open_dt
        hours_open = time_diff.total_seconds() / 3600.0

        # Clamp to valid range [0, 6.5]
        return max(0.0, min(TRADING_HOURS, hours_open))

    except Exception as e:
        log.warning("time_calculation_failed err=%s", str(e))
        # Safe fallback: assume mid-day (3 hours open)
        return 3.0


def get_volume_baseline(ticker: str, days: int = 20) -> Optional[float]:
    """
    Calculate 20-day average volume baseline (excluding today).

    Args:
        ticker: Stock ticker symbol
        days: Number of days for baseline (default: 20)

    Returns:
        Average daily volume over past {days} days, or None if insufficient data
    """
    ticker = ticker.strip().upper()

    try:
        # Fetch historical data (exclude today)
        end_date = datetime.now() - timedelta(days=1)  # Yesterday
        start_date = end_date - timedelta(days=days + 5)  # Buffer for weekends

        # Try Tiingo first if available
        settings = get_settings()
        hist_df = None

        if getattr(settings, "feature_tiingo", False) and getattr(
            settings, "tiingo_api_key", ""
        ):
            try:
                from .market import _tiingo_daily_history

                hist_df = _tiingo_daily_history(
                    ticker,
                    settings.tiingo_api_key,
                    start_date=start_date.strftime("%Y-%m-%d"),
                    end_date=end_date.strftime("%Y-%m-%d"),
                )
            except Exception as e:
                log.debug("tiingo_volume_baseline_failed ticker=%s err=%s", ticker, str(e))

        # Fallback to yfinance
        if hist_df is None or (hasattr(hist_df, "empty") and hist_df.empty):
            ticker_obj = yf.Ticker(ticker)
            hist_df = ticker_obj.history(
                start=start_date.strftime("%Y-%m-%d"),
                end=end_date.strftime("%Y-%m-%d"),
                interval="1d",
            )

        if hist_df is None or hist_df.empty:
            log.debug("rvol_baseline_no_data ticker=%s", ticker)
            return None

        # Get volume column
        if "Volume" not in hist_df.columns:
            log.debug("rvol_baseline_no_volume_column ticker=%s", ticker)
            return None

        # Get last {days} days of volume
        volume_series = hist_df["Volume"].tail(days)

        # Calculate average (excluding very low volume days)
        valid_volumes = volume_series[volume_series > MIN_VOLUME_THRESHOLD]

        if len(valid_volumes) < days * 0.5:  # Need at least 50% valid days
            log.debug(
                "rvol_baseline_insufficient_data ticker=%s valid_days=%d required=%d",
                ticker,
                len(valid_volumes),
                days // 2,
            )
            return None

        avg_volume = float(valid_volumes.mean())
        return avg_volume

    except Exception as e:
        log.warning(
            "rvol_baseline_calculation_failed ticker=%s err=%s",
            ticker,
            str(e.__class__.__name__),
        )
        return None


def get_current_volume(ticker: str) -> Optional[int]:
    """
    Get current intraday volume for a ticker.

    Args:
        ticker: Stock ticker symbol

    Returns:
        Current trading volume (cumulative for the day), or None if unavailable
    """
    ticker = ticker.strip().upper()

    try:
        # Use yfinance fast_info for quick current volume
        ticker_obj = yf.Ticker(ticker)

        # Try fast_info first (fastest method)
        try:
            fast_info = getattr(ticker_obj, "fast_info", None)
            if fast_info:
                volume = getattr(fast_info, "last_volume", None)
                if volume and volume > 0:
                    return int(volume)
        except Exception:
            pass

        # Fallback: Get most recent bar from history
        try:
            hist = ticker_obj.history(period="1d", interval="1m")
            if not hist.empty and "Volume" in hist.columns:
                # Sum all volume bars for the day
                total_volume = int(hist["Volume"].sum())
                if total_volume > 0:
                    return total_volume
        except Exception:
            pass

        log.debug("current_volume_unavailable ticker=%s", ticker)
        return None

    except Exception as e:
        log.warning(
            "current_volume_fetch_failed ticker=%s err=%s",
            ticker,
            str(e.__class__.__name__),
        )
        return None


def classify_rvol(rvol: float) -> str:
    """
    Classify RVol into discrete categories.

    Args:
        rvol: Relative volume multiplier (e.g., 2.5 = 2.5x average volume)

    Returns:
        RVol classification: EXTREME_RVOL, HIGH_RVOL, ELEVATED_RVOL, NORMAL_RVOL, LOW_RVOL
    """
    if rvol >= 5.0:
        return "EXTREME_RVOL"
    elif rvol >= 3.0:
        return "HIGH_RVOL"
    elif rvol >= 2.0:
        return "ELEVATED_RVOL"
    elif rvol >= 1.0:
        return "NORMAL_RVOL"
    else:
        return "LOW_RVOL"


def get_rvol_multiplier(rvol: float) -> float:
    """
    Get confidence multiplier based on RVol level.

    Higher RVol = higher confidence in catalyst significance.

    Args:
        rvol: Relative volume multiplier

    Returns:
        Confidence multiplier (0.8x to 1.4x)
    """
    if rvol >= 5.0:
        return 1.4  # EXTREME: 40% boost
    elif rvol >= 3.0:
        return 1.3  # HIGH: 30% boost
    elif rvol >= 2.0:
        return 1.2  # ELEVATED: 20% boost
    elif rvol >= 1.0:
        return 1.0  # NORMAL: baseline
    else:
        return 0.8  # LOW: 20% reduction


def _get_from_cache(ticker: str) -> Optional[Dict[str, Any]]:
    """
    Get RVol data from in-memory cache (5-minute TTL).

    Args:
        ticker: Stock ticker symbol

    Returns:
        Cached RVol data dict, or None if not cached or expired
    """
    ticker = ticker.strip().upper()
    cache_entry = _intraday_cache.get(ticker)

    if cache_entry is None:
        return None

    # Check TTL
    cached_at = cache_entry.get("cached_at")
    if cached_at is None:
        return None

    # Get TTL from settings
    settings = get_settings()
    ttl_minutes = getattr(settings, "rvol_cache_ttl_minutes", 5)
    ttl_seconds = ttl_minutes * 60

    age_seconds = time.time() - cached_at
    if age_seconds > ttl_seconds:
        # Expired - remove from cache
        del _intraday_cache[ticker]
        return None

    return cache_entry


def _save_to_cache(ticker: str, data: Dict[str, Any]) -> None:
    """
    Save RVol data to in-memory cache.

    Args:
        ticker: Stock ticker symbol
        data: RVol data dict to cache
    """
    ticker = ticker.strip().upper()
    data["cached_at"] = time.time()
    _intraday_cache[ticker] = data


def calculate_rvol_intraday(ticker: str) -> Optional[Dict[str, Any]]:
    """
    Calculate real-time intraday RVol with time-of-day adjustment.

    This is the MAIN FUNCTION for real-time RVol calculation. It extrapolates
    current intraday volume to a full trading day and compares to 20-day average.

    Args:
        ticker: Stock ticker symbol

    Returns:
        Dict containing:
        - ticker: Stock symbol
        - rvol: Relative volume multiplier (e.g., 2.5 = 2.5x average)
        - rvol_class: Classification (EXTREME/HIGH/ELEVATED/NORMAL/LOW)
        - multiplier: Confidence multiplier for classification (0.8 to 1.4)
        - current_volume: Cumulative intraday volume so far
        - avg_volume_20d: 20-day average daily volume baseline
        - hours_open: Hours since market open (for time-of-day adjustment)
        - estimated_full_day_volume: Extrapolated full-day volume
        - calculated_at: Timestamp of calculation

    Example:
        >>> result = calculate_rvol_intraday("AAPL")
        >>> print(result)
        {
            "ticker": "AAPL",
            "rvol": 3.2,
            "rvol_class": "HIGH_RVOL",
            "multiplier": 1.3,
            "current_volume": 1600000,
            "avg_volume_20d": 500000,
            "hours_open": 2.5,
            "estimated_full_day_volume": 4160000,
            "calculated_at": "2025-10-13T12:00:00Z"
        }
    """
    ticker = ticker.strip().upper()

    # Check feature flag
    settings = get_settings()
    if not getattr(settings, "feature_rvol", True):
        return None

    # Check cache first
    cached = _get_from_cache(ticker)
    if cached is not None:
        return cached

    try:
        # Get 20-day average volume baseline (excluding today)
        avg_volume_20d = get_volume_baseline(ticker, days=20)
        if avg_volume_20d is None:
            log.debug("rvol_no_baseline ticker=%s", ticker)
            return None

        # Check minimum average volume threshold
        min_avg_vol = getattr(settings, "rvol_min_avg_volume", 100000)
        if avg_volume_20d < min_avg_vol:
            log.debug(
                "rvol_below_min_volume ticker=%s avg_vol=%.0f min=%d",
                ticker,
                avg_volume_20d,
                min_avg_vol,
            )
            return None

        # Get current intraday volume
        current_volume = get_current_volume(ticker)
        if current_volume is None or current_volume == 0:
            log.debug("rvol_no_current_volume ticker=%s", ticker)
            return None

        # Calculate hours since market open
        hours_open = calculate_hours_since_market_open()

        # Extrapolate to full trading day (KEY INSIGHT: time-of-day adjustment)
        if hours_open < TRADING_HOURS and hours_open > 0.0:
            # During market hours: extrapolate to full day
            estimated_full_day_volume = int(current_volume * (TRADING_HOURS / hours_open))
        else:
            # Pre-market, after-hours, or exactly at close: use current volume as-is
            estimated_full_day_volume = current_volume

        # Calculate RVol
        rvol = estimated_full_day_volume / avg_volume_20d

        # Classify and get multiplier
        rvol_class = classify_rvol(rvol)
        multiplier = get_rvol_multiplier(rvol)

        # Build result
        result = {
            "ticker": ticker,
            "rvol": round(rvol, 2),
            "rvol_class": rvol_class,
            "multiplier": round(multiplier, 2),
            "current_volume": current_volume,
            "avg_volume_20d": round(avg_volume_20d, 2),
            "hours_open": round(hours_open, 2),
            "estimated_full_day_volume": estimated_full_day_volume,
            "calculated_at": datetime.now(timezone.utc).isoformat(),
        }

        # Cache result
        _save_to_cache(ticker, result)

        log.info(
            "rvol_calculated ticker=%s rvol=%.2fx class=%s multiplier=%.2f "
            "current_vol=%d avg_vol=%.0f hours_open=%.2f est_vol=%d",
            ticker,
            rvol,
            rvol_class,
            multiplier,
            current_volume,
            avg_volume_20d,
            hours_open,
            estimated_full_day_volume,
        )

        return result

    except Exception as e:
        log.warning(
            "rvol_intraday_calculation_failed ticker=%s err=%s",
            ticker,
            str(e.__class__.__name__),
        )
        return None


# Public API
__all__ = [
    "calculate_rvol",  # Historical backtesting (MOA Agent 1 - legacy)
    "bulk_calculate_rvol",  # Bulk historical backtesting
    "get_cache_stats",  # Cache statistics
    "calculate_rvol_intraday",  # Real-time RVol calculation (Quick Win #4)
    "get_rvol_multiplier",  # Get confidence multiplier from RVol
    "classify_rvol",  # Classify RVol into categories
    "get_volume_baseline",  # Get 20-day average volume
    "get_current_volume",  # Get current intraday volume
    "calculate_hours_since_market_open",  # Calculate hours since 9:30 AM ET
    "VOLUME_LOOKBACK_DAYS",
]
