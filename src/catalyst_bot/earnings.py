"""Earnings calendar helpers for Catalyst‑Bot.

This module provides utilities to load an earnings calendar from a CSV file
downloaded from Alpha Vantage and to query upcoming earnings dates for
individual tickers.  The free Alpha Vantage API exposes an `EARNINGS_CALENDAR`
function that returns a CSV containing upcoming earnings reports.  Each row
includes the stock symbol, company name, report date, fiscal period end,
consensus estimate, and currency.  The jobs/earnings_pull.py script uses
this API to refresh the local cache; this module focuses on reading that
cache and exposing a simple lookup interface.

The primary entry point is :func:`load_earnings_calendar`, which returns a
mapping from uppercase ticker symbols to the next known report date.  If
multiple rows exist for a ticker (e.g. multiple horizons), the earliest
upcoming report date is selected.  Unparseable dates or malformed rows
are ignored.  If the file cannot be read, an empty mapping is returned.

Example usage::

    from catalyst_bot.earnings import load_earnings_calendar
    earnings = load_earnings_calendar("data/earnings_calendar.csv")
    next_date = earnings.get("AAPL")
    if next_date:
        print(f"AAPL reports on {next_date}")

"""

from __future__ import annotations

import csv
from datetime import date as date_cls
from datetime import datetime
from typing import Dict, Optional

__all__ = ["load_earnings_calendar"]


def _parse_date(val: str) -> Optional[date_cls]:
    """Attempt to parse a date in YYYY-MM-DD format to a ``date``.

    Returns None on failure.
    """
    if not val:
        return None
    try:
        dt = datetime.strptime(val.strip(), "%Y-%m-%d")
        return dt.date()
    except Exception:
        return None


def load_earnings_calendar(path: str) -> Dict[str, date_cls]:
    """Load an earnings calendar CSV and return a mapping of ticker → next date.

    Parameters
    ----------
    path : str
        Path to the CSV file containing upcoming earnings dates.  The file is
        expected to have at least the columns ``symbol`` and ``reportDate``.

    Returns
    -------
    Dict[str, date]
        Mapping from uppercase ticker symbols to the earliest upcoming earnings
        date.  If the file is missing or cannot be parsed, an empty mapping is
        returned.
    """
    out: Dict[str, date_cls] = {}
    if not path:
        return out
    try:
        with open(path, newline="", encoding="utf-8") as fp:
            rdr = csv.DictReader(fp)
            for row in rdr:
                if not row:
                    continue
                # Normalise header names to lowercase
                low = {k.strip().lower(): v for k, v in row.items() if k}
                sym = (low.get("symbol") or low.get("ticker") or "").strip().upper()
                date_str = (
                    low.get("reportdate") or low.get("report_date") or ""
                ).strip()
                d = _parse_date(date_str)
                if not sym or not d:
                    continue
                # Keep the earliest upcoming date per ticker
                cur = out.get(sym)
                if cur is None or d < cur:
                    out[sym] = d
    except Exception:
        # Fail silently on any error
        return {}
    return out
