from __future__ import annotations

import json
import os
import time

# Ensure we have datetime and timedelta available for intraday helpers
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Optional, Tuple

# Pandas is used for DatetimeIndex checks in get_intraday_snapshots
import pandas as pd
import requests

from .config import get_settings
from .logging_utils import get_logger
from .models import NewsItem, ScoredItem  # re-export for market.NewsItem
from .validation import validate_ticker

log = get_logger("market")

try:
    import yfinance as yf  # type: ignore
except Exception:  # pragma: no cover
    yf = None  # type: ignore

# Pandas is used for calculating momentum indicators when requested. The
# computation functions below will import pandas and yfinance lazily as
# needed. Do not import pandas at module load time to keep startup overhead minimal.

# ---------------------------------------------------------------------------
# Alpha Vantage caching
#
# To reduce external API calls (and avoid unnecessary rate limiting), the
# Alpha Vantage price fetcher supports a lightweight on-disk cache. The cache
# stores the last and previous close prices for each ticker along with a
# timestamp. When enabled, subsequent calls within the configured TTL will
# return the cached values instead of querying the API. Set
# AV_CACHE_TTL_SECS (default: 0, disabled) to the desired lifetime in
# seconds. Set AV_CACHE_DIR to override the cache directory (defaults to
# data/cache/alpha relative to the current working directory). The cache
# gracefully degrades: if the directory cannot be created or read, or if the
# JSON is malformed, the fetcher falls back to live API calls.

try:
    _AV_CACHE_TTL = int(os.getenv("AV_CACHE_TTL_SECS", "0").strip() or "0")
except Exception:
    _AV_CACHE_TTL = 0
try:
    _AV_CACHE_DIR = os.getenv("AV_CACHE_DIR", "data/cache/alpha")
    _AV_CACHE_PATH = Path(_AV_CACHE_DIR).resolve()
    if _AV_CACHE_TTL > 0:
        try:
            _AV_CACHE_PATH.mkdir(parents=True, exist_ok=True)
        except Exception:
            # If we cannot create the directory, disable caching.
            _AV_CACHE_TTL = 0
            _AV_CACHE_PATH = None  # type: ignore
except Exception:
    _AV_CACHE_TTL = 0
    _AV_CACHE_PATH = None  # type: ignore


def _alpha_last_prev_cached(
    ticker: str, api_key: str, *, timeout: int = 8
) -> Tuple[Optional[float], Optional[float]]:
    """
    Return (last, previous_close) using Alpha Vantage with optional disk cache.

    When caching is enabled (AV_CACHE_TTL_SECS > 0 and a cache directory exists),
    this function reads a JSON file named "<ticker>.json" from the cache directory.
    The file is expected to contain "last", "prev" and "ts" fields (epoch seconds).
    If the timestamp is within the TTL, the cached values are returned.
    Otherwise, the underlying _alpha_last_prev function is invoked to fetch fresh data.
    Successful fetches update the cache file.

    If caching is disabled or any read/write error occurs, the function
    transparently falls back to _alpha_last_prev.
    """
    # If caching is disabled, delegate directly.
    if _AV_CACHE_TTL <= 0 or not _AV_CACHE_PATH:
        return _alpha_last_prev(ticker, api_key, timeout=timeout)

    # Security: Validate ticker to prevent path injection attacks
    key = validate_ticker(ticker)
    if not key:
        log.error("market_cache_invalid_ticker ticker=%s", ticker)
        raise ValueError(f"Invalid ticker: {ticker}")

    cache_file = _AV_CACHE_PATH / f"{key}.json"
    now = time.time()
    # Attempt to read from cache
    try:
        if cache_file.exists():
            with cache_file.open("r", encoding="utf-8") as fp:
                data = json.load(fp)
            ts = float(data.get("ts", 0))
            if now - ts < _AV_CACHE_TTL:
                last = data.get("last")
                prev = data.get("prev")
                lval = float(last) if last is not None else None
                pval = float(prev) if prev is not None else None
                return lval, pval
    except Exception:
        # Corrupted cache or read error: fall through to live fetch
        pass
    # Cache miss: perform live fetch
    last, prev = _alpha_last_prev(ticker, api_key, timeout=timeout)
    # Write to cache (best-effort)
    try:
        cache_data = {"ts": now, "last": last, "prev": prev}
        with cache_file.open("w", encoding="utf-8") as fp:
            json.dump(cache_data, fp)
    except Exception:
        pass
    return last, prev


_AV_KEY = os.getenv("ALPHAVANTAGE_API_KEY", "").strip()
_SKIP_ALPHA = os.getenv("MARKET_SKIP_ALPHA", "0").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}


def _norm_ticker(t: Optional[str]) -> Optional[str]:
    """Normalize and validate a ticker symbol.

    Returns validated ticker in uppercase, or None if invalid.
    """
    if not t:
        return None
    t = t.strip().upper()
    # Remove $ prefix if present (common in social media mentions)
    if t.startswith("$"):
        t = t[1:]
    # Validate the ticker to prevent injection attacks
    validated = validate_ticker(t, allow_empty=False)
    return validated


def _fi_get(fi, attr: str) -> Optional[float]:
    """Return a numeric value from yfinance fast_info via attr or dict key."""
    if fi is None:
        return None
    val = None
    if hasattr(fi, attr):
        val = getattr(fi, attr, None)
    elif isinstance(fi, dict):
        val = fi.get(attr)
    try:
        return float(val) if val is not None else None
    except Exception:
        return None


