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
from typing import Dict, List, Optional, Set


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


# -----------------------------------------------------------------------------
# Screener support
#
# Wave‑3 introduces optional support for loading tickers from a Finviz screener
# CSV.  The screener CSV may contain many columns; this loader extracts
# uppercase ticker symbols from either a "Ticker"/"Symbol" column (case
# insensitive) or from the first column when no standard header is present.
# Unreadable files or malformed rows yield an empty set.  See
# :class:`catalyst_bot.config.Settings` for environment knobs controlling
# screener boosting.


def load_screener_set(path: str) -> Set[str]:
    """Load a Finviz screener CSV and return a set of uppercase tickers.

    Parameters
    ----------
    path : str
        Path to the CSV file containing screener entries.  If the file
        cannot be read, an empty set is returned.

    Returns
    -------
    Set[str]
        Uppercase ticker symbols extracted from the CSV.
    """
    tickers: Set[str] = set()
    if not path:
        return tickers
    try:
        with open(path, mode="r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            # Determine candidate columns for ticker values
            fieldnames = [fn.strip() for fn in (reader.fieldnames or [])]
            candidate_cols: List[str] = []
            for col in ("Ticker", "ticker", "Symbol", "symbol"):
                if col in fieldnames:
                    candidate_cols.append(col)
                    break
            for row in reader:
                if not row:
                    continue
                tick: Optional[str] = None
                for col in candidate_cols:
                    val = row.get(col) or ""
                    if val:
                        tick = val.strip().upper()
                        break
                # Fallback: use first value in the row if no header matched
                if not tick:
                    # Convert to list of values; avoid header names
                    values = list(row.values())
                    if values:
                        first_val = values[0] or ""
                        if first_val:
                            tick = str(first_val).strip().upper()
                if tick:
                    # Strip invalid tickers (non-alphanumeric or too long)
                    if tick.isalnum() and 1 <= len(tick) <= 6:
                        tickers.add(tick)
        return tickers
    except Exception:
        return set()


# -----------------------------------------------------------------------------
# Dynamic watchlist helpers
#
# Patch‑2 introduces a small API for modifying the watchlist at runtime.  The
# primary use case is handling Discord slash commands that add or remove
# tickers without requiring a bot restart.  The helpers below operate on the
# same CSV format expected by load_watchlist_csv().  They tolerate missing
# files and attempt to preserve any existing metadata when updating rows.


def _normalise_ticker(sym: str) -> str:
    """Return a normalised uppercase ticker, or an empty string on failure."""
    if not sym:
        return ""
    return str(sym).strip().upper()


def list_watchlist(path: str) -> Set[str]:
    """Return the set of uppercase tickers contained in ``path``.

    This is a convenience wrapper around load_watchlist_set().  Missing
    or unreadable files yield an empty set.
    """
    try:
        return load_watchlist_set(path)
    except Exception:
        return set()


def add_to_watchlist(ticker: str, path: str) -> bool:
    """Add ``ticker`` to the watchlist CSV located at ``path``.

    Returns True if the ticker was added or already present, False on
    unrecoverable errors (e.g. file could not be written).  When the CSV
    does not exist, it will be created with a header row.  Existing
    metadata for other tickers is preserved.
    """
    tick = _normalise_ticker(ticker)
    if not tick:
        return False
    # Load existing entries
    try:
        entries = load_watchlist_csv(path)
    except Exception:
        entries = {}
    # If already present, nothing to do
    if tick in entries:
        return True
    # Add a blank metadata dict; preserve order by copying
    entries[tick] = {}
    try:
        # Determine header
        headers = ["ticker"]
        # Include optional columns if any entry defines them
        for meta in entries.values():
            for k in meta.keys():
                if k not in headers:
                    headers.append(k)
        # Write back to CSV
        with open(path, mode="w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=headers)
            writer.writeheader()
            for sym, meta in entries.items():
                row = {h: "" for h in headers}
                row["ticker"] = sym
                # Fill any known metadata
                for k, v in (meta or {}).items():
                    if k in headers:
                        row[k] = v if v is not None else ""
                writer.writerow(row)
        return True
    except Exception:
        return False


def remove_from_watchlist(ticker: str, path: str) -> bool:
    """Remove ``ticker`` from the watchlist CSV at ``path``.

    Returns True if the ticker was removed or not present, False on
    unrecoverable errors.  If the resulting list is empty, a header
    row is still written to keep the file valid.
    """
    tick = _normalise_ticker(ticker)
    if not tick:
        return False
    try:
        entries = load_watchlist_csv(path)
    except Exception:
        entries = {}
    # Remove if present
    if tick in entries:
        entries.pop(tick, None)
    try:
        # Compute header across remaining entries
        headers = ["ticker"]
        for meta in entries.values():
            for k in meta.keys():
                if k not in headers:
                    headers.append(k)
        # Always write at least the header to maintain a valid CSV
        with open(path, mode="w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=headers)
            writer.writeheader()
            for sym, meta in entries.items():
                row = {h: "" for h in headers}
                row["ticker"] = sym
                for k, v in (meta or {}).items():
                    if k in headers:
                        row[k] = v if v is not None else ""
                writer.writerow(row)
        return True
    except Exception:
        return False


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
