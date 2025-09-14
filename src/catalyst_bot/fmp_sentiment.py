"""Utilities for fetching and merging Financial Modeling Prep sentiment data.

This module provides helper functions to retrieve a stock news sentiment RSS
feed from Financial Modeling Prep (FMP) and merge the resulting sentiment
scores into Catalyst Bot event dicts.  The sentiment values augment the
existing classification score and can be displayed in analyzer summaries.

Design notes
------------

The FMP sentiment feed delivers the latest news headlines along with a
computed sentiment score for each article.  Because the canonical RSS
endpoint may require an API key in the future, the URL is constructed
dynamically and a ``fmp_api_key`` setting (or ``FMP_API_KEY`` environment
variable) will be appended when present.  To minimise external calls, the
fetch helper short‑circuits unless the ``feature_fmp_sentiment`` flag is
enabled.  When disabled, both helpers return immediately without raising.

Consumers of this module should call ``fetch_fmp_sentiment()`` once per
cycle and then pass the returned mapping into ``attach_fmp_sentiment()``
alongside the list of events returned from ``feeds.fetch_pr_feeds()``.
"""

from __future__ import annotations

# Standard library imports
import os
import re
from typing import Dict, Iterable, Optional
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

# Third‑party imports
import requests

# Third‑party optional dependency: feedparser.
# Import feedparser at module load time; if unavailable, fall back to None.
try:
    import feedparser  # type: ignore
except Exception:
    feedparser = None  # type: ignore

# Internal imports
from .config import get_settings
from .logging_utils import get_logger

# Logger for this module
log = get_logger("fmp_sentiment")

# We intentionally avoid importing `_canonicalize_link` from feeds.py to
# prevent a circular import (feeds imports fmp_sentiment).  Instead, we
# replicate the canonicalization logic here.  This helper normalises URLs
# by forcing HTTPS, lowercasing the host, stripping trailing slashes and
# removing common tracking query parameters.


def _canonicalize_link(url: str) -> str:
    """Canonicalise a URL for reliable lookups.

    The function lowercases the host, forces the ``https`` scheme, strips
    trailing slashes from the path and drops well‑known tracking query
    parameters (e.g. ``utm_source``).  If the input is empty or
    unparsable, the original string is returned unchanged.
    """
    if not url:
        return ""
    try:
        p = urlparse(url)
        scheme = "https"
        netloc = p.netloc.lower()
        path = p.path.rstrip("/")
        drop = {
            "utm_source",
            "utm_medium",
            "utm_campaign",
            "utm_term",
            "utm_content",
            "gclid",
            "fbclid",
            "cmpid",
            "icid",
            "src",
            "ref",
            "mc_cid",
            "mc_eid",
        }
        q = [
            (k, v)
            for (k, v) in parse_qsl(p.query, keep_blank_values=True)
            if k not in drop
        ]
        query = urlencode(q, doseq=True)
        return urlunparse((scheme, netloc, path, "", query, ""))
    except Exception:
        return url


def _feature_enabled() -> bool:
    """Return True if FMP sentiment integration should run.

    The feature may be enabled via the Settings dataclass or by the
    ``FEATURE_FMP_SENTIMENT`` environment variable.  Falling back to the
    environment allows toggling the feature at runtime during tests.
    """
    try:
        settings = get_settings()
        if getattr(settings, "feature_fmp_sentiment", False):
            return True
    except Exception:
        pass
    val = os.getenv("FEATURE_FMP_SENTIMENT", "0").strip().lower()
    return val in {"1", "true", "yes", "on"}


def _get_api_key() -> str:
    """Return the configured FMP API key, if any."""
    try:
        settings = get_settings()
        key = getattr(settings, "fmp_api_key", "") or ""
        if key:
            return key
    except Exception:
        pass
    return os.getenv("FMP_API_KEY", "") or ""


