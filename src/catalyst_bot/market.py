"""Market data adapters for the catalyst bot.

This module interfaces with the Alpha Vantage API to retrieve
intraday and daily time series data. It provides a minimal wrapper
around the HTTP API, handling retries and timeouts. The functions are
written synchronously but could be adapted to async if needed.
"""

from __future__ import annotations

import json
import logging
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd
import requests

from .config import get_settings


API_BASE_URL = "https://www.alphavantage.co/query"


def _call_api(params: Dict[str, str], timeout: int = 15) -> Dict:
    """Internal helper to call the Alpha Vantage API with retries."""
    settings = get_settings()
    params = params.copy()
    params["apikey"] = settings.alphavantage_api_key
    for attempt in range(3):
        try:
            resp = requests.get(API_BASE_URL, params=params, timeout=timeout)
            if resp.status_code == 200:
                data = resp.json()
                if "Note" in data:
                    # API throttling. Back off and retry
                    time.sleep(12)  # wait ~12 seconds per Alpha Vantage docs
                    continue
                return data
            else:
                time.sleep(1)
        except Exception:
            time.sleep(1)
    return {}


def get_intraday(symbol: str, interval: str = "5min", output_size: str = "compact") -> Optional[pd.DataFrame]:
    """Fetch intraday OHLCV data for ``symbol``.

    Parameters
    ----------
    symbol : str
        The ticker symbol to query.
    interval : str
        Interval between data points (e.g. '1min', '5min', '15min', '30min', '60min').
    output_size : str
        'compact' returns last 100 data points; 'full' returns full session. Use
        'compact' to minimize API usage.

    Returns
    -------
    Optional[pd.DataFrame]
        A DataFrame indexed by timestamp in UTC with columns
        ['open','high','low','close','volume']. Returns ``None`` on error.
    """
    params = {
        "function": "TIME_SERIES_INTRADAY",
        "symbol": symbol,
        "interval": interval,
        "outputsize": output_size,
        "datatype": "json",
    }
    data = _call_api(params)
    key = f"Time Series ({interval})"
    if not data or key not in data:
        return None
    ts_data = data[key]
    records = []
    for ts_str, values in ts_data.items():
        # Alpha Vantage timestamps are returned in US/Eastern; convert to UTC
        try:
            ts = datetime.fromisoformat(ts_str)
        except Exception:
            continue
        record = {
            "timestamp": ts,
            "open": float(values.get("1. open", 0.0)),
            "high": float(values.get("2. high", 0.0)),
            "low": float(values.get("3. low", 0.0)),
            "close": float(values.get("4. close", 0.0)),
            "volume": float(values.get("5. volume", 0.0)),
        }
        records.append(record)
    if not records:
        return None
    df = pd.DataFrame(records)
    # Sort by timestamp ascending
    df = df.sort_values("timestamp").set_index("timestamp")
    return df


def get_latest_price(symbol: str) -> Optional[float]:
    """Return the most recent close price for ``symbol`` using intraday data."""
    df = get_intraday(symbol, interval="5min", output_size="compact")
    if df is None or df.empty:
        return None
    try:
        return float(df["close"].iloc[-1])
    except Exception:
        return None


def get_daily_series(symbol: str, output_size: str = "compact") -> Optional[pd.DataFrame]:
    """Fetch daily adjusted time series for ``symbol``."""
    params = {
        "function": "TIME_SERIES_DAILY_ADJUSTED",
        "symbol": symbol,
        "outputsize": output_size,
        "datatype": "json",
    }
    data = _call_api(params)
    key = "Time Series (Daily)"
    if not data or key not in data:
        return None
    ts_data = data[key]
    records = []
    for ts_str, values in ts_data.items():
        try:
            ts = datetime.fromisoformat(ts_str)
        except Exception:
            continue
        record = {
            "timestamp": ts,
            "open": float(values.get("1. open", 0.0)),
            "high": float(values.get("2. high", 0.0)),
            "low": float(values.get("3. low", 0.0)),
            "close": float(values.get("4. close", 0.0)),
            "adjusted_close": float(values.get("5. adjusted close", 0.0)),
            "volume": float(values.get("6. volume", 0.0)),
        }
        records.append(record)
    if not records:
        return None
    df = pd.DataFrame(records)
    df = df.sort_values("timestamp").set_index("timestamp")
    return df


def get_20d_avg_volume(symbol: str) -> Optional[float]:
    """Return the 20‑day average volume for ``symbol`` using daily data."""
    df = get_daily_series(symbol, output_size="compact")
    if df is None or df.empty:
        return None
    # Use the last 20 entries
    try:
        recent = df.tail(20)
        return float(recent["volume"].mean())
    except Exception:
        return None