def _alpha_last_prev(
    ticker: str, api_key: str, *, timeout: int = 8
) -> Tuple[Optional[float], Optional[float]]:
    """
    Alpha Vantage GLOBAL_QUOTE: returns (last, previous_close) or (None, None) on failure.
    Never raises.
    """
    try:
        url = "https://www.alphavantage.co/query"
        params = {"function": "GLOBAL_QUOTE", "symbol": ticker, "apikey": api_key}
        r = requests.get(url, params=params, timeout=timeout)
        if r.status_code != 200:
            return None, None

        try:
            j = r.json()
        except (ValueError, requests.exceptions.JSONDecodeError) as e:
            log.warning("alpha_vantage_invalid_json ticker=%s err=%s", ticker, str(e))
            return None, None

        if not j or not isinstance(j, dict):
            log.warning(
                "alpha_vantage_unexpected_response ticker=%s type=%s",
                ticker,
                type(j).__name__,
            )
            return None, None

        q = j.get("Global Quote") or j.get("globalQuote") or {}
        last = q.get("05. price") or q.get("price")
        prev = q.get("08. previous close") or q.get("previousClose")
        return (
            float(last) if last not in (None, "", "0", "0.0") else None,
            float(prev) if prev not in (None, "", "0", "0.0") else None,
        )
    except Exception:
        return None, None


# ---------------------------------------------------------------------------
# Tiingo price fetcher
#
# When FEATURE_TIINGO=1 and TIINGO_API_KEY is set, the bot will prefer Tiingo for price data.
# The Tiingo IEX endpoint provides real-time quotes and intraday OHLC, and the Tiingo daily
# endpoint provides historical daily OHLC. The helpers below fetch data from Tiingo, falling
# back to None on errors, so that caller functions can proceed to alternate providers.


def _tiingo_last_prev(
    ticker: str, api_key: str, *, timeout: int = 8
) -> Tuple[Optional[float], Optional[float]]:
    """Return (last, previous_close) using Tiingo IEX API.

    Attempts to fetch the latest trade price and previous close from Tiingo's IEX endpoint.
    Returns (None, None) gracefully on any error or missing field.
    """
    try:
        url = f"https://api.tiingo.com/iex/{ticker.strip().upper()}"
        params = {"token": api_key.strip()}
        r = requests.get(url, params=params, timeout=timeout)
        if r.status_code != 200:
            return None, None

        try:
            data = r.json()
        except (ValueError, requests.exceptions.JSONDecodeError) as e:
            log.warning("tiingo_invalid_json ticker=%s err=%s", ticker, str(e))
            return None, None

        # Response may be a list of quote objects or a single object
        q: Dict[str, float] = {}
        if isinstance(data, list):
            if not data:
                return None, None
            q = data[0] or {}
        elif isinstance(data, dict):
            q = data
        else:
            return None, None
        # Extract last price from any of several possible fields
        last_candidates = [
            q.get("last"),
            q.get("tngoLast"),
            q.get("lastSalePrice"),
            q.get("close"),
            q.get("adjClose"),
        ]
        prev_candidates = [
            q.get("prevClose"),
            q.get("previousClose"),
            q.get("priorClose"),
            q.get("prevclose"),
        ]
        last_val = None
        prev_val = None
        for cand in last_candidates:
            try:
                if cand not in (None, "", "0", "0.0"):
                    last_val = float(cand)
                    break
            except Exception:
                continue
        for cand in prev_candidates:
            try:
                if cand not in (None, "", "0", "0.0"):
                    prev_val = float(cand)
                    break
            except Exception:
                continue
        return last_val, prev_val
    except Exception:
        return None, None


def _tiingo_intraday_series(
    ticker: str,
    api_key: str,
    *,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    resample_freq: str = "5min",
    after_hours: bool = True,
    timeout: int = 10,
) -> Optional[pd.DataFrame]:
    """Fetch intraday OHLCV series for `ticker` from Tiingo (IEX) API.

    Returns a DataFrame indexed by timestamp with columns Open, High, Low, Close, Volume.
    Includes pre/post-market data if `after_hours` is True. Returns None on failure or no data.
    """
    try:
        url = f"https://api.tiingo.com/iex/{ticker.strip().upper()}/prices"
        params: Dict[str, str] = {
            "token": api_key.strip(),
            "resampleFreq": str(resample_freq),
        }
        params["afterHours"] = "true" if after_hours else "false"
        if start_date:
            params["startDate"] = start_date
        if end_date:
            params["endDate"] = end_date
        # Use tuple timeout (connect_timeout, read_timeout) to properly handle hangs
        r = requests.get(url, params=params, timeout=(timeout, timeout))
        if r.status_code != 200:
            return None

        try:
            data = r.json()
        except (ValueError, requests.exceptions.JSONDecodeError) as e:
            log.warning("tiingo_intraday_invalid_json ticker=%s err=%s", ticker, str(e))
            return None

        if not data or not isinstance(data, list):
            return None
        df = pd.DataFrame(data)
        if df is None or df.empty:
            return None
        # Parse 'date' field as datetime index if present
        if "date" in df.columns:
            try:
                df["date"] = pd.to_datetime(df["date"])
                df.set_index("date", inplace=True)
            except Exception:
                pass  # If parsing fails, leave index as is
        # Standardize column names (Tiingo returns lowercase keys)
        rename_map: Dict[str, str] = {}
        for col in list(df.columns):
            clow = col.lower()
            if clow == "open":
                rename_map[col] = "Open"
            elif clow == "high":
                rename_map[col] = "High"
            elif clow == "low":
                rename_map[col] = "Low"
            elif clow == "close":
                rename_map[col] = "Close"
            elif clow == "volume":
                rename_map[col] = "Volume"
        if rename_map:
            df.rename(columns=rename_map, inplace=True)
        return df
    except Exception:
        return None


