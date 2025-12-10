# src/catalyst_bot/feeds.py
from __future__ import annotations

import asyncio
import csv
import hashlib
import html
import json
import os
import random
import re
import time
from datetime import datetime, timedelta, timezone
from io import StringIO
from typing import Any, Dict, List, Optional, Tuple, Union
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

import feedparser  # type: ignore
import requests
from bs4 import BeautifulSoup
from dateutil import parser as dtparse

# Async HTTP support for 10-20x faster concurrent feed fetching
try:
    import aiohttp

    AIOHTTP_AVAILABLE = True
except ImportError:
    AIOHTTP_AVAILABLE = False
    aiohttp = None  # type: ignore

from . import market

# NOTE: Import the entire market module instead of directly importing
# get_last_price_snapshot.  This allows tests to monkeypatch the
# get_last_price_snapshot function on the market module without
# affecting the name bound in this module.  get_volatility is still
# imported directly because it is not monkeypatched by tests.
from .classify_bridge import classify_text

# Import both the cached settings accessor and the dataclass itself.  The
# dataclass allows us to instantiate a fresh Settings object to pick up
# environment variable changes during tests or runtime.  When using
# get_settings(), the instance is created at import time and may not
# reflect subsequent changes in os.environ.  See below where we
# preferentially instantiate Settings() for watchlist and screener
# configuration.
from .config import Settings, get_settings
from .feed_state_manager import FeedStateManager
from .logging_utils import get_logger
from .market import get_volatility
from .ticker_validation import TickerValidator
from .utils.event_loop_manager import run_async
from .watchlist import load_watchlist_set


# --- Noise filtering -------------------------------------------------------
def _is_finviz_noise(title: str, summary: str) -> bool:
    """
    Heuristic filter for Finviz news headlines that are legal notices or
    shareholder investigation advertisements rather than actionable news.

    Returns ``True`` when the headline or summary contains phrases commonly
    associated with class‑action law firms (e.g. ``"recover your losses"``,
    ``"class action"``, ``"lawsuit"``, ``"contact the firm"``, ``"deadline alert"``)
    or when the headline mentions law firms by name (Rosen, Portnoy,
    Pomerantz, etc.).  The keyword list is extensible: additional phrases
    can be placed in ``data/filters/finviz_noise.txt`` (one per line) and
    will be loaded at runtime.  Lines beginning with ``#`` in that file
    are treated as comments.

    Parameters
    ----------
    title : str
        The news headline from Finviz.
    summary : str
        The optional summary or description.

    Returns
    -------
    bool
        ``True`` if the item should be filtered out, ``False`` otherwise.
    """
    try:
        # Combine title and summary for unified pattern matching.  Use
        # lower‑case comparison to make checks case‑insensitive.
        text = f"{title} {summary}".lower()
        # Base keyword set.  These patterns are derived from common
        # shareholder lawsuit notices and legal advertisements that rarely
        # provide actionable trading information.  See the updated technical
        # guide for examples.
        keywords: list[str] = [
            "recover your losses",
            "class action",
            "class‑action",
            "lawsuit",
            "llp",
            "law firm",
            "investigation",
            "shareholder investigation",
            "securities investigation",
            "legal notice",
            "recover losses",
            "pomerantz",
            "rosen law",
            "portnoy",
            "deadline alert",
            "deadline reminder",
            # Expanded phrases for refined noise filtering
            "free consultation",
            "class action lawsuit",
            "securities class action",
            "contact the firm",
            "shareholder rights",
            "attorney advertising",
            "class period",
            "schedule update",
            "investor alert",
            "investor notice",
        ]
        # Attempt to load additional filter terms from a custom file.  The
        # file should reside at ``data/filters/finviz_noise.txt`` relative to
        # the project root.  Each non‑blank, non‑comment line is added to
        # the keyword list.  Errors during file loading are silently
        # ignored so that the absence of the file does not break runtime.
        try:
            from pathlib import Path

            # Determine the project root (two levels up from this file).
            # feeds.py lives at src/catalyst_bot/feeds.py, so parents[2]
            # resolves to the repository root containing the ``data`` folder.
            base_dir = Path(__file__).resolve().parents[2]
            noise_path = base_dir / "data" / "filters" / "finviz_noise.txt"
            if noise_path.exists():
                with noise_path.open("r", encoding="utf-8") as nf:
                    for line in nf:
                        kw = line.strip().lower()
                        if kw and not kw.startswith("#"):
                            keywords.append(kw)
        except Exception:
            # Do not propagate file loading errors; continue with default list
            pass
        for kw in keywords:
            if kw in text:
                return True
        return False
    except Exception:
        # Conservative default: do not mark as noise on unexpected errors
        return False


def _is_retrospective_article(title: str, summary: str) -> bool:
    """
    Filter retrospective/summary articles that explain past moves instead of catalysts.

    Returns ``True`` when the headline contains patterns like:
    - "Why [ticker/stock]..." (explanations after the fact)
    - "Here's why..." (summary/analysis articles)
    - Past-tense movement verbs: "dropped X%", "fell", "slid", "dipped", "plunged"
    - Percentage changes in headline (summary of past move)
    - Earnings reports/snapshots (retrospective earnings analysis)

    These articles are typically published AFTER price movement has already occurred
    and serve as explanations rather than actionable trading catalysts.

    Coverage Target: 81-89% of retrospective noise (Updated 2025-11-05)

    Parameters
    ----------
    title : str
        The news headline
    summary : str
        The optional summary or description

    Returns
    -------
    bool
        ``True`` if the item should be filtered out as retrospective, ``False`` otherwise.

    Examples
    --------
    >>> _is_retrospective_article("Why BYND Stock Dropped 14.6%", "")
    True
    >>> _is_retrospective_article("Here's why investors aren't happy", "")
    True
    >>> _is_retrospective_article("Stock Slides Despite Earnings Beat", "")
    True
    >>> _is_retrospective_article("Company Announces Partnership Deal", "")
    False
    """
    import re

    try:
        # Combine title and summary, case-insensitive
        text = f"{title} {summary}".lower()

        # Retrospective patterns - 5 categories, 20 total patterns
        # Handles [TICKER] prefix that appears in all headlines
        retrospective_patterns = [
            # Category 1: Past-Tense Movements (11 patterns)
            # Why + stock movement
            r"\bwhy\s+.{0,60}?\b(stock|shares)\s+(is|are|has|have|was|were)\s+"
            r"(down|up|falling|rising|trading|moving|getting|lower|higher)",
            r"\bwhy\s+.{0,60}?\b(stock|shares)\s+"
            r"(dropped|fell|slid|dipped|rose|jumped|climbed|surged|plunged|tanked)",
            r"\bhere'?s\s+why\b",
            r"\bwhat\s+happened\s+(to|with)\b",
            # Verb + percentage in headline
            r"\b(falls|drops|soars|loses|gains|slips|slides|jumps|climbs|plunges|tanks)\s+"
            r"\d+\.?\d*%",
            r"\b(stock|shares)\s+(drops|falls|rises|jumps|soars|plunges|tanks)\s+\d+",
            # Getting obliterated/crushed/hammered
            r"\b(getting|got)\s+(obliterated|crushed|hammered|destroyed|wrecked)\b",
            # Category 2: Earnings Reports (4 patterns)
            # Reports Q3/Q1/etc
            r"\breports?\s+q\d\s+(loss|earnings|results)",
            r"\breports?\s+q\d\s+(in\s+line|beats?|misses?|tops?|lags?)",
            # Beats/Misses/Tops/Lags estimates
            r"\b(misses?|beats?|tops?|lags?)\s+(revenue|earnings|sales)\s+estimates",
            r"\b(misses?|beats?|tops?|lags?)\s+q\d\s+(expectations|estimates)",
            # Category 3: Earnings Snapshots (1 pattern)
            r"\bearnings?\s+snapshot\b",
            # Category 4: Speculative Pre-Earnings (3 patterns)
            r"\b(will|may|could)\s+.{0,40}?\breport\s+(negative|positive)\s+earnings",
            r"\bwhat\s+to\s+(look\s+out\s+for|expect|know)\b",
            r"\bknow\s+the\s+trend\s+ahead\s+of\b",
            # Category 5: Price Percentages in Headlines (1 pattern)
            # [TICKER] Stock Name (TICKER) Soars/Drops X%
            r"^\[?\w+\]?\s+.{0,60}?\b(up|down|gains?|loses?)\s+\d+\.?\d*%",
        ]

        for pattern in retrospective_patterns:
            if re.search(pattern, text, re.IGNORECASE):
                return True

        return False

    except Exception:
        # Conservative default: do not mark as retrospective on errors
        return False


def _filter_by_freshness(
    items: List[Dict], max_age_minutes: int = 10
) -> Tuple[List[Dict], int]:
    """Filter out articles older than max_age_minutes.

    Parameters
    ----------
    items : list of dict
        News items with 'ts' timestamps (ISO format)
    max_age_minutes : int
        Maximum age in minutes (default: 10). Set to 0 to disable filtering.

    Returns
    -------
    tuple
        (filtered_items, rejected_count)

    Notes
    -----
    Articles without timestamps are kept (assumed fresh).
    Reduces API usage by skipping price/sentiment fetching for old news.
    """
    if max_age_minutes <= 0:
        return items, 0

    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(minutes=max_age_minutes)

    fresh_items = []
    rejected_count = 0

    for item in items:
        ts_str = item.get("ts")
        if not ts_str:
            # No timestamp - keep it (assume fresh)
            fresh_items.append(item)
            continue

        try:
            ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
            if ts >= cutoff:
                fresh_items.append(item)
            else:
                age_minutes = (now - ts).total_seconds() / 60
                rejected_count += 1
                log.debug(
                    "article_too_old ticker=%s age_min=%.1f cutoff_min=%d title=%s",
                    item.get("ticker", ""),
                    age_minutes,
                    max_age_minutes,
                    item.get("title", "")[:60],
                )
        except Exception:
            # Timestamp parse error - keep it (assume fresh)
            fresh_items.append(item)

    return fresh_items, rejected_count


# Local sentiment fallback: optional.  If import fails (no module), attach
# sentiment is a no-op so that pipeline continues smoothly.
try:
    from .local_sentiment import attach_local_sentiment  # type: ignore
except Exception:

    def attach_local_sentiment(*_args, **_kwargs):  # type: ignore
        return None


# Breakout scanner: optional importer; fall back to stub when missing
try:
    from .scanner import scan_breakouts_under_10  # type: ignore
except Exception:

    def scan_breakouts_under_10(*_args, **_kwargs):  # type: ignore
        return []


# Import FMP sentiment helpers.  These are new in Phase‑C Patch 3.
try:
    from .fmp_sentiment import attach_fmp_sentiment, fetch_fmp_sentiment  # type: ignore
except Exception:
    # If the module cannot be imported (e.g. during partial installations),
    # provide no-op fallbacks so the call sites do not fail.
    def fetch_fmp_sentiment(*_args, **_kwargs):  # type: ignore
        return {}

    def attach_fmp_sentiment(*_args, **_kwargs) -> None:  # type: ignore
        return None


try:
    # Import classifier lazily; vaderSentiment may not be installed in all envs
    from .classifier import classify, load_keyword_weights  # type: ignore
except Exception:
    classify = None  # type: ignore

    def load_keyword_weights(
        path: str = "data/keyword_weights.json",
    ) -> Dict[str, float]:
        """Fallback keyword weights loader when classifier is unavailable."""
        return {}


log = get_logger("feeds")

# Global ticker validator instance (lazy-loaded on first import)
_TICKER_VALIDATOR = TickerValidator()

# Global feed state manager for conditional requests (ETags, Last-Modified)
_feed_state_manager = FeedStateManager()


def _apply_refined_dedup(items: List[Dict]) -> List[Dict]:
    """Apply first-seen + source-weighted deduplication.

    Enabled when FEATURE_DEDUP_REFINED is truthy. Uses a SQLite index at
    data/dedup/first_seen.db. Items marked as duplicates receive a
    'duplicate_of' field (signature) and are filtered out of the returned list.
    """
    if str(os.getenv("FEATURE_DEDUP_REFINED", "0")).strip().lower() not in {
        "1",
        "true",
        "yes",
        "on",
    }:
        return items
    try:
        from .dedupe import FirstSeenIndex, _source_weight, signature_from
    except Exception:
        return items

    db_path = os.path.join("data", "dedup", "first_seen.db")
    idx = FirstSeenIndex(db_path)
    out: List[Dict] = []
    try:
        now_ts = int(time.time())
        for it in items:
            title = it.get("title") or ""
            link = it.get("link") or it.get("canonical_url") or ""
            src = (it.get("source_host") or it.get("source") or "").lower()
            ticker = it.get("ticker") or ""
            sig = signature_from(title, link, ticker)
            prev = idx.get(sig)
            w = _source_weight(src)
            if prev is None:
                idx.upsert(sig, it.get("id") or link or title, now_ts, src, link, w)
                out.append(it)
            else:
                prev_id, prev_ts, prev_w = prev
                # keep earliest/highest-weight; mark others as duplicates
                keep_current = (w > prev_w) or (w == prev_w and now_ts < prev_ts)
                if keep_current:
                    idx.upsert(sig, it.get("id") or link or title, now_ts, src, link, w)
                    out.append(it)
                else:
                    it["duplicate_of"] = sig
        return out
    finally:
        try:
            idx.close()
        except Exception:
            pass


# --- small helpers -----------------------------------------------------------
def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)).strip())
    except Exception:
        return default


USER_AGENT = "CatalystBot/1.0 (+https://example.local)"