def fetch_fmp_sentiment(timeout: int = 12) -> Dict[str, float]:
    """Fetch the FMP Stock News Sentiment RSS feed and return a mapping.

    The returned dict maps canonicalised article links to a floating‑point
    sentiment value.  On any error (network, parsing, unexpected fields),
    an empty mapping is returned and a warning is logged.

    The function performs no work unless the feature flag is enabled via
    settings or environment.  When enabled, it constructs the request URL
    (optionally including the API key), performs a GET request and passes
    the response text to ``feedparser.parse()``.  Each entry is examined
    for a sentiment score.  Recognised fields include ``sentiment``,
    ``sentiment_score``, ``sentimentscore`` and ``sentimentScore``.  If
    none of these fields are present, the helper attempts to extract the
    first floating‑point number following a case‑insensitive ``sentiment``
    label from the entry summary or description.
    """
    if not _feature_enabled():
        return {}
    # Attempt to build the URL.  The legacy RSS endpoint does not accept
    # pagination or other parameters, but we append the API key when present.
    base_url = "https://financialmodelingprep.com/api/v4/stock-news-sentiments-rss-feed"
    params = {}
    api_key = _get_api_key()
    if api_key:
        # Use the documented query parameter name for FMP API keys.
        params["apikey"] = api_key
    try:
        r = requests.get(base_url, params=params or None, timeout=timeout)
        if r.status_code != 200:
            log.warning("fmp_sentiment_http status=%s", r.status_code)
            return {}
        text = r.text or ""
    except Exception as e:
        log.warning("fmp_sentiment_request error=%s", e.__class__.__name__)
        return {}
    if not text:
        return {}
    # If feedparser is unavailable (e.g. not installed), bail out quietly.
    if feedparser is None:
        return {}
    try:
        parsed = feedparser.parse(text)
    except Exception as e:
        log.warning("fmp_sentiment_parse error=%s", e.__class__.__name__)
        return {}
    entries: Iterable = getattr(parsed, "entries", []) or []
    out: Dict[str, float] = {}
    for entry in entries:
        link = None
        # Extract link from RSS item attributes in order of preference.
        for attr in ("link", "id", "guid"):
            val = getattr(entry, attr, None)
            if val:
                link = str(val).strip()
                break
        if not link:
            continue
        # Normalise link to canonical form for stable matching.
        canon = _canonicalize_link(link)
        sent: Optional[float] = None
        # Look for explicit sentiment fields on the entry.
        for key in ("sentiment", "sentiment_score", "sentimentscore", "sentimentScore"):
            val = getattr(entry, key, None)
            if val is None:
                val = entry.__dict__.get(key)
            if val is not None:
                try:
                    sent = float(val)
                    break
                except Exception:
                    continue
        # If no explicit field found, try parsing from the summary/description.
        if sent is None:
            desc = None
            for k in ("summary", "description"):
                dv = getattr(entry, k, None)
                if dv:
                    desc = str(dv)
                    break
            if desc:
                m = re.search(
                    r"(?i)sentiment\s*(?:score)?\s*[:=]\s*([-+]?[0-9]*\.?[0-9]+)",
                    desc,
                )
                if m:
                    try:
                        sent = float(m.group(1))
                    except Exception:
                        pass
        if sent is None:
            continue
        out[canon] = sent
    return out


def attach_fmp_sentiment(events: Iterable[Dict], sentiments: Dict[str, float]) -> None:
    """Merge FMP sentiment scores into a list of event dicts in place.

    Each event is expected to have a ``link`` field.  The helper derives
    a canonical form of the link and looks it up in the provided
    ``sentiments`` mapping.  When a match is found, the event dict is
    updated with a new ``sentiment_fmp`` key containing the float value.
    Events without a matching link remain unmodified.  Duplicate links
    implicitly overwrite earlier values, which is intentional because the
    canonicalised link is unique per article.
    """
    if not sentiments:
        return
    for ev in events:
        link = ev.get("link") or ev.get("url")
        if not link:
            continue
        try:
            canon = _canonicalize_link(str(link))
        except Exception:
            continue
        if canon in sentiments:
            try:
                ev["sentiment_fmp"] = float(sentiments[canon])
            except Exception:
                pass