def _tiingo_daily_history(
    ticker: str,
    api_key: str,
    *,
    start_date: str,
    end_date: str,
    timeout: int = 10,
) -> Optional[pd.DataFrame]:
    """
    Fetch daily historical OHLCV data for `ticker` from Tiingo daily prices API.

    Returns a DataFrame indexed by date with columns Open, High, Low, Close, Volume
    (and AdjClose if available). Returns None on failure or if no data is returned.
    """
    try:
        url = f"https://api.tiingo.com/tiingo/daily/{ticker.strip().upper()}/prices"
        params = {
            "token": api_key.strip(),
            "startDate": start_date,
            "endDate": end_date,
            "resampleFreq": "daily",
        }
        r = requests.get(url, params=params, timeout=timeout)
        if r.status_code != 200:
            return None

        try:
            data = r.json()
        except (ValueError, requests.exceptions.JSONDecodeError) as e:
            log.warning("tiingo_daily_invalid_json ticker=%s err=%s", ticker, str(e))
            return None

        if not data or not isinstance(data, list):
            return None
        df = pd.DataFrame(data)
        if df is None or df.empty:
            return None
        if "date" in df.columns:
            try:
                df["date"] = pd.to_datetime(df["date"])
                df.set_index("date", inplace=True)
            except Exception:
                pass
        rename_map: Dict[str, str] = {}
        for col in list(df.columns):
            clow = col.lower()
            if clow == "open":
                rename_map[col] = "Open"
            elif clow == "high":
                rename_map[col] = "High"
            elif clow == "low":
                rename_map[col] = "Low"
            elif clow == "close":
                rename_map[col] = "Close"
            elif clow == "volume":
                rename_map[col] = "Volume"
            elif clow == "adjclose":
                rename_map[col] = "AdjClose"
        if rename_map:
            df.rename(columns=rename_map, inplace=True)
        return df
    except Exception:
        return None


def get_last_price_snapshot(
    ticker: str, retries: int = 2
) -> Tuple[Optional[float], Optional[float]]:
    """
    Return the best-effort last traded price and previous close for a ticker.

    PROVIDER PRIORITY STRATEGY:
    ===========================
    This function implements a fallback chain for price data with clear priorities:

    1. PRIMARY: Tiingo IEX API ($30/month)
       - Real-time quotes with superior reliability
       - Excellent rate limits (1000 req/hr on starter plan)
       - Intraday OHLC data available
       - Requires: FEATURE_TIINGO=1, TIINGO_API_KEY
       - NOTE: Does NOT support OTC tickers

    2. BACKUP: Alpha Vantage GLOBAL_QUOTE
       - Free tier: 25 API calls/day (very limited)
       - Falls back when Tiingo unavailable
       - Requires: ALPHAVANTAGE_API_KEY
       - NOTE: Limited OTC ticker support

    3. BACKUP: yfinance
       - Final fallback, no API key required
       - Uses fast_info and history() methods
       - May be slower and less reliable
       - BEST SUPPORT for OTC tickers

    OTC TICKER HANDLING:
    ====================
    OTC tickers (OTCQB, OTCQX, Pink Sheets) are NOT supported by Tiingo IEX
    and have limited support in Alpha Vantage. For OTC tickers, this function
    automatically prioritizes yfinance as the PRIMARY provider to maximize
    success rate.

    OTC Detection: Checks if ticker validation marks it as OTC exchange

    Respects the MARKET_PROVIDER_ORDER setting to determine provider precedence.
    Supported identifiers include:
      - ``tiingo`` (Tiingo IEX API - PRIMARY for listed stocks)
      - ``av`` or ``alpha`` (Alpha Vantage - BACKUP)
      - ``yf`` or ``yahoo`` (yfinance - PRIMARY for OTC, BACKUP for listed)

    Providers are tried in order; missing values from earlier providers may be
    filled by later ones. Telemetry is logged for each provider attempt, including
    the provider role (PRIMARY/BACKUP).

    This function never raises; it returns (last, prev) where either component
    may be None.

    Returns
    -------
    tuple of (float or None, float or None)
        (last_price, previous_close) where either value may be None if unavailable
    """
    nt = _norm_ticker(ticker)
    if not nt:
        return None, None
    last: Optional[float] = None
    prev: Optional[float] = None

    # Resolve settings lazily to get feature flags without circular import
    try:
        settings = get_settings()
    except Exception:
        settings = None  # pragma: no cover

    # Determine provider order (default "tiingo,av,yf")
    order_str = getattr(settings, "market_provider_order", None) if settings else None
    if not order_str:
        order_str = "av,yf,tiingo"
    providers = [p.strip().lower() for p in str(order_str).split(",") if p.strip()]

    # OTC TICKER FIX: Detect OTC tickers and prioritize yfinance
    # Tiingo IEX and Alpha Vantage do not support OTC markets reliably
    # yfinance has the best OTC ticker support via Yahoo Finance data
    is_otc = False
    try:
        from .ticker_validation import TickerValidator
        validator = TickerValidator()
        is_otc = validator.is_otc(nt)
        if is_otc:
            # Reorder providers: yfinance first, then others
            log.info(
                "otc_ticker_detected ticker=%s provider_reorder=yf_first",
                nt
            )
            # Move yfinance variants to front
            yf_providers = [p for p in providers if p in {"yf", "yahoo", "yfinance"}]
            other_providers = [p for p in providers if p not in {"yf", "yahoo", "yfinance"}]
            providers = yf_providers + other_providers
            # Ensure yfinance is always in the list for OTC tickers
            if not yf_providers:
                log.warning(
                    "otc_ticker_missing_yfinance ticker=%s adding_yf_provider",
                    nt
                )
                providers = ["yf"] + providers
    except Exception as e:
        # If OTC detection fails, continue with default provider order
        log.debug(
            "otc_detection_failed ticker=%s err=%s continuing_with_defaults",
            nt,
            str(e.__class__.__name__)
        )

    # Helper to log telemetry
    def _log_provider(
        provider: str,
        t0: float,
        l: Optional[float],
        p: Optional[float],
        error: Optional[str] = None,
    ) -> None:
        try:
            elapsed = (time.perf_counter() - t0) * 1000.0
            status = "ok" if (l is not None or p is not None) else (error or "no_data")
            log.info(
                "provider_usage provider=%s t_ms=%.1f status=%s",
                provider,
                elapsed,
                status,
            )
        except Exception:
            pass  # Logging should never disrupt execution

    # Try each provider in order
    for prov in providers:
        pname = prov.lower()
        if pname in {"tiingo", "tngo"}:
            # Only use Tiingo if feature flag is enabled and API key is set
            use_tiingo = False
            key = ""
            if settings is not None:
                use_tiingo = bool(getattr(settings, "feature_tiingo", False))
                key = getattr(settings, "tiingo_api_key", "") or ""
            if use_tiingo and key:
                for attempt in range(retries + 1):
                    t0 = time.perf_counter()
                    try:
                        t_last, t_prev = _tiingo_last_prev(nt, key)
                        if t_last is not None:
                            last = t_last
                        if t_prev is not None:
                            prev = t_prev
                        _log_provider("tiingo", t0, t_last, t_prev)
                        # If both values obtained, return immediately
                        if last is not None and prev is not None:
                            log.info(
                                "provider provider=tiingo ticker=%s role=PRIMARY "
                                "last=%.2f prev=%.2f",
                                nt,
                                last,
                                prev,
                            )
                            return last, prev
                    except Exception as e:
                        _log_provider(
                            "tiingo", t0, None, None, error=str(e.__class__.__name__)
                        )
                    time.sleep(0.35 * (attempt + 1))  # brief backoff between attempts
            continue

        if pname in {"av", "alpha", "alphavantage", "alpha_vantage"}:
            if not _AV_KEY or _SKIP_ALPHA:
                continue
            for attempt in range(retries + 1):
                t0 = time.perf_counter()
                try:
                    a_last, a_prev = _alpha_last_prev_cached(nt, _AV_KEY)
                    if a_last is not None:
                        last = a_last
                    if a_prev is not None:
                        prev = a_prev
                    _log_provider("alpha", t0, a_last, a_prev)
                    if last is not None and prev is not None:
                        log.info(
                            "provider provider=alpha_vantage ticker=%s role=BACKUP "
                            "last=%.2f prev=%.2f",
                            nt,
                            last,
                            prev,
                        )
                        return last, prev
                except Exception as e:
                    _log_provider(
                        "alpha", t0, None, None, error=str(e.__class__.__name__)
                    )
                time.sleep(0.35 * (attempt + 1))
            continue

        if pname in {"yf", "yahoo", "yfinance"}:
            if yf is None:
                log.info("yf_missing skip_price_lookup")
                continue
            t = yf.Ticker(nt)
            for attempt in range(retries + 1):
                t0 = time.perf_counter()
                try:
                    # Use fast_info if available to get last and prev quickly
                    fi = getattr(t, "fast_info", None)
                    if fi is not None:
                        if last is None:
                            candidate = _fi_get(fi, "last_price")
                            if candidate is not None:
                                last = candidate
                        if prev is None:
                            candidate = _fi_get(fi, "previous_close")
                            if candidate is not None:
                                prev = candidate
                    # If any value still missing, fall back to a tiny history call
                    hist = t.history(period="2d", interval="1d", auto_adjust=False)
                    if not getattr(hist, "empty", False):
                        # Always prefer history for the most recent closing price
                        # when falling back to yfinance
                        try:
                            last = float(hist["Close"].iloc[-1])
                            if len(hist) >= 2:
                                prev = float(hist["Close"].iloc[-2])
                            else:
                                # if only one row, keep prev unchanged or try t.info
                                info = getattr(t, "info", None)
                                if isinstance(info, dict):
                                    pv = info.get("previousClose") or info.get(
                                        "regularMarketPreviousClose"
                                    )
                                    if pv is not None:
                                        prev = float(pv)
                        except Exception:
                            pass
                    _log_provider("yf", t0, last, prev)
                    if last is not None and prev is not None:
                        log.info(
                            "provider provider=yfinance ticker=%s role=BACKUP "
                            "last=%.2f prev=%.2f",
                            nt,
                            last,
                            prev,
                        )
                    # After one attempt (fast_info + possibly history), break out
                    break
                except Exception as e:
                    _log_provider("yf", t0, None, None, error=str(e.__class__.__name__))
                    if attempt >= retries:
                        break
                    time.sleep(0.4 * (attempt + 1))
            # (We don't break the outer loop here,
            # to allow merging values from other providers if needed)
            continue

    # After trying all providers, return what we have (possibly None values)
    # Log warning if OTC ticker failed to get price data
    if is_otc and (last is None or prev is None):
        log.warning(
            "otc_price_unavailable ticker=%s providers_tried=%s last=%s prev=%s "
            "hint=yfinance_is_best_for_otc",
            nt,
            ",".join(providers),
            "available" if last is not None else "N/A",
            "available" if prev is not None else "N/A"
        )
    return last, prev


