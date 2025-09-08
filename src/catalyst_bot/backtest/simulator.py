"""Simple backtest simulator for Catalyst Bot alerts.

This module provides a minimal scaffold to replay historical alerts and
evaluate a set of trading heuristics. It uses the existing trade
simulation logic from ``catalyst_bot.tradesim`` and converts event
dictionaries into ``NewsItem`` instances. Metrics such as win rate and
average return are computed on the fly. Future extensions may include
precision/recall, category‑level analysis and configurable exit
strategies.
"""

from __future__ import annotations

from datetime import datetime
from typing import Dict, Iterable, List, Optional

import pandas as pd

from ..models import NewsItem, TradeSimResult
from ..tradesim import simulate_trades


def _dict_to_news_item(ev: Dict) -> Optional[NewsItem]:
    """Convert an event dict into a NewsItem for simulation.

    Returns None if essential fields are missing or unparsable.
    """
    try:
        ts_str = ev.get("ts") or ev.get("timestamp")
        if not ts_str:
            return None
        try:
            ts_dt = datetime.fromisoformat(ts_str.replace("Z", "00:00"))
        except Exception:
            from dateutil import parser as dtparse

            ts_dt = dtparse.parse(ts_str)
        title = ev.get("title") or ""
        ticker = (ev.get("ticker") or "").upper() or None
        # canonical_url maps to link
        link = ev.get("link") or ev.get("canonical_url") or ""
        source = ev.get("source") or ev.get("source_host") or ""
        return NewsItem(
            ts_utc=ts_dt,
            title=title,
            canonical_url=link,
            source_host=source,
            ticker=ticker,
        )
    except Exception:
        return None


def simulate_events(events: Iterable[Dict]) -> List[TradeSimResult]:
    """Simulate trades for a collection of events.

    Converts each event dict into a NewsItem and runs the existing
    ``simulate_trades`` function. Events with missing tickers or timestamps
    are skipped silently.

    Returns
    -------
    list of TradeSimResult
        Flattened list of results for all entry/hold combinations.
    """
    results: List[TradeSimResult] = []
    for ev in events:
        item = _dict_to_news_item(ev)
        if item is None:
            continue
        res = simulate_trades(item)
        if res:
            results.extend(res)
    return results


def summarize_results(results: List[TradeSimResult]) -> pd.DataFrame:
    """Aggregate a list of TradeSimResults into a DataFrame with metrics.

    The returned DataFrame contains one row per simulation and includes
    columns for the ticker, entry offset, hold duration and the simulated
    return (midpoint). Additional columns can be added in future versions.
    """
    rows: List[Dict] = []
    for r in results:
        try:
            rows.append(
                {
                    "ticker": r.item.ticker,
                    "entry_offset": r.entry_offset,
                    "hold_duration": r.hold_duration,
                    "return": r.returns.get("mid", 0.0),
                }
            )
        except Exception:
            continue
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows)
