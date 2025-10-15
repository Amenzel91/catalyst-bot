"""
Sector and Industry Context Tracking System
============================================

Provides sector performance tracking to establish market baseline for catalyst evaluation.
Sector momentum affects catalyst success rate significantly - this module tracks sector
performance relative to SPY to identify hot/cold sectors when catalysts occur.

Features:
- Sector/industry lookup via yfinance
- Sector performance tracking (daily, weekly returns)
- Sector relative volume vs market
- Multi-level caching (30-day TTL for sector info, 1-day TTL for performance)
- Bulk operations support
- Sector ETF mapping (XLK, XLF, XLE, etc.)

Author: Claude Code (Agent 3)
Date: 2025-10-12
"""

from __future__ import annotations

import hashlib
import pickle
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yfinance as yf

from .logging_utils import get_logger

log = get_logger("sector_context")

# Cache TTLs
SECTOR_INFO_CACHE_TTL_DAYS = 30  # Sector/industry mappings change rarely
SECTOR_PERFORMANCE_CACHE_TTL_DAYS = 1  # Performance data changes daily

# Sector ETF mapping (SPDR sector ETFs)
SECTOR_ETF_MAP = {
    "Technology": "XLK",
    "Information Technology": "XLK",
    "Financials": "XLF",
    "Financial Services": "XLF",
    "Energy": "XLE",
    "Health Care": "XLV",
    "Healthcare": "XLV",
    "Industrials": "XLI",
    "Consumer Staples": "XLP",
    "Consumer Defensive": "XLP",
    "Consumer Discretionary": "XLY",
    "Consumer Cyclical": "XLY",
    "Materials": "XLB",
    "Basic Materials": "XLB",
    "Utilities": "XLU",
    "Real Estate": "XLRE",
    "Communication Services": "XLC",
    "Communication": "XLC",
    "Telecommunications": "XLC",
}