def get_last_price_change(
    ticker: str, retries: int = 2
) -> Tuple[Optional[float], Optional[float]]:
    """
    Returns (last_price, change_pct).

    The change_pct is None if the previous close is unknown or zero.
    """
    last, prev = get_last_price_snapshot(ticker, retries=retries)
    # Use epsilon check to avoid division by zero (handles 0, 0.0, very small numbers)
    if last is None or prev is None or abs(prev) < 1e-9:
        return last, None
    try:
        change_pct = ((last - prev) / prev) * 100.0
    except Exception:
        return last, None
    return last, float(change_pct)


def batch_get_prices(
    tickers: list[str],
) -> Dict[str, Tuple[Optional[float], Optional[float]]]:
    """
    Batch fetch prices for multiple tickers (10-20x faster than sequential calls).

    Uses yfinance batch download to fetch all prices concurrently. This is
    significantly faster than calling get_last_price_change() in a loop.

    Parameters
    ----------
    tickers : list[str]
        List of ticker symbols to fetch prices for

    Returns
    -------
    Dict[str, Tuple[Optional[float], Optional[float]]]
        Mapping of ticker → (last_price, change_pct)
        Returns (None, None) for tickers that fail

    Examples
    --------
    >>> prices = batch_get_prices(['AAPL', 'MSFT', 'GOOGL'])
    >>> prices['AAPL']
    (150.25, 1.5)  # last price, change %

    Notes
    -----
    For a single cycle processing 200 tickers:
    - Sequential: ~43 seconds (200 × 250ms avg)
    - Batch: ~3-5 seconds (10-15x speedup)
    """
    if not tickers:
        return {}

    if yf is None:
        log.warning("yfinance_missing batch_fetch_skipped")
        return {ticker: (None, None) for ticker in tickers}

    # Normalize tickers
    norm_tickers = [_norm_ticker(t) for t in tickers]
    valid_tickers = [t for t in norm_tickers if t]

    if not valid_tickers:
        return {ticker: (None, None) for ticker in tickers}

    results = {}
    t0 = time.perf_counter()

    try:
        # Use yfinance batch download (much faster than individual Ticker() calls)
        # Set threads=True for concurrent downloads
        data = yf.download(
            tickers=" ".join(valid_tickers),  # Space-separated string
            period="2d",  # Get last 2 days for prev close calculation
            interval="1d",
            auto_adjust=False,
            progress=False,
            threads=True,  # Enable concurrent fetching
        )

        # Handle both single and multiple ticker results
        if data is None or data.empty:
            log.warning("batch_fetch_empty tickers=%d", len(valid_tickers))
            return {ticker: (None, None) for ticker in tickers}

        # Process results for each ticker
        for ticker in valid_tickers:
            try:
                # For single ticker, data structure is different
                if len(valid_tickers) == 1:
                    ticker_data = data
                else:
                    # Multi-ticker: data.columns is MultiIndex
                    ticker_data = data.xs(ticker, level=1, axis=1, drop_level=True)

                if ticker_data.empty or len(ticker_data) < 1:
                    results[ticker] = (None, None)
                    continue

                # Get last row (most recent)
                last_row = ticker_data.iloc[-1]
                last_price = last_row.get("Close")

                # FIX: Pandas returns NaN for missing data, convert to None
                # NaN would pass through filters since NaN != None and NaN > 10 = False
                import math
                if last_price is not None and (math.isnan(last_price) or not math.isfinite(last_price)):
                    last_price = None

                # Get prev close (if available)
                if len(ticker_data) >= 2:
                    prev_row = ticker_data.iloc[-2]
                    prev_close = prev_row.get("Close")
                    # FIX: Convert NaN to None
                    if prev_close is not None and (math.isnan(prev_close) or not math.isfinite(prev_close)):
                        prev_close = None
                else:
                    prev_close = None

                # Calculate change %
                change_pct = None
                if (
                    last_price is not None
                    and prev_close is not None
                    and abs(prev_close) > 1e-9
                ):  # noqa: E501
                    try:
                        change_pct = ((last_price - prev_close) / prev_close) * 100.0
                        # FIX: Check if result is NaN
                        if math.isnan(change_pct) or not math.isfinite(change_pct):
                            change_pct = None
                    except Exception:
                        pass

                results[ticker] = (
                    float(last_price) if last_price is not None else None,
                    float(change_pct) if change_pct is not None else None,
                )

            except Exception as e:
                log.debug(
                    "batch_fetch_ticker_failed ticker=%s err=%s",
                    ticker,
                    e.__class__.__name__,
                )
                results[ticker] = (None, None)

        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        log.info(
            "batch_fetch_complete tickers=%d t_ms=%.1f speedup=~%.0fx",
            len(valid_tickers),
            elapsed_ms,
            (len(valid_tickers) * 250.0) / elapsed_ms if elapsed_ms > 0 else 1,
        )

    except Exception as e:
        log.warning(
            "batch_fetch_failed tickers=%d err=%s",
            len(valid_tickers),
            e.__class__.__name__,
        )
        return {ticker: (None, None) for ticker in tickers}

    # Fill in any missing tickers
    for ticker in tickers:
        norm_t = _norm_ticker(ticker)
        if norm_t and norm_t not in results:
            results[norm_t] = (None, None)

    # TIINGO FALLBACK: Retry failed tickers using get_price() which has Tiingo support
    # This gives us reliable fallback for tickers where yfinance fails
    failed_tickers = [
        ticker for ticker, (price, _) in results.items() if price is None
    ]

    if failed_tickers:
        log.info(
            "tiingo_fallback_retry failed_count=%d tickers=%s",
            len(failed_tickers),
            ",".join(failed_tickers[:5]) + ("..." if len(failed_tickers) > 5 else "")
        )

        for ticker in failed_tickers:
            try:
                # get_price() has built-in provider chain (tiingo -> av -> yf)
                fallback_price, fallback_change = get_price(ticker)
                if fallback_price is not None:
                    results[ticker] = (fallback_price, fallback_change)
                    log.debug(
                        "tiingo_fallback_success ticker=%s price=%.2f change=%.2f",
                        ticker,
                        fallback_price,
                        fallback_change if fallback_change is not None else 0.0
                    )
            except Exception as e:
                log.debug(
                    "tiingo_fallback_failed ticker=%s err=%s",
                    ticker,
                    e.__class__.__name__
                )

    return results


