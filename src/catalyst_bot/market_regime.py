"""
VIX/Market Regime Classification System
========================================

Provides market regime classification based on VIX levels and SPY trend analysis.
Regime classification affects catalyst score multipliers - high volatility regimes
reduce confidence in catalyst signals, while calm bull markets increase confidence.

Features:
- VIX-based regime classification (BULL_MARKET, NEUTRAL, HIGH_VOLATILITY, BEAR_MARKET, CRASH)
- SPY 20-day trend analysis (UPTREND, DOWNTREND, SIDEWAYS)
- Combined confidence scoring
- Multi-level caching (5-minute TTL for VIX data)
- Fallback chain: yfinance (primary) → Alpha Vantage (fallback)
- Graceful degradation with safe defaults

Regime Multipliers:
- BULL_MARKET (VIX < 15): 1.2x boost
- NEUTRAL (VIX 15-20): 1.0x baseline
- HIGH_VOLATILITY (VIX 20-30): 0.8x reduction
- BEAR_MARKET (VIX 30-40): 0.7x reduction
- CRASH (VIX >= 40): 0.5x strong reduction

Author: Claude Code (Sonnet 4.5)
Date: 2025-10-13
"""

from __future__ import annotations

import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional, Tuple

from .config import get_settings
from .logging_utils import get_logger

log = get_logger("market_regime")

# Import providers lazily to avoid circular imports
try:
    import yfinance as yf
except Exception:
    yf = None

try:
    import requests
except Exception:
    requests = None

# VIX thresholds for regime classification
VIX_THRESHOLD_BULL = 15.0  # Below this: BULL_MARKET
VIX_THRESHOLD_NEUTRAL = 20.0  # 15-20: NEUTRAL
VIX_THRESHOLD_HIGH_VOL = 30.0  # 20-30: HIGH_VOLATILITY
VIX_THRESHOLD_BEAR = 40.0  # 30-40: BEAR_MARKET, >=40: CRASH

# SPY trend thresholds (20-day return percentages)
SPY_TREND_UP_THRESHOLD = 2.0  # Above +2%: UPTREND
SPY_TREND_DOWN_THRESHOLD = -2.0  # Below -2%: DOWNTREND

# Cache TTL
REGIME_CACHE_TTL_SEC = 300  # 5 minutes

# Regime types
REGIME_BULL_MARKET = "BULL_MARKET"
REGIME_NEUTRAL = "NEUTRAL"
REGIME_HIGH_VOLATILITY = "HIGH_VOLATILITY"
REGIME_BEAR_MARKET = "BEAR_MARKET"
REGIME_CRASH = "CRASH"

# SPY trend types
TREND_UPTREND = "UPTREND"
TREND_SIDEWAYS = "SIDEWAYS"
TREND_DOWNTREND = "DOWNTREND"

# Default multipliers (can be overridden in config)
DEFAULT_MULTIPLIERS = {
    REGIME_BULL_MARKET: 1.2,
    REGIME_NEUTRAL: 1.0,
    REGIME_HIGH_VOLATILITY: 0.8,
    REGIME_BEAR_MARKET: 0.7,
    REGIME_CRASH: 0.5,
}