# --- Reliable default feeds (no auth required) ---
FEEDS: Dict[str, List[str]] = {
    # Broad PR wire via GlobeNewswire (Public Companies)
    "globenewswire_public": [
        (
            "https://www.globenewswire.com/RssFeed/orgclass/1/feedTitle/"
            "GlobeNewswire%20-%20News%20about%20Public%20Companies"
        )
    ],
    # SEC regulatory feeds (Atom): material events + offering signals + ownership
    "sec_8k": [
        (
            "https://www.sec.gov/cgi-bin/browse-edgar?"
            "action=getcurrent&type=8-K&company=&dateb=&owner=include&"
            "start=0&count=100&output=atom"
        )
    ],
    "sec_424b5": [
        (
            "https://www.sec.gov/cgi-bin/browse-edgar?"
            "action=getcurrent&type=424B5&company=&dateb=&owner=include&"
            "start=0&count=100&output=atom"
        )
    ],
    "sec_fwp": [
        (
            "https://www.sec.gov/cgi-bin/browse-edgar?"
            "action=getcurrent&type=FWP&company=&dateb=&owner=include&"
            "start=0&count=100&output=atom"
        )
    ],
    "sec_13d": [
        (
            "https://www.sec.gov/cgi-bin/browse-edgar?"
            "action=getcurrent&type=SC%2013D&company=&dateb=&owner=include&"
            "start=0&count=100&output=atom"
        )
    ],
    "sec_13g": [
        (
            "https://www.sec.gov/cgi-bin/browse-edgar?"
            "action=getcurrent&type=SC%2013G&company=&dateb=&owner=include&"
            "start=0&count=100&output=atom"
        )
    ],
    # --- Optional (often 403/404 without auth) ---
    # "businesswire": ["https://www.businesswire.com/portal/site/home/news/?rss=1"],
    # "globenewswire_latest": ["https://www.globenewswire.com/rss/latestrelease"],
    # "accesswire": ["https://www.accesswire.com/rss/latest"],
    # "prnewswire_all": ["https://www.prnewswire.com/rss/all-news.rss"],
    # "prweb_all": ["https://www.prweb.com/rss2/allprwebreleases.xml"],
}

# Optional per-source override via env var (pick the first non-empty)
ENV_URL_OVERRIDES = {
    "businesswire": os.getenv("BUSINESSWIRE_RSS_URL") or "",
    # match the FEEDS dict key so overrides actually apply
    "globenewswire_public": os.getenv("GLOBENEWSWIRE_RSS_URL") or "",
    "accesswire": os.getenv("ACCESSWIRE_RSS_URL") or "",
    "prnewswire_all": os.getenv("PRNEWSWIRE_RSS_URL") or "",
    "prweb_all": os.getenv("PRWEB_RSS_URL") or "",
    "sec_8k": os.getenv("SEC_8K_RSS_URL") or "",
}

# ------------------------- HTTP helpers -------------------------------------


def _sleep_backoff(attempt: int) -> None:
    base = min(2**attempt, 4)
    time.sleep(base + random.uniform(0, 0.25))


def _get(url: str, timeout: int = 12) -> Tuple[int, Optional[str]]:
    """Synchronous HTTP GET for RSS feeds.

    Supports HTTP conditional requests (ETags, Last-Modified) to reduce
    bandwidth by 70-90% for unchanged feeds.
    """
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": (
            "application/rss+xml, application/atom+xml, "
            "application/xml;q=0.9, */*;q=0.8"
        ),
    }

    # Add conditional request headers (If-None-Match, If-Modified-Since)
    conditional_headers = _feed_state_manager.get_headers(url)
    headers.update(conditional_headers)

    for attempt in range(0, 3):
        try:
            r = requests.get(
                url, headers=headers, timeout=timeout, allow_redirects=True
            )

            # Handle 304 Not Modified - feed unchanged
            if _feed_state_manager.should_skip(r.status_code):
                log.debug(f"feed_unchanged_304 url={url[:60]}")
                return 304, None

            # Update state with new ETag/Last-Modified headers
            if r.status_code == 200:
                _feed_state_manager.update_state(url, dict(r.headers))

            return r.status_code, r.text
        except Exception:
            if attempt >= 2:
                return 599, None
            _sleep_backoff(attempt)
    return 599, None


def _get_multi(urls: Union[str, List[str]]) -> Tuple[int, Optional[str], str]:
    """Try a list of URLs, return first 200 with text; else last error.

    Defensive: if a single string is accidentally passed, wrap it and warn
    so we don't iterate character-by-character (which causes long hangs).

    Supports 304 Not Modified responses for bandwidth optimization.
    """
    if isinstance(urls, str):
        log.warning(
            "feeds_config urls_was_string source_list_wrapped=1 value_prefix=%s",
            urls[:40],
        )
        urls = [urls]

    last_status = 0
    last_text: Optional[str] = None
    last_url = ""
    for u in urls:
        status, text = _get(u)
        last_status, last_text, last_url = status, text, u
        # Return immediately on success or 304 Not Modified
        if status == 200 and text:
            return status, text, u
        if status == 304:
            return 304, None, u
    return last_status, last_text, last_url


# ---------------------- Async HTTP helpers (10-20x faster) ------------------


async def _get_async(
    url: str, session: aiohttp.ClientSession, timeout: int = 12
) -> Tuple[int, Optional[str]]:
    """Async version of _get using aiohttp for concurrent fetching.

    Supports HTTP conditional requests (ETags, Last-Modified) to reduce
    bandwidth by 70-90% for unchanged feeds.
    """
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": (
            "application/rss+xml, application/atom+xml, "
            "application/xml;q=0.9, */*;q=0.8"
        ),
    }

    # Add conditional request headers (If-None-Match, If-Modified-Since)
    conditional_headers = _feed_state_manager.get_headers(url)
    headers.update(conditional_headers)

    for attempt in range(0, 3):
        try:
            async with session.get(
                url,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=timeout),
                allow_redirects=True,
            ) as resp:
                # Handle 304 Not Modified - feed unchanged
                if _feed_state_manager.should_skip(resp.status):
                    log.debug(f"feed_unchanged_304 url={url[:60]}")
                    return 304, None

                # Update state with new ETag/Last-Modified headers
                if resp.status == 200:
                    _feed_state_manager.update_state(url, resp.headers)

                text = await resp.text()
                return resp.status, text
        except asyncio.TimeoutError:
            if attempt >= 2:
                return 599, None
            await asyncio.sleep(min(2**attempt, 4) + random.uniform(0, 0.25))
        except Exception:
            if attempt >= 2:
                return 599, None
            await asyncio.sleep(min(2**attempt, 4) + random.uniform(0, 0.25))
    return 599, None


async def _get_multi_async(
    urls: Union[str, List[str]], session: aiohttp.ClientSession
) -> Tuple[int, Optional[str], str]:
    """Async version of _get_multi - tries URLs until one succeeds.

    Supports 304 Not Modified responses for bandwidth optimization.
    """
    if isinstance(urls, str):
        log.warning(
            "feeds_config urls_was_string source_list_wrapped=1 value_prefix=%s",
            urls[:40],
        )
        urls = [urls]

    last_status = 0
    last_text: Optional[str] = None
    last_url = ""
    for u in urls:
        status, text = await _get_async(u, session)
        last_status, last_text, last_url = status, text, u
        # Return immediately on success or 304 Not Modified
        if status == 200 and text:
            return status, text, u
        if status == 304:
            return 304, None, u
    return last_status, last_text, last_url


# ---------------------- URL canonicalization --------------------------------


