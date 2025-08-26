"""Intraday trade simulation for the catalyst bot.

This module provides a simplified trade simulator that approximates
entry and exit points at discrete intraday intervals. It is not
intended to be a high‑fidelity backtester but rather a heuristic
for gauging the reaction of a stock to a news catalyst within the
constraints of the data available from Alpha Vantage.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import List, Optional

import pandas as pd

from .market import get_intraday
from .models import NewsItem, TradeSimConfig, TradeSimResult


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
    if config is None:
        config = TradeSimConfig()
    results: List[TradeSimResult] = []
    # Fetch intraday data (5min bars). Use full session to ensure coverage.
    df = get_intraday(item.ticker or "", interval="5min", output_size="full")
    if df is None or df.empty:
        return results
    for offset in config.entry_offsets:
        entry_ts = item.ts_utc + timedelta(minutes=offset)
        entry_idx = _find_bar_index(df, entry_ts)
        if entry_idx is None:
            continue
        entry_price = df.iloc[entry_idx]["open"]
        for hold in config.hold_durations:
            exit_ts = entry_ts + timedelta(minutes=hold)
            exit_idx = _find_bar_index(df, exit_ts)
            if exit_idx is None:
                # If the exit time is beyond available data, use last close
                exit_price = df.iloc[-1]["close"]
            else:
                exit_price = df.iloc[exit_idx]["close"]
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