def sample_alpaca_stream(tickers: list[str] | tuple[str, ...], secs: int) -> None:
    """Sample Alpaca IEX stream for given tickers for up to `secs` seconds (stub).

    Logs when streaming starts and ends; does not open a real stream.
    """
    try:
        secs_int = int(secs)
    except Exception:
        secs_int = 0
    tickers_list = [str(t).strip().upper() for t in tickers if t]
    try:
        log.info(
            "alpaca_stream_start tickers=%s secs=%s", ",".join(tickers_list), secs_int
        )
    except Exception:
        pass
    try:
        wait_time = min(max(secs_int, 0), 30)
        time.sleep(wait_time)
    except Exception:
        pass
    try:
        log.info("alpaca_stream_end tickers=%s", ",".join(tickers_list))
    except Exception:
        pass
    return None


# Public API (explicit export list)
__all__ = [
    "NewsItem",
    "ScoredItem",
    "get_last_price_snapshot",
    "get_last_price_change",
    "batch_get_prices",
    "get_volatility",
    "get_intraday",
    "get_intraday_snapshots",
    "get_intraday_indicators",
    "sample_alpaca_stream",
]
# ---------------------------------------------------------------------------
# Volatility and intraday helpers
#
# - get_volatility: average daily range (High-Low)/Close over the past N days.
# - get_intraday: intraday OHLC data via Tiingo (if enabled) or yfinance.
# - get_intraday_snapshots: premarket/intraday/after-hours OHLC snapshots for a given date.
# - get_intraday_indicators: simple indicators (VWAP, RSI14) from 1-minute bars.
# - get_momentum_indicators: extended indicators (MACD, EMA crosses, VWAP delta) from 1-minute bars.


