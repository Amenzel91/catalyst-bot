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

log = get_logger("market")

try:
    import yfinance as yf  # type: ignore
except Exception:  # pragma: no cover
    yf = None  # type: ignore

# Pandas is used for calculating momentum indicators when requested.  The
# computation functions below will import pandas and yfinance lazily as
# needed.  Do not import pandas at module load time to keep startup
# overhead minimal.

# ---------------------------------------------------------------------------
# Alpha Vantage caching
#
# To reduce external API calls (and avoid unnecessary rate limiting), the
# Alpha Vantage price fetcher supports a lightweight on‑disk cache. The cache
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
        # Only create directories when caching is enabled; ignore errors.
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
    """Return (last, previous_close) using Alpha Vantage with optional disk cache.

    When caching is enabled (AV_CACHE_TTL_SECS > 0 and a cache directory
    exists), this function reads a JSON file named ``<ticker>.json`` from the
    cache directory. The file is expected to contain ``last``, ``prev`` and
    ``ts`` fields (epoch seconds). If the timestamp is within the TTL, the
    cached values are returned. Otherwise, the underlying ``_alpha_last_prev``
    function is invoked to fetch fresh data. Successful fetches update the
    cache file.

    If caching is disabled or any read/write error occurs, the function
    transparently falls back to ``_alpha_last_prev``.
    """
    # If caching is disabled, delegate directly.
    if _AV_CACHE_TTL <= 0 or not _AV_CACHE_PATH:
        return _alpha_last_prev(ticker, api_key, timeout=timeout)
    key = ticker.strip().upper()
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
                # Return floats when values are present; else None
                lval = float(last) if last is not None else None
                pval = float(prev) if prev is not None else None
                return lval, pval
    except Exception:
        # Corrupted cache file or read error: fall through to live fetch
        pass
    # Cache miss: perform live fetch
    last, prev = _alpha_last_prev(ticker, api_key, timeout=timeout)
    # Write to cache (best‑effort)
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
    if not t:
        return None
    t = t.strip().upper()
    if t.startswith("$"):
        t = t[1:]
    return t or None


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
        j = r.json() or {}
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
# When enabled via FEATURE_TIINGO and a non‑empty TIINGO_API_KEY, Tiingo is
# consulted first for real‑time last price and previous close. The Tiingo IEX
# endpoint returns a JSON array of quote objects; we extract the ``last`` (or
# ``tngoLast``) and ``prevClose`` fields. On any error or missing data,
# (None, None) is returned without raising.
def _tiingo_last_prev(
    ticker: str, api_key: str, *, timeout: int = 8
) -> Tuple[Optional[float], Optional[float]]:
    """Return (last, previous_close) using Tiingo IEX API.

    This helper attempts to fetch the most recent trade price and previous close
    from the Tiingo IEX endpoint. It gracefully handles network errors,
    unexpected response formats and absent fields by returning (None, None).
    """
    try:
        # Build the request; Tiingo requires a token parameter.
        url = f"https://api.tiingo.com/iex/{ticker.strip().upper()}"
        params = {"token": api_key.strip()}
        r = requests.get(url, params=params, timeout=timeout)
        if r.status_code != 200:
            return None, None
        data = r.json()
        # The response may be a list of quote objects or a single object.
        q: Dict[str, float] = {}  # type: ignore
        if isinstance(data, list):
            if not data:
                return None, None
            # take the first record
            q = data[0] or {}
        elif isinstance(data, dict):
            q = data
        else:
            return None, None
        # Extract last price (multiple possible field names)
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
        last_val: Optional[float] = None
        prev_val: Optional[float] = None
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


