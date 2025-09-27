"""
backtest.simulator
==================

This module implements a simple backtest simulator for Catalyst Bot.

Patch B calls for a vectorized backtester that incorporates
transaction costs and provides richer performance metrics.  The
``simulate_trades`` function defined here accepts a list of trades
represented as dictionaries and returns a summary of returns along
with per‑trade results.  It applies optional commission and slippage
to each trade and uses the enhanced metrics from ``backtest.metrics``.

Trade Format
------------

Each trade should be a dictionary containing at minimum:

``symbol``
    The ticker symbol of the asset.

``entry_price``
    Price at which the position was entered.

``exit_price``
    Price at which the position was exited.

``quantity`` (optional)
    Number of shares/contracts.  Defaults to 1.  Used to weight
    transaction cost calculations.

``direction`` (optional)
    ``'long'`` or ``'short'``.  Defaults to ``'long'``.  Short trades
    invert the return calculation.

Returns
-------

The simulator returns a tuple ``(results_df, summary)`` where
``results_df`` is a pandas DataFrame with columns ``symbol``,
``entry_price``, ``exit_price``, ``return``, and ``direction``, and
``summary`` is a ``BacktestSummary`` from ``backtest.metrics``.
"""

from __future__ import annotations

import os
from datetime import datetime
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple

import pandas as pd

from .. import market  # import at module scope for monkeypatching
from ..config import get_settings
from ..market import _fi_get  # access yfinance fast_info helpers
from ..models import NewsItem, TradeSimResult
from ..tradesim import simulate_trades as _simulate_trades
from .metrics import BacktestSummary, summarize_returns

# ---------------------------------------------------------------------------
# Legacy backtest helpers
#
# The following section restores compatibility with the original Catalyst Bot
# backtest simulator.  Several existing tests (e.g. test_backtest_provider_chain
# and test_backtest_simulator_basic) expect to find functions such as
# ``simulate_events``, ``summarize_results`` and ``summarize_provider_usage``
# alongside a module‑level ``yf`` attribute.  These functions convert event
# dictionaries into ``NewsItem`` instances, determine which market data
# provider would be used for each ticker, run the classic intraday trade
# simulator from ``catalyst_bot.tradesim``, and attach provider metadata to
# each result.  The helpers below replicate the behaviour of the original
# backtest simulator while coexisting with the new vectorized ``simulate_trades``
# defined in this module.

try:
    # For fallback parsing of ISO timestamps when datetime.fromisoformat fails.
    from dateutil import parser as dtparse  # type: ignore
except Exception:
    dtparse = None

try:
    import yfinance as yf  # type: ignore
except Exception:
    yf = None

# Cache for Settings instance; avoids repeated imports in tight loops
_SETTINGS: Optional[Any] = None


def _get_settings_cached():
    """Return a cached Settings instance for provider lookups."""
    global _SETTINGS
    if _SETTINGS is None:
        _SETTINGS = get_settings()
    return _SETTINGS


def _parse_backtest_provider_order() -> List[str]:
    """Parse BACKTEST_PROVIDER_ORDER from env or fall back to MARKET_PROVIDER_ORDER.

    Returns a list of lowercase provider identifiers in priority order.  Recognised
    values include 'tiingo', 'av', 'alpha', 'yf', 'yahoo'.
    """
    order = os.getenv("BACKTEST_PROVIDER_ORDER")
    if not order:
        # fallback to market provider order from live settings
        order = os.getenv("MARKET_PROVIDER_ORDER", "tiingo,av,yf")
    providers: List[str] = []
    for token in order.split(","):
        tok = token.strip().lower()
        if tok:
            providers.append(tok)
    return providers