def get_volatility(ticker: str, *, days: int = 14) -> Optional[float]:
    """
    Return the average daily range percentage over the past `days` days.

    The daily range is (High - Low) / Close for each day.
    Returns the average (percentage) over `days` days.
    If insufficient data is available or no provider is available,
    returns None.
    """
    nt = _norm_ticker(ticker)
    try:
        settings = get_settings()
    except Exception:
        settings = None
    use_tiingo = bool(settings and getattr(settings, "feature_tiingo", False))
    tiingo_key = getattr(settings, "tiingo_api_key", "") if settings else ""
    if nt is None or (yf is None and not (use_tiingo and tiingo_key)):
        return None
    try:
        period_days = max(
            days + 1, days + 5
        )  # fetch a bit extra to ensure `days` complete days
        hist_df: Optional[pd.DataFrame] = None
        if use_tiingo and tiingo_key:
            try:
                end_dt = datetime.now().date()
                start_dt = end_dt - timedelta(days=period_days)
                tiingo_df = _tiingo_daily_history(
                    nt,
                    tiingo_key,
                    start_date=start_dt.strftime("%Y-%m-%d"),
                    end_date=end_dt.strftime("%Y-%m-%d"),
                )
                if tiingo_df is not None and not getattr(tiingo_df, "empty", False):
                    hist_df = tiingo_df
            except Exception:
                hist_df = None
        if hist_df is None:
            if yf is None:
                return None
            hist_df = yf.Ticker(nt).history(
                period=f"{period_days}d",
                interval="1d",
                auto_adjust=False,
                prepost=False,
            )
        if hist_df is None or getattr(hist_df, "empty", False):
            return None
        df_slice = hist_df.tail(days)
        if df_slice.empty:
            return None
        try:
            ranges = (df_slice["High"] - df_slice["Low"]) / df_slice["Close"]
            avg_range = float(ranges.mean()) * 100.0
            return avg_range
        except Exception:
            return None
    except Exception:
        return None


def get_intraday(
    ticker: str,
    *,
    interval: str = "5min",
    output_size: str = "full",
    prepost: bool = True,
) -> Optional[pd.DataFrame]:
    """Return intraday OHLC data for a ticker (prefers Tiingo IEX if configured, else yfinance).

    Parameters:
        ticker (str): Ticker symbol to fetch.
        interval (str): Bar interval (e.g., "1m", "5min", "15min").
        output_size (str): "full" (max data) or "compact" (recent data).
        prepost (bool): Include pre/post-market data if True.

    Returns:
        pandas.DataFrame or None: DataFrame of OHLCV bars indexed by timestamp, or None on error.
    """
    try:
        settings = get_settings()
    except Exception:
        settings = None
    use_tiingo = bool(settings and getattr(settings, "feature_tiingo", False))
    tiingo_key = getattr(settings, "tiingo_api_key", "") if settings else ""
    if yf is None and not (use_tiingo and tiingo_key):
        return None
    nt = _norm_ticker(ticker)
    if nt is None:
        return None
    try:
        # Try Tiingo intraday if enabled
        if use_tiingo and tiingo_key:
            try:
                end_date = datetime.now().date()
                start_date = end_date - timedelta(
                    days=(7 if output_size.lower() == "compact" else 60)
                )
                df_ti = _tiingo_intraday_series(
                    nt,
                    tiingo_key,
                    start_date=start_date.strftime("%Y-%m-%d"),
                    end_date=end_date.strftime("%Y-%m-%d"),
                    resample_freq=interval,
                    after_hours=prepost,
                )
                if df_ti is not None and not getattr(df_ti, "empty", False):
                    return df_ti
            except Exception:
                pass  # On failure, fall back to yfinance
        # Fallback to yfinance
        if yf is None:
            return None
        period = "5d" if output_size.lower() == "compact" else "60d"
        # Map '5min' -> '5m' etc. so yfinance accepts it
        _yf_interval_map = {
            "1min": "1m",
            "2min": "2m",
            "5min": "5m",
            "15min": "15m",
            "30min": "30m",
            "60min": "60m",
            "90min": "90m",
            "1hour": "1h",
        }
        yf_interval = _yf_interval_map.get(interval.lower(), interval)
        df = yf.download(
            nt,
            period=period,
            interval=yf_interval,
            prepost=prepost,
            auto_adjust=False,
            progress=False,
        )
        if df is None or getattr(df, "empty", False):
            log.info(
                "yf_fallback_empty ticker=%s interval=%s period=%s",
                nt,
                yf_interval,
                period,
            )
            return None
        return df
    except Exception:
        return None