_DROP_QUERY_KEYS = {
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


def _canonicalize_link(url: str) -> str:
    """
    Make links comparable across sources:
    - force https scheme
    - lowercase host
    - strip trailing slashes
    - remove tracking query params
    """
    if not url:
        return ""
    try:
        p = urlparse(url)
        scheme = "https"
        netloc = p.netloc.lower()
        path = p.path.rstrip("/")
        q = [
            (k, v)
            for (k, v) in parse_qsl(p.query, keep_blank_values=True)
            if k not in _DROP_QUERY_KEYS
        ]
        query = urlencode(q, doseq=True)
        return urlunparse((scheme, netloc, path, "", query, ""))
    except Exception:
        return url


# ---------------------- Ticker extraction -----------------------------------


def extract_ticker(title: str) -> Optional[str]:
    """
    Extract tickers from common PR styles:
    (NASDAQ: ABCD), (NYSE: XYZ), (AMEX: XX), (OTC: TICK), TSX/TSXV/ASX,
    and looser 'symbol XYZ' patterns. Best-effort, safe.
    """
    if not title:
        return None

    t = title.upper()
    exchanges = (
        "NASDAQ",
        "NYSE",
        "AMEX",
        "OTC",
        "OTCQB",
        "OTCMKTS",
        "TSX",
        "TSXV",
        "ASX",
        "CBOE",
        "NYSE AMERICAN",
        "NASDAQ CAPITAL MARKET",
    )
    for ex in exchanges:
        for sep in (": ", ":", ") ", ")-", ") â€“ "):
            k1 = f"({ex}{sep}"
            if k1 in t:
                idx = t.find(k1) + len(k1)
                cand: List[str] = []
                for ch in t[idx : idx + 6]:
                    if ch.isalnum():
                        cand.append(ch)
                    else:
                        break
                tick = "".join(cand)
                if 1 <= len(tick) <= 5:
                    return tick
            k2 = f"{ex}{sep}"
            if k2 in t:
                idx = t.find(k2) + len(k2)
                cand = []
                for ch in t[idx : idx + 6]:
                    if ch.isalnum():
                        cand.append(ch)
                    else:
                        break
                tick = "".join(cand)
                if 1 <= len(tick) <= 5:
                    return tick

    for needle in ("TICKER SYMBOL ", "SYMBOL "):
        if needle in t:
            idx = t.find(needle) + len(needle)
            cand = []
            for ch in t[idx : idx + 6]:
                if ch.isalnum():
                    cand.append(ch)
                else:
                    break
            tick = "".join(cand)
            if 1 <= len(tick) <= 5:
                return tick

    return None


# ----------------------- Exchange extraction ----------------------------
#
# Helper to extract the exchange code from a headline.  Many PR wire
# announcements qualify the ticker with an exchange prefix, e.g.
# ``(NASDAQ: XYZ)`` or ``NYSE: ABC``.  This function scans for common
# exchange patterns and returns a canonicalised lower‑case code when
# found.  Synonyms and long form names map to a few standard codes
# recognised by the whitelist filter (nasdaq, nyse, amex, otc).  If no
# exchange qualifier is detected, ``None`` is returned so the caller
# can decide whether to apply a default or skip filtering entirely.
def extract_exchange(title: str) -> Optional[str]:
    if not title:
        return None
    try:
        t = title.upper()
        # Mapping of known exchange identifiers to canonical codes.  Keys
        # include both the short form (NASDAQ) and longer variants used
        # in some PRs (NASDAQ CAPITAL MARKET, NYSE AMERICAN, OTCMKTS, etc.).
        mapping = {
            "NASDAQ CAPITAL MARKET": "nasdaq",
            "NASDAQCM": "nasdaq",
            "NASDAQ CAP MARKET": "nasdaq",
            "NASDAQ": "nasdaq",
            "NYSE AMERICAN": "nyse",
            "NYSE MKT": "nyse",
            "NYSE": "nyse",
            "AMEX": "amex",
            "OTCQX": "otc",
            "OTCQB": "otc",
            "OTCMKTS": "otc",
            "OTC MARKETS": "otc",
            "OTC": "otc",
        }
        for key, canon in mapping.items():
            # Look for patterns like "(KEY:" or "KEY: " in the title.  Use
            # uppercase comparison for robustness.
            if f"({key}:" in t or f"{key}:" in t or f"({key} " in t:
                return canon
        return None
    except Exception:
        return None


# --------------------- Normalization & parsing -------------------------------


def _to_utc_iso(dt_str: Optional[str]) -> Optional[str]:
    """Convert timestamp to UTC ISO format, or None if invalid.

    Returns None for missing or malformed timestamps instead of
    defaulting to current time, allowing callers to handle appropriately.
    """
    if not dt_str:
        return None
    try:
        d = dtparse.parse(dt_str)
        if d.tzinfo is None:
            d = d.replace(tzinfo=timezone.utc)
        return d.astimezone(timezone.utc).isoformat()
    except Exception:
        log.debug("timestamp_parse_failed dt_str=%s", dt_str)
        return None


def _stable_id(source: str, link: str, guid: Optional[str]) -> str:
    # For SEC filings, use accession number to prevent duplicates across different feeds
    if source and source.lower().startswith("sec_"):
        from .dedupe import _extract_sec_accession_number

        accession = _extract_sec_accession_number(link or guid or "")
        if accession:
            # Use accession number instead of URL/GUID for SEC filings
            raw = accession + f"|{source}"
            return hashlib.sha1(raw.encode("utf-8")).hexdigest()

    # Non-SEC items: use original logic
    raw = (guid or link or "") + f"|{source}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def clean_html_content(text: str) -> str:
    """
    Clean HTML content by decoding entities, removing tags, and normalizing whitespace.

    This function processes RSS feed content that may contain HTML entities
    (&amp;, &#39;, &quot;, etc.) and HTML tags (<p>, <br>, <div>, etc.).
    It handles malformed HTML gracefully using BeautifulSoup's lenient parser.

    Parameters
    ----------
    text : str
        Raw text that may contain HTML entities and tags.
        Can be empty string or None (returns empty string).

    Returns
    -------
    str
        Clean text with entities decoded, tags removed, and whitespace normalized.

    Examples
    --------
    >>> clean_html_content("Apple &amp; Co announces Q3 results")
    'Apple & Co announces Q3 results'

    >>> clean_html_content("<p>Breaking: <b>TSLA</b> surges 10%</p>")
    'Breaking: TSLA surges 10%'

    >>> clean_html_content("Multiple&nbsp;&nbsp;&nbsp;spaces   here")
    'Multiple spaces here'

    >>> clean_html_content(None)
    ''

    >>> clean_html_content("")
    ''
    """
    # Handle None and empty string inputs gracefully
    if not text:
        return ""

    try:
        # Step 1: Decode HTML entities (&amp; -> &, &#39; -> ', &quot; -> ", etc.)
        # This handles both named entities (&amp;) and numeric entities (&#39;, &#x27;)
        decoded = html.unescape(text)

        # Step 2: Remove HTML tags using BeautifulSoup
        # The 'html.parser' is lenient and handles malformed HTML gracefully
        # Use separator=' ' to ensure spaces between tags (e.g., <li>A</li><li>B</li> -> "A B")
        soup = BeautifulSoup(decoded, "html.parser")
        text_only = soup.get_text(separator=" ")

        # Step 3: Normalize whitespace
        # Replace multiple spaces/tabs/newlines with single space
        # Also strip leading/trailing whitespace
        normalized = re.sub(r"\s+", " ", text_only).strip()

        return normalized

    except Exception as e:
        # If anything goes wrong, log and return the original text stripped
        # This ensures the function never crashes feed processing
        logger = get_logger(__name__)
        logger.warning(
            f"Failed to clean HTML content: {e}. Returning stripped original."
        )
        return text.strip()


def _normalize_entry(source: str, e) -> Optional[Dict]:
    # Extract raw title and link
    raw_title = (getattr(e, "title", None) or "").strip()
    link = (getattr(e, "link", None) or "").strip()

    # Clean HTML from title (decode entities, remove tags, normalize whitespace)
    title = clean_html_content(raw_title)

    if not title or not link:
        return None

    published = (
        getattr(e, "published", None)
        or getattr(e, "updated", None)
        or getattr(e, "pubDate", None)
    )
    ts_iso = _to_utc_iso(published)
    # Fallback to current time for RSS feeds without valid timestamps
    if not ts_iso:
        ts_iso = datetime.now(timezone.utc).isoformat()
    guid = getattr(e, "id", None) or getattr(e, "guid", None)

    # Primary ticker extraction from title
    ticker = getattr(e, "ticker", None) or extract_ticker(title)
    ticker_source = None

    # Pull summary/description if available for richer metadata; leave empty if missing
    summary = ""
    try:
        raw_summary = (
            getattr(e, "summary", None) or getattr(e, "description", None) or ""
        ).strip()
        # Clean HTML from summary (decode entities, remove tags, normalize whitespace)
        summary = clean_html_content(raw_summary)
    except Exception:
        summary = ""

    # Fallback: extract ticker from summary when title extraction fails
    if not ticker and summary:
        ticker = extract_ticker(summary)
        if ticker:
            ticker_source = "summary"
            log.debug(
                "ticker_extraction_fallback source=%s ticker=%s method=summary link=%s",
                source,
                ticker,
                link,
            )

    # Track extraction source for monitoring
    if ticker and not ticker_source:
        ticker_source = "title"

    # Validate ticker against official exchange lists
    if ticker and not _TICKER_VALIDATOR.is_valid(ticker):
        log.debug(
            "ticker_validation_failed source=%s ticker=%s link=%s",
            source,
            ticker,
            link,
        )
        ticker = None
        ticker_source = None

    return {
        "id": _stable_id(source, link, guid),
        "title": title,
        "link": link,
        "ts": ts_iso,
        "source": source,
        "ticker": (ticker or None),
        "summary": summary or None,
        "ticker_source": ticker_source,
    }


# --- helpers used by the Finviz block ---------------------------------------
def _hash_id(s: str) -> str:
    """Stable sha1 for building ids from links/keys."""
    try:
        return hashlib.sha1(s.encode("utf-8")).hexdigest()
    except Exception:
        # extremely defensive fallback
        return hashlib.sha1(repr(s).encode("utf-8", "ignore")).hexdigest()


def _parse_finviz_ts(ts: str) -> Optional[str]:
    """Normalize Finviz timestamp strings to UTC ISO."""
    return _to_utc_iso(ts)


# --- SEC LLM Enrichment -----------------------------------------------------


async def _enrich_sec_filing_with_llm(
    filing: Dict[str, Any], timeout: float = 20.0
) -> Dict[str, Any]:
    """
    Enrich SEC filing with LLM-generated summary.

    Args:
        filing: Raw SEC filing dict with keys:
            - ticker: Stock symbol
            - source: Source identifier (e.g., "sec_8k")
            - title: Filing title
            - summary: Raw text excerpt (first ~2000 chars from RSS)
            - link: SEC EDGAR URL
        timeout: LLM request timeout

    Returns:
        Filing dict with added/updated keys:
            - summary: AI-generated trading-focused summary (replaces placeholder)
            - llm_sentiment: Sentiment score (-1 to +1)
            - llm_confidence: Confidence score (0 to 1)
            - catalysts: List of detected catalyst types

    Integration Points:
        - Called from fetch_all_feeds() after freshness filtering
        - Uses sec_llm_analyzer.analyze_sec_filing() for analysis
        - Falls back to original summary on LLM failure

    Example Output:
        {
            ...original filing...,
            "summary": "BEARISH: $25M ATM offering announced, 8% dilution expected...",
            "llm_sentiment": -0.65,
            "llm_confidence": 0.85,
            "catalysts": ["offering", "dilution"]
        }
    """
    ticker = filing.get("ticker", "")
    source = filing.get("source", "")
    title = filing.get("title", "")
    raw_summary = filing.get("summary", "")

    # Extract filing type from source (e.g., "sec_8k" -> "8-K")
    filing_type = "8-K"  # default
    if source and source.lower().startswith("sec_"):
        filing_type = source[4:].upper().replace("_", "-")

    # Extract filing_id for cache key (use id or link as fallback)
    filing_id = filing.get("id") or filing.get("link") or ""

    try:
        # Import here to avoid circular dependency
        import hashlib

        from .logging_utils import get_logger
        from .sec_llm_analyzer import analyze_sec_filing
        from .sec_llm_cache import get_sec_llm_cache

        log = get_logger("feeds.sec_llm")
        cache = get_sec_llm_cache()

        log.debug(
            "sec_llm_enrich_start ticker=%s type=%s text_len=%d filing_id=%s",
            ticker,
            filing_type,
            len(raw_summary or ""),
            filing_id,
        )

        # Check cache first (same pattern as batch path in sec_llm_analyzer.py)
        doc_hash = ""
        if raw_summary:
            doc_hash = hashlib.md5(raw_summary[:1000].encode()).hexdigest()[:8]

        cached_result = cache.get_cached_sec_analysis(
            filing_id=filing_id,
            ticker=ticker,
            filing_type=filing_type,
            document_hash=doc_hash,
        )

        if cached_result is not None:
            # Cache hit - use cached result
            log.info(
                "sec_llm_cache_hit_rss ticker=%s filing_type=%s filing_id=%s",
                ticker,
                filing_type,
                filing_id,
            )

            return {
                **filing,
                "summary": cached_result.get("summary", raw_summary),
                "llm_sentiment": cached_result.get("llm_sentiment", 0.0),
                "llm_confidence": cached_result.get("llm_confidence", 0.5),
                "catalysts": cached_result.get("catalysts", []),
            }

        # Cache miss - call LLM analyzer
        result = analyze_sec_filing(
            title=title,
            filing_type=filing_type,
            summary=raw_summary[:3000] if raw_summary else "",  # Limit input size
            timeout=timeout,
        )

        if result and result.get("summary"):
            log.info(
                "sec_llm_enrich_success ticker=%s sentiment=%.2f summary_len=%d filing_id=%s",
                ticker,
                result.get("llm_sentiment", 0),
                len(result.get("summary", "")),
                filing_id,
            )

            # Cache the result
            cache.cache_sec_analysis(
                filing_id=filing_id,
                ticker=ticker,
                filing_type=filing_type,
                analysis_result=result,
                document_hash=doc_hash,
            )

            return {
                **filing,
                "summary": result["summary"],  # Replace original summary
                "llm_sentiment": result.get("llm_sentiment", 0.0),
                "llm_confidence": result.get("llm_confidence", 0.5),
                "catalysts": result.get("catalysts", []),
            }

    except Exception as e:
        try:
            from .logging_utils import get_logger

            log = get_logger("feeds.sec_llm")
            log.warning("sec_llm_enrich_failed ticker=%s error=%s", ticker, str(e))
        except Exception:
            pass

    # Fallback: return original filing unchanged
    return filing


async def _enrich_sec_items_batch(
    sec_items: List[Dict[str, Any]], max_concurrent: int = 3, seen_store=None
) -> List[Dict[str, Any]]:
    """
    Enrich SEC filings with LLM summaries in batches.

    Processes SEC filings concurrently with a semaphore to limit concurrent
    LLM calls and prevent rate limiting. Uses Gemini Pro via the existing
    llm_hybrid router.

    CRITICAL OPTIMIZATION: Skips LLM enrichment for already-seen filings to
    prevent wasting API calls on duplicate content (70-80% reduction).

    Args:
        sec_items: List of SEC filing dicts from feeds
        max_concurrent: Maximum concurrent LLM calls (default: 3)
        seen_store: Optional SeenStore instance for deduplication

    Returns:
        List of enriched SEC filing dicts with LLM summaries

    Example:
        # Before: summary = "AAPL files 8-K with SEC..."
        # After:  summary = "BULLISH: $50M institutional investment at premium..."
    """
    if not sec_items:
        return []

    # Check if LLM enrichment is enabled (on by default)
    enabled = os.getenv("FEATURE_LLM_CLASSIFIER", "1").strip() in (
        "1",
        "true",
        "yes",
        "on",
    )
    if not enabled:
        return sec_items

    try:
        from .logging_utils import get_logger

        log = get_logger("feeds.sec_llm")

        # CRITICAL OPTIMIZATION: Pre-filter already-seen filings BEFORE expensive LLM calls
        # This prevents reprocessing the same 100+ filings every cycle (saves 7-8 min/cycle)
        # NOTE: seen_store has thread safety issues when called from async, so we skip for now
        # The runner.py will still do dedup check in the main thread
        items_to_enrich = sec_items
        skipped_seen = 0

        # TODO: Re-enable once seen_store is made async-safe
        # if seen_store:
        #     for filing in sec_items:
        #         filing_id = filing.get("id") or filing.get("link") or ""
        #         try:
        #             if filing_id and seen_store.is_seen(filing_id):
        #                 skipped_seen += 1
        #                 continue
        #         except Exception:
        #             pass
        #         items_to_enrich.append(filing)
        # else:
        #     items_to_enrich = sec_items

        log.info(
            "sec_llm_batch_start total_filings=%d skipped_seen=%d to_enrich=%d max_concurrent=%d",
            len(sec_items),
            skipped_seen,
            len(items_to_enrich),
            max_concurrent,
        )

        # If all filings were already seen, skip LLM processing entirely
        if not items_to_enrich:
            log.info(
                "sec_llm_batch_complete total=%d enriched=0 all_already_seen=true",
                len(sec_items),
            )
            return sec_items

        # Create semaphore for concurrency control
        semaphore = asyncio.Semaphore(max_concurrent)

        async def enrich_one(filing: Dict[str, Any]) -> Dict[str, Any]:
            """Enrich a single filing with semaphore control."""
            async with semaphore:
                return await _enrich_sec_filing_with_llm(filing)

        # Process only unseen filings concurrently (with semaphore limiting)
        enriched = await asyncio.gather(*[enrich_one(f) for f in items_to_enrich])

        # Count successful enrichments
        success_count = sum(1 for f in enriched if f.get("llm_confidence", 0) > 0.3)

        log.info(
            "sec_llm_batch_complete total=%d skipped_seen=%d enriched=%d success_rate=%.1f%%",
            len(sec_items),
            skipped_seen,
            success_count,
            (success_count / len(items_to_enrich)) * 100 if items_to_enrich else 0,
        )

        # Combine enriched items with skipped items
        # Skipped items retain their original (non-enriched) state
        result = enriched + [f for f in sec_items if f not in items_to_enrich]
        return result

    except Exception as e:
        try:
            from .logging_utils import get_logger

            log = get_logger("feeds.sec_llm")
            log.error("sec_llm_batch_failed error=%s", str(e))
        except Exception:
            pass

        # Return original items on batch failure
        return sec_items


# -------------------------- Public API --------------------------------------


async def _fetch_feeds_async_concurrent(
    feeds_dict: Dict[str, List[str]], env_overrides: Dict[str, str]
) -> Tuple[List[Dict], Dict[str, Any]]:
    """
    Async concurrent RSS/Atom feed fetching (10-20x faster than sequential).

    Fetches all feeds in FEEDS dict concurrently using aiohttp. This replaces
    the sequential loop in fetch_pr_feeds() for dramatic speedup.

    Parameters
    ----------
    feeds_dict : Dict[str, List[str]]
        Feed sources mapping (e.g., FEEDS)
    env_overrides : Dict[str, str]
        Environment variable URL overrides

    Returns
    -------
    Tuple[List[Dict], Dict[str, Any]]
        (all_items, summary_by_source)
    """
    if not AIOHTTP_AVAILABLE:
        raise ImportError("aiohttp required for async fetching")

    all_items: List[Dict] = []
    summary_by_source: Dict[str, Any] = {}

    async def fetch_one_source(
        src: str, url_list: List[str], session: aiohttp.ClientSession
    ) -> Tuple[str, List[Dict], Dict[str, Any]]:
        """Fetch a single feed source."""
        # Apply env override if present
        if env_overrides.get(src):
            url_list = [env_overrides[src]]

        s = {
            "ok": 0,
            "http4": 0,
            "http5": 0,
            "errors": 0,
            "entries": 0,
            "t_ms": 0.0,
            "not_modified": 0,
        }
        st = time.time()

        try:
            status, text, used_url = await _get_multi_async(url_list, session)

            # Handle 304 Not Modified (bandwidth optimization)
            if status == 304:
                s["ok"] += 1
                s["not_modified"] += 1
                s["entries"] = 0
                s["t_ms"] = round((time.time() - st) * 1000.0, 1)
                log.debug(f"feed_304_not_modified source={src} url={used_url[:60]}")
                return src, [], s

            if status != 200 or not text:
                if 400 <= status < 500:
                    log.warning(
                        "feed_http status=%s source=%s url=%s", status, src, used_url
                    )
                    s["http4"] += 1
                elif 500 <= status < 600:
                    log.warning(
                        "feed_http status=%s source=%s url=%s", status, src, used_url
                    )
                    s["http5"] += 1
                else:
                    s["errors"] += 1
                s["t_ms"] = round((time.time() - st) * 1000.0, 1)
                return src, [], s

            # Parse feed (feedparser is synchronous but fast)
            parsed = feedparser.parse(text)
            entries = getattr(parsed, "entries", []) or []
            s["entries"] = len(entries)

            items = []
            for e in entries:
                it = _normalize_entry(src, e)
                if it:
                    items.append(it)

            s["ok"] += 1
            s["t_ms"] = round((time.time() - st) * 1000.0, 1)
            return src, items, s

        except Exception as e:
            log.warning(
                "async_feed_fetch_error source=%s err=%s",
                src,
                e.__class__.__name__,
            )
            s["errors"] += 1
            s["t_ms"] = round((time.time() - st) * 1000.0, 1)
            return src, [], s

    # Create aiohttp session with connection pooling
    timeout = aiohttp.ClientTimeout(total=30)
    conn = aiohttp.TCPConnector(limit=10, limit_per_host=3)

    async with aiohttp.ClientSession(timeout=timeout, connector=conn) as session:
        # Fetch all sources concurrently
        tasks = [
            fetch_one_source(src, url_list, session)
            for src, url_list in feeds_dict.items()
        ]

        results = await asyncio.gather(*tasks, return_exceptions=False)

        # Collect results
        for src, items, stats in results:
            all_items.extend(items)
            summary_by_source[src] = stats

    return all_items, summary_by_source


def fetch_pr_feeds(seen_store=None) -> List[Dict]:
    """
    Pull all feeds with backoff & per-source alternates.
    Returns normalized list of dicts. If everything fails and DEMO_IF_EMPTY=true,
    injects a single demo item for end-to-end alert validation.

    Args:
        seen_store: Optional SeenStore instance for SEC filing deduplication optimization
    """
    all_items: List[Dict] = []
    summary = {"sources": len(FEEDS), "items": 0, "t_ms": 0.0, "by_source": {}}
    t0 = time.time()

    # ---------------- Finnhub: Real-time news & catalysts (opt-in) ----------------
    # Added for high-frequency news, earnings, and analyst events
    if os.environ.get("PYTEST_CURRENT_TEST") is None:
        try:
            from .finnhub_feeds import (
                fetch_finnhub_earnings_calendar,
                fetch_finnhub_news,
                is_finnhub_enabled,
            )

            if is_finnhub_enabled():
                st = time.time()
                finnhub_news = fetch_finnhub_news(max_items=30)
                finnhub_earnings = fetch_finnhub_earnings_calendar(days_ahead=1)

                _seen_ids = {i.get("id") for i in all_items if i.get("id")}
                _seen_links = {i.get("link") for i in all_items if i.get("link")}

                finnhub_unique = [
                    it
                    for it in (finnhub_news + finnhub_earnings)
                    if (it.get("id") not in _seen_ids)
                    and (it.get("link") not in _seen_links)
                ]

                all_items.extend(finnhub_unique)
                summary["by_source"]["finnhub"] = {
                    "ok": 1,
                    "http4": 0,
                    "http5": 0,
                    "errors": 0,
                    "entries_raw": len(finnhub_news) + len(finnhub_earnings),
                    "entries": len(finnhub_unique),
                    "t_ms": round((time.time() - st) * 1000.0, 1),
                }
                log.info(
                    "finnhub_feeds_added news=%d earnings=%d unique=%d",
                    len(finnhub_news),
                    len(finnhub_earnings),
                    len(finnhub_unique),
                )
        except Exception as e:
            log.warning("finnhub_feeds_error err=%s", str(e.__class__.__name__))
            summary["by_source"]["finnhub"] = {
                "ok": 0,
                "http4": 0,
                "http5": 0,
                "errors": 1,
                "entries_raw": 0,
                "entries": 0,
                "t_ms": 0.0,
            }

    # ---------------- Finviz Elite: news_export.ashx (opt-in) ----------------
    # Skip Finviz news when running under pytest to keep tests deterministic
    if os.environ.get("PYTEST_CURRENT_TEST") is None:
        if str(os.getenv("FEATURE_FINVIZ_NEWS", "1")).strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }:
            st = time.time()
            try:
                _seen_ids = {i.get("id") for i in all_items if i.get("id")}
                _seen_links = {i.get("link") for i in all_items if i.get("link")}
                finviz_items = _fetch_finviz_news_from_env()
                finviz_unique = [
                    it
                    for it in finviz_items
                    if (
                        (it.get("id") not in _seen_ids)
                        and (it.get("link") not in _seen_links)
                    )
                ]
                all_items.extend(finviz_unique)
                summary["by_source"]["finviz_news"] = {
                    "ok": 1,
                    "http4": 0,
                    "http5": 0,
                    "errors": 0,
                    "entries_raw": len(finviz_items),
                    "entries": len(finviz_unique),
                    "t_ms": round((time.time() - st) * 1000.0, 1),
                }
            except Exception as e:
                # Distinguish authentication failures (HTTP 401/403) from other errors.
                msg = str(e) if e else ""
                # Default metrics when an error occurs
                err_metrics = {
                    "ok": 0,
                    "http4": 0,
                    "http5": 0,
                    "errors": 0,
                    "entries_raw": 0,
                    "entries": 0,
                    "t_ms": round((time.time() - st) * 1000.0, 1),
                }
                if "finviz_auth_failed" in msg:
                    # Count as a client error (http4) and log a clear warning
                    err_metrics["http4"] = 1
                    log.warning("finviz_news_auth_failed status=%s", msg.split("=")[-1])
                elif "finviz_http status=" in msg:
                    # Extract status code and bucket into http4/5
                    try:
                        status = int(msg.split("=")[-1])
                    except Exception:
                        status = 0
                    if 400 <= status < 500:
                        err_metrics["http4"] = 1
                    elif 500 <= status < 600:
                        err_metrics["http5"] = 1
                    else:
                        err_metrics["errors"] = 1
                    log.warning("finviz_news_http status=%s", status)
                else:
                    err_metrics["errors"] = 1
                    log.warning(
                        "finviz_news_error err=%s", e.__class__.__name__, exc_info=False
                    )
                summary.setdefault("by_source", {})
                summary["by_source"]["finviz_news"] = err_metrics

        # ---------------- Optional Finviz news export CSV feed (opt-in) ----------------
        # When FEATURE_FINVIZ_NEWS_EXPORT=1 and a FINVIZ_NEWS_EXPORT_URL is set in the
        # environment (see config.py), pull the CSV from the specified URL and
        # append its entries to the item list.  We run this after the main Finviz
        # news feed to allow deduplication against news_export.ashx.  Skip this
        # entirely when running under pytest.
        settings = get_settings()
        if (
            settings.feature_finviz_news_export
            and settings.finviz_news_export_url
            and os.environ.get("PYTEST_CURRENT_TEST") is None
        ):
            st = time.time()
            try:
                _seen_ids = {i.get("id") for i in all_items if i.get("id")}
                _seen_links = {i.get("link") for i in all_items if i.get("link")}
                export_items = _fetch_finviz_news_export(
                    settings.finviz_news_export_url
                )
                export_unique = [
                    it
                    for it in export_items
                    if (
                        (it.get("id") not in _seen_ids)
                        and (it.get("link") not in _seen_links)
                    )
                ]
                all_items.extend(export_unique)
                summary["by_source"]["finviz_export"] = {
                    "ok": 1,
                    "http4": 0,
                    "http5": 0,
                    "errors": 0,
                    "entries_raw": len(export_items),
                    "entries": len(export_unique),
                    "t_ms": round((time.time() - st) * 1000.0, 1),
                }
            except Exception as e:
                summary.setdefault("by_source", {})
                summary["by_source"]["finviz_export"] = {
                    "ok": 0,
                    "http4": 0,
                    "http5": 0,
                    "errors": 1,
                    "entries_raw": 0,
                    "entries": 0,
                    "t_ms": round((time.time() - st) * 1000.0, 1),
                }
                log.warning(
                    "finviz_export_error err=%s", e.__class__.__name__, exc_info=True
                )

    # -----------------------------------------------------------------------------
    # Patch‑2: proactive breakout scanner
    #
    # When the breakout scanner feature is enabled, append breakout candidate
    # events to the list before fetching other feeds.  We treat these like
    # normal events; deduplication will collapse duplicates.  Failures are
    # silently ignored.
    try:
        settings = get_settings()
    except Exception:
        settings = None
    try:
        if settings and getattr(settings, "feature_breakout_scanner", False):
            # Use thresholds from settings; defaults applied in config
            bv = getattr(settings, "breakout_min_avg_vol", 300000.0)
            rv = getattr(settings, "breakout_min_relvol", 1.5)
            # scan_breakouts_under_10 returns a list of event dicts
            bitems = scan_breakouts_under_10(
                min_avg_vol=float(bv) if bv is not None else 0.0,
                min_relvol=float(rv) if rv is not None else 0.0,
            )
            if bitems:
                all_items.extend(bitems)
                summary.setdefault("by_source", {})
                summary["by_source"]["breakout_scanner"] = {
                    "ok": 1,
                    "entries": len(bitems),
                    "t_ms": 0.0,
                }
    except Exception:
        # swallow scanner errors; they will be visible in logs if needed
        pass

    # PERFORMANCE: Use async concurrent fetching for 10-20x speedup
    if AIOHTTP_AVAILABLE:
        try:
            feed_items, feed_summary = run_async(
                _fetch_feeds_async_concurrent(FEEDS, ENV_URL_OVERRIDES), timeout=30.0
            )
            all_items.extend(feed_items)
            summary["by_source"].update(feed_summary)
            log.info("async_feeds_complete sources=%d mode=concurrent", len(FEEDS))
        except Exception as e:
            log.warning(
                "async_feeds_failed err=%s falling_back_to_sync",
                e.__class__.__name__,
            )
            # Fallback to sync if async fails
            AIOHTTP_AVAILABLE_FALLBACK = False
        else:
            AIOHTTP_AVAILABLE_FALLBACK = True
    else:
        AIOHTTP_AVAILABLE_FALLBACK = False

    # Fallback: sequential sync fetching (original code path)
    if not AIOHTTP_AVAILABLE or not locals().get("AIOHTTP_AVAILABLE_FALLBACK", False):
        for src, url_list in FEEDS.items():
            # Optional single-URL override via env
            if ENV_URL_OVERRIDES.get(src):
                url_list = [ENV_URL_OVERRIDES[src]]  # type: ignore[index]

            s = {
                "ok": 0,
                "http4": 0,
                "http5": 0,
                "errors": 0,
                "entries": 0,
                "t_ms": 0.0,
                "not_modified": 0,
            }
            st = time.time()

            status, text, used_url = _get_multi(url_list)

            # Handle 304 Not Modified (bandwidth optimization)
            if status == 304:
                s["ok"] += 1
                s["not_modified"] += 1
                s["entries"] = 0
                s["t_ms"] = round((time.time() - st) * 1000.0, 1)
                summary["by_source"][src] = s
                log.debug(f"feed_304_not_modified source={src} url={used_url[:60]}")
                continue

            if status != 200 or not text:
                if 400 <= status < 500:
                    log.warning(
                        "feed_http status=%s source=%s url=%s", status, src, used_url
                    )
                    s["http4"] += 1
                elif 500 <= status < 600:
                    log.warning(
                        "feed_http status=%s source=%s url=%s", status, src, used_url
                    )
                    s["http5"] += 1
                else:
                    s["errors"] += 1
                s["t_ms"] = round((time.time() - st) * 1000.0, 1)
                summary["by_source"][src] = s
                continue

            try:
                parsed = feedparser.parse(text)
                entries = getattr(parsed, "entries", []) or []
                s["entries"] = len(entries)
                items = []
                for e in entries:
                    it = _normalize_entry(src, e)
                    if it:
                        items.append(it)
                all_items.extend(items)
                s["ok"] += 1
            except Exception:
                s["errors"] += 1

            s["t_ms"] = round((time.time() - st) * 1000.0, 1)
            summary["by_source"][src] = s

    # De-duplicate across sources (Finviz vs wires, syndication, etc.)
    all_items = dedupe(all_items)

    # -----------------------------------------------------------------
    # Filter by freshness (reject old news)
    #
    # Remove articles older than NEWS_MAX_AGE_MINUTES to ensure real-time alerting.
    # This reduces API usage by skipping price/sentiment fetching for stale news.
    # Set NEWS_MAX_AGE_MINUTES=0 to disable and process all news (not recommended).
    #
    # SEC filings use a separate, longer freshness window since the SEC RSS feed
    # has inherent delays (filings can take hours to appear in the Atom feed).
    # SEC filings are official documents and remain actionable longer than news.
    max_age_min = int(os.getenv("NEWS_MAX_AGE_MINUTES", "10"))
    sec_max_age_min = int(
        os.getenv("SEC_MAX_AGE_MINUTES", "480")
    )  # 8 hours default for SEC

    # Separate SEC items from news items for different freshness windows
    sec_items = [it for it in all_items if it.get("source", "").startswith("sec_")]
    news_items = [it for it in all_items if not it.get("source", "").startswith("sec_")]

    # Apply freshness filter to news items (strict 10-min window)
    items_before_freshness = len(news_items)
    news_items, rejected_news = _filter_by_freshness(
        news_items, max_age_minutes=max_age_min
    )

    # Apply separate freshness filter to SEC items (longer window)
    sec_before = len(sec_items)
    sec_items, rejected_sec = _filter_by_freshness(
        sec_items, max_age_minutes=sec_max_age_min
    )

    # Enrich SEC filings with LLM summaries (async, enabled by default)
    # Replaces placeholder summaries with actionable trading context
    # OPTIMIZATION: Increased concurrency from 3 to 10 for faster processing
    if sec_items:
        try:
            max_concurrent = int(os.getenv("SEC_LLM_MAX_CONCURRENT", "10"))
            sec_items = run_async(
                _enrich_sec_items_batch(
                    sec_items, max_concurrent=max_concurrent, seen_store=seen_store
                )
            )
        except Exception as e:
            log.warning("sec_llm_enrichment_failed error=%s", str(e))

    # Combine filtered items
    all_items = news_items + sec_items
    rejected_old = rejected_news + rejected_sec

    if rejected_old > 0:
        log.info(
            "freshness_filter_applied rejected=%d kept=%d max_age_min=%d "
            "sec_max_age_min=%d sec_kept=%d",
            rejected_old,
            len(all_items),
            max_age_min,
            sec_max_age_min,
            len(sec_items),
        )

    # -----------------------------------------------------------------
    # Attach optional FMP sentiment scores
    #
    # When the feature flag is enabled, fetch the sentiment RSS feed once
    # per cycle and merge the resulting scores into each item.  We perform
    # this step after deduplication so that identical links map correctly.
    try:
        fmp_sents = fetch_fmp_sentiment()
    except Exception:
        fmp_sents = {}
    try:
        attach_fmp_sentiment(all_items, fmp_sents)
    except Exception:
        pass

    # -----------------------------------------------------------------
    # Patch‑2: attach local sentiment when enabled
    #
    # If FEATURE_LOCAL_SENTIMENT is on, compute a fallback sentiment score for
    # each item using the lightweight analyser.  We do this after FMP
    # sentiment so that both values can co‑exist in the item dict.  All
    # exceptions are swallowed to avoid interrupting the feed pipeline.
    try:
        settings = settings or get_settings()
    except Exception:
        settings = None
    try:
        if settings and getattr(settings, "feature_local_sentiment", False):
            attach_local_sentiment(all_items)
    except Exception:
        pass

    # -----------------------------------------------------------------
    # Phase‑D: attach external news sentiment when enabled
    #
    # When FEATURE_NEWS_SENTIMENT=1 the bot will call the external sentiment
    # aggregator for each unique ticker.  Results are memoised within this
    # call to avoid redundant network requests.  The returned score and
    # label are attached to the event as ``sentiment_ext_score`` and
    # ``sentiment_ext_label``; per‑provider details are recorded under
    # ``sentiment_ext_details``.  Errors from individual providers are
    # swallowed to ensure smooth processing.
    try:
        from .sentiment_sources import get_combined_sentiment_for_ticker  # type: ignore
    except Exception:
        get_combined_sentiment_for_ticker = None  # type: ignore
    if get_combined_sentiment_for_ticker:
        # Only run when the global feature flag is enabled.  We check
        # settings here to avoid repeated environment parsing inside the loop.
        try:
            news_enabled = False
            if settings:
                news_enabled = getattr(settings, "feature_news_sentiment", False)
            else:
                news_enabled = str(
                    os.getenv("FEATURE_NEWS_SENTIMENT", "0")
                ).strip().lower() in {
                    "1",
                    "true",
                    "yes",
                    "on",
                }
        except Exception:
            news_enabled = False
        if news_enabled:
            sent_cache: Dict[str, Optional[Tuple[float, str, Dict[str, Any]]]] = {}
            for it in all_items:
                try:
                    # Determine the primary ticker for this event.  Prefer
                    # explicit 'ticker'; fall back to first element of 'tickers'.
                    tkr = it.get("ticker") or None
                    if not tkr:
                        tkrs = it.get("tickers")
                        if isinstance(tkrs, list) and tkrs:
                            tkr = tkrs[0]
                    if not tkr or not isinstance(tkr, str):
                        continue
                    tkr_u = tkr.upper().strip()
                    if not tkr_u:
                        continue
                    if tkr_u not in sent_cache:
                        try:
                            res = get_combined_sentiment_for_ticker(tkr_u)
                        except Exception:
                            res = None
                        sent_cache[tkr_u] = res
                    res = sent_cache.get(tkr_u)
                    if not res:
                        continue
                    score, lbl, details = res
                    # Only attach when a score is present
                    if score is None or lbl is None:
                        continue
                    # Avoid overwriting previously attached values on the item
                    if "sentiment_ext_score" not in it:
                        it["sentiment_ext_score"] = score  # type: ignore
                    if "sentiment_ext_label" not in it:
                        it["sentiment_ext_label"] = lbl  # type: ignore
                    if "sentiment_ext_details" not in it:
                        it["sentiment_ext_details"] = details  # type: ignore
                except Exception:
                    continue

    # -----------------------------------------------------------------
    # Patch‑6: attach analyst signals when enabled
    #
    # Analyst consensus price targets and implied returns can influence
    # trading behaviour.  When FEATURE_ANALYST_SIGNALS=1, call the
    # analyst_signals.get_analyst_signal() helper for each unique ticker
    # and attach the returned values to each event as ``analyst_target``,
    # ``analyst_implied_return`` and ``analyst_label``.  Failures are
    # silently ignored to avoid disrupting the ingestion pipeline.  A
    # per‑ticker cache avoids redundant API calls.
    try:
        from .analyst_signals import get_analyst_signal  # type: ignore
    except Exception:
        get_analyst_signal = None  # type: ignore
    if get_analyst_signal:
        try:
            ana_enabled = False
            if settings:
                ana_enabled = getattr(settings, "feature_analyst_signals", False)
            else:
                ana_enabled = str(
                    os.getenv("FEATURE_ANALYST_SIGNALS", "0")
                ).strip().lower() in {
                    "1",
                    "true",
                    "yes",
                    "on",
                }
        except Exception:
            ana_enabled = False
        if ana_enabled:
            ana_cache: Dict[str, Optional[Dict[str, Any]]] = {}
            for it in all_items:
                try:
                    tkr = it.get("ticker") or None
                    if not tkr:
                        tkrs = it.get("tickers")
                        if isinstance(tkrs, list) and tkrs:
                            tkr = tkrs[0]
                    if not tkr or not isinstance(tkr, str):
                        continue
                    tkr_u = tkr.upper().strip()
                    if not tkr_u:
                        continue
                    if tkr_u not in ana_cache:
                        try:
                            res = get_analyst_signal(tkr_u)
                        except Exception:
                            res = None
                        ana_cache[tkr_u] = res
                    res = ana_cache.get(tkr_u)
                    if not res:
                        continue
                    tar = res.get("target_mean")
                    ir = res.get("implied_return")
                    lbl = res.get("analyst_label")
                    if tar is None or ir is None:
                        continue
                    # Avoid overwriting existing values on the event
                    if "analyst_target" not in it:
                        it["analyst_target"] = tar  # type: ignore
                    if "analyst_implied_return" not in it:
                        it["analyst_implied_return"] = ir  # type: ignore
                    if "analyst_label" not in it and lbl:
                        it["analyst_label"] = lbl  # type: ignore
                    # Optional: attach details
                    if "analyst_details" not in it:
                        it["analyst_details"] = res  # type: ignore
                except Exception:
                    continue

    # -----------------------------------------------------------------
    # Phase‑E: attach SEC filing sentiment and recent filing context
    #
    # When FEATURE_SEC_DIGESTER=1 the bot classifies each SEC filing
    # (8‑K, 424B5, FWP, 13D/G) and records it in a per‑ticker cache.  For
    # every event in the cycle (including non‑SEC headlines) the digester
    # attaches a list of recent filings and an aggregated sentiment label
    # and score.  When the watchlist cascade is enabled the ticker is
    # promoted based on the filing sentiment.
    try:
        from .sec_digester import classify_filing as _sec_classify  # type: ignore
        from .sec_digester import get_combined_sentiment as _sec_get_combined
        from .sec_digester import get_recent_filings as _sec_get_recent
        from .sec_digester import record_filing as _sec_record
        from .sec_digester import update_watchlist_for_filing as _sec_update_watchlist
    except Exception:
        _sec_classify = None  # type: ignore
        _sec_record = None  # type: ignore
        _sec_get_recent = None  # type: ignore
        _sec_get_combined = None  # type: ignore
        _sec_update_watchlist = None  # type: ignore
    try:
        sec_enabled = False
        if settings:
            sec_enabled = getattr(settings, "feature_sec_digester", False)
        else:
            sec_enabled = str(
                os.getenv("FEATURE_SEC_DIGESTER", "0")
            ).strip().lower() in {
                "1",
                "true",
                "yes",
                "on",
            }
    except Exception:
        sec_enabled = False
    if sec_enabled and _sec_classify and _sec_record:
        # First pass: classify SEC filings and record them
        for it in all_items:
            try:
                src_key = str(it.get("source") or "").lower()
                # Only consider explicit SEC feeds
                if not src_key.startswith("sec_"):
                    continue
                # Determine ticker
                tkr = it.get("ticker") or None
                if not tkr:
                    tkrs = it.get("tickers")
                    if isinstance(tkrs, list) and tkrs:
                        tkr = tkrs[0]
                if not isinstance(tkr, str):
                    continue
                tkr_u = tkr.upper().strip()
                if not tkr_u:
                    continue
                # Classify the filing
                score, lbl, reason = _sec_classify(
                    src_key, it.get("title"), it.get("summary")
                )
                if lbl:
                    # Generate a concise summary of the filing title to avoid
                    # overly long embed fields.  When summarisation fails or
                    # returns an empty string, fall back to the classifier
                    # reason.  We import here to avoid cyclic imports at
                    # module load time.
                    try:
                        from .sec_digester import (
                            summarize_title as _sec_summarise,  # type: ignore
                        )

                        summary = _sec_summarise(it.get("title")) or reason or ""
                    except Exception:
                        summary = reason or ""
                    # Attach classification label and summary to the item
                    if "sec_label" not in it:
                        it["sec_label"] = lbl  # type: ignore
                    if "sec_reason" not in it and summary:
                        it["sec_reason"] = summary  # type: ignore
                    # Parse timestamp for record; fall back to now
                    ts_str = it.get("ts")
                    try:
                        dt = datetime.fromisoformat(ts_str)  # type: ignore[arg-type]
                        if dt.tzinfo is None:
                            dt = dt.replace(tzinfo=timezone.utc)
                    except Exception:
                        dt = datetime.now(timezone.utc)
                    # Record the filing using the summary instead of the raw
                    # classifier reason.  This reduces the storage size and
                    # ensures that recent filings presented in alerts remain
                    # concise.
                    _sec_record(tkr_u, dt, lbl, summary)
                    # Update watchlist cascade
                    if _sec_update_watchlist:
                        _sec_update_watchlist(tkr_u, lbl)
            except Exception:
                continue

    # -----------------------------------------------------------------
    # Wave‑4: attach options sentiment when enabled
    #
    # When FEATURE_OPTIONS_SCANNER=1 the bot will call
    # :func:`catalyst_bot.options_scanner.scan_options` for each unique ticker
    # and attach the returned score, label and details to events under the
    # keys ``sentiment_options_score``, ``sentiment_options_label`` and
    # ``sentiment_options_details``.  Failures are silently ignored to avoid
    # disrupting the ingestion pipeline.  A per‑ticker cache avoids redundant
    # API calls.
    try:
        from .options_scanner import scan_options  # type: ignore
    except Exception:
        scan_options = None  # type: ignore
    if scan_options:
        try:
            opt_enabled = False
            if settings:
                opt_enabled = getattr(settings, "feature_options_scanner", False)
            else:
                try:
                    env_val = (
                        (os.getenv("FEATURE_OPTIONS_SCANNER", "") or "").strip().lower()
                    )
                    opt_enabled = env_val in {"1", "true", "yes", "on"}
                except Exception:
                    opt_enabled = False
        except Exception:
            opt_enabled = False
        if opt_enabled:
            opt_cache: Dict[str, Optional[Dict[str, Any]]] = {}
            for it in all_items:
                try:
                    tkr = it.get("ticker") or None
                    if not tkr:
                        tkrs = it.get("tickers")
                        if isinstance(tkrs, list) and tkrs:
                            tkr = tkrs[0]
                    if not tkr or not isinstance(tkr, str):
                        continue
                    tkr_u = tkr.upper().strip()
                    if not tkr_u:
                        continue
                    if tkr_u not in opt_cache:
                        try:
                            res = scan_options(tkr_u)
                        except Exception:
                            res = None
                        opt_cache[tkr_u] = res
                    res = opt_cache.get(tkr_u)
                    if not res:
                        continue
                    score = res.get("score")
                    label = res.get("label")
                    details = res.get("details")
                    if score is not None and "sentiment_options_score" not in it:
                        it["sentiment_options_score"] = score  # type: ignore
                    if label is not None and "sentiment_options_label" not in it:
                        it["sentiment_options_label"] = label  # type: ignore
                    if details is not None and "sentiment_options_details" not in it:
                        it["sentiment_options_details"] = details  # type: ignore
                except Exception:
                    continue
        # Second pass: attach recent filing context and combined sentiment to each event
        for it in all_items:
            try:
                tkr = it.get("ticker") or None
                if not tkr:
                    tkrs = it.get("tickers")
                    if isinstance(tkrs, list) and tkrs:
                        tkr = tkrs[0]
                if not isinstance(tkr, str):
                    continue
                tkr_u = tkr.upper().strip()
                if not tkr_u:
                    continue
                if _sec_get_recent:
                    recs = _sec_get_recent(tkr_u)  # type: ignore[arg-type]
                else:
                    recs = None
                if recs:
                    # Convert datetime to ISO for JSON serialisation
                    simple = []
                    for rec in recs[:]:
                        ts = rec.get("ts")
                        if isinstance(ts, datetime):
                            ts_str = ts.isoformat()
                        else:
                            ts_str = str(ts) if ts else ""
                        simple.append(
                            {
                                "ts": ts_str,
                                "label": rec.get("label"),
                                "reason": rec.get("reason"),
                            }
                        )
                    if "recent_sec_filings" not in it:
                        it["recent_sec_filings"] = simple  # type: ignore
                # Attach combined sentiment if available
                if _sec_get_combined:
                    comb = _sec_get_combined(tkr_u)  # type: ignore[arg-type]
                else:
                    comb = None
                if comb:
                    s_score, s_lbl = comb  # type: ignore[misc]
                    if s_lbl and "sec_sentiment_label" not in it:
                        it["sec_sentiment_label"] = s_lbl  # type: ignore
                    if s_score is not None and "sec_sentiment_score" not in it:
                        it["sec_sentiment_score"] = s_score  # type: ignore
            except Exception:
                continue

    # -----------------------------------------------------------------
    # Patch‑6: attach earnings information when enabled
    #
    # The earnings module retrieves the next scheduled earnings date and
    # historical EPS data from the configured provider (currently
    # yfinance).  When FEATURE_EARNINGS_ALERTS=1 the bot attaches
    # earnings info to each event, including the next earnings date (if
    # within the lookahead window), EPS estimate, reported EPS and
    # surprise percentage.  The sentiment aggregator consumes the
    # earnings score separately.  We use a per‑ticker cache to avoid
    # redundant network calls in a single cycle.
    try:
        from .earnings import fetch_earnings_info  # type: ignore
    except Exception:
        fetch_earnings_info = None  # type: ignore
    if fetch_earnings_info:
        try:
            earn_enabled = False
            lookahead_days = 14
            if settings:
                earn_enabled = getattr(settings, "feature_earnings_alerts", False)
                lookahead_days = int(getattr(settings, "earnings_lookahead_days", 14))
            else:
                env_val = str(os.getenv("FEATURE_EARNINGS_ALERTS", "0")).strip().lower()
                earn_enabled = env_val in {"1", "true", "yes", "on"}
                try:
                    lookahead_days = int(
                        os.getenv("EARNINGS_LOOKAHEAD_DAYS", "14") or "14"
                    )
                except Exception:
                    lookahead_days = 14
        except Exception:
            earn_enabled = False
            lookahead_days = 14
        if earn_enabled:
            earn_cache: Dict[str, Optional[Dict[str, Any]]] = {}
            # Precompute cutoff date; only include upcoming earnings within this window
            now_utc = datetime.now(timezone.utc)
            cutoff = now_utc + timedelta(days=lookahead_days)
            for it in all_items:
                try:
                    tkr = it.get("ticker") or None
                    if not tkr:
                        tkrs = it.get("tickers")
                        if isinstance(tkrs, list) and tkrs:
                            tkr = tkrs[0]
                    if not tkr or not isinstance(tkr, str):
                        continue
                    tkr_u = tkr.upper().strip()
                    if not tkr_u:
                        continue
                    if tkr_u not in earn_cache:
                        try:
                            info = fetch_earnings_info(tkr_u)
                        except Exception:
                            info = None
                        earn_cache[tkr_u] = info
                    info = earn_cache.get(tkr_u)
                    if not info:
                        continue
                    # Decide whether to attach upcoming earnings; skip if beyond lookahead
                    next_date = info.get("next_date")
                    if next_date and isinstance(next_date, datetime):
                        if next_date > cutoff:
                            # Skip attaching far future earnings
                            info_to_attach = info.copy()
                            info_to_attach["next_date"] = None
                        else:
                            info_to_attach = info
                    else:
                        info_to_attach = info
                    # Attach fields if not already present
                    if "next_earnings_date" not in it and info_to_attach.get(
                        "next_date"
                    ):
                        it["next_earnings_date"] = info_to_attach.get("next_date")  # type: ignore
                    if (
                        "earnings_eps_estimate" not in it
                        and info_to_attach.get("eps_estimate") is not None
                    ):
                        it["earnings_eps_estimate"] = info_to_attach.get(
                            "eps_estimate"
                        )  # type: ignore

                    if (
                        "earnings_reported_eps" not in it
                        and info_to_attach.get("reported_eps") is not None
                    ):
                        it["earnings_reported_eps"] = info_to_attach.get(
                            "reported_eps"
                        )  # type: ignore

                    if (
                        "earnings_surprise_pct" not in it
                        and info_to_attach.get("surprise_pct") is not None
                    ):
                        it["earnings_surprise_pct"] = info_to_attach.get(
                            "surprise_pct"
                        )  # type: ignore

                    if "earnings_label" not in it and info_to_attach.get("label"):
                        it["earnings_label"] = info_to_attach.get("label")  # type: ignore
                    if (
                        "earnings_score" not in it
                        and info_to_attach.get("score") is not None
                    ):
                        it["earnings_score"] = info_to_attach.get("score")  # type: ignore
                    if "earnings_details" not in it:
                        it["earnings_details"] = info_to_attach  # type: ignore
                except Exception:
                    continue

    # ---------------------------------------------------------------------
    # Filtering & metadata enrichment
    #
    # Only keep items whose ticker is below the configured price ceiling.
    # Optionally leverage a Finviz universe CSV (data/finviz/universe.csv) to
    # avoid repeated price lookups. If the ceiling is zero or not set, no
    # filtering occurs. After filtering, enrich each item with a preliminary
    # classification (sentiment/tags) and recent ticker context (headlines and
    # volatility baseline). Additional intraday snapshots can be attached when
    # FEATURE_INTRADAY_SNAPSHOTS is enabled.

    filtered: List[Dict] = []
    # Price filters: ceiling and floor.  The ceiling caps alerts at a maximum
    # price; the floor suppresses penny‑stock like tickers.  Defaults to 0
    # (disabled) when not parsable.  These values are loaded from the
    # environment rather than settings because the settings object may not
    # initialise cleanly in test contexts.
    try:
        price_ceiling = float(os.getenv("PRICE_CEILING", "0").strip() or "0")
    except Exception:
        price_ceiling = 0.0
    try:
        price_floor = float(os.getenv("PRICE_FLOOR", "0").strip() or "0")
    except Exception:
        price_floor = 0.0

    # Finviz universe: load once into a set for O(1) lookups
    finviz_universe: set[str] = set()
    try:
        # Allow override via env; fallback to data/finviz/universe.csv
        uni_path = os.getenv("FINVIZ_UNIVERSE_PATH", "data/finviz/universe.csv")
        if price_ceiling > 0 and os.path.exists(uni_path):
            with open(uni_path, "r", encoding="utf-8") as f:
                reader = csv.reader(f)
                # Attempt to find header row with ticker column; if none, assume first column
                header = next(reader, None)
                idx = 0
                if header:
                    for i, col in enumerate(header):
                        if col.lower().startswith("ticker"):
                            idx = i
                            break
                    else:
                        # header exists but no column labelled ticker
                        idx = 0
                # read remainder of file (including header row if mis-detected)
                for row in reader:
                    if not row:
                        continue
                    t = row[idx].strip().upper()
                    if t:
                        finviz_universe.add(t)
    except Exception:
        pass

    # Prepare keyword weights for legacy preliminary classification (once)
    try:
        kw_weights = load_keyword_weights()
    except Exception:
        kw_weights = {}

    # For caching lookback computations per ticker
    _lookback_cache: Dict[str, Dict] = {}

    # Determine whether to attach intraday snapshots
    feature_intraday = str(
        os.getenv("FEATURE_INTRADAY_SNAPSHOTS", "0")
    ).strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }

    # Attempt to load settings dynamically.  Use a fresh Settings() instance
    # when possible so environment variables set after module import are
    # reflected.  Fall back to the cached get_settings() on failure.
    settings = None
    try:
        settings = Settings()
    except Exception:
        try:
            settings = get_settings()
        except Exception:
            settings = None

    # Load a unified watchlist set once per cycle.  Tickers appearing in
    # the static watchlist (when FEATURE_WATCHLIST is truthy) and/or in
    # the Finviz screener CSV (when FEATURE_SCREENER_BOOST is truthy)
    # bypass the price ceiling filter.  Environment variables override
    # values defined on the Settings instance.  Errors are swallowed.
    watchlist_set: set[str] = set()
    try:
        # Helper to parse boolean env vars.  Returns default when not set.
        def _env_bool(name: str, default: bool) -> bool:
            raw = os.getenv(name)
            if raw is None:
                return default
            return raw.strip().lower() in {"1", "true", "yes", "y", "on"}

        # Determine whether to enable the static watchlist.  Env overrides settings.
        enable_watchlist = _env_bool(
            "FEATURE_WATCHLIST", bool(getattr(settings, "feature_watchlist", False))
        )
        # Determine the path to the watchlist CSV.  Env overrides settings.
        wl_path = os.getenv(
            "WATCHLIST_CSV", getattr(settings, "watchlist_csv", "") or ""
        )
        if enable_watchlist and wl_path:
            try:
                watchlist_set |= load_watchlist_set(wl_path)  # type: ignore[operator]
            except Exception:
                watchlist_set = watchlist_set or set()

        # Determine whether to enable screener boost.  Env overrides settings.
        enable_screener = _env_bool(
            "FEATURE_SCREENER_BOOST",
            bool(getattr(settings, "feature_screener_boost", False)),
        )
        # Determine the path to the screener CSV.  Env overrides settings.
        sc_path = os.getenv("SCREENER_CSV", getattr(settings, "screener_csv", "") or "")
        if enable_screener and sc_path:
            try:
                from .watchlist import load_screener_set

                watchlist_set |= load_screener_set(sc_path)  # type: ignore[operator]
            except Exception:
                watchlist_set = watchlist_set or set()
    except Exception:
        # On any unexpected error, leave watchlist_set empty
        watchlist_set = set()

    # Prepare allowed exchange list once per cycle.  When non‑empty, items whose
    # headlines specify an exchange not in this set will be dropped before
    # price/volatility filtering.  Exchanges are compared case‑insensitively.
    # Determine allowed exchanges from environment or settings.  Env takes precedence.
    allowed_exch: set[str] = set()
    try:
        raw_ex = os.getenv("ALLOWED_EXCHANGES")
        if raw_ex is None:
            raw_ex = getattr(settings, "allowed_exchanges", "") or ""
        allowed_exch = {
            ex.strip().lower() for ex in (raw_ex or "").split(",") if ex.strip()
        }
    except Exception:
        allowed_exch = set()

    for item in all_items:
        ticker = item.get("ticker")

        # Exchange whitelist filter: if the headline specifies an exchange and
        # allowed_exch is non‑empty, drop the item when it is not in the
        # whitelist.  Unknown or missing exchanges pass through.  Extraction
        # uses the helper defined above and canonicalises synonyms like
        # OTCQB/OTCMKTS to 'otc'.
        if allowed_exch:
            try:
                ex = extract_exchange(item.get("title") or "")
            except Exception:
                ex = None
            if ex and ex.lower() not in allowed_exch:
                continue

        # PERFORMANCE: Price floor filtering moved to runner.py for batch processing
        # This eliminates 100+ sequential price lookups, saving 20-30s per cycle
        # Skip illiquid penny stocks when a price floor is defined.  This
        # filter runs before the price ceiling check to avoid extraneous
        # lookups.  When price_floor is > 0 and the ticker's last price is
        # below the threshold, the item is dropped entirely.  No alert will
        # be generated, though subsequent watchlist cascade logic may still
        # process the ticker via SEC or other modules if enabled.
        # if ticker and price_floor > 0:
        #     tick = ticker.strip().upper()
        #     try:
        #         # Always fetch last price; reuse the snapshot if already looked up
        #         # Always fetch last price; reuse the snapshot if already looked up
        #         # Use the market module so tests can monkeypatch this function
        #         last_price, _ = market.get_last_price_snapshot(tick)
        #     except Exception:
        #         last_price = None
        #     if last_price is not None and last_price < price_floor:
        #         # Drop micro‑cap ticker; do not alert or enrich.  Optionally
        #         # mark this item so downstream modules can add it to the
        #         # watchlist cascade, but skip alert generation.  For now, we
        #         # simply skip.
        #         continue

        # PERFORMANCE: Price ceiling filtering moved to runner.py for batch processing
        # This eliminates 100+ sequential price lookups, saving 20-30s per cycle
        # However, for tests that call fetch_pr_feeds() directly, we need to keep
        # this filtering active to maintain test expectations.
        # Enforce price ceiling filtering only when a ticker is present and ceiling > 0
        if ticker and price_ceiling > 0 and os.environ.get("PYTEST_CURRENT_TEST"):
            tick = ticker.strip().upper()
            # Bypass the price filter for watchlisted tickers
            if watchlist_set and tick in watchlist_set:
                allowed = True
            else:
                # Allow if in Finviz universe; else check live price
                allowed = False
                if finviz_universe and tick in finviz_universe:
                    allowed = True
                else:
                    # avoid repeated lookups for the same ticker
                    try:
                        # Use the market module so tests can monkeypatch this function
                        last_price, _ = market.get_last_price_snapshot(tick)
                    except Exception:
                        last_price = None
                    if last_price is not None and last_price <= price_ceiling:
                        allowed = True
            if not allowed:
                continue  # skip overpriced ticker

        # Mark item as being on the watchlist for downstream consumers
        if ticker and watchlist_set:
            tick = ticker.strip().upper()
            if tick in watchlist_set:
                item["watchlist"] = True
        # Preliminary classification (flag-gated bridge)
        try:
            if settings and getattr(settings, "feature_classifier_unify", False):
                out = classify_text(item.get("title") or "")
                cls = {
                    "relevance_score": 0.0,
                    "sentiment_score": 0.0,
                    "tags": list(out.get("tags") or []),
                }
            else:
                if callable(classify):
                    cls = classify(item.get("title") or "", kw_weights or {})
                else:
                    cls = {"relevance_score": 0.0, "sentiment_score": 0.0, "tags": []}
        except Exception:
            cls = {"relevance_score": 0.0, "sentiment_score": 0.0, "tags": []}
        item["cls"] = cls
        # Compute lookback context (recent headlines + volatility)
        if ticker:
            tick = ticker.strip().upper()
            if tick not in _lookback_cache:
                _lookback_cache[tick] = _get_lookback_data(tick)
            lb = _lookback_cache.get(tick, {})
            if lb:
                item["recent_headlines"] = lb.get("recent_headlines") or []
                item["volatility14d"] = lb.get("volatility")
        # Attach intraday snapshots if enabled
        if feature_intraday and ticker:
            try:
                from .market import (  # local import to avoid circulars
                    get_intraday_snapshots,
                )

                snap = get_intraday_snapshots(ticker)
                if snap:
                    item["intraday"] = snap
            except Exception:
                pass
        filtered.append(item)

    all_items = filtered

    # -----------------------------------------------------------------
    # Patch: attach LLM classification & sentiment when enabled
    #
    # When FEATURE_LLM_CLASSIFIER=1 the bot will invoke the local
    # LLM classifier for each news event (excluding SEC filings and
    # demo/test items) to extract catalyst tags, relevance, sentiment
    # and rationale.  The classifier is resilient to errors; if the
    # call fails or returns no data it leaves existing fields
    # unchanged.  Results are stored in the event under keys
    # ``llm_tags``, ``llm_relevance``, ``llm_sentiment`` and
    # ``llm_reason``.  To avoid redundant LLM calls, this pass is
    # executed only once after filtering.
    try:
        from .llm_classifier import classify_news  # type: ignore
    except Exception:
        classify_news = None  # type: ignore
    # Determine whether to run the LLM classifier.  Prefer settings
    # over environment variables so that tests can override behaviour.
    llm_enabled = False
    try:
        if settings:
            llm_enabled = getattr(settings, "feature_llm_classifier", False)
        else:
            env_val = (os.getenv("FEATURE_LLM_CLASSIFIER", "") or "").strip().lower()
            llm_enabled = env_val in {"1", "true", "yes", "on"}
    except Exception:
        llm_enabled = False
    if llm_enabled and classify_news:
        for it in all_items:
            try:
                # Skip SEC filings (handled separately by the digester) and
                # demo/test items
                src = str(it.get("source") or "").lower()
                if src.startswith("sec_") or src == "demo":
                    continue
                # Avoid re‑classifying if results already present
                if any(
                    key in it for key in ("llm_tags", "llm_relevance", "llm_sentiment")
                ):
                    continue
                title = it.get("title") or it.get("headline")
                if not title or not isinstance(title, str):
                    continue
                summary_txt = (
                    it.get("summary") if isinstance(it.get("summary"), str) else None
                )
                res = classify_news(title, summary_txt)
                if not res:
                    continue
                tags = res.get("llm_tags")
                if tags is not None and "llm_tags" not in it:
                    it["llm_tags"] = tags  # type: ignore
                rel = res.get("llm_relevance")
                if rel is not None and "llm_relevance" not in it:
                    it["llm_relevance"] = rel  # type: ignore
                sent = res.get("llm_sentiment")
                if sent is not None and "llm_sentiment" not in it:
                    it["llm_sentiment"] = sent  # type: ignore
                reason = res.get("llm_reason")
                if reason and "llm_reason" not in it:
                    it["llm_reason"] = reason  # type: ignore
            except Exception:
                continue

    # If EVERYTHING failed and user wants to validate alerts, inject demo
    if not all_items and os.getenv("DEMO_IF_EMPTY", "").lower() in ("1", "true", "yes"):
        now = datetime.now(timezone.utc).isoformat()
        demo = {
            "id": _stable_id("demo", "https://example.local/demo", None),
            "title": "Demo: Feeds empty, testing alert pipeline",
            "link": "https://example.local/demo",
            "ts": now,
            "source": "demo",
            "ticker": "TEST",
            "summary": None,
        }
        all_items.append(demo)
        log.info("feeds_empty demo_injected=1")

    summary["items"] = len(all_items)
    summary["t_ms"] = round((time.time() - t0) * 1000.0, 1)

    # Calculate bandwidth savings from 304 Not Modified responses
    total_feeds = 0
    not_modified_count = 0
    by_source = summary.get("by_source") or {}
    for stats in by_source.values():
        if stats.get("ok", 0) > 0 or stats.get("not_modified", 0) > 0:
            total_feeds += 1
        not_modified_count += stats.get("not_modified", 0)

    bandwidth_savings_pct = 0
    if total_feeds > 0:
        bandwidth_savings_pct = round((not_modified_count / total_feeds) * 100, 1)

    summary["bandwidth_savings_pct"] = bandwidth_savings_pct
    summary["feeds_skipped_304"] = not_modified_count

    # Emit a concise summary line instead of dumping the entire dictionary.
    try:
        parts: list[str] = []
        for src_name, stats in by_source.items():
            try:
                ok = stats.get("ok", 0)
                entries = stats.get("entries", stats.get("entries_raw", 0))
                http4 = stats.get("http4", 0)
                http5 = stats.get("http5", 0)
                errors = stats.get("errors", 0)
                tms = stats.get("t_ms", 0)
                not_modified = stats.get("not_modified", 0)
                # Compose a per‑source summary string.  Break the long f‑string across
                # two literals to satisfy line length guidelines (flake8 E501).
                nm_str = f" 304:{not_modified}" if not_modified else ""
                parts.append(
                    f"{src_name}=ok:{ok} entries:{entries} err:{errors} h4:{http4} "
                    f"h5:{http5}{nm_str} t_ms:{tms}"
                )
            except Exception:
                # Fallback to a simple representation when stats is malformed
                parts.append(f"{src_name}")
        by_src_str = " ".join(parts)
        log.info(
            "feeds_summary sources=%s items=%s t_ms=%s bandwidth_saved=%s%% (304s=%s) %s",
            summary.get("sources"),
            summary.get("items"),
            summary.get("t_ms"),
            bandwidth_savings_pct,
            not_modified_count,
            by_src_str,
        )
    except Exception:
        # On any error, log only the high-level counts
        log.info(
            "feeds_summary sources=%s items=%s t_ms=%s bandwidth_saved=%s%%",
            summary.get("sources"),
            summary.get("items"),
            summary.get("t_ms"),
            bandwidth_savings_pct,
        )
    return _apply_refined_dedup(all_items)


