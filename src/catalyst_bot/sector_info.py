"""
Sector and market session utilities for Catalyst Bot
===================================================

This module provides helper functions to determine the sector and
industry associated with a given ticker symbol and to compute the
market session for a given timestamp.  It also exposes helpers for
parsing low‑beta configuration and computing neutral band
adjustments based on sector risk.

The implementation is intentionally lightweight and contains no
external dependencies or network calls.  Sector information is
looked up from a static mapping; unknown tickers will return
``None`` values to trigger a graceful fallback in the caller.  Market
session computation is based on U.S. market hours.

To enable sector and session fields in your alert embeds, set the
environment variables ``FEATURE_SECTOR_INFO`` and/or
``FEATURE_MARKET_TIME`` to ``1``.  For low‑beta relaxation, set
``FEATURE_SECTOR_RELAX`` to ``1`` and configure per‑sector basis points
via the ``LOW_BETA_SECTORS`` variable (e.g. ``utilities:5,consumer
staples:7``) and a default via ``DEFAULT_NEUTRAL_BAND_BPS``.
"""

from __future__ import annotations

import os
from datetime import datetime, time, timezone
from typing import Dict, Optional, Tuple

# -----------------------------------------------------------------------------
# Sector lookup
#
# This static mapping should be populated with known tickers.  In a
# production environment you should consider loading this from a data
# source or provider.  For now, it includes a handful of widely traded
# examples for illustration purposes.  Values are dictionaries with
# ``sector``, ``industry`` and ``beta`` keys.  ``beta`` is a float or
# ``None`` when unknown.
SECTOR_MAP: Dict[str, Dict[str, Optional[object]]] = {
    # Example entries; extend as needed
    "AAPL": {
        "sector": "Information Technology",
        "industry": "Consumer Electronics",
        "beta": 1.28,
    },
    "MSFT": {
        "sector": "Information Technology",
        "industry": "Systems Software",
        "beta": 0.91,
    },
    "TSLA": {
        "sector": "Consumer Discretionary",
        "industry": "Automobile Manufacturers",
        "beta": 2.09,
    },
    "JNJ": {
        "sector": "Health Care",
        "industry": "Pharmaceuticals",
        "beta": 0.54,
    },
    "XOM": {
        "sector": "Energy",
        "industry": "Integrated Oil & Gas",
        "beta": 1.05,
    },
}


def get_sector_info(ticker: str) -> Dict[str, Optional[object]]:
    """Return sector, industry and beta for the given ticker.

    Parameters
    ----------
    ticker: str
        The stock symbol (case‑insensitive).

    Returns
    -------
    Dict[str, Optional[object]]
        A dictionary with keys ``sector``, ``industry`` and ``beta``.  If
        the ticker is not found in the static map, all values are
        ``None``.  Callers can detect ``None`` and substitute a
        user‑friendly placeholder.
    """

    if not ticker or not isinstance(ticker, str):
        raise ValueError("ticker must be a non-empty string")

    info = SECTOR_MAP.get(ticker.upper())
    if info:
        return info.copy()
    # Unknown ticker → return none values
    return {"sector": None, "industry": None, "beta": None}


# -----------------------------------------------------------------------------
# Market session computation
#
# U.S. trading hours (Eastern Time) are roughly 04:00–09:30 (pre‑market),
# 09:30–16:00 (regular), and 16:00–20:00 (after hours).  Outside these
# windows the market is considered closed.  Session names are
# configurable via the ``SESSION_NAMES`` environment variable.

PRE_MARKET_START = time(hour=4, minute=0)
REGULAR_MARKET_START = time(hour=9, minute=30)
REGULAR_MARKET_END = time(hour=16, minute=0)
AFTER_MARKET_END = time(hour=20, minute=0)

DEFAULT_SESSION_NAMES = {
    "pre": "Pre‑Mkt",
    "regular": "Regular",
    "after": "After‑Hours",
    "closed": "Closed",
}


