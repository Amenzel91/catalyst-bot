"""
SEC filing digester for Catalyst‑Bot.

This module classifies SEC filings pulled from the feeds defined in
``catalyst_bot.feeds`` and tracks recent filings per ticker.  It is
designed for sub‑$10 stocks where regulatory news and financing
transactions can materially move price.  The digester attaches a
sentiment label (Bullish/Neutral/Bearish) and a short reason to each
filing based on simple keyword heuristics derived from common market
reactions.  It also exposes helpers to aggregate sentiment across a
lookback window and to update the watchlist cascade accordingly.

The implementation is deliberately lightweight: no network calls are
made, and the cache resides in memory.  Expired entries are purged on
each call based on ``sec_lookback_days``.  When the watchlist cascade
feature is enabled, classified filings promote the ticker in the
cascade to HOT/WARM/COOL depending on the sentiment.

Functions
---------
classify_filing(src, title, summary)
    Return (score, label, reason) for a filing given its feed key and
    textual fields.  Returns (None, None, None) when unclassified.

record_filing(ticker, dt, label, reason)
    Append a classified filing to the per‑ticker cache.

get_recent_filings(ticker)
    Return a list of recent filings (within ``sec_lookback_days``) for
    the ticker.

get_combined_sentiment(ticker)
    Aggregate recent filings into a mean score and majority label.

update_watchlist_for_filing(ticker, label)
    Promote the ticker in the watchlist cascade based on the filing
    sentiment when the cascade feature is enabled.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple

from .config import get_settings

# In‑memory cache of recent filings.  Keys are uppercase tickers; values
# are lists of dictionaries with keys: ``ts`` (datetime), ``label``
# (str) and ``reason`` (str).  The cache is pruned on each write/read.
_SEC_CACHE: Dict[str, List[Dict[str, object]]] = {}

# Mapping from sentiment labels to numeric scores.  Used when
# aggregating multiple filings into a single score.
_LABEL_SCORE = {"Bullish": 1.0, "Neutral": 0.0, "Bearish": -1.0}

# ---------------------------------------------------------------------------
# Heuristic summarisation for SEC filings
#
# Discord embeds have strict character limits; including the full filing title
# in the alert embed can easily exceed these limits, especially when the
# bot attaches a history of recent filings.  To reduce noise and avoid
# HTTP 400 errors from Discord, we summarise each filing title into a
# concise keyword or category.  This helper attempts to map known
# phrases (e.g. offerings, buybacks, resignations) into a single word.
# When no known patterns match, it falls back to extracting the first
# few significant tokens from the title after removing common stopwords.

# Common stopwords and corporate suffixes to ignore when extracting
# keywords from filing titles.  Tokens shorter than 3 characters or
# appearing in this set will be skipped during summarisation.
_STOPWORDS: set[str] = {
    "inc",
    "inc.",
    "incorporated",
    "corporation",
    "corp",
    "corp.",
    "company",
    "co",
    "co.",
    "plc",
    "plc.",
    "llc",
    "ltd",
    "ltd.",
    "the",
    "a",
    "an",
    "for",
    "and",
    "with",
    "of",
    "to",
    "in",
    "on",
    "by",
    "as",
    "from",
    "at",
    "its",
    "it's",
    "was",
    "were",
    "their",
    "his",
    "her",
    "over",
    "into",
    "about",
    "after",
    "before",
    "via",
}


def summarize_title(title: Optional[str]) -> str:
    """Return a short summary of the SEC filing title.

    The summary is either a predefined category (e.g. "offering",
    "buyback", "resignation") when a keyword is detected, or a
    slash‑separated list of up to three significant tokens extracted
    from the title.  When no title is supplied, an empty string is
    returned.

    Parameters
    ----------
    title : Optional[str]
        The filing title from the SEC feed.

    Returns
    -------
    str
        A concise summary suitable for display in Discord embeds.
    """
    t = _clean(title)
    if not t:
        return ""
    # Pattern → summary mappings for common filing types.  Keywords are
    # checked in order; the first match wins.  All comparisons are
    # case‑insensitive due to _clean().
    patterns = [
        (  # Dilutive offerings and equity financings
            [
                "offering",
                "registered direct",
                "atm",
                "equity financing",
                "dilutive",
            ],
            "offering",
        ),
        (  # Buybacks and repurchases
            ["buyback", "repurchase"],
            "buyback",
        ),
        (  # Leadership departures
            ["resignation", "retire", "termination", "fired"],
            "resignation",
        ),
        (  # Legal or compliance issues
            [
                "investigation",
                "lawsuit",
                "class action",
                "legal",
                "compliance notice",
                "deficiency",
            ],
            "legal",
        ),
        (  # Mergers and acquisitions
            ["merger", "acquisition"],
            "merger",
        ),
        (  # Clinical trial updates
            [
                "phase 2",
                "phase 3",
                "clinical",
                "trial",
                "fast track",
                "designation",
            ],
            "clinical",
        ),
        (  # Guidance changes and restatements
            ["guidance", "cut", "restatement"],
            "guidance",
        ),
        (  # Contracts and awards
            [
                "contract",
                "partnership",
                "agreement",
                "license",
                "award",
                "win",
            ],
            "contract",
        ),
    ]
    for kws, summary in patterns:
        for kw in kws:
            if kw in t:
                return summary
    # Fallback: extract up to three significant tokens from the title.  We
    # split on non‑alphanumeric characters and filter out stopwords and
    # short tokens.  Use a simple regular expression to identify words.
    import re

    tokens = re.findall(r"[a-z0-9]+", t)
    keywords: list[str] = []
    for tok in tokens:
        if tok in _STOPWORDS or len(tok) < 3:
            continue
        keywords.append(tok)
        if len(keywords) >= 3:
            break
    if keywords:
        return "/".join(keywords)
    # As a last resort return the first token (if any)
    return tokens[0] if tokens else ""


def _clean(s: Optional[str]) -> str:
    """Return a lowercase version of ``s`` or an empty string when None."""
    if not s:
        return ""
    return str(s).lower()


def classify_filing(
    src: str, title: Optional[str], summary: Optional[str]
) -> Tuple[Optional[float], Optional[str], Optional[str]]:
    """
    Classify an SEC filing into a sentiment tuple.

    Parameters
    ----------
    src : str
        The feed key for the filing (e.g. ``"sec_8k"``).  Case is
        ignored.
    title : Optional[str]
        The filing title.  May be None.
    summary : Optional[str]
        The filing summary or description.  May be None.

    Returns
    -------
    Tuple[score, label, reason]
        ``score`` is 1.0 for Bullish, 0.0 for Neutral, −1.0 for Bearish
        and None when the filing cannot be classified.  ``label`` is
        one of ``"Bullish"``, ``"Neutral"``, ``"Bearish"`` or None.
        ``reason`` is a short human‑readable explanation for the
        classification or None.
    """
    src_l = (src or "").lower()
    t = _clean(title)
    s = _clean(summary)

    # Treat certain form types as inherently bearish due to dilution.
    if src_l in {"sec_424b5", "sec_fwp"}:
        return -1.0, "Bearish", "Dilutive offering"
    # Beneficial ownership filings (13D/G) are neutral unless keywords
    # suggest an activist stake increase.
    if src_l in {"sec_13d", "sec_13g"}:
        if any(k in t or k in s for k in ["increase", "acquire", "stake", "buy"]):
            return 1.0, "Bullish", "Stake increase"
        return 0.0, "Neutral", "Beneficial ownership"
    # Current reports (8‑K) contain a wide range of events.  Use
    # positive/negative keyword heuristics to classify.  When no
    # keywords match, treat as informational (neutral).
    if src_l == "sec_8k":
        positive_kws = [
            "contract",
            "partnership",
            "agreement",
            "approval",
            "authorized",
            "buyback",
            "repurchase",
            "acquisition",
            "merger",
            "fast track",
            "designation",
            "award",
            "win",
            "launch",
            "license",
            "phase 2",
            "phase 3",
        ]
        negative_kws = [
            "offering",
            "registered direct",
            "atm",
            "equity financing",
            "dilutive",
            "resignation",
            "retire",
            "termination",
            "fired",
            "investigation",
            "lawsuit",
            "clinical hold",
            "guidance",
            "cut",
            "restatement",
            "compliance notice",
            "listing deficiency",
            "deficiency notice",
        ]
        for kw in positive_kws:
            if kw in t or kw in s:
                return 1.0, "Bullish", f"8‑K: positive news ({kw})"
        for kw in negative_kws:
            if kw in t or kw in s:
                return -1.0, "Bearish", f"8‑K: negative news ({kw})"
        # Unknown 8‑K content → neutral
        return 0.0, "Neutral", "8‑K: informational"
    # Unknown source → skip
    return None, None, None


def record_filing(ticker: str, dt: datetime, label: str, reason: str) -> None:
    """
    Record a classified filing in the per‑ticker cache.

    Keeps only filings within the lookback window as defined by
    ``sec_lookback_days``.  Invalid inputs are ignored silently.
    """
    tick = (ticker or "").strip().upper()
    if not tick or not label:
        return
    # Determine lookback days from settings or env
    try:
        settings = get_settings()
        days = getattr(settings, "sec_lookback_days", 7)
    except Exception:
        try:
            days = int(os.getenv("SEC_LOOKBACK_DAYS", "7") or "7")
        except Exception:
            days = 7
    now = datetime.now(timezone.utc)
    expire_before = now - timedelta(days=days)
    cur = _SEC_CACHE.get(tick, [])
    # Keep only unexpired records
    new_list: List[Dict[str, object]] = []
    for rec in cur:
        ts = rec.get("ts")
        if isinstance(ts, datetime) and ts >= expire_before:
            new_list.append(rec)
    # Append current record
    new_list.append({"ts": dt, "label": label, "reason": reason})
    _SEC_CACHE[tick] = new_list


def get_recent_filings(ticker: str) -> List[Dict[str, object]]:
    """Return recent filings for ``ticker`` within the lookback window."""
    tick = (ticker or "").strip().upper()
    if not tick:
        return []
    # Determine lookback days
    try:
        settings = get_settings()
        days = getattr(settings, "sec_lookback_days", 7)
    except Exception:
        try:
            days = int(os.getenv("SEC_LOOKBACK_DAYS", "7") or "7")
        except Exception:
            days = 7
    now = datetime.now(timezone.utc)
    expire_before = now - timedelta(days=days)
    cur = _SEC_CACHE.get(tick, [])
    out: List[Dict[str, object]] = []
    for rec in cur:
        ts = rec.get("ts")
        if isinstance(ts, datetime) and ts >= expire_before:
            out.append(rec)
    # Prune expired
    if out:
        _SEC_CACHE[tick] = out
    else:
        _SEC_CACHE.pop(tick, None)
    return out


def get_combined_sentiment(ticker: str) -> Tuple[Optional[float], Optional[str]]:
    """
    Aggregate recent filings into a mean score and majority label.

    Returns (score, label) where ``score`` is the average of numeric
    scores for recent filings and ``label`` is the majority sentiment.
    When no filings are present, returns (None, None).
    """
    recs = get_recent_filings(ticker)
    if not recs:
        return None, None
    scores: List[float] = []
    counts: Dict[str, int] = {}
    for rec in recs:
        lbl = rec.get("label")
        if not isinstance(lbl, str) or lbl not in _LABEL_SCORE:
            continue
        scores.append(_LABEL_SCORE[lbl])
        counts[lbl] = counts.get(lbl, 0) + 1
    if not scores:
        return None, None
    avg = sum(scores) / len(scores)
    # Determine majority label (tie → Neutral)
    majority: Optional[str] = None
    max_count = 0
    for lbl, cnt in counts.items():
        if cnt > max_count:
            majority = lbl
            max_count = cnt
        elif cnt == max_count:
            majority = None
    if not majority:
        majority = "Neutral"
    return avg, majority


def update_watchlist_for_filing(ticker: str, label: str) -> None:
    """
    Update the watchlist cascade based on a filing classification.

    When ``feature_watchlist_cascade`` is enabled, the ticker is
    promoted in the cascade to a state corresponding to the sentiment
    label: Bullish → HOT, Neutral → WARM, Bearish → COOL.  When the
    cascade feature is off or any errors occur, the update is skipped.
    """
    try:
        settings = get_settings()
        if not getattr(settings, "feature_watchlist_cascade", False):
            return
        from .watchlist_cascade import load_state, promote_ticker, save_state

        state = load_state(settings.watchlist_state_file)
        # Map sentiment to cascade state
        st_name = "HOT"
        if label == "Bearish":
            st_name = "COOL"
        elif label == "Neutral":
            st_name = "WARM"
        promote_ticker(state, ticker, state_name=st_name)
        save_state(settings.watchlist_state_file, state)
    except Exception:
        # Do not propagate cascade failures to the caller
        return
