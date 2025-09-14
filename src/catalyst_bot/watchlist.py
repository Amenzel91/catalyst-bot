"""Watchlist support for Catalyst‑Bot.

This module provides helpers to load a list of watchlist tickers from a CSV
file and query whether a given ticker is present.  The watchlist file
(``data/watchlist.csv`` by default) can contain one row per ticker with
optional metadata such as a rationale or a custom weight.

The expected CSV header should include a column named ``ticker`` (case
insensitive).  Additional columns like ``rationale`` or ``weight`` will be
captured if present.  Rows with missing or blank tickers are ignored.

Example ``watchlist.csv``::

    ticker,rationale,weight
    AAPL,long term conviction,1.5
    TSLA,EV growth story,

Loading this file via :func:`load_watchlist_csv` will produce a mapping
``{"AAPL": {"rationale": "long term conviction", "weight": "1.5"},
  "TSLA": {"rationale": "EV growth story", "weight": ""}}``.

Use :func:`load_watchlist_set` to get a simple ``set`` of uppercase tickers.
These helpers are tolerant of missing files and malformed rows – they
silently return empty structures on errors.
"""

from __future__ import annotations

import csv
from typing import Dict, Optional, Set


def load_watchlist_csv(path: str) -> Dict[str, Dict[str, Optional[str]]]:
    """Load a watchlist CSV and return a mapping of tickers to metadata.

    Parameters
    ----------
    path : str
        Path to the CSV file containing watchlist entries.  If the file
        cannot be read, an empty dict is returned.

    Returns
    -------
    Dict[str, Dict[str, Optional[str]]]
        Mapping from uppercase ticker symbols to a dict of metadata
        extracted from the row.  Known keys include ``rationale`` and
        ``weight`` if present in the header.  Unknown columns are ignored.
    """
    watchlist: Dict[str, Dict[str, Optional[str]]] = {}
    if not path:
        return watchlist
    try:
        with open(path, mode="r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            # normalise header names to lowercase for lookup
            field_map = {name.lower(): name for name in reader.fieldnames or []}
            for row in reader:
                if not row:
                    continue
                # find ticker column; support variations like 'symbol'
                ticker_col = None
                for k in ("ticker", "symbol"):
                    if k in field_map:
                        ticker_col = field_map[k]
                        break
                if not ticker_col:
                    # no ticker column; abort
                    break
                raw_ticker = (row.get(ticker_col) or "").strip()
                if not raw_ticker:
                    continue
                tick = raw_ticker.upper()
                # capture optional fields
                entry: Dict[str, Optional[str]] = {}
                for opt in ("rationale", "reason"):
                    col = field_map.get(opt)
                    if col:
                        entry["rationale"] = row.get(col, "").strip() or None
                        break
                weight_col = field_map.get("weight")
                if weight_col:
                    entry["weight"] = row.get(weight_col, "").strip() or None
                watchlist[tick] = entry
    except Exception:
        # Fail silently; return empty watchlist on any error
        return {}
    return watchlist


def load_watchlist_set(path: str) -> Set[str]:
    """Load a watchlist CSV and return a set of uppercase tickers.

    This is a convenience wrapper around :func:`load_watchlist_csv` when
    only the ticker symbols are needed.  Unreadable files yield an empty
    set.

    Parameters
    ----------
    path : str
        Path to the CSV file to load.

    Returns
    -------
    Set[str]
        Uppercase ticker symbols contained in the file.
    """
    mapping = load_watchlist_csv(path)
    return set(mapping.keys())
