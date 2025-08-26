# src/catalyst_bot/market.py
from __future__ import annotations

import time
from typing import Optional, Tuple

from .logging_utils import get_logger

log = get_logger("yfinance")

try:
    import yfinance as yf  # type: ignore
except Exception:  # pragma: no cover
    yf = None  # type: ignore


def _norm_ticker(t: Optional[str]) -> Optional[str]:
    if not t:
        return None
    t = t.strip().upper()
    if t.startswith("$"):
        t = t[1:]
    return t or None


def get_last_price_snapshot(
    ticker: str, retries: int = 2
) -> Tuple[Optional[float], Optional[float]]:
    """
    Best-effort last price and previous close from yfinance.
    Returns (last_price, previous_close); either may be None.
    Never raises.
    """
    if not ticker:
        return None, None
    if yf is None:
        log.info("yf_missing skip_price_lookup")
        return None, None

    t = yf.Ticker(ticker)
    last: Optional[float] = None
    prev: Optional[float] = None

    for attempt in range(retries + 1):
        try:
            # fast path
            fi = getattr(t, "fast_info", None)
            if fi:
                last = float(getattr(fi, "last_price", None) or 0) or None
                prev = float(getattr(fi, "previous_close", None) or 0) or None
            # fallback: 1d history
            if last is None or prev is None:
                hist = t.history(period="2d", interval="1d", auto_adjust=False)
                if not hist.empty:
                    last = float(hist["Close"].iloc[-1])
                    if len(hist) >= 2:
                        prev = float(hist["Close"].iloc[-2])
                    elif "Previous Close" in getattr(t.info, "__dict__", {}):
                        prev = float(t.info["previousClose"])  # type: ignore[index]
            return last, prev
        except Exception:
            if attempt >= retries:
                return last, prev
            time.sleep(0.4 * (attempt + 1))
    return last, prev
