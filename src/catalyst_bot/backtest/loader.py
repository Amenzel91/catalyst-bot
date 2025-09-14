"""Historical data loading helpers for Catalyst Bot backtests.

This module provides simple functions to read historical events and price
information. The intent is to decouple IO from simulation logic. In its
current form, the loader reads events from a newline‑delimited JSON
(`events.jsonl`) and exposes a helper to load intraday data via the
existing market functions. Caching and Alpha Vantage integration can be
added in later phases.
"""

from __future__ import annotations

import json
from datetime import datetime

# Note: avoid importing ``Dict`` here because this module does not refer to it
# directly.  Importing unused type names can lead to flake8 (F821) warnings
# when type annotations are evaluated lazily under ``from __future__ import annotations``.
from typing import Iterable, List, Optional

import pandas as pd

from ..market import get_intraday


def load_events(path: str) -> List[dict]:
    """Load a list of event dicts from a newline‑delimited JSON file.

    Parameters
    ----------
    path : str
        The path to an events JSONL file. Each line should be a valid JSON
        object with at least a ``ts`` timestamp, ``title`` and ``ticker``.

    Returns
    -------
    list of dict
        All parsed events. Invalid JSON lines are skipped silently.
    """
    events: List[dict] = []
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                try:
                    ev = json.loads(line)
                    # Ensure essential fields exist
                    if "ts" in ev and "title" in ev:
                        events.append(ev)
                except Exception:
                    continue
    except FileNotFoundError:
        # No events file found; return empty list
        return []
    except Exception:
        return events
    return events


def load_price_history(
    ticker: str, *, interval: str = "1d", days: int = 365
) -> Optional[pd.DataFrame]:
    """Fetch a historical price DataFrame for a ticker.

    This helper uses the existing intraday loader for consistency. For daily
    history, it falls back to yfinance via get_intraday with a longer
    interval. In future, a dedicated Alpha Vantage loader could be added.
    Returns None on any exception.
    """
    try:
        # For daily history, rely on yfinance through get_intraday
        # Convert days to a period string; include a buffer for weekends
        # Add a buffer for weekends when calculating period_days
        period_days = days + 7
        if interval in ("1d", "1day"):
            # yfinance download for daily bars via market.get_intraday is not
            # supported; fallback to yfinance directly here
            import yfinance as yf  # type: ignore

            df = yf.download(ticker, period=f"{period_days}d", interval="1d")
            return df
        else:
            df = get_intraday(ticker, interval=interval, output_size="full")
            return df
    except Exception:
        return None


def get_event_window(
    events: Iterable[dict], *, start_date: datetime, end_date: datetime
) -> List[dict]:
    """Filter events within a date range [start_date, end_date].

    Parameters
    ----------
    events : iterable of dict
        Events loaded via ``load_events``.
    start_date : datetime
        Inclusive start timestamp (UTC).
    end_date : datetime
        Inclusive end timestamp (UTC).

    Returns
    -------
    list of dict
        Events whose timestamp falls within the specified date range.
    """
    # Use builtin ``dict`` in type annotations to avoid requiring an explicit
    # ``Dict`` import.  Flake8 (F821) can complain if ``Dict`` is not defined
    # when type annotations are evaluated with ``from __future__ import annotations``.
    window: List[dict] = []
    for ev in events:
        ts = ev.get("ts")
        if not ts:
            continue
        try:
            dt = datetime.fromisoformat(ts.replace("Z", "00:00"))
        except Exception:
            try:
                from dateutil import parser as dtparse

                dt = dtparse.parse(ts)
            except Exception:
                continue
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=None)
        if start_date <= dt <= end_date:
            window.append(ev)
    return window