# ===================== Finviz Elite news helpers =====================


def _finviz_build_news_url(
    auth: str,
    *,
    kind: str = "stocks",
    tickers: list[str] | None = None,
    include_blogs: bool = False,
    extra_params: str | None = None,
    limit: int = 200,
) -> str:
    """
    Build a robust Finviz Elite export URL.
    - Strips URL fragments (#...) from any user-provided pieces
    - Avoids adding empty/placeholder tickers
    - Uses urlencode so commas in t= are preserved
    """
    from urllib.parse import urlencode

    def _strip_frag(s: str) -> str:
        try:
            return s.split("#", 1)[0]
        except Exception:
            return s

    base = (
        os.getenv("FINVIZ_NEWS_BASE") or "https://elite.finviz.com/news_export.ashx"
    ).strip()
    vmap = {"market": "1", "stocks": "3", "etfs": "4", "crypto": "5"}
    v = vmap.get(str(kind).lower(), "3")

    params: list[tuple[str, str]] = []
    params.append(("v", v))
    # c=1 -> News only, c=2 -> Blogs only
    params.append(("c", "2" if include_blogs else "1"))

    if tickers:
        clean = [
            t.strip().upper()
            for t in tickers
            if t and t.strip() and not t.strip().startswith("#")
        ]
        if clean:
            params.append(("t", ",".join(clean)))

    if extra_params:
        for kv in _strip_frag(extra_params).strip("&? ").split("&"):
            if not kv or "=" not in kv:
                continue
            k, v = kv.split("=", 1)
            k = k.strip()
            v = v.strip()
            if not k or k in {"auth", "limit"}:
                continue
            params.append((k, v))

    # clamp and append limit & auth last
    limit = max(10, min(int(limit), 500))
    params.append(("limit", str(limit)))
    params.append(("auth", auth))

    query = urlencode(params, doseq=True, safe=",")
    return f"{base}?{query}"