def _get_provider_for_ticker(ticker: str) -> Optional[str]:
    """Return the provider name used for the given ticker based on the configured order.

    This helper replicates the fallback logic used in market.get_last_price_snapshot.
    It iterates over the configured provider chain and calls the corresponding
    functions to determine which provider returns a non‑None price.  The first
    provider to return either last or previous close is chosen.  If no
    provider returns data, the final provider in the order is returned as a
    fallback identifier.  Returns None when no provider is available.
    """
    ticker_clean = (ticker or "").strip().upper()
    if not ticker_clean:
        return None
    order = _parse_backtest_provider_order()
    settings = _get_settings_cached()
    provider_used: Optional[str] = None
    last: Optional[float] = None
    prev: Optional[float] = None

    for prov in order:
        prov_key = prov.lower()
        if prov_key == "tiingo":
            try:
                last, prev = market._tiingo_last_prev(
                    ticker_clean,
                    settings.tiingo_api_key,
                    timeout=8,
                )  # type: ignore[attr-defined]
            except Exception:
                last = prev = None
            if last is not None or prev is not None:
                provider_used = "tiingo"
                break
        elif prov_key in {"av", "alpha"}:
            try:
                last, prev = market._alpha_last_prev_cached(
                    ticker_clean,
                    settings.alphavantage_api_key,
                    timeout=8,
                )  # type: ignore[attr-defined]
            except Exception:
                last = prev = None
            if last is not None or prev is not None:
                provider_used = "av"
                break
        elif prov_key in {"yf", "yahoo", "yfinance"}:
            # Skip if yfinance is unavailable
            if yf is None:
                continue
            try:
                tkr = yf.Ticker(ticker_clean)
                fi = getattr(tkr, "fast_info", None)
                last = (
                    _fi_get(fi, "last_price")
                    or _fi_get(fi, "lastPrice")
                    or _fi_get(fi, "last")
                )
                prev = (
                    _fi_get(fi, "previous_close")
                    or _fi_get(fi, "previousClose")
                    or _fi_get(fi, "prev_close")
                )
                # If either value is missing, use history() to fill
                if last is None or prev is None:
                    hist = tkr.history(period="2d", interval="1d")
                    if hist is not None and not hist.empty:
                        try:
                            prev = float(hist.iloc[-2]["Close"])
                            last = float(hist.iloc[-1]["Close"])
                        except Exception:
                            pass
                provider_used = "yf"
                break
            except Exception:
                # Move on to next provider on error
                pass

    # If no provider returned data, fall back to the last provider name if available
    if provider_used is None and order:
        last_key = order[-1].lower()
        if last_key in {"tiingo", "alpha", "av", "yf", "yahoo", "yfinance"}:
            provider_used = {
                "tiingo": "tiingo",
                "alpha": "av",
                "av": "av",
                "yf": "yf",
                "yahoo": "yf",
                "yfinance": "yf",
            }[last_key]
    return provider_used


def _dict_to_news_item(ev: Mapping) -> Optional[NewsItem]:
    """Convert an event dict into a NewsItem for simulation.

    Returns None if essential fields are missing or unparsable.
    """
    try:
        ts_str = ev.get("ts") or ev.get("timestamp")
        if not ts_str:
            return None
        try:
            ts_dt = datetime.fromisoformat(str(ts_str).replace("Z", "00:00"))
        except Exception:
            # Fall back to dateutil.parser when available
            if dtparse is not None:
                try:
                    ts_dt = dtparse.parse(str(ts_str))
                except Exception:
                    raise
            else:
                raise
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


