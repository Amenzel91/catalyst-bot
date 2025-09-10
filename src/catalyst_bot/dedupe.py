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
    text, and strips non‑alphanumeric characters. This function is
    intentionally conservative to avoid accidentally conflating
    unrelated headlines.
    """
    # Remove punctuation and lowercase
    clean = re.sub(r"[^A-Za-z0-9]+", " ", title).lower()
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
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self._conn = sqlite3.connect(db_path, timeout=10)
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS index("
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
            "SELECT id, ts, weight FROM index WHERE signature = ?", (signature,)
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
            "INSERT INTO index(signature, id, ts, source, link, weight) "
            "VALUES(?,?,?,?,?,?) "
            "ON CONFLICT(signature) DO UPDATE SET "
            "id=excluded.id, ts=excluded.ts, "
            "source=excluded.source, link=excluded.link, "
            "weight=excluded.weight",
            (signature, item_id, ts, source, link, weight),
        )
        self._conn.commit()


# If your file does not already define signature_from(), add this minimal helper:
try:
    signature_from  # type: ignore[name-defined]
except NameError:

    def signature_from(title: str, url: str) -> str:
        core = normalize_title(title) + "|" + (url or "")
        return hashlib.sha1(core.encode("utf-8")).hexdigest()
