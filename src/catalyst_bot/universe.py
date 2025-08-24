"""Universe construction for low‑priced US equities.

This module builds and maintains the universe of securities eligible for
alerting. The universe is derived from two sources:

* Finviz Elite screener export (or API) for tickers and average volume
  information. The screener should be configured to include only US
  exchange‑listed equities (NYSE, NASDAQ, AMEX) and exclude OTC
  securities.
* Alpha Vantage listing status API for a complete list of US securities
  and their current trading status (active vs delisted).

The combination of these sources ensures that the bot only considers
tickers that are both officially listed and have sufficient liquidity.
"""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Dict, Iterable, Optional, Tuple

from .config import get_settings
from .market import get_latest_price

import requests
import csv
from io import StringIO


def load_finviz_universe(path: Optional[Path] = None) -> Dict[str, float]:
    """Load a Finviz screener export CSV and return ticker → average volume.

    Finviz Elite allows exports of screener results to CSV. Each row
    should include a ticker and an "AvgVol" column. Only rows with
    non‑empty tickers are returned.
    """
    settings = get_settings()
    if path is None:
        path = settings.data_dir / "finviz_universe.csv"
    universe: Dict[str, float] = {}
    if not path.exists():
        return universe
    try:
        with path.open("r", encoding="utf-8") as fh:
            reader = csv.DictReader(fh)
            for row in reader:
                ticker = row.get("Ticker") or row.get("ticker") or row.get("Symbol")
                avg_vol_str = row.get("AvgVol") or row.get("average volume") or "0"
                if ticker:
                    try:
                        avg_vol = float(avg_vol_str.replace(",", ""))
                    except ValueError:
                        avg_vol = 0.0
                    universe[ticker.upper()] = avg_vol
    except Exception:
        pass
    return universe


def fetch_finviz_screener(filters: str = "", view: str = "111") -> Dict[str, float]:
    """Fetch screener results directly from Finviz Elite export API.

    When a valid Finviz auth token is provided in the environment
    (``FINVIZ_AUTH_TOKEN``), this function constructs a request to
    the export endpoint and returns a mapping of ticker → average volume.

    Parameters
    ----------
    filters : str
        Finviz screener filter parameters, e.g. ``"fa_div_pos,sec_technology"``.
        Leave blank to use whatever default you have configured on the
        Finviz website.
    view : str
        Finviz view code controlling which columns are returned. The
        default ``"111"`` includes ticker, company, sector, industry,
        country, market cap, P/E, price, change, and volume. See
        Finviz documentation for other view codes.

    Returns
    -------
    Dict[str, float]
        Dictionary mapping tickers to average volume. If the request
        fails or the token is missing, an empty dictionary is returned.
    """
    settings = get_settings()
    token = settings.finviz_auth_token
    if not token:
        return {}
    # Build the export URL. Note: `v` parameter controls which columns,
    # filters are comma‑separated. Auth token is appended at the end.
    url = f"https://elite.finviz.com/export.ashx?"
    params = []
    if filters:
        params.append(f"f={filters}")
    if view:
        params.append(f"v={view}")
    params.append(f"auth={token}")
    url += "&".join(params)
    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        # Finviz returns CSV content. Use StringIO for csv.DictReader.
        csv_io = StringIO(resp.text)
        reader = csv.DictReader(csv_io)
        universe: Dict[str, float] = {}
        for row in reader:
            ticker = row.get("Ticker") or row.get("ticker") or row.get("Symbol")
            avg_vol_str = row.get("Avg Vol") or row.get("AvgVol") or row.get("Average Volume")
            if not ticker:
                continue
            try:
                avg_vol = float(avg_vol_str.replace(",", "")) if avg_vol_str else 0.0
            except Exception:
                avg_vol = 0.0
            universe[ticker.upper()] = avg_vol
        return universe
    except Exception:
        return {}


def load_listing_status(path: Optional[Path] = None) -> Dict[str, str]:
    """Load Alpha Vantage listing status data.

    Alpha Vantage provides a ``LISTING_STATUS`` endpoint which returns
    current and delisted securities. This function expects that the CSV
    exported from that endpoint has been downloaded to disk. The CSV
    should contain at least ``symbol`` and ``status`` columns.
    """
    settings = get_settings()
    if path is None:
        path = settings.data_dir / "listing_status.csv"
    status_map: Dict[str, str] = {}
    if not path.exists():
        return status_map
    try:
        with path.open("r", encoding="utf-8") as fh:
            reader = csv.DictReader(fh)
            for row in reader:
                symbol = row.get("symbol") or row.get("Symbol")
                status = row.get("status") or row.get("Status") or ""
                if symbol:
                    status_map[symbol.upper()] = status.lower()
    except Exception:
        pass
    return status_map


def build_universe(price_ceiling: float | None = None) -> Dict[str, float]:
    """Return a dictionary mapping eligible tickers to their average volumes.

    Filters tickers based on the configured price ceiling using latest
    price data from Alpha Vantage. If no ``price_ceiling`` is provided,
    the ceiling from configuration is used.
    """
    settings = get_settings()
    if price_ceiling is None:
        price_ceiling = settings.price_ceiling

    # Prefer live data from Finviz export API if available
    finviz_universe: Dict[str, float] = {}
    if settings.finviz_auth_token:
        finviz_universe = fetch_finviz_screener()
    # Fallback to reading from a saved CSV
    if not finviz_universe:
        finviz_universe = load_finviz_universe()
    listing_status = load_listing_status()
    universe: Dict[str, float] = {}
    for ticker, avg_vol in finviz_universe.items():
        # Exclude delisted or inactive securities
        if listing_status.get(ticker, "active") != "active":
            continue
        # Price filter (call Alpha Vantage only if necessary)
        try:
            price = get_latest_price(ticker)
        except Exception:
            price = None
        if price is None:
            # If price unavailable, fall back to including the ticker but will be
            # filtered later at alert time
            universe[ticker] = avg_vol
            continue
        if price <= price_ceiling:
            universe[ticker] = avg_vol
    return universe


def is_under_price_ceiling(ticker: str, price_ceiling: float | None = None) -> bool:
    """Return True if the current price of ``ticker`` is <= ``price_ceiling``."""
    settings = get_settings()
    if price_ceiling is None:
        price_ceiling = settings.price_ceiling
    try:
        price = get_latest_price(ticker)
        return price is not None and price <= price_ceiling
    except Exception:
        return False