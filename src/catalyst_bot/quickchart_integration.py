"""QuickChart integration helper with availability checking and fallback logic.

This module provides utilities to check QuickChart availability, generate charts
using QuickChart or fallback methods, and integrate with the existing alert system.
"""

from __future__ import annotations

import os
import time
from typing import Any, Dict, List, Optional

import requests

try:
    from .chart_cache import get_cache
    from .charts_quickchart import get_quickchart_url
    from .logging_utils import get_logger
except Exception:
    import logging

    logging.basicConfig(level=logging.INFO)

    def get_logger(_):
        return logging.getLogger("quickchart_integration")

    get_cache = None  # type: ignore
    get_quickchart_url = None  # type: ignore


log = get_logger("quickchart_integration")


# Cache QuickChart availability status
_QUICKCHART_AVAILABLE: Optional[bool] = None
_QUICKCHART_LAST_CHECK: float = 0
_QUICKCHART_CHECK_INTERVAL = 60  # Check every 60 seconds


def is_quickchart_available(
    base_url: Optional[str] = None,
    timeout: float = 2.0,
    force_check: bool = False,
) -> bool:
    """Check if QuickChart service is available.

    Parameters
    ----------
    base_url : Optional[str]
        QuickChart base URL (defaults to QUICKCHART_URL env var)
    timeout : float
        HTTP request timeout in seconds
    force_check : bool
        Force a fresh check even if cached result is recent

    Returns
    -------
    bool
        True if QuickChart is available, False otherwise
    """
    global _QUICKCHART_AVAILABLE, _QUICKCHART_LAST_CHECK

    # Use cached result if recent enough
    now = time.time()
    if (
        not force_check
        and _QUICKCHART_AVAILABLE is not None
        and (now - _QUICKCHART_LAST_CHECK) < _QUICKCHART_CHECK_INTERVAL
    ):
        return _QUICKCHART_AVAILABLE

    # Resolve base URL
    base_url = (
        base_url
        or os.getenv("QUICKCHART_URL")
        or os.getenv("QUICKCHART_BASE_URL")
        or "http://localhost:3400"
    )
    base_url = base_url.rstrip("/")

    # Try to ping the service
    try:
        resp = requests.get(base_url, timeout=timeout)
        available = resp.ok
    except Exception as e:
        log.debug(
            "quickchart_availability_check_failed url=%s err=%s", base_url, str(e)
        )
        available = False

    # Update cache
    _QUICKCHART_AVAILABLE = available
    _QUICKCHART_LAST_CHECK = now

    log.info(
        "quickchart_availability_check url=%s available=%s",
        base_url,
        available,
    )

    return available


def generate_chart_url_with_fallback(
    ticker: str,
    timeframe: str,
    ohlcv_data: List[Dict[str, Any]],
    indicators: Optional[Dict[str, Any]] = None,
    *,
    use_cache: bool = True,
    fallback_url: Optional[str] = None,
) -> Optional[str]:
    """Generate chart URL using QuickChart or fallback method.

    Parameters
    ----------
    ticker : str
        Stock ticker symbol
    timeframe : str
        Timeframe (1D, 5D, 1M, etc.)
    ohlcv_data : List[Dict[str, Any]]
        OHLC data points
    indicators : Optional[Dict[str, Any]]
        Technical indicators to overlay
    use_cache : bool
        Check cache before generating
    fallback_url : Optional[str]
        Fallback URL to use if QuickChart unavailable (e.g., Tiingo or Finviz)

    Returns
    -------
    Optional[str]
        Chart URL or None on failure
    """
    # Check if QuickChart feature is enabled
    quickchart_enabled = os.getenv("FEATURE_QUICKCHART", "1").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }

    if not quickchart_enabled:
        log.debug("quickchart_disabled using_fallback ticker=%s", ticker)
        return fallback_url

    # Check cache first if enabled
    if use_cache and get_cache:
        try:
            cache = get_cache()
            cached_url = cache.get_cached_chart(ticker, timeframe)
            if cached_url:
                log.info(
                    "chart_url_from_cache ticker=%s tf=%s",
                    ticker,
                    timeframe,
                )
                return cached_url
        except Exception as e:
            log.debug("cache_check_failed ticker=%s err=%s", ticker, str(e))

    # Check QuickChart availability
    if not is_quickchart_available():
        log.info(
            "quickchart_unavailable using_fallback ticker=%s tf=%s",
            ticker,
            timeframe,
        )
        return fallback_url

    # Generate QuickChart URL
    if not get_quickchart_url:
        log.warning("quickchart_module_unavailable using_fallback")
        return fallback_url

    try:
        chart_url = get_quickchart_url(ticker, timeframe, ohlcv_data, indicators)

        if chart_url:
            # Store in cache if enabled
            if use_cache and get_cache:
                try:
                    cache = get_cache()
                    cache.cache_chart(ticker, timeframe, chart_url)
                except Exception as e:
                    log.debug("cache_put_failed ticker=%s err=%s", ticker, str(e))

            log.info(
                "chart_url_generated source=quickchart ticker=%s tf=%s",
                ticker,
                timeframe,
            )
            return chart_url
        else:
            log.warning(
                "quickchart_generation_failed using_fallback ticker=%s tf=%s",
                ticker,
                timeframe,
            )
            return fallback_url

    except Exception as e:
        log.warning(
            "quickchart_error using_fallback ticker=%s err=%s",
            ticker,
            str(e),
        )
        return fallback_url


def log_chart_generation_metrics(
    ticker: str,
    timeframe: str,
    source: str,
    elapsed: float,
    success: bool,
) -> None:
    """Log chart generation metrics for monitoring.

    Parameters
    ----------
    ticker : str
        Stock ticker symbol
    timeframe : str
        Timeframe
    source : str
        Chart source (quickchart, tiingo, finviz, matplotlib, etc.)
    elapsed : float
        Generation time in seconds
    success : bool
        Whether generation succeeded
    """
    log.info(
        "chart_generation_metric ticker=%s tf=%s source=%s elapsed=%.3fs success=%s",
        ticker,
        timeframe,
        source,
        elapsed,
        success,
    )


def get_default_chart_timeframe() -> str:
    """Get default chart timeframe from environment.

    Returns
    -------
    str
        Default timeframe (defaults to "1D")
    """
    return os.getenv("CHART_DEFAULT_TIMEFRAME", "1D").strip().upper()