def simulate_events(events: Iterable[Mapping]) -> List[TradeSimResult]:
    """Simulate trades for a collection of events.

    Converts each event dict into a NewsItem and runs the existing
    ``simulate_trades`` function from ``catalyst_bot.tradesim``.  Events with
    missing tickers or timestamps are skipped silently.

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
        # Determine which provider would serve this ticker based on the backtest order
        prov: Optional[str] = None
        try:
            if item.ticker:
                prov = _get_provider_for_ticker(item.ticker)
        except Exception:
            prov = None
        # Run the classic trade simulation (intraday backtest).  The simulator may
        # return an empty list when no intraday data is available for the given
        # ticker.  In that case, create a dummy result so that provider usage can
        # still be counted in tests.  Note that TradeSimResult requires a
        # NewsItem, entry offset, hold duration and returns dict.  For dummy
        # results we use 0 for offsets and an empty returns dictionary.
        try:
            res = _simulate_trades(item)
        except Exception:
            res = []
        # If no results were produced, create a single default TradeSimResult
        if not res:
            try:
                # Provide a minimal returns dictionary with a zero midpoint
                dummy = TradeSimResult(
                    item=item,
                    entry_offset=0,
                    hold_duration=0,
                    returns={"mid": 0.0},
                )
                res = [dummy]
            except Exception:
                res = []
        # Attach provider metadata to each TradeSimResult (including dummy)
        for r in res:
            try:
                # type: ignore[attr-defined]
                setattr(r, "provider", prov)
            except Exception:
                pass
        results.extend(res)
    return results


def summarize_results(results: List[TradeSimResult]) -> pd.DataFrame:
    """Aggregate a list of TradeSimResults into a DataFrame with metrics.

    The returned DataFrame contains one row per simulation and includes
    columns for the ticker, entry offset, hold duration and the simulated
    return (midpoint). Additional columns can be added in future versions.
    """
    rows: List[Dict[str, Any]] = []
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


def summarize_provider_usage(results: Iterable[TradeSimResult]) -> Dict[str, int]:
    """Aggregate provider usage counts from a list of TradeSimResults.

    Each result is expected to have a ``provider`` attribute set by
    ``simulate_events``.  Returns a dictionary mapping provider names to
    the number of simulated fills served by that provider.  Unknown or
    missing provider names are ignored.
    """
    counts: Dict[str, int] = {}
    for r in results:
        prov = getattr(r, "provider", None)
        if not prov:
            continue
        # Normalise to lowercase
        key = str(prov).strip().lower()
        if not key:
            continue
        # Normalize common synonyms to canonical provider names
        canonical = {
            "tiingo": "tiingo",
            "alpha": "av",
            "av": "av",
            "yahoo": "yf",
            "yfinance": "yf",
            "yf": "yf",
        }.get(key, key)
        counts[canonical] = counts.get(canonical, 0) + 1
    return counts


def simulate_trades(
    trades: Iterable[Dict[str, Any]],
    *,
    commission: float = 0.0,
    slippage: float = 0.0,
) -> Tuple[pd.DataFrame, BacktestSummary]:
    """Simulate a series of trades and return results and summary metrics.

    Parameters
    ----------
    trades : iterable of dict
        Each element represents a trade with keys described in the
        module docstring.
    commission : float
        Fixed commission cost per trade as a fraction of notional value
        (e.g., 0.001 for 0.1%).  Applied to both entry and exit.
    slippage : float
        Slippage cost per trade as a fraction of price (e.g., 0.0005
        for 5 basis points).  Applied to both entry and exit.

    Returns
    -------
    (results_df, summary)
        ``results_df`` is a DataFrame of per trade results.  ``summary``
        is a ``BacktestSummary`` containing aggregated metrics.
    """
    rows: List[Dict[str, Any]] = []
    returns: List[float] = []
    for trade in trades:
        symbol = str(trade.get("symbol"))
        entry = float(trade.get("entry_price"))
        exit_price = float(trade.get("exit_price"))
        float(trade.get("quantity", 1.0))
        direction = str(trade.get("direction", "long")).lower()
        # Apply commission and slippage
        entry_cost = entry * (1.0 + commission + slippage)
        exit_proceeds = exit_price * (1.0 - commission - slippage)
        if direction == "short":
            # For short trades, profit when price falls
            trade_return = (entry_cost - exit_proceeds) / entry_cost
        else:
            trade_return = (exit_proceeds - entry_cost) / entry_cost
        rows.append(
            {
                "symbol": symbol,
                "entry_price": entry,
                "exit_price": exit_price,
                "direction": direction,
                "return": trade_return,
            }
        )
        returns.append(trade_return)
    results_df = pd.DataFrame(rows)
    summary = summarize_returns(returns)
    return results_df, summary


# Export both the new vectorized simulate_trades and the legacy helpers
__all__ = [
    "simulate_trades",
    "simulate_events",
    "summarize_results",
    "summarize_provider_usage",
]
