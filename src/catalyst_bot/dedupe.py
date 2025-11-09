"""Deduplication helpers for news items.

This module provides functions to normalize news headlines, compute
stable hashes, and detect near duplicates using fuzzy matching. It
leverages the ``rapidfuzz`` library for efficient string similarity
scoring. If ``rapidfuzz`` is not available, the functions fall back
to simple exact matching.
"""

from __future__ import annotations

import hashlib
import os
import re
import sqlite3
from typing import Dict, Iterable, Optional, Tuple

try:
    from rapidfuzz import fuzz
except ImportError:  # pragma: no cover
    fuzz = None  # type: ignore[assignment]


def normalize_title(title: str) -> str:
    """Return a normalized version of a headline for hashing/comparison.

    The normalization process removes extra whitespace, lowercases the
    text, strips non‑alphanumeric characters, and normalizes synonyms
    to reduce duplicate alerts with similar content.
    """
    # Remove punctuation and lowercase
    clean = re.sub(r"[^A-Za-z0-9]+", " ", title).lower()

    # Normalize common synonym phrases to catch near-duplicates
    # (e.g., "cuts outlook" = "lowers outlook" = "reduces outlook")
    synonym_map = {
        r"\b(cut|lower|reduce|slash)s?\s+(outlook|guidance|forecast)": "revises_outlook",
        r"\b(miss|disappoint)(?:es|ed)?\s+(estimate|expectation)s?": "misses_estimates",
        r"\b(price|cost)\s+(hike|increase|rise|surge)s?": "price_increase",
        r"\b(consumer|customer)s?\s+(resist|avoid|reject)s?": "consumer_resistance",
        r"\b(plunge|plummet|drop|fall|tank|crater)s?": "declines",
        r"\b(surge|soar|jump|climb|rally)s?": "increases",
        r"\b(tariff|tax)s?\s+(hurt|impact|affect)": "tariff_impact",
    }

    for pattern, replacement in synonym_map.items():
        clean = re.sub(pattern, replacement, clean)

    # Collapse multiple spaces
    return " ".join(clean.split())


def hash_title(title: str) -> str:
    """Compute a deterministic hash for a news headline."""
    normalized = normalize_title(title)
    return hashlib.md5(normalized.encode("utf-8")).hexdigest()


def similarity(a: str, b: str) -> float:
    """Return a similarity score between 0 and 1 for two strings."""
    if not a or not b:
        return 0.0
    if fuzz is None:
        # Fallback: 1.0 if exact match, else 0
        return 1.0 if a == b else 0.0
    return fuzz.token_set_ratio(a, b) / 100.0


def is_near_duplicate(
    title: str, existing: Iterable[str], threshold: float = 0.8
) -> bool:
    """Determine if ``title`` is a near duplicate of any in ``existing``.

    Parameters
    ----------
    title : str
        The headline to compare.
    existing : Iterable[str]
        An iterable of previously seen headlines (already normalized).
    threshold : float, optional
        Similarity threshold above which a title is considered a duplicate.

    Returns
    -------
    bool
        ``True`` if ``title`` is sufficiently similar to any existing
        headline, ``False`` otherwise.
    """
    normalized = normalize_title(title)
    for prev in existing:
        if similarity(normalized, prev) >= threshold:
            return True
    return False


# --- Refined dedup: first-seen index with source weighting -----------------

DEFAULT_SOURCE_WEIGHTS: Dict[str, float] = {
    # Prefer original wires over aggregates
    "businesswire.com": 1.0,
    "globenewswire.com": 0.98,
    "prnewswire.com": 0.95,
    "sec.gov": 0.9,
    # common aggregators lower
    "finance.yahoo.com": 0.6,
    "seekingalpha.com": 0.6,
    "marketwatch.com": 0.6,
    "benzinga.com": 0.6,
}


def _source_weight(host: str, overrides: Optional[Dict[str, float]] = None) -> float:
    host = (host or "").lower()
    w = (overrides or {}).get(host)
    if w is not None:
        return float(w)
    return DEFAULT_SOURCE_WEIGHTS.get(host, 0.7)


class FirstSeenIndex:
    """SQLite-backed first-seen index for content signatures.

    Schema:
      index(signature TEXT PRIMARY KEY, id TEXT, ts INTEGER, source TEXT, link TEXT, weight REAL)
    """

    def __init__(self, db_path: str) -> None:
        from .storage import init_optimized_connection

        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self._conn = init_optimized_connection(db_path, timeout=30)
        self._conn.execute(
            # Use a non-reserved table name instead of 'index'
            "CREATE TABLE IF NOT EXISTS first_seen_index("
            "signature TEXT PRIMARY KEY,"
            "id TEXT,"
            "ts INTEGER,"
            "source TEXT,"
            "link TEXT,"
            "weight REAL)"
        )
        self._conn.commit()

    def close(self) -> None:
        try:
            self._conn.close()
        except Exception:
            pass

    def get(self, signature: str) -> Optional[Tuple[str, int, float]]:
        cur = self._conn.execute(
            "SELECT id, ts, weight FROM first_seen_index WHERE signature = ?",
            (signature,),
        )
        row = cur.fetchone()
        return (row[0], int(row[1]), float(row[2])) if row else None

    def upsert(
        self,
        signature: str,
        item_id: str,
        ts: int,
        source: str,
        link: str,
        weight: float,
    ) -> None:
        self._conn.execute(
            "INSERT INTO first_seen_index(signature, id, ts, source, link, weight) "
            "VALUES(?,?,?,?,?,?) "
            "ON CONFLICT(signature) DO UPDATE SET "
            "id=excluded.id, ts=excluded.ts, "
            "source=excluded.source, link=excluded.link, "
            "weight=excluded.weight",
            (signature, item_id, ts, source, link, weight),
        )
        self._conn.commit()