def _get_session_names() -> Dict[str, str]:
    """Return session names from environment or defaults.

    You can override session names by setting the ``SESSION_NAMES`` env
    variable to a comma‑separated list of ``key:value`` pairs, where keys
    are ``pre``, ``regular``, ``after`` and ``closed``.  Unknown keys are
    ignored.
    """
    env_value = os.getenv("SESSION_NAMES", "").strip()
    names = DEFAULT_SESSION_NAMES.copy()
    if env_value:
        for pair in env_value.split(","):
            if ":" not in pair:
                continue
            key, value = pair.split(":", 1)
            key = key.strip().lower()
            value = value.strip()
            if key in names and value:
                names[key] = value
    return names


def get_session(ts: datetime, tz: timezone = timezone.utc) -> str:
    """Return a human‑readable market session name for the given timestamp.

    The timestamp ``ts`` is converted to the given timezone ``tz`` and
    compared against the defined market hours.  Pre‑market is considered
    from 04:00 to 09:30 Eastern Time, regular market from 09:30 to 16:00,
    after hours from 16:00 to 20:00, and closed at all other times.

    Session names may be customised via the ``SESSION_NAMES`` env var; see
    :func:`_get_session_names` for details.

    Parameters
    ----------
    ts: datetime
        A timezone aware or naive datetime.  Naive datetimes are treated
        as UTC.
    tz: timezone, optional
        The timezone used for comparison.  Defaults to UTC.  Use
        ``datetime.timezone.utc`` explicitly to avoid deprecation
        warnings from ``datetime.utcnow``.

    Returns
    -------
    str
        The session name (e.g. ``"Pre‑Mkt"`` or ``"Closed"``).
    """

    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    ts_local = ts.astimezone(tz)
    t = ts_local.timetz()
    names = _get_session_names()
    # Compare against pre‑market / regular / after hours ranges
    if PRE_MARKET_START <= t < REGULAR_MARKET_START:
        return names["pre"]
    if REGULAR_MARKET_START <= t < REGULAR_MARKET_END:
        return names["regular"]
    if REGULAR_MARKET_END <= t < AFTER_MARKET_END:
        return names["after"]
    return names["closed"]


# -----------------------------------------------------------------------------
# Low beta neutral band adjustment
#
# When computing bullishness, low‑beta sectors may warrant a wider
# neutral band to avoid false alarms.  The :func:`get_neutral_band_bps`
# helper reads the ``LOW_BETA_SECTORS`` and ``DEFAULT_NEUTRAL_BAND_BPS``
# environment variables to compute a per‑sector adjustment in basis points.


def _parse_low_beta_config() -> Tuple[Dict[str, int], int]:
    """Parse low‑beta sector configuration from environment variables.

    Returns a tuple ``(per_sector, default_bps)`` where ``per_sector`` is a
    mapping of sector name (lower case) to basis points and
    ``default_bps`` is the basis points to apply to all other sectors.
    Unrecognised or malformed entries are ignored.
    """
    mapping: Dict[str, int] = {}
    raw = os.getenv("LOW_BETA_SECTORS", "")
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        if ":" not in part:
            # If no basis points specified, assume 0
            sector = part.lower()
            mapping[sector] = 0
            continue
        sector, bps = part.split(":", 1)
        sector = sector.strip().lower()
        try:
            mapping[sector] = int(bps.strip())
        except ValueError:
            # ignore invalid entries
            continue
    try:
        default_bps = int(os.getenv("DEFAULT_NEUTRAL_BAND_BPS", "0"))
    except ValueError:
        default_bps = 0
    return mapping, default_bps


def get_neutral_band_bps(sector: Optional[str]) -> int:
    """Return neutral band adjustment in basis points for the given sector.

    If ``FEATURE_SECTOR_RELAX`` is enabled (non‑zero), this helper returns
    the per‑sector basis points specified in ``LOW_BETA_SECTORS`` or
    ``DEFAULT_NEUTRAL_BAND_BPS``.  Otherwise it returns 0.
    ``sector`` is compared case‑insensitively.

    Parameters
    ----------
    sector: Optional[str]
        The sector name.  May be ``None``.

    Returns
    -------
    int
        The neutral band expansion in basis points.
    """
    if not os.getenv("FEATURE_SECTOR_RELAX", "0").strip():
        return 0
    per_sector, default_bps = _parse_low_beta_config()
    if sector is None:
        return default_bps
    return per_sector.get(sector.lower(), default_bps)