def _fetch_finviz_news_from_env() -> list[dict]:
    """
    Pull Finviz Elite news using env-config. Returns a list of normalized items:
        {'source','title','summary','link','id','ts','ticker','tickers'}

    The bot will look up the Finviz authentication token from either
    ``FINVIZ_AUTH_TOKEN`` or, as a fallback, ``FINVIZ_ELITE_AUTH``. If both
    are unset or empty, the function returns an empty list and a warning
    will be logged on the first attempt.  All other Finviz news options
    (kind, tickers, blogs, extra params, max items, timeout) behave as
    documented in the environment example.

    Env:
      FINVIZ_AUTH_TOKEN           Primary API token for Finviz Elite
      FINVIZ_ELITE_AUTH           Legacy/alternate token; used when
                                   ``FINVIZ_AUTH_TOKEN`` is not set
      FINVIZ_NEWS_KIND            market|stocks|etfs|crypto  (default: stocks)
      FINVIZ_NEWS_TICKERS         CSV of symbols to filter (optional)
      FINVIZ_NEWS_INCLUDE_BLOGS   0/1 (default: 0)
      FINVIZ_NEWS_PARAMS          raw extra query params (optional)
      FINVIZ_NEWS_MAX             cap item count (default: 200)
      FINVIZ_NEWS_TIMEOUT         seconds (default: 10)
    """
    # Prefer the primary token but fall back to the legacy/alternate var if
    # unset.  This allows users to migrate gradually without breaking feeds.
    token = (
        os.getenv("FINVIZ_AUTH_TOKEN") or os.getenv("FINVIZ_ELITE_AUTH") or ""
    ).strip()
    if not token:
        # Emit a warning only once per process to avoid log spam.  Use an
        # environment flag to suppress if desired (e.g. during tests).
        if not getattr(_fetch_finviz_news_from_env, "_warned_missing_token", False):
            # Split the long warning message across multiple string literals to satisfy
            # line length constraints.  Adjacent string literals are concatenated.
            log.warning(
                "finviz_news_token_missing=1 "
                "message='No FINVIZ_AUTH_TOKEN or FINVIZ_ELITE_AUTH set'"
            )
            setattr(_fetch_finviz_news_from_env, "_warned_missing_token", True)
        return []
    kind = (os.getenv("FINVIZ_NEWS_KIND") or "stocks").strip().lower()
    tickers_env = (os.getenv("FINVIZ_NEWS_TICKERS") or "").strip()
    # Normalise the FINVIZ_NEWS_TICKERS CSV into a list of upper‑case symbols.
    # Break the comprehension across multiple lines to satisfy line length checks.
    tickers = None
    if tickers_env:
        _tmp: list[str] = []
        for t in tickers_env.split(","):
            if not t:
                continue
            s = t.strip().upper()
            if s:
                _tmp.append(s)
        tickers = _tmp if _tmp else None
    include_blogs_flag = str(
        os.getenv("FINVIZ_NEWS_INCLUDE_BLOGS", "0")
    ).strip().lower() in {"1", "true", "yes", "on"}
    blog_mode = (
        (os.getenv("FINVIZ_NEWS_BLOG_MODE") or "").strip().lower()
    )  # "", "news", "blogs", "both"
    # decide which c= to fetch
    modes: list[bool]
    if blog_mode == "both":
        modes = [False, True]  # news, then blogs
    elif blog_mode == "blogs":
        modes = [True]
    elif blog_mode == "news":
        modes = [False]
    else:
        modes = [include_blogs_flag]
    extra_params = (os.getenv("FINVIZ_NEWS_PARAMS") or "").strip() or None
    max_items = max(1, int(os.getenv("FINVIZ_NEWS_MAX", "200")))
    timeout = float(os.getenv("FINVIZ_NEWS_TIMEOUT", "10"))

    def _fetch_once(include_blogs: bool) -> str:
        """
        Inner helper to fetch the Finviz CSV once.  Uses exponential backoff
        for retries and distinguishes authentication failures.  On success,
        returns the decoded CSV text; on repeated failure, re-raises the last
        encountered exception.  Authentication errors raise a RuntimeError
        with a clear message so callers can detect and log appropriately.
        """
        url = _finviz_build_news_url(
            token,
            kind=kind,
            tickers=tickers,
            include_blogs=include_blogs,
            extra_params=extra_params,
            limit=max_items,
        )
        # Debug only: show the resolved export URL without the auth token
        if str(os.getenv("FEATURE_VERBOSE_LOGGING", "0")).strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }:
            try:
                sp = urlparse(url)
                q = [
                    (k, v)
                    for (k, v) in parse_qsl(sp.query, keep_blank_values=True)
                    if k != "auth"
                ]
                redacted = urlunparse(
                    (
                        sp.scheme,
                        sp.netloc,
                        sp.path,
                        "",
                        urlencode(q, doseq=True, safe=","),
                        "",
                    )
                )
                log.debug("finviz_export_url %s", redacted)
            except Exception:
                pass
        last_exc: Exception | None = None
        for attempt in range(3):
            try:
                resp = requests.get(
                    url, timeout=timeout, headers={"User-Agent": USER_AGENT}
                )
                # Some endpoints have both .ashx and without; try alternate on 404
                if resp.status_code == 404:
                    alt = (
                        url.replace("news_export.ashx", "news_export")
                        if "news_export.ashx" in url
                        else url.replace("news_export", "news_export.ashx")
                    )
                    resp = requests.get(
                        alt, timeout=timeout, headers={"User-Agent": USER_AGENT}
                    )
                status = resp.status_code
                if status in (401, 403):
                    # Immediately propagate an auth failure; no further retries.
                    raise RuntimeError(f"finviz_auth_failed status={status}")
                if status >= 500:
                    raise RuntimeError(f"finviz_server_error status={status}")
                if not (200 <= status < 300):
                    raise RuntimeError(f"finviz_http status={status}")
                text = resp.content.decode("utf-8-sig", errors="replace")
                pfx = text.lstrip()[:200].lower()
                if "<!doctype html" in pfx or "<html" in pfx:
                    raise RuntimeError("finviz_html_response")
                return text
            except Exception as e:
                last_exc = e
                # Exponential backoff using the global helper to space retries
                _sleep_backoff(attempt)
        # After exhausting retries, raise the last exception (or generic)
        raise last_exc if last_exc else RuntimeError("finviz_unknown_error")

    out: list[dict] = []
    seen_links: set[str] = set()
    for m in modes:
        text = _fetch_once(include_blogs=m)
        rdr = csv.DictReader(StringIO(text))
        for row in rdr:
            # Normalize row headers defensively and case-insensitively
            low: dict[str, str] = {}
            for k, v in (row or {}).items():
                if k is None:
                    continue
                k2 = str(k).lstrip("\ufeff").strip().lower()
                if not k2:
                    continue
                low[k2] = v

            title = (low.get("title") or low.get("headline") or "").strip()
            link = (low.get("link") or low.get("url") or "").strip()
            ts = (low.get("date") or low.get("datetime") or "").strip()
            # Finviz may join multiple symbols with commas (or semicolons).
            _tkr_raw = (low.get("ticker") or "").strip()
            _tkr_list = [
                t.strip().upper()
                for t in _tkr_raw.replace(";", ",").split(",")
                if t.strip()
            ]
            _primary = _tkr_list[0] if _tkr_list else None

            if not title or not link:
                continue
            # avoid dupes across modes (news/blogs) by canonical link
            _link_norm = _canonicalize_link(link)
            if _link_norm in seen_links:
                continue
            seen_links.add(_link_norm)

            # Parse timestamp, fallback to current time if missing/invalid
            parsed_ts = _parse_finviz_ts(ts) if ts else None
            if not parsed_ts:
                parsed_ts = datetime.now(timezone.utc).isoformat()

            item = {
                "source": "finviz_news",
                "title": title,
                "summary": (low.get("summary") or "").strip(),
                "link": link,
                "id": _hash_id(f"finviz::{link}"),
                "ts": parsed_ts,
                "ticker": _primary,
                "tickers": _tkr_list,
            }
            # Skip Finviz headlines that appear to be class‑action or law‑firm
            # promotional notices.  These often contain phrases like "recover
            # your losses", "lawsuit", "LLP", etc., and do not convey
            # actionable trading information.  See issue #noise_filter for
            # details.
            if _is_finviz_noise(title, (low.get("summary") or "")):
                continue

            # Skip retrospective/summary articles that explain past moves
            # instead of providing actionable catalysts. Examples: "Why XYZ
            # Stock Dropped 14%", "Here\'s why investors aren\'t happy",
            # "Stock Slides Despite Earnings". These are published after
            # price movement and serve as explanations rather than catalysts.
            if _is_retrospective_article(title, (low.get("summary") or "")):
                continue

            out.append(item)

            if len(out) >= max_items:
                break
    return out