def get_last_price_snapshot(
    ticker: str, retries: int = 2
) -> Tuple[Optional[float], Optional[float]]:
    """
    Return the best‑effort last traded price and previous close for a ticker.

    This implementation honours the MARKET_PROVIDER_ORDER setting to select
    providers.  Supported identifiers include ``tiingo`` (Tiingo IEX API),
    ``av`` or ``alpha`` (Alpha Vantage), and ``yf`` or ``yahoo`` (yfinance).
    Values are tried in the order provided; missing values from earlier
    providers may be filled by later ones.  Telemetry is logged to record
    which provider responded along with the latency and whether any values
    were returned.  On any exception or missing provider, the function
    continues to the next provider.  It never raises and returns
    ``(last, prev)`` where either component may be ``None``.
    """
    nt = _norm_ticker(ticker)
    if not nt:
        return None, None
    last: Optional[float] = None
    prev: Optional[float] = None

    # Resolve settings lazily to avoid circular imports in tests
    try:
        settings = get_settings()
    except Exception:
        settings = None  # pragma: no cover

    # Determine provider order
    order_str = None
    if settings is not None:
        order_str = getattr(settings, "market_provider_order", None)
    if not order_str:
        order_str = "tiingo,av,yf"
    providers = [p.strip().lower() for p in str(order_str).split(",") if p.strip()]

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
            # logging should never cause failures
            pass

    # Try each provider in order
    for prov in providers:
        pname = prov.lower()
        if pname in {"tiingo", "tngo"}:
            # Only consult Tiingo when feature flag and key present
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
                        # update values if present
                        if t_last is not None:
                            last = t_last
                        if t_prev is not None:
                            prev = t_prev
                        _log_provider("tiingo", t0, t_last, t_prev)
                        # Break early if both populated
                        if last is not None and prev is not None:
                            return last, prev
                    except Exception as e:
                        _log_provider(
                            "tiingo", t0, None, None, error=str(e.__class__.__name__)
                        )
                    # small backoff before next attempt
                    time.sleep(0.35 * (attempt + 1))
            continue

        if pname in {"av", "alpha", "alphavantage", "alpha_vantage"}:
            # Skip alpha when no key or skip flag
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
                        return last, prev
                except Exception as e:
                    _log_provider(
                        "alpha", t0, None, None, error=str(e.__class__.__name__)
                    )
                time.sleep(0.35 * (attempt + 1))
            continue

        if pname in {"yf", "yahoo", "yfinance"}:
            # yfinance fallback; if missing, log and skip
            if yf is None:
                log.info("yf_missing skip_price_lookup")
                continue
            t = yf.Ticker(nt)
            for attempt in range(retries + 1):
                t0 = time.perf_counter()
                try:
                    # Use fast_info to fill missing values; only update missing slots
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
                    # If still missing, fetch small history and override both values
                    if last is None or prev is None:
                        hist = t.history(period="2d", interval="1d", auto_adjust=False)
                        if not getattr(hist, "empty", False):
                            try:
                                close_series = hist["Close"]
                                last = float(close_series.iloc[-1])
                                if len(hist) >= 2:
                                    prev = float(close_series.iloc[-2])
                                else:
                                    info = getattr(t, "info", None)
                                    if isinstance(info, dict):
                                        pv = info.get("previousClose") or info.get(
                                            "regularMarketPreviousClose"
                                        )
                                        if pv is not None:
                                            try:
                                                prev = float(pv)
                                            except Exception:
                                                pass
                            except Exception:
                                pass
                    _log_provider("yf", t0, last, prev)
                    # Regardless of completeness, break after one attempt
                    break
                except Exception as e:
                    _log_provider("yf", t0, None, None, error=str(e.__class__.__name__))
                    if attempt >= retries:
                        break
                    time.sleep(0.4 * (attempt + 1))
            # Do not break outer loop; yfinance is typically last provider
            continue
    # After trying all providers, return whatever we collected (may be None)
    return last, prev


def get_last_price_change(
    ticker: str, retries: int = 2
) -> Tuple[Optional[float], Optional[float]]:
    """
    Returns (last_price, change_pct). change_pct may be None if previous close unknown.
    """
    last, prev = get_last_price_snapshot(ticker, retries=retries)
    if last is None or prev is None or prev == 0:
        return last, None
    try:
        chg_pct = (last - prev) / prev * 100.0
    except Exception:
        chg_pct = None
    return last, chg_pct


