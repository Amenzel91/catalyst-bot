from __future__ import annotations

import os
import time
from typing import Optional, Tuple

import requests

from .logging_utils import get_logger
from .models import NewsItem, ScoredItem  # re-export for market.NewsItem

log = get_logger("market")

try:
    import yfinance as yf  # type: ignore
except Exception:  # pragma: no cover
    yf = None  # type: ignore

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
        for attempt in range(retries + 1):
            a_last, a_prev = _alpha_last_prev(nt, _AV_KEY)
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