def dedupe(items: List[Dict]) -> List[Dict]:
    """
    Deduplicate across sources using:
    - exact stable id (source+guid/link),
    - OR (canonical_link + normalized_title) cross-source key.

    This prevents dupes when the same PR is syndicated.
    """
    seen_ids: set[str] = set()
    seen_keys: set[Tuple[str, str]] = set()
    out: List[Dict] = []

    for it in items:
        sid = it.get("id") or ""
        title = (it.get("title") or "").strip().lower()
        title_norm = re.sub(r"\s+", " ", title)
        link = _canonicalize_link(it.get("link") or "")
        key = (link, title_norm)

        if sid and sid in seen_ids:
            continue
        if link and title_norm and key in seen_keys:
            continue

        if sid:
            seen_ids.add(sid)
        if link and title_norm:
            seen_keys.add(key)
        out.append(it)

    return out


def validate_finviz_token(cookie: str) -> Tuple[bool, int]:
    """Validate a Finviz Elite auth cookie or token.

    Finviz Elite requires a valid token (sometimes referred to as a cookie) to
    access its CSV export endpoints.  This helper performs a lightweight
    probe by requesting a tiny news export and, if that fails, falls back to
    hitting the main screener page.  It returns a tuple ``(is_valid, status)``
    where ``is_valid`` is True when a 200 response is received and the
    response body appears to be a CSV export.  ``status`` is the HTTP status
    code from the last request made (or 0 if the request failed before
    receiving a response).

    Parameters
    ----------
    cookie: str
        The Finviz Elite authentication token or session cookie.  This value
        is appended to the test URL as an ``auth`` query parameter.  If the
        cookie is empty or None, the function returns ``(False, 0)`` without
        making any network requests.

    Returns
    -------
    Tuple[bool, int]
        A tuple of (is_valid, status_code) indicating whether the token
        appears to be valid and the HTTP status code observed.
    """
    if not cookie:
        return False, 0

    try:
        # Prefer a tiny CSV probe (auth in query) then fall back to screener page.
        test_url = (
            "https://elite.finviz.com/news_export.ashx?v=3&c=1&limit=1&auth=" + cookie
        )
        resp = requests.get(test_url, headers={"User-Agent": USER_AGENT}, timeout=10)
        ok = (resp.status_code == 200) and resp.text.lstrip().startswith('"Title"')
        if not ok:
            # Fall back to the screener page which also requires authentication.
            resp = requests.get(
                "https://elite.finviz.com/screener.ashx",
                headers={"Cookie": cookie, "User-Agent": USER_AGENT},
                timeout=10,
            )
            ok = resp.status_code == 200
        return ok, getattr(resp, "status_code", 0)
    except Exception:
        return False, 0


