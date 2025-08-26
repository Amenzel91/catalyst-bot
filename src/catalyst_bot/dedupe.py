"""Deduplication helpers for news items.

This module provides functions to normalize news headlines, compute
stable hashes, and detect near duplicates using fuzzy matching. It
leverages the ``rapidfuzz`` library for efficient string similarity
scoring. If ``rapidfuzz`` is not available, the functions fall back
to simple exact matching.
"""

from __future__ import annotations

import hashlib
import re
from typing import Iterable

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
