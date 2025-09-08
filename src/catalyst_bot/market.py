from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Optional, Tuple

import requests

from .logging_utils import get_logger
from .models import NewsItem, ScoredItem  # re-export for market.NewsItem

log = get_logger("market")

try:
    import yfinance as yf  # type: ignore
except Exception:  # pragma: no cover
    yf = None  # type: ignore

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


def get_last_price_snapshot(
    ticker: str, retries: int = 2
) -> Tuple[Optional[float], Optional[float]]:
    """
    Best-effort last price and previous close.
    Order: Alpha Vantage (if key present) → yfinance fallback.
    Returns (last_price, previous_close); either may be None. Never raises.
    """
    nt = _norm_ticker(ticker)
    if not nt:
        return None, None
    last: Optional[float] = None
    prev: Optional[float] = None

    # 1) Alpha Vantage primary (if configured)
    if _AV_KEY and not _SKIP_ALPHA:
        # Use the cached Alpha Vantage wrapper to avoid repeated API calls.
        for attempt in range(retries + 1):
            a_last, a_prev = _alpha_last_prev_cached(nt, _AV_KEY)
            # Take what we can get (sometimes prev is missing temporarily)
            if a_last is not None:
                last = a_last
            if a_prev is not None:
                prev = a_prev
            if last is not None and prev is not None:
                return last, prev
            time.sleep(0.35 * (attempt + 1))

    # 2) yfinance fallback
    if yf is None:
        log.info("yf_missing skip_price_lookup")
        return last, prev

    t = yf.Ticker(nt)
    for attempt in range(retries + 1):
        try:
            # Fast path via fast_info (attribute or dict-like)
            fi = getattr(t, "fast_info", None)
            if fi is not None:
                last = last or _fi_get(fi, "last_price")
                prev = prev or _fi_get(fi, "previous_close")

            # Fallback: tiny 1d/2d history scrape
            if last is None or prev is None:
                hist = t.history(period="2d", interval="1d", auto_adjust=False)
                if not hist.empty:
                    last = float(hist["Close"].iloc[-1])
                    if len(hist) >= 2:
                        prev = float(hist["Close"].iloc[-2])
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
            return last, prev
        except Exception:
            if attempt >= retries:
                return last, prev
            time.sleep(0.4 * (attempt + 1))
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


__all__ = [
    "NewsItem",
    "ScoredItem",
    "get_last_price_snapshot",
    "get_last_price_change",
]