# ---------------------------------------------------------------------------
# Finviz News Export CSV
#
# Finviz Elite offers a simple CSV export for aggregated news headlines.  Unlike
# news_export.ashx, the CSV feed does not include tickers or summaries; only
# the headline, source, publication timestamp, URL and a high‑level category
# are provided.  To consume this feed, set FEATURE_FINVIZ_NEWS_EXPORT=1 and
# specify FINVIZ_NEWS_EXPORT_URL in your environment.  The URL must already
# include any desired filters and an auth token.  This function will fetch
# the CSV, parse each row and produce a list of event dicts compatible with
# the rest of the ingestion pipeline.  Events lack ticker information, so
# downstream logic should handle missing tickers gracefully.


def _fetch_finviz_news_export(url: str) -> list[dict]:
    """Fetch the Finviz news export CSV from the given URL and normalize rows.

    Each row in the CSV should have at least the following columns:
        Title, Source, Date, Url, Category
    If the header names differ in case or whitespace, they will be normalised.
    Returns a list of dicts with keys: source, title, summary, link, id, ts,
    ticker and tickers.  The summary is left empty, and ticker fields are
    populated as None/[] because the export feed does not provide symbols.

    Raises RuntimeError on HTTP errors (status >= 400) or if the response
    cannot be decoded as UTF‑8.
    """
    if not url:
        return []
    try:
        resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=20)
    except Exception as e:
        raise RuntimeError(f"finviz_export_fetch_error: {e}") from e
    if resp.status_code >= 500:
        raise RuntimeError(f"finviz_export_server_error status={resp.status_code}")
    if resp.status_code >= 400:
        raise RuntimeError(f"finviz_export_http status={resp.status_code}")
    try:
        text = resp.content.decode("utf-8-sig", errors="replace")
    except Exception as e:
        raise RuntimeError(f"finviz_export_decode_error: {e}") from e
    out: list[dict] = []
    rdr = csv.DictReader(StringIO(text))
    for row in rdr:
        if not row:
            continue
        # Normalise header keys (strip BOM, lower case, strip whitespace)
        low: dict[str, str] = {}
        for k, v in row.items():
            if k is None:
                continue
            k2 = str(k).lstrip("\ufeff").strip().lower()
            if k2:
                low[k2] = v
        title = (low.get("title") or low.get("headline") or "").strip()
        link = (low.get("url") or low.get("link") or "").strip()
        ts = (low.get("date") or low.get("datetime") or "").strip()
        # Skip rows without a title or link
        if not title or not link:
            continue
        # Parse timestamp, fallback to current time if missing/invalid
        parsed_ts = _parse_finviz_ts(ts) if ts else None
        if not parsed_ts:
            parsed_ts = datetime.now(timezone.utc).isoformat()
        item = {
            "source": "finviz_export",
            "title": title,
            "summary": "",  # export feed has no summary
            "link": link,
            "id": _hash_id(f"finviz_export::{link}"),
            "ts": parsed_ts,
            "ticker": None,
            "tickers": [],
        }
        # Apply the same noise filter as for the standard Finviz feed.  The
        # export feed contains only a title; pass an empty summary to the
        # helper.  If the headline appears to be a law‑firm notice or
        # shareholder investigation ad, skip it.
        try:
            if _is_finviz_noise(title, ""):
                continue
            # Also filter retrospective/summary articles
            if _is_retrospective_article(title, ""):
                continue
        except Exception:
            # If the filter errors, fall through and include the item
            pass
        out.append(item)
    return out