def get_intraday_snapshots(
    ticker: str, *, target_date: Optional[datetime.date] = None
) -> Optional[Dict[str, Dict[str, float]]]:
    """Compute premarket/intraday/after-hours OHLC snapshots for `ticker` on a given date.

    Returns a dict with keys "premarket", "intraday", "afterhours". Each value is a dict with keys:
    {"open", "high", "low", "close"} (floats or None if no data for that segment).
    Returns None on error or if data unavailable.
    """
    try:
        settings = get_settings()
    except Exception:
        settings = None
    use_tiingo = bool(settings and getattr(settings, "feature_tiingo", False))
    tiingo_key = getattr(settings, "tiingo_api_key", "") if settings else ""
    if yf is None and not (use_tiingo and tiingo_key):
        return None
    nt = _norm_ticker(ticker)
    if nt is None:
        return None
    try:
        from zoneinfo import ZoneInfo  # Python 3.9+
    except Exception:
        try:
            from backports.zoneinfo import ZoneInfo  # type: ignore
        except Exception:
            ZoneInfo = None  # type: ignore
    if ZoneInfo is None:
        return None
    try:
        if target_date is None:
            target_date = datetime.now().date()
        df = None
        if use_tiingo and tiingo_key:
            try:
                start_dt = target_date - timedelta(days=1)
                end_dt = target_date + timedelta(days=1)
                df_ti = _tiingo_intraday_series(
                    nt,
                    tiingo_key,
                    start_date=start_dt.strftime("%Y-%m-%d"),
                    end_date=end_dt.strftime("%Y-%m-%d"),
                    resample_freq="1min",
                    after_hours=True,
                )
                if df_ti is not None and not getattr(df_ti, "empty", False):
                    df = df_ti
            except Exception:
                df = None
        if df is None:
            if yf is None:
                return None
            df = yf.download(
                nt,
                start=(target_date - timedelta(days=1)).strftime("%Y-%m-%d"),
                end=(target_date + timedelta(days=1)).strftime("%Y-%m-%d"),
                interval="1m",
                prepost=True,
                auto_adjust=False,
                progress=False,
            )
        if df is None or getattr(df, "empty", False):
            return None
        idx = df.index
        if not isinstance(idx, pd.DatetimeIndex):
            return None
        try:
            if idx.tz is None:
                df.index = idx.tz_localize("UTC").tz_convert("America/New_York")
            else:
                df.index = idx.tz_convert("America/New_York")
        except Exception:
            return None

        # Define day segments in US/Eastern time
        def segment_range(start_hm: Tuple[int, int], end_hm: Tuple[int, int]):
            sdt = datetime(
                target_date.year,
                target_date.month,
                target_date.day,
                start_hm[0],
                start_hm[1],
                tzinfo=ZoneInfo("America/New_York"),
            )
            edt = datetime(
                target_date.year,
                target_date.month,
                target_date.day,
                end_hm[0],
                end_hm[1],
                tzinfo=ZoneInfo("America/New_York"),
            )
            return sdt, edt

        segments = {
            "premarket": segment_range((4, 0), (9, 30)),
            "intraday": segment_range((9, 30), (16, 1)),
            "afterhours": segment_range((16, 0), (20, 1)),
        }
        snaps: Dict[str, Dict[str, Optional[float]]] = {}
        for name, (sdt, edt) in segments.items():
            seg_df = df.loc[(df.index >= sdt) & (df.index < edt)]
            if seg_df is None or seg_df.empty:
                snaps[name] = {"open": None, "high": None, "low": None, "close": None}
                continue
            try:
                open_val = (
                    float(seg_df.iloc[0]["Open"])
                    if "Open" in seg_df.columns
                    else float(seg_df.iloc[0]["Close"])
                )
            except Exception:
                open_val = None
            try:
                high_val = (
                    float(seg_df["High"].max()) if "High" in seg_df.columns else None
                )
            except Exception:
                high_val = None
            try:
                low_val = (
                    float(seg_df["Low"].min()) if "Low" in seg_df.columns else None
                )
            except Exception:
                low_val = None
            try:
                close_val = float(seg_df.iloc[-1]["Close"])
            except Exception:
                close_val = None
            snaps[name] = {
                "open": open_val,
                "high": high_val,
                "low": low_val,
                "close": close_val,
            }
        return snaps
    except Exception:
        return None


def get_intraday_indicators(
    ticker: str, *, target_date: Optional[datetime.date] = None
) -> Dict[str, Optional[float]]:
    """
    Compute basic intraday indicators (VWAP and 14-period RSI) for `ticker`
    using 1-minute bars.

    Returns {'vwap': <value_or_None>, 'rsi14': <value_or_None>} or {} on
    failure or if indicators feature is disabled.
    """
    try:
        if not getattr(get_settings(), "feature_indicators", False):
            return {}
    except Exception:
        return {}
    try:
        settings = get_settings()
    except Exception:
        settings = None
    use_tiingo = bool(settings and getattr(settings, "feature_tiingo", False))
    tiingo_key = getattr(settings, "tiingo_api_key", "") if settings else ""
    if yf is None and not (use_tiingo and tiingo_key):
        return {}
    nt = _norm_ticker(ticker)
    if not nt:
        return {}
    try:
        if target_date is None:
            target_date = datetime.now().date()
        df = None
        if use_tiingo and tiingo_key:
            try:
                start_dt = target_date - timedelta(days=1)
                end_dt = target_date + timedelta(days=1)
                df_ti = _tiingo_intraday_series(
                    nt,
                    tiingo_key,
                    start_date=start_dt.strftime("%Y-%m-%d"),
                    end_date=end_dt.strftime("%Y-%m-%d"),
                    resample_freq="1min",
                    after_hours=True,
                )
                if df_ti is not None and not getattr(df_ti, "empty", False):
                    df = df_ti
            except Exception:
                df = None
        if df is None:
            if yf is None:
                return {}
            df = yf.download(
                nt,
                start=(target_date - timedelta(days=1)).strftime("%Y-%m-%d"),
                end=(target_date + timedelta(days=1)).strftime("%Y-%m-%d"),
                interval="1m",
                prepost=True,
                auto_adjust=False,
                progress=False,
            )
        if df is None or getattr(df, "empty", False):
            return {}
        cols = {c.lower(): c for c in df.columns}
        close = df[cols.get("close", "Close")]
        vol = df[cols.get("volume", "Volume")]
        # VWAP
        try:
            vwap_val = float((close * vol).sum() / vol.sum()) if vol.sum() else None
        except Exception:
            vwap_val = None
        # RSI-14 (Wilder's)
        try:
            delta = close.diff()
            up = delta.clip(lower=0.0)
            down = (-delta).clip(lower=0.0)
            roll = 14
            ma_up = up.ewm(alpha=1 / roll, adjust=False).mean()
            ma_down = down.ewm(alpha=1 / roll, adjust=False).mean()
            rs = ma_up / ma_down.replace(0, float("nan"))
            rsi = 100 - (100 / (1 + rs))
            rsi14_val = float(rsi.iloc[-1]) if rsi.notna().any() else None
        except Exception:
            rsi14_val = None
        out: Dict[str, Optional[float]] = {}
        if vwap_val is not None:
            out["vwap"] = vwap_val
        if rsi14_val is not None:
            out["rsi14"] = rsi14_val
        return out
    except Exception:
        return {}