class MarketRegimeManager:
    """
    Manages market regime classification with caching.

    Provides:
    - VIX-based regime classification
    - SPY 20-day trend analysis
    - Combined confidence scoring
    - 5-minute cache TTL
    - Fallback chain: yfinance → Alpha Vantage
    """

    def __init__(self):
        """Initialize market regime manager."""
        self._cache: Optional[Dict[str, Any]] = None
        self._cache_time: float = 0.0
        self._cache_lock = threading.Lock()
        self._last_cache_check: float = 0.0

        # Track cache stats
        self._cache_hits = 0
        self._cache_misses = 0
        self._api_errors = 0

        log.info("market_regime_init cache_ttl_sec=%d", REGIME_CACHE_TTL_SEC)

    def get_current_regime(self) -> Dict[str, Any]:
        """
        Get current market regime classification.

        Returns:
            Dict with:
            - regime: str (BULL_MARKET, BEAR_MARKET, HIGH_VOLATILITY, NEUTRAL, CRASH)
            - vix: float (current VIX level)
            - multiplier: float (score adjustment multiplier)
            - spy_trend: str (UPTREND, DOWNTREND, SIDEWAYS)
            - spy_20d_return: float (20-day SPY return percentage)
            - confidence: float (0.0-1.0, combined confidence score)
            - cached_at: datetime (when data was fetched)
        """
        # Check cache first
        cached = self._get_from_cache()
        if cached:
            self._cache_hits += 1
            return cached

        self._cache_misses += 1

        # Fetch fresh data
        try:
            regime_data = self._fetch_regime_data()

            # Store in cache
            with self._cache_lock:
                self._cache = regime_data
                self._cache_time = time.time()

            return regime_data

        except Exception as e:
            log.warning(f"regime_fetch_failed err={e}")
            self._api_errors += 1
            # Return safe default on error
            return self._get_default_regime()

    def _get_from_cache(self) -> Optional[Dict[str, Any]]:
        """
        Get regime data from cache if valid.

        Returns:
            Cached regime data or None if expired/missing
        """
        with self._cache_lock:
            if self._cache is None:
                return None

            # Check TTL
            age_sec = time.time() - self._cache_time
            if age_sec > REGIME_CACHE_TTL_SEC:
                # Expired
                log.debug(f"cache_expired age_sec={age_sec:.1f}")
                self._cache = None
                return None

            log.debug(f"cache_hit age_sec={age_sec:.1f}")
            return self._cache

    def _fetch_regime_data(self) -> Dict[str, Any]:
        """
        Fetch fresh regime data from market APIs.

        Uses fallback chain: yfinance → Alpha Vantage

        Returns:
            Dict with regime classification and metrics
        """
        start_time = time.time()

        # Fetch VIX and SPY data
        vix_value = self._fetch_vix()
        spy_return = self._fetch_spy_return()

        # Classify regime based on VIX
        regime = self._classify_vix_regime(vix_value)

        # Classify SPY trend
        spy_trend = self._classify_spy_trend(spy_return)

        # Get multiplier from config or use default
        multiplier = self._get_multiplier(regime)

        # Calculate combined confidence
        confidence = self._calculate_confidence(vix_value, spy_return, regime, spy_trend)

        elapsed_ms = (time.time() - start_time) * 1000.0

        vix_str = f"{vix_value:.2f}" if vix_value is not None else "None"
        spy_str = f"{spy_return:.2f}" if spy_return is not None else "None"

        log.info(
            f"regime_update regime={regime} vix={vix_str} "
            f"spy_trend={spy_trend} spy_20d_return={spy_str}% "
            f"multiplier={multiplier:.2f} confidence={confidence:.2f} "
            f"t_ms={elapsed_ms:.1f}"
        )

        return {
            "regime": regime,
            "vix": vix_value,
            "multiplier": multiplier,
            "spy_trend": spy_trend,
            "spy_20d_return": spy_return,
            "confidence": confidence,
            "cached_at": datetime.now(timezone.utc),
        }

    def _fetch_vix(self) -> Optional[float]:
        """
        Fetch current VIX value.

        Primary: yfinance
        Fallback: Alpha Vantage

        Returns:
            Current VIX value or None on failure
        """
        # Try yfinance first (free, fast, reliable)
        if yf is not None:
            try:
                vix_ticker = yf.Ticker("^VIX")

                # Try fast_info first
                fast_info = getattr(vix_ticker, "fast_info", None)
                if fast_info:
                    vix_val = None
                    if hasattr(fast_info, "last_price"):
                        vix_val = getattr(fast_info, "last_price", None)
                    elif isinstance(fast_info, dict):
                        vix_val = fast_info.get("last_price")

                    if vix_val is not None:
                        log.debug(f"vix_fetch_success provider=yfinance_fast vix={vix_val:.2f}")
                        return float(vix_val)

                # Fallback to history
                hist = vix_ticker.history(period="1d", interval="1d")
                if hist is not None and not hist.empty:
                    vix_val = float(hist["Close"].iloc[-1])
                    log.debug(f"vix_fetch_success provider=yfinance_hist vix={vix_val:.2f}")
                    return vix_val

            except Exception as e:
                log.debug(f"vix_yfinance_failed err={e}")

        # Try Alpha Vantage fallback
        try:
            settings = get_settings()
            av_key = getattr(settings, "alphavantage_api_key", "")

            if av_key and requests is not None:
                vix_val = self._fetch_vix_alpha_vantage(av_key)
                if vix_val is not None:
                    log.debug(f"vix_fetch_success provider=alpha_vantage vix={vix_val:.2f}")
                    return vix_val

        except Exception as e:
            log.debug(f"vix_alpha_vantage_failed err={e}")

        log.warning("vix_fetch_failed all_providers_failed")
        return None

    def _fetch_vix_alpha_vantage(self, api_key: str) -> Optional[float]:
        """
        Fetch VIX from Alpha Vantage GLOBAL_QUOTE.

        Args:
            api_key: Alpha Vantage API key

        Returns:
            VIX value or None on failure
        """
        try:
            url = "https://www.alphavantage.co/query"
            params = {
                "function": "GLOBAL_QUOTE",
                "symbol": "VIX",
                "apikey": api_key,
            }

            r = requests.get(url, params=params, timeout=8)
            if r.status_code != 200:
                return None

            data = r.json()
            quote = data.get("Global Quote", {})

            price = quote.get("05. price") or quote.get("price")
            if price:
                return float(price)

        except Exception as e:
            log.debug(f"av_vix_fetch_failed err={e}")

        return None

    def _fetch_spy_return(self) -> Optional[float]:
        """
        Fetch SPY 20-day return.

        Returns:
            20-day return percentage or None on failure
        """
        if yf is None:
            log.debug("spy_fetch_failed yfinance_not_available")
            return None

        try:
            spy_ticker = yf.Ticker("SPY")

            # Fetch 25 days to ensure we have 20 trading days
            hist = spy_ticker.history(period="25d", interval="1d")

            if hist is None or hist.empty or len(hist) < 20:
                log.debug(f"spy_fetch_insufficient_data rows={len(hist) if hist is not None else 0}")
                return None

            # Calculate 20-day return
            # Get last 20 days
            hist_20d = hist.tail(20)

            price_start = float(hist_20d["Close"].iloc[0])
            price_end = float(hist_20d["Close"].iloc[-1])

            if price_start == 0:
                return None

            return_pct = ((price_end - price_start) / price_start) * 100.0

            log.debug(f"spy_fetch_success return_20d={return_pct:.2f}%")
            return return_pct

        except Exception as e:
            log.debug(f"spy_fetch_failed err={e}")
            return None

    def _classify_vix_regime(self, vix_value: Optional[float]) -> str:
        """
        Classify market regime based on VIX level.

        VIX thresholds:
        - VIX < 15: BULL_MARKET
        - 15 <= VIX < 20: NEUTRAL
        - 20 <= VIX < 30: HIGH_VOLATILITY
        - 30 <= VIX < 40: BEAR_MARKET
        - VIX >= 40: CRASH

        Args:
            vix_value: Current VIX level

        Returns:
            Regime classification string
        """
        if vix_value is None:
            return REGIME_NEUTRAL  # Safe default

        if vix_value < VIX_THRESHOLD_BULL:
            return REGIME_BULL_MARKET
        elif vix_value < VIX_THRESHOLD_NEUTRAL:
            return REGIME_NEUTRAL
        elif vix_value < VIX_THRESHOLD_HIGH_VOL:
            return REGIME_HIGH_VOLATILITY
        elif vix_value < VIX_THRESHOLD_BEAR:
            return REGIME_BEAR_MARKET
        else:
            return REGIME_CRASH

    def _classify_spy_trend(self, spy_return: Optional[float]) -> str:
        """
        Classify SPY trend based on 20-day return.

        Thresholds:
        - > 2%: UPTREND
        - -2% to 2%: SIDEWAYS
        - < -2%: DOWNTREND

        Args:
            spy_return: 20-day return percentage

        Returns:
            Trend classification string
        """
        if spy_return is None:
            return TREND_SIDEWAYS  # Safe default

        if spy_return > SPY_TREND_UP_THRESHOLD:
            return TREND_UPTREND
        elif spy_return < SPY_TREND_DOWN_THRESHOLD:
            return TREND_DOWNTREND
        else:
            return TREND_SIDEWAYS

    def _get_multiplier(self, regime: str) -> float:
        """
        Get score multiplier for regime.

        Checks config for overrides, falls back to defaults.

        Args:
            regime: Regime classification

        Returns:
            Score multiplier
        """
        try:
            settings = get_settings()

            # Check for config overrides
            override_map = {
                REGIME_BULL_MARKET: getattr(settings, "regime_multiplier_bull", None),
                REGIME_NEUTRAL: getattr(settings, "regime_multiplier_neutral", None),
                REGIME_HIGH_VOLATILITY: getattr(settings, "regime_multiplier_high_vol", None),
                REGIME_BEAR_MARKET: getattr(settings, "regime_multiplier_bear", None),
                REGIME_CRASH: getattr(settings, "regime_multiplier_crash", None),
            }

            override_val = override_map.get(regime)
            if override_val is not None:
                return float(override_val)

        except Exception as e:
            log.debug(f"multiplier_config_read_failed err={e}")

        # Use default
        return DEFAULT_MULTIPLIERS.get(regime, 1.0)

    def _calculate_confidence(
        self,
        vix_value: Optional[float],
        spy_return: Optional[float],
        regime: str,
        spy_trend: str,
    ) -> float:
        """
        Calculate combined confidence score.

        Confidence factors:
        - VIX data availability: +0.5 if available
        - SPY data availability: +0.5 if available
        - Regime/trend alignment: +0.2 if aligned (bull+uptrend or bear+downtrend)
        - Regime/trend conflict: -0.2 if conflicted (bull+downtrend or bear+uptrend)

        Args:
            vix_value: Current VIX level
            spy_return: 20-day SPY return
            regime: Regime classification
            spy_trend: SPY trend classification

        Returns:
            Confidence score (0.0-1.0)
        """
        confidence = 0.0

        # Base confidence from data availability
        if vix_value is not None:
            confidence += 0.5
        if spy_return is not None:
            confidence += 0.5

        # Adjust for regime/trend alignment
        if vix_value is not None and spy_return is not None:
            # Check for alignment
            aligned = False
            conflicted = False

            if regime == REGIME_BULL_MARKET and spy_trend == TREND_UPTREND:
                aligned = True
            elif regime in (REGIME_BEAR_MARKET, REGIME_CRASH) and spy_trend == TREND_DOWNTREND:
                aligned = True
            elif regime == REGIME_BULL_MARKET and spy_trend == TREND_DOWNTREND:
                conflicted = True
            elif regime in (REGIME_BEAR_MARKET, REGIME_CRASH) and spy_trend == TREND_UPTREND:
                conflicted = True

            if aligned:
                confidence = min(1.0, confidence + 0.2)
            elif conflicted:
                confidence = max(0.0, confidence - 0.2)

        return round(confidence, 2)

    def _get_default_regime(self) -> Dict[str, Any]:
        """
        Return safe default regime when fetch fails.

        Returns:
            Dict with NEUTRAL regime and 1.0 multiplier
        """
        return {
            "regime": REGIME_NEUTRAL,
            "vix": None,
            "multiplier": 1.0,
            "spy_trend": TREND_SIDEWAYS,
            "spy_20d_return": None,
            "confidence": 0.0,
            "cached_at": datetime.now(timezone.utc),
        }

    def get_cache_stats(self) -> Dict[str, int]:
        """
        Get cache statistics.

        Returns:
            Dict with cache hits, misses, and error counts
        """
        return {
            "cache_hits": self._cache_hits,
            "cache_misses": self._cache_misses,
            "api_errors": self._api_errors,
            "total_requests": self._cache_hits + self._cache_misses,
        }