# ---------------------------------------------------------------------------
# Alpaca streaming (optional booster)
#
# When FEATURE_ALPACA_STREAM is enabled and valid credentials are provided,
# the runner may subscribe to Alpaca’s free IEX data feed for a short
# window after sending an alert.  This helper is a stub implementation that
# logs the intent to subscribe and waits for the configured sample window.


def sample_alpaca_stream(tickers: list[str] | tuple[str, ...], secs: int) -> None:
    """Sample Alpaca IEX stream for the given tickers for up to ``secs`` seconds.

    This function is a no‑op stub that logs when streaming starts and ends.
    In a production environment, this would open a websocket to Alpaca’s
    market data endpoint and stream real‑time quotes.  To avoid blocking
    the main thread, consider invoking this helper in a background thread.

    Parameters
    ----------
    tickers : list or tuple of str
        Tickers to subscribe to.
    secs : int
        Duration of the subscription window in seconds.  Values less than or
        equal to zero result in an immediate return.
    """
    try:
        secs_int = int(secs) if secs is not None else 0
    except Exception:
        secs_int = 0
    if not tickers or secs_int <= 0:
        return
    # Normalize and join tickers for logging
    tickers_list = [str(t).strip().upper() for t in tickers if t]
    try:
        log.info(
            "alpaca_stream_start tickers=%s secs=%s",
            ",".join(tickers_list),
            secs_int,
        )
    except Exception:
        pass
    # Sleep for the requested duration (clamped to 30s); in real usage this
    # would run asynchronously.
    try:
        wait_time = min(max(secs_int, 0), 30)
        time.sleep(wait_time)
    except Exception:
        pass
    try:
        log.info(
            "alpaca_stream_end tickers=%s",
            ",".join(tickers_list),
        )
    except Exception:
        pass


# Public API of this module (explicit export list)
__all__ = [
    "NewsItem",
    "ScoredItem",
    "get_last_price_snapshot",
    "get_last_price_change",
    "get_volatility",
    "get_intraday",
    "get_intraday_snapshots",
    "get_intraday_indicators",
    "sample_alpaca_stream",
]

# ---------------------------------------------------------------------------
# Volatility and intraday helpers
#
# These helpers provide additional context around a ticker's price action.
# - get_volatility returns the average daily range (high-low)/close over a
#   configurable number of days.
# - get_intraday fetches intraday OHLC data via yfinance for configurable
#   intervals; this can be used by the trade simulator or downstream analysis.
# - get_intraday_snapshots computes simple premarket, intraday and after-hours
#   snapshots for a given date. The snapshots return basic stats (open/high/low/close)
#   per segment in US Eastern time.


def get_volatility(ticker: str, *, days: int = 14) -> Optional[float]:
    """Return the average daily range percentage over the past `days` days.

    The daily range is defined as (high - low) / close. The result is
    expressed as a percentage. If insufficient data is available or yfinance
    is unavailable, returns None.
    """
    nt = _norm_ticker(ticker)
    if nt is None or yf is None:
        return None
    try:
        # Fetch a few extra days to ensure at least `days` complete entries
        period_days = max(days + 1, days + 5)
        hist = yf.Ticker(nt).history(
            period=f"{period_days}d", interval="1d", auto_adjust=False, prepost=False
        )
        if hist is None or getattr(hist, "empty", False):
            return None
        # Use the last `days` rows
        df = hist.tail(days)
        if df.empty:
            return None
        try:
            ranges = (df["High"] - df["Low"]) / df["Close"]
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
) -> Optional["pd.DataFrame"]:
    """Return intraday OHLC data for a ticker via yfinance.

    Parameters
    ----------
    ticker : str
        The security to fetch.
    interval : str, default "5min"
        The bar interval (e.g. "1m", "5min", "15min"). Must be supported by
        yfinance. Note that Alpha Vantage intervals differ; this helper uses
        yfinance exclusively.
    output_size : str, default "full"
        Either "full" or "compact". This flag is passed through to
        yfinance, which returns as much data as possible when "full".
    prepost : bool, default True
        Whether to include pre/post market data. Default is True to
        capture extended hours.

    Returns
    -------
    pandas.DataFrame or None
        A DataFrame indexed by timestamp with columns open/high/low/close/volume.
        Returns None if yfinance is unavailable or on error.
    """
    # Avoid import at module top to speed import path when not used
    if yf is None:
        return None
    nt = _norm_ticker(ticker)
    if nt is None:
        return None
    try:
        # Use download because it handles extended hours when prepost=True
        # yfinance distinguishes between "compact" and "full" via period arg; map
        period = "5d" if output_size == "compact" else "60d"
        df = yf.download(
            nt,
            period=period,
            interval=interval,
            prepost=prepost,
            auto_adjust=False,
            progress=False,
        )
        if df is None or getattr(df, "empty", False):
            return None
        return df
    except Exception:
        return None