def get_momentum_indicators(
    ticker: str, *, target_date: Optional[datetime.date] = None
) -> Dict[str, Optional[float]]:
    """
    Compute additional momentum indicators (MACD, EMA9/21 crossovers, VWAP delta)
    from 1-minute bars.

    Returns a dict with keys: macd, macd_signal, macd_cross, ema9, ema21,
    ema_cross, vwap_delta (values or None).

    Respects feature_momentum_indicators; returns {} if disabled or on error.
    """
    try:
        s = get_settings()
        if not (
            getattr(s, "feature_indicators", False)
            and getattr(s, "feature_momentum_indicators", False)
        ):
            return {}
    except Exception:
        return {}
    if yf is None:
        return {}
    nt = _norm_ticker(ticker)
    if not nt:
        return {}
    try:
        if target_date is None:
            target_date = datetime.now().date()
        df = None
        try:
            settings = get_settings()
        except Exception:
            settings = None
        use_tiingo = bool(settings and getattr(settings, "feature_tiingo", False))
        tiingo_key = getattr(settings, "tiingo_api_key", "") if settings else ""
        if use_tiingo and tiingo_key:
            try:
                start_dt = target_date - timedelta(days=3)
                end_dt = target_date + timedelta(days=1)
                df_ti = _tiingo_intraday_series(
                    nt,
                    tiingo_key,
                    start_date=start_dt.strftime("%Y-%m-%d"),
                    end_date=end_dt.strftime("%Y-%m-%d"),
                    resample_freq="1min",
                    after_hours=True,
                )
                if df_ti is not None and not getattr(df_ti, "empty", False):
                    df = df_ti
            except Exception:
                df = None
        if df is None:
            df = yf.download(
                nt,
                start=(target_date - timedelta(days=3)).strftime("%Y-%m-%d"),
                end=(target_date + timedelta(days=1)).strftime("%Y-%m-%d"),
                interval="1m",
                prepost=True,
                auto_adjust=False,
                progress=False,
            )
        if df is None or getattr(df, "empty", False):
            return {}
        cols = {c.lower(): c for c in df.columns}
        close = df[cols.get("close", "Close")]
        vol = df[cols.get("volume", "Volume")]
        out: Dict[str, Optional[float]] = {}
        # VWAP delta (last close vs VWAP)
        try:
            vwap_series = (close * vol).cumsum() / vol.cumsum()
            last_close = float(close.iloc[-1])
            vwap_val = (
                float(vwap_series.iloc[-1]) if not vwap_series.isna().iloc[-1] else None
            )
            if vwap_val is not None:
                out["vwap_delta"] = last_close - vwap_val
        except Exception:
            pass
        # EMA9 & EMA21 + crossover
        try:
            ema9_series = close.ewm(span=9, adjust=False).mean()
            ema21_series = close.ewm(span=21, adjust=False).mean()
            ema9_val = (
                float(ema9_series.iloc[-1]) if ema9_series.notna().iloc[-1] else None
            )
            ema21_val = (
                float(ema21_series.iloc[-1]) if ema21_series.notna().iloc[-1] else None
            )
            if ema9_val is not None:
                out["ema9"] = ema9_val
            if ema21_val is not None:
                out["ema21"] = ema21_val
            ema_cross = 0
            try:
                if len(ema9_series) >= 2 and len(ema21_series) >= 2:
                    prev_diff = ema9_series.iloc[-2] - ema21_series.iloc[-2]
                    curr_diff = ema9_series.iloc[-1] - ema21_series.iloc[-1]
                    if prev_diff < 0 <= curr_diff:
                        ema_cross = 1
                    elif prev_diff > 0 >= curr_diff:
                        ema_cross = -1
                out["ema_cross"] = ema_cross
            except Exception:
                pass
        except Exception:
            pass
        # MACD (EMA12-EMA26) and signal (EMA9 of MACD) + crossover
        try:
            ema12_series = close.ewm(span=12, adjust=False).mean()
            ema26_series = close.ewm(span=26, adjust=False).mean()
            macd_series = ema12_series - ema26_series
            signal_series = macd_series.ewm(span=9, adjust=False).mean()
            macd_val = (
                float(macd_series.iloc[-1]) if macd_series.notna().iloc[-1] else None
            )
            signal_val = (
                float(signal_series.iloc[-1])
                if signal_series.notna().iloc[-1]
                else None
            )
            if macd_val is not None:
                out["macd"] = macd_val
            if signal_val is not None:
                out["macd_signal"] = signal_val
            macd_cross = 0
            try:
                if len(macd_series) >= 2 and len(signal_series) >= 2:
                    prev_diff = macd_series.iloc[-2] - signal_series.iloc[-2]
                    curr_diff = macd_series.iloc[-1] - signal_series.iloc[-1]
                    if prev_diff < 0 <= curr_diff:
                        macd_cross = 1
                    elif prev_diff > 0 >= curr_diff:
                        macd_cross = -1
                out["macd_cross"] = macd_cross
            except Exception:
                pass
        except Exception:
            pass
        return out
    except Exception:
        return {}