# Global singleton instance
_regime_manager: Optional[MarketRegimeManager] = None
_manager_lock = threading.Lock()


def get_regime_manager() -> MarketRegimeManager:
    """
    Get global market regime manager instance (singleton).

    Returns:
        MarketRegimeManager instance
    """
    global _regime_manager

    if _regime_manager is None:
        with _manager_lock:
            if _regime_manager is None:
                _regime_manager = MarketRegimeManager()

    return _regime_manager


def get_current_regime() -> Dict[str, Any]:
    """
    Convenience function to get current market regime.

    Returns:
        Dict with regime classification and metrics
    """
    manager = get_regime_manager()
    return manager.get_current_regime()


def get_regime_multiplier() -> float:
    """
    Convenience function to get current regime multiplier.

    Returns:
        Score adjustment multiplier for current regime
    """
    regime_data = get_current_regime()
    return regime_data.get("multiplier", 1.0)


def is_high_volatility_regime() -> bool:
    """
    Check if current regime is high volatility.

    Returns:
        True if regime is HIGH_VOLATILITY, BEAR_MARKET, or CRASH
    """
    regime_data = get_current_regime()
    regime = regime_data.get("regime", REGIME_NEUTRAL)
    return regime in (REGIME_HIGH_VOLATILITY, REGIME_BEAR_MARKET, REGIME_CRASH)


# Public API
__all__ = [
    "get_current_regime",
    "get_regime_multiplier",
    "is_high_volatility_regime",
    "get_regime_manager",
    "REGIME_BULL_MARKET",
    "REGIME_NEUTRAL",
    "REGIME_HIGH_VOLATILITY",
    "REGIME_BEAR_MARKET",
    "REGIME_CRASH",
    "TREND_UPTREND",
    "TREND_SIDEWAYS",
    "TREND_DOWNTREND",
]