def get_intraday_snapshots(
    ticker: str, *, target_date: Optional["datetime.date"] = None
) -> Optional[Dict[str, Dict[str, float]]]:
    """Compute premarket/intraday/after-hours snapshots for a given ticker.

    This helper returns a dictionary with three keys: "premarket", "intraday"
    and "afterhours". Each entry is itself a dict with keys "open", "high",
    "low" and "close". Values may be None if the segment contains no data.

    The function uses yfinance 1-minute bars (if available). If extended
    hours data is unavailable or the ticker is illiquid, some segments may
    return None. Snapshots are calculated for the specified `target_date` (or
    the current date if None) in US/Eastern time. The returned dictionary is
    intended to be JSON‑serializable.
    """
    if yf is None:
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
        # Determine date of interest (assume current day if not provided)
        if target_date is None:
            dt_now = datetime.now()
            target_date = dt_now.date()
        # Fetch 1m bars for the surrounding days to ensure full coverage
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
        # Index to datetime and convert to US/Eastern
        idx = df.index
        if not isinstance(idx, pd.DatetimeIndex):
            return None
        try:
            # If naive, localize to UTC first
            if idx.tz is None:
                df.index = idx.tz_localize("UTC").tz_convert("America/New_York")
            else:
                df.index = idx.tz_convert("America/New_York")
        except Exception:
            return None

        # Build segments; times are naive but interpreted in America/New_York
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

        # Define trading day segments. We end intraday at 16:01 (so
        # 16:00 is captured) and start after‑hours at 16:00. The
        # after‑hours segment ends at 20:01 so that the 20:00 bar is
        # included. Each range is half‑open [start, end), so the end
        # time is exclusive.
        segments = {
            "premarket": segment_range((4, 0), (9, 30)),
            "intraday": segment_range((9, 30), (16, 1)),
            "afterhours": segment_range((16, 0), (20, 1)),
        }

        snaps: Dict[str, Dict[str, Optional[float]]] = {}
        for name, (sdt, edt) in segments.items():
            seg_df = df.loc[(df.index >= sdt) & (df.index < edt)]
            if seg_df is None or seg_df.empty:
                snaps[name] = {
                    "open": None,
                    "high": None,
                    "low": None,
                    "close": None,
                }
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
    ticker: str, *, target_date: Optional["datetime.date"] = None
) -> Dict[str, Optional[float]]:
    """
    Compute light indicators (VWAP, RSI14) from 1-minute bars using yfinance.
    Returns {'vwap': float|None, 'rsi14': float|None} or {} on failure/disabled.
    Respects Settings.feature_indicators; never raises.
    """
    try:
        if not getattr(get_settings(), "feature_indicators", False):
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
        # Normalize columns
        cols = {c.lower(): c for c in df.columns}
        close = df[cols.get("close", "Close")]
        vol = df[cols.get("volume", "Volume")]
        # VWAP
        try:
            vwap = float((close * vol).sum() / vol.sum()) if vol.sum() else None
        except Exception:
            vwap = None
        # RSI14 (Wilder smoothing)
        try:
            delta = close.diff()
            up = delta.clip(lower=0.0)
            down = (-delta).clip(lower=0.0)
            roll = 14
            ma_up = up.ewm(alpha=1 / roll, adjust=False).mean()
            ma_down = down.ewm(alpha=1 / roll, adjust=False).mean()
            rs = ma_up / (ma_down.replace(0, float("nan")))
            rsi = 100 - (100 / (1 + rs))
            rsi14 = float(rsi.iloc[-1]) if rsi.notna().any() else None
        except Exception:
            rsi14 = None
        out: Dict[str, Optional[float]] = {}
        if vwap is not None:
            out["vwap"] = vwap
        if rsi14 is not None:
            out["rsi14"] = rsi14
        return out
    except Exception:
        return {}


