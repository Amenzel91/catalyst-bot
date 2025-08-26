"""Intraday trade simulation for the catalyst bot.

This module provides a simplified trade simulator that approximates
entry and exit points at discrete intraday intervals. It is not
intended to be a high-fidelity backtester but rather a heuristic
for gauging the reaction of a stock to a news catalyst within the
constraints of the data available from a market data provider.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Callable, List, Optional

import pandas as pd

from .models import NewsItem, TradeSimConfig, TradeSimResult


def _resolve_intraday_func() -> Optional[Callable[..., pd.DataFrame]]:
    """Resolve a get_intraday-like function from catalyst_bot.market.

    We try a few common names to be robust against refactors.
    """
    try:
        from . import market  # type: ignore
    except Exception:
        return None

    for name in ("get_intraday", "get_intraday_df", "fetch_intraday"):
        fn = getattr(market, name, None)
        if callable(fn):
            return fn
    return None


def _find_bar_index(df: pd.DataFrame, ts: datetime) -> Optional[int]:
    """Return the integer index of the first bar whose timestamp >= ts."""
    if df is None or df.empty:
        return None
    try:
        idx = df.index.searchsorted(ts)
        if idx >= len(df):
            return None
        return int(idx)
    except Exception:
        return None


def simulate_trades(
    item: NewsItem, config: Optional[TradeSimConfig] = None
) -> List[TradeSimResult]:
    """Simulate a set of entry and hold strategies for a single news item.

    Parameters
    ----------
    item : NewsItem
        The news item to simulate trades for.
    config : Optional[TradeSimConfig]
        Override default simulation parameters.

    Returns
    -------
    List[TradeSimResult]
        A list of trade results for each entry/hold combination.
    """
    if not item or not (item.ticker or "").strip():
        return []

    if config is None:
        config = TradeSimConfig()

    intraday_fn = _resolve_intraday_func()
    if intraday_fn is None:
        # Market data function unavailable; return no simulations.
        return []

    # Fetch intraday data (5min bars). Use full session to ensure coverage.
    try:
        df = intraday_fn(item.ticker, interval="5min", output_size="full")
    except TypeError:
        # Handle functions that may accept only (ticker) or different kwargs.
        try:
            df = intraday_fn(item.ticker)  # type: ignore[misc]
        except Exception:
            df = None
    except Exception:
        df = None

    if df is None or not isinstance(df, pd.DataFrame) or df.empty:
        return []

    # Ensure the index is a DatetimeIndex in UTC
    if not isinstance(df.index, pd.DatetimeIndex):
        # Try common columns
        for col in ("timestamp", "time", "datetime"):
            if col in df.columns:
                df = df.set_index(pd.to_datetime(df[col], utc=True))
                break
    if not isinstance(df.index, pd.DatetimeIndex):
        # Give up if we can't establish a datetime index
        return []

    # Normalize to UTC (no-op if already UTC)
    try:
        df.index = df.index.tz_convert("UTC")
    except Exception:
        try:
            df.index = df.index.tz_localize("UTC")  # if naive
        except Exception:
            return []

    results: List[TradeSimResult] = []

    for offset in config.entry_offsets:
        entry_ts = item.ts_utc + timedelta(minutes=offset)
        entry_idx = _find_bar_index(df, entry_ts)
        if entry_idx is None:
            continue
        # Prefer 'open' if present; fall back to 'close'
        entry_price = (
            float(df.iloc[entry_idx]["open"])
            if "open" in df.columns
            else float(df.iloc[entry_idx]["close"])
        )

        for hold in config.hold_durations:
            exit_ts = entry_ts + timedelta(minutes=hold)
            exit_idx = _find_bar_index(df, exit_ts)
            if exit_idx is None:
                # If the exit time is beyond available data, use last close
                exit_price = float(df.iloc[-1]["close"])
            else:
                exit_price = float(df.iloc[exit_idx]["close"])

            # Compute simple return; slippage subtracted from both sides
            slippage = entry_price * (config.slippage_bps / 10000.0)
            entry_net = entry_price + slippage
            exit_net = exit_price - slippage
            pct_return = (exit_net - entry_net) / entry_net if entry_net > 0 else 0.0

            results.append(
                TradeSimResult(
                    item=item,
                    entry_offset=offset,
                    hold_duration=hold,
                    returns={
                        "best": pct_return,
                        "mid": pct_return,
                        "worst": pct_return,
                    },
                )
            )

    return results