class SectorContextManager:
    """
    Manages sector/industry lookup and performance tracking with caching.

    Provides:
    - Ticker → sector/industry mapping (via yfinance)
    - Sector performance metrics (1d, 5d returns vs SPY)
    - Sector relative volume
    - Multi-level caching with TTL
    - Bulk operations
    """

    def __init__(self, cache_dir: Optional[Path] = None):
        """
        Initialize sector context manager.

        Args:
            cache_dir: Directory for disk cache. Defaults to data/cache/sector
        """
        self.cache_dir = cache_dir or Path("data/cache/sector")
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        # In-memory caches
        self._sector_info_cache: Dict[str, Dict[str, Any]] = {}
        self._sector_perf_cache: Dict[str, Dict[str, Any]] = {}
        self._cache_lock = threading.Lock()

        log.info(f"sector_context_init cache_dir={self.cache_dir}")

    def get_ticker_sector_info(self, ticker: str) -> Dict[str, Any]:
        """
        Get sector and industry for a ticker.

        Uses multi-level cache: memory → disk → yfinance API.

        Args:
            ticker: Stock ticker symbol

        Returns:
            Dict with keys:
            - sector: str or None
            - industry: str or None
            - cached_at: datetime
        """
        if not ticker:
            return {"sector": None, "industry": None, "cached_at": None}

        ticker = ticker.upper()

        # Check memory cache
        cached = self._get_sector_info_from_cache(ticker)
        if cached:
            return cached

        # Check disk cache
        cached = self._load_sector_info_from_disk(ticker)
        if cached:
            # Store in memory cache
            with self._cache_lock:
                self._sector_info_cache[ticker] = cached
            return cached

        # Fetch from yfinance
        try:
            info = self._fetch_sector_info_from_yfinance(ticker)

            # Store in both caches
            self._store_sector_info(ticker, info)

            return info

        except Exception as e:
            log.warning(f"sector_info_fetch_failed ticker={ticker} err={e}")
            return {"sector": None, "industry": None, "cached_at": None}

    def get_sector_performance(
        self, sector: str, as_of_date: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """
        Get sector performance metrics.

        Args:
            sector: Sector name (e.g., "Technology")
            as_of_date: Date to calculate performance as of. Defaults to now.

        Returns:
            Dict with keys:
            - sector_1d_return: float (percent)
            - sector_5d_return: float (percent)
            - sector_vs_spy: float (sector outperformance vs SPY in 5d period)
            - sector_rvol: float (relative volume vs 20-day average)
            - etf_ticker: str (sector ETF used)
            - cached_at: datetime
        """
        if not sector:
            return self._empty_performance_result()

        as_of_date = as_of_date or datetime.now(timezone.utc)

        # Map sector to ETF
        etf = self._get_sector_etf(sector)
        if not etf:
            log.debug(f"no_etf_mapping sector='{sector}'")
            return self._empty_performance_result()

        # Check cache
        cache_key = f"{etf}_{as_of_date.date()}"
        cached = self._get_sector_perf_from_cache(cache_key)
        if cached:
            return cached

        # Fetch performance
        try:
            perf = self._fetch_sector_performance(etf, as_of_date)
            perf["etf_ticker"] = etf

            # Store in cache
            self._store_sector_perf(cache_key, perf)

            return perf

        except Exception as e:
            log.warning(f"sector_perf_fetch_failed etf={etf} err={e}")
            return self._empty_performance_result()

    def get_bulk_sector_info(self, tickers: List[str]) -> Dict[str, Dict[str, Any]]:
        """
        Get sector info for multiple tickers (bulk operation).

        Optimizes by checking cache first, then batching API calls.

        Args:
            tickers: List of ticker symbols

        Returns:
            Dict mapping ticker → sector info
        """
        if not tickers:
            return {}

        results = {}
        to_fetch = []

        # Check cache first
        for ticker in tickers:
            ticker = ticker.upper()
            cached = self._get_sector_info_from_cache(ticker)
            if cached:
                results[ticker] = cached
            else:
                # Check disk cache
                disk_cached = self._load_sector_info_from_disk(ticker)
                if disk_cached:
                    with self._cache_lock:
                        self._sector_info_cache[ticker] = disk_cached
                    results[ticker] = disk_cached
                else:
                    to_fetch.append(ticker)

        # Fetch remaining tickers
        if to_fetch:
            log.info(f"bulk_sector_fetch tickers={len(to_fetch)}")

            for ticker in to_fetch:
                try:
                    info = self._fetch_sector_info_from_yfinance(ticker)
                    self._store_sector_info(ticker, info)
                    results[ticker] = info

                    # Small delay to avoid rate limiting
                    time.sleep(0.1)

                except Exception as e:
                    log.debug(f"bulk_fetch_failed ticker={ticker} err={e}")
                    results[ticker] = {
                        "sector": None,
                        "industry": None,
                        "cached_at": None,
                    }

        return results

    def _get_sector_etf(self, sector: str) -> Optional[str]:
        """
        Map sector name to sector ETF ticker.

        Args:
            sector: Sector name

        Returns:
            ETF ticker or None
        """
        return SECTOR_ETF_MAP.get(sector.strip())

    def _fetch_sector_info_from_yfinance(self, ticker: str) -> Dict[str, Any]:
        """
        Fetch sector/industry from yfinance ticker.info.

        Args:
            ticker: Stock ticker

        Returns:
            Dict with sector, industry, cached_at
        """
        ticker_obj = yf.Ticker(ticker)
        info = ticker_obj.info

        sector = info.get("sector")
        industry = info.get("industry")

        return {
            "sector": sector,
            "industry": industry,
            "cached_at": datetime.now(timezone.utc),
        }

    def _fetch_sector_performance(
        self, etf: str, as_of_date: datetime
    ) -> Dict[str, Any]:
        """
        Fetch sector performance metrics from ETF.

        Args:
            etf: Sector ETF ticker
            as_of_date: Date to calculate performance as of

        Returns:
            Dict with performance metrics
        """
        # Fetch ETF historical data
        start_date = (as_of_date - timedelta(days=30)).strftime("%Y-%m-%d")
        end_date = (as_of_date + timedelta(days=1)).strftime("%Y-%m-%d")

        etf_obj = yf.Ticker(etf)
        hist = etf_obj.history(start=start_date, end=end_date, interval="1d")

        if hist is None or hist.empty or len(hist) < 2:
            return self._empty_performance_result()

        # Calculate returns
        current_price = float(hist["Close"].iloc[-1])

        # 1-day return
        sector_1d_return = 0.0
        if len(hist) >= 2:
            price_1d_ago = float(hist["Close"].iloc[-2])
            sector_1d_return = ((current_price - price_1d_ago) / price_1d_ago) * 100.0

        # 5-day return (look back 5 trading days)
        sector_5d_return = 0.0
        if len(hist) >= 6:
            # iloc[-6] gives us the price 5 days ago (6th element from end)
            price_5d_ago = float(hist["Close"].iloc[-6])
            sector_5d_return = ((current_price - price_5d_ago) / price_5d_ago) * 100.0

        # Fetch SPY for comparison
        spy_obj = yf.Ticker("SPY")
        spy_hist = spy_obj.history(start=start_date, end=end_date, interval="1d")

        sector_vs_spy = 0.0
        if spy_hist is not None and not spy_hist.empty and len(spy_hist) >= 6:
            spy_current = float(spy_hist["Close"].iloc[-1])
            spy_5d_ago = float(spy_hist["Close"].iloc[-6])
            spy_5d_return = ((spy_current - spy_5d_ago) / spy_5d_ago) * 100.0
            sector_vs_spy = sector_5d_return - spy_5d_return

        # Calculate relative volume
        sector_rvol = 1.0
        if len(hist) >= 20:
            avg_vol_20d = hist["Volume"].rolling(20).mean().iloc[-1]
            current_vol = hist["Volume"].iloc[-1]
            if avg_vol_20d > 0:
                sector_rvol = current_vol / avg_vol_20d

        return {
            "sector_1d_return": round(sector_1d_return, 2),
            "sector_5d_return": round(sector_5d_return, 2),
            "sector_vs_spy": round(sector_vs_spy, 2),
            "sector_rvol": round(sector_rvol, 2),
            "cached_at": datetime.now(timezone.utc),
        }

    def _empty_performance_result(self) -> Dict[str, Any]:
        """Return empty performance result."""
        return {
            "sector_1d_return": None,
            "sector_5d_return": None,
            "sector_vs_spy": None,
            "sector_rvol": None,
            "etf_ticker": None,
            "cached_at": None,
        }

    # ========================================================================
    # Caching Methods
    # ========================================================================

    def _get_sector_info_from_cache(self, ticker: str) -> Optional[Dict[str, Any]]:
        """
        Get sector info from memory cache (with TTL check).

        Args:
            ticker: Stock ticker

        Returns:
            Cached info or None
        """
        with self._cache_lock:
            if ticker not in self._sector_info_cache:
                return None

            cached = self._sector_info_cache[ticker]
            cached_at = cached.get("cached_at")

            if not cached_at:
                return None

            # Check TTL
            age_days = (datetime.now(timezone.utc) - cached_at).days
            if age_days > SECTOR_INFO_CACHE_TTL_DAYS:
                # Expired
                del self._sector_info_cache[ticker]
                return None

            return cached

    def _get_sector_perf_from_cache(self, cache_key: str) -> Optional[Dict[str, Any]]:
        """
        Get sector performance from memory cache (with TTL check).

        Args:
            cache_key: Cache key (etf_date)

        Returns:
            Cached performance or None
        """
        with self._cache_lock:
            if cache_key not in self._sector_perf_cache:
                return None

            cached = self._sector_perf_cache[cache_key]
            cached_at = cached.get("cached_at")

            if not cached_at:
                return None

            # Check TTL
            age_days = (datetime.now(timezone.utc) - cached_at).days
            if age_days > SECTOR_PERFORMANCE_CACHE_TTL_DAYS:
                # Expired
                del self._sector_perf_cache[cache_key]
                return None

            return cached

    def _load_sector_info_from_disk(self, ticker: str) -> Optional[Dict[str, Any]]:
        """
        Load sector info from disk cache.

        Args:
            ticker: Stock ticker

        Returns:
            Cached info or None
        """
        cache_path = self._get_disk_cache_path("sector_info", ticker)

        if not cache_path.exists():
            return None

        try:
            with open(cache_path, "rb") as f:
                cached = pickle.load(f)

            cached_at = cached.get("cached_at")
            if not cached_at:
                return None

            # Check TTL
            age_days = (datetime.now(timezone.utc) - cached_at).days
            if age_days > SECTOR_INFO_CACHE_TTL_DAYS:
                # Expired - delete cache file
                cache_path.unlink(missing_ok=True)
                return None

            return cached

        except Exception as e:
            log.debug(f"disk_cache_load_failed ticker={ticker} err={e}")
            return None

    def _store_sector_info(self, ticker: str, info: Dict[str, Any]) -> None:
        """
        Store sector info in both memory and disk cache.

        Args:
            ticker: Stock ticker
            info: Sector info dict
        """
        # Memory cache
        with self._cache_lock:
            self._sector_info_cache[ticker] = info

        # Disk cache
        try:
            cache_path = self._get_disk_cache_path("sector_info", ticker)
            cache_path.parent.mkdir(parents=True, exist_ok=True)

            with open(cache_path, "wb") as f:
                pickle.dump(info, f)

        except Exception as e:
            log.debug(f"disk_cache_write_failed ticker={ticker} err={e}")

    def _store_sector_perf(self, cache_key: str, perf: Dict[str, Any]) -> None:
        """
        Store sector performance in memory cache.

        Args:
            cache_key: Cache key
            perf: Performance dict
        """
        with self._cache_lock:
            self._sector_perf_cache[cache_key] = perf

    def _get_disk_cache_path(self, cache_type: str, key: str) -> Path:
        """
        Get disk cache file path.

        Args:
            cache_type: Type of cache (sector_info, sector_perf)
            key: Cache key

        Returns:
            Path to cache file
        """
        # Use hash to create subdirectories
        key_hash = hashlib.md5(key.encode()).hexdigest()

        # Create 2-level directory structure
        subdir = self.cache_dir / cache_type / key_hash[:2] / key_hash[2:4]
        subdir.mkdir(parents=True, exist_ok=True)

        return subdir / f"{key}.pkl"


# Global instance for convenience
_sector_manager: Optional[SectorContextManager] = None
_manager_lock = threading.Lock()


def get_sector_manager() -> SectorContextManager:
    """
    Get global sector context manager instance (singleton).

    Returns:
        SectorContextManager instance
    """
    global _sector_manager

    if _sector_manager is None:
        with _manager_lock:
            if _sector_manager is None:
                _sector_manager = SectorContextManager()

    return _sector_manager


def get_ticker_sector(ticker: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Convenience function to get sector and industry for a ticker.

    Args:
        ticker: Stock ticker

    Returns:
        Tuple of (sector, industry)
    """
    manager = get_sector_manager()
    info = manager.get_ticker_sector_info(ticker)
    return info.get("sector"), info.get("industry")


def get_sector_metrics(
    sector: str, as_of_date: Optional[datetime] = None
) -> Dict[str, Any]:
    """
    Convenience function to get sector performance metrics.

    Args:
        sector: Sector name
        as_of_date: Date to calculate metrics as of

    Returns:
        Dict with performance metrics
    """
    manager = get_sector_manager()
    return manager.get_sector_performance(sector, as_of_date)