def get_momentum_indicators(
    ticker: str, *, target_date: Optional["datetime.date"] = None
) -> Dict[str, Optional[float]]:
    """
    Compute additional momentum indicators (MACD, EMA crossovers and VWAP
    delta) from 1‑minute bars using yfinance.  The returned dictionary
    contains the following keys when successful:

    - ``macd``: the latest MACD value (EMA12 – EMA26).
    - ``macd_signal``: the latest 9‑period signal line value.
    - ``macd_cross``: +1 when the MACD crosses above the signal line on
      the most recent bar, −1 when it crosses below, and 0 otherwise.
    - ``ema9``: the latest 9‑period exponential moving average.
    - ``ema21``: the latest 21‑period exponential moving average.
    - ``ema_cross``: +1 when the 9 EMA crosses above the 21 EMA on the
      most recent bar, −1 when it crosses below, and 0 otherwise.
    - ``vwap_delta``: the difference between the last close and VWAP.

    This helper respects the ``feature_momentum_indicators`` flag.  It
    returns an empty dictionary when disabled, when data is unavailable
    or when any errors occur.  Indicators are computed without raising
    exceptions.
    """
    try:
        s = get_settings()
        # Require both indicators and momentum flags to be enabled
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
        # Pull the last two days to compute EMAs and MACD with enough history
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
        # Normalize columns
        cols = {c.lower(): c for c in df.columns}
        close = df[cols.get("close", "Close")]  # type: ignore[index]
        vol = df[cols.get("volume", "Volume")]  # type: ignore[index]

        out: Dict[str, Optional[float]] = {}
        # VWAP delta: last close minus VWAP
        try:
            vwap = (close * vol).cumsum() / vol.cumsum()
            last_close = float(close.iloc[-1])
            vwap_val = float(vwap.iloc[-1]) if not vwap.isna().iloc[-1] else None
            if vwap_val is not None:
                out["vwap_delta"] = last_close - vwap_val
        except Exception:
            pass
        # EMA9 and EMA21
        try:
            ema9 = close.ewm(span=9, adjust=False).mean()
            ema21 = close.ewm(span=21, adjust=False).mean()
            ema9_val = float(ema9.iloc[-1]) if ema9.notna().iloc[-1] else None
            ema21_val = float(ema21.iloc[-1]) if ema21.notna().iloc[-1] else None
            if ema9_val is not None:
                out["ema9"] = ema9_val
            if ema21_val is not None:
                out["ema21"] = ema21_val
            # Detect cross on the most recent interval
            ema_cross = 0
            try:
                if len(ema9) >= 2 and len(ema21) >= 2:
                    prev_diff = ema9.iloc[-2] - ema21.iloc[-2]
                    curr_diff = ema9.iloc[-1] - ema21.iloc[-1]
                    if prev_diff < 0 <= curr_diff:
                        ema_cross = 1
                    elif prev_diff > 0 >= curr_diff:
                        ema_cross = -1
                out["ema_cross"] = ema_cross
            except Exception:
                pass
        except Exception:
            pass
        # MACD (12/26 EMAs) and signal
        try:
            ema12 = close.ewm(span=12, adjust=False).mean()
            ema26 = close.ewm(span=26, adjust=False).mean()
            macd_series = ema12 - ema26
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
            # Detect MACD cross
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