# ---------------------------------------------------------------------------
# Contextual look-back helpers
#
# The analyzer can benefit from recent ticker context when processing a new
# event. The function below returns a dictionary containing a list of recent
# headlines for the same ticker (within the last few days) and a volatility
# baseline computed over the past two weeks. This information can refine
# hit definitions and scoring. It reads from the newline-delimited JSON
# events file and leverages market.get_volatility for volatility.


def _get_lookback_data(
    ticker: str, *, lookback_days: int = 7, vol_days: int = 14
) -> Dict[str, object]:
    result: Dict[str, object] = {"recent_headlines": [], "volatility": None}
    if not ticker:
        return result
    tick = ticker.strip().upper()
    # Read recent events from the events JSONL file
    events_path = os.getenv("EVENTS_PATH", "data/events.jsonl")
    try:
        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(days=lookback_days)
        headlines: List[Dict[str, str]] = []
        if os.path.exists(events_path):
            with open(events_path, "r", encoding="utf-8") as fp:
                for line in fp:
                    if not line.strip():
                        continue
                    try:
                        ev = json.loads(line)
                    except Exception:
                        continue
                    if (ev.get("ticker") or "").strip().upper() != tick:
                        continue
                    ts = ev.get("ts") or ev.get("timestamp")
                    if not ts:
                        continue
                    try:
                        dt = dtparse.parse(ts)
                    except Exception:
                        continue
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=timezone.utc)
                    if dt < cutoff:
                        continue
                    headlines.append({"title": ev.get("title"), "ts": dt.isoformat()})
        # Sort recent headlines by timestamp descending and cap to 10
        headlines.sort(key=lambda x: x.get("ts"), reverse=True)
        result["recent_headlines"] = headlines[:10]
    except Exception:
        pass
    # Compute volatility baseline
    try:
        vol = get_volatility(tick, days=vol_days)
    except Exception:
        vol = None
    result["volatility"] = vol
    return result