# --------------------------------------------------------------------------
# Schema migration helpers
#
# To support database initialization from standalone scripts (e.g., jobs/db_init.py),
# expose a simple migration function that creates the required table when
# invoked on a connection.  This avoids having to instantiate a FirstSeenIndex
# purely for schema setup.


def migrate(conn: sqlite3.Connection) -> None:
    """Ensure the first_seen_index table exists.

    This function creates the ``first_seen_index`` table if it is missing and
    commits the transaction.  It is safe to call multiple times.

    Parameters
    ----------
    conn : sqlite3.Connection
        An open SQLite connection.  WAL mode should be configured by the
        caller prior to migration if desired.
    """
    try:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS first_seen_index("
            "signature TEXT PRIMARY KEY,"
            "id TEXT,"
            "ts INTEGER,"
            "source TEXT,"
            "link TEXT,"
            "weight REAL)"
        )
        conn.commit()
    except Exception:
        # swallow errors silently to prevent initialization failure
        pass


# MIGRATION NOTE (2025-10-24):
# The signature_from() function now includes an optional 'ticker' parameter.
# Existing code can continue to call signature_from(title, url) without ticker,
# but new code should use signature_from(title, url, ticker) for better dedup.
#
# For temporal deduplication with sliding windows, use temporal_dedup_key() instead.


def _extract_sec_accession_number(url: str) -> Optional[str]:
    """
    Extract SEC accession number from EDGAR URL.

    SEC filings are uniquely identified by their accession numbers, not URLs.
    Different feeds (RSS, WebSocket, API) may provide different URLs for the same filing.

    Args:
        url: SEC EDGAR URL (various formats supported)

    Returns:
        Accession number (e.g., "0001193125-24-249922") or None if not found

    Examples:
        >>> _extract_sec_accession_number("https://www.sec.gov/cgi-bin/viewer?action=view&cik=6201&accession_number=0001193125-24-249922")
        '0001193125-24-249922'
        >>> _extract_sec_accession_number("https://www.sec.gov/Archives/edgar/data/1234/000119312524249922/d12345.htm")
        '0001193125-24-249922'
    """
    if not url or "sec.gov" not in url.lower():
        return None

    # Pattern 1: accession_number=NNNNNNNNNN-NN-NNNNNN (query parameter)
    match = re.search(r"accession_number=(\d{10}-\d{2}-\d{6})", url)
    if match:
        return match.group(1)

    # Pattern 2: /Archives/edgar/data/CIK/ACCESSION/filename.htm (path with dashes)
    match = re.search(r"/(\d{10}-\d{2}-\d{6})/", url)
    if match:
        return match.group(1)

    # Pattern 3: /NNNNNNNNNNNNNNNNNN/ (path without dashes - 18 digits)
    match = re.search(r"/(\d{18})/", url)
    if match:
        # Re-add dashes: NNNNNNNNNN-NN-NNNNNN
        raw = match.group(1)
        return f"{raw[:10]}-{raw[10:12]}-{raw[12:]}"

    # Pattern 4: Accession number in filename: 0001193125-24-249922.txt
    match = re.search(r"/(\d{10}-\d{2}-\d{6})\.", url)
    if match:
        return match.group(1)

    return None


def signature_from(title: str, url: str, ticker: str = "") -> str:
    """
    Compute a stable signature for a news item.

    Includes ticker to prevent cross-ticker deduplication.
    E.g., "AAPL announces earnings" vs "TSLA announces earnings" get different signatures.

    For SEC filings, uses accession numbers as the primary deduplication key instead of URLs.
    This prevents duplicates when the same filing comes from different feeds (RSS, WebSocket, API)
    with different URLs but the same accession number.

    Args:
        title: News headline
        url: Article URL
        ticker: Stock ticker symbol (optional but recommended)

    Returns:
        SHA1 hash of normalized content
    """
    # Normalize title
    normalized_title = normalize_title(title)

    # Include ticker in signature to allow same news for different tickers
    ticker_component = ticker.upper().strip() if ticker else ""

    # For SEC filings, extract and use accession number as primary dedup key
    # This ensures same filing from different sources (RSS vs WebSocket) is caught as duplicate
    accession_number = _extract_sec_accession_number(url)
    if accession_number:
        # Use accession number instead of full URL for SEC filings
        # Format: ticker|title|accession (not URL) to catch cross-source duplicates
        core = ticker_component + "|" + normalized_title + "|" + accession_number
    else:
        # Non-SEC items: use original logic (ticker + title + URL)
        core = ticker_component + "|" + normalized_title + "|" + (url or "")

    return hashlib.sha1(core.encode("utf-8")).hexdigest()


def temporal_dedup_key(ticker: str, title: str, timestamp: int) -> str:
    """
    Generate a dedup key that includes time bucket for sliding window dedup.

    Groups items into 30-minute buckets to prevent rapid-fire duplicates
    while allowing same news to re-alert after sufficient time has passed.

    Args:
        ticker: Stock ticker symbol
        title: News headline
        timestamp: Unix timestamp (seconds since epoch)

    Returns:
        Dedup key combining ticker, title, and 30-min time bucket
    """
    # Bucket timestamp into 30-minute windows
    # This allows same news to alert again after 30 minutes
    bucket_size = 30 * 60  # 30 minutes in seconds
    time_bucket = (timestamp // bucket_size) * bucket_size

    # Normalize title
    normalized_title = normalize_title(title)

    # Combine ticker + title + time bucket
    key = f"{ticker.upper()}|{normalized_title}|{time_bucket}"

    return hashlib.sha1(key.encode("utf-8")).hexdigest()
