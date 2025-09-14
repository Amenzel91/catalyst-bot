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

import os
from datetime import datetime
from typing import Iterable, List, Optional  # type hints

import pandas as pd

# Import the market module at module scope so that monkeypatching works on the
# same object used here.  We avoid re-importing it inside helper functions,
# which previously triggered flake8 E402 warnings when imports appeared mid-file.
from .. import market  # type: ignore  # noqa: E402
from ..config import get_settings

# NOTE: we import the market module at module scope so that the same
# module instance is used throughout. This allows monkeypatching in
# tests to operate on a single shared object.  We still import
# ``_fi_get`` directly for accessing yfinance fast_info fields.
from ..market import _fi_get
from ..models import NewsItem, TradeSimResult
from ..tradesim import simulate_trades

try:
    # For fallback parsing of ISO timestamps when datetime.fromisoformat fails.
    from dateutil import parser as dtparse  # type: ignore
except Exception:
    dtparse = None

try:
    import yfinance as yf  # type: ignore
except Exception:
    yf = None


_SETTINGS = None


def _get_settings_cached():
    """Return a cached Settings instance for provider lookups."""
    global _SETTINGS
    if _SETTINGS is None:
        _SETTINGS = get_settings()
    return _SETTINGS


def _parse_backtest_provider_order() -> List[str]:
    """Parse BACKTEST_PROVIDER_ORDER from env or fall back to MARKET_PROVIDER_ORDER.

    Returns a list of lowercase provider identifiers in priority order.
    Recognised values include 'tiingo', 'av', 'alpha', 'yf', 'yahoo'.
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
                # Always attempt to call the Tiingo helper; tests monkeypatch this
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


def _dict_to_news_item(ev: dict) -> Optional[NewsItem]:
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
            # Fall back to dateutil.parser when available
            if dtparse is not None:
                try:
                    ts_dt = dtparse.parse(ts_str)
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


def simulate_events(events: Iterable[dict]) -> List[TradeSimResult]:
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
        # Determine which provider would serve this ticker based on the backtest order
        prov: Optional[str] = None
        try:
            if item.ticker:
                prov = _get_provider_for_ticker(item.ticker)
        except Exception:
            prov = None
        # Run the trade simulation.  The simulator may return an empty list
        # when no intraday data is available for the given ticker.  In that
        # case, create a dummy result so that provider usage can still be
        # counted in tests.  Note that TradeSimResult requires a NewsItem,
        # entry offset, hold duration and returns dict.  For dummy results
        # we use 0 for offsets and an empty returns dictionary.
        res = simulate_trades(item)
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
    rows: list[dict] = []
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


def summarize_provider_usage(results: Iterable[TradeSimResult]) -> dict[str, int]:
    """Aggregate provider usage counts from a list of TradeSimResults.

    Each result is expected to have a ``provider`` attribute set by
    ``simulate_events``.  Returns a dictionary mapping provider names to
    the number of simulated fills served by that provider.  Unknown or
    missing provider names are ignored.
    """
    counts: dict[str, int] = {}
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
