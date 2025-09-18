# src/catalyst_bot/feeds.py
from __future__ import annotations

import csv
import hashlib
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
from dateutil import parser as dtparse

from .classify_bridge import classify_text
from .config import get_settings
from .logging_utils import get_logger
from .market import get_last_price_snapshot, get_volatility
from .watchlist import load_watchlist_set

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
            sig = signature_from(title, link)
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
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": (
            "application/rss+xml, application/atom+xml, "
            "application/xml;q=0.9, */*;q=0.8"
        ),
    }
    for attempt in range(0, 3):
        try:
            r = requests.get(
                url, headers=headers, timeout=timeout, allow_redirects=True
            )
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
        if status == 200 and text:
            return status, text, u
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


# --------------------- Normalization & parsing -------------------------------


def _to_utc_iso(dt_str: Optional[str]) -> str:
    if not dt_str:
        return datetime.now(timezone.utc).isoformat()
    try:
        d = dtparse.parse(dt_str)
        if d.tzinfo is None:
            d = d.replace(tzinfo=timezone.utc)
        return d.astimezone(timezone.utc).isoformat()
    except Exception:
        return datetime.now(timezone.utc).isoformat()


def _stable_id(source: str, link: str, guid: Optional[str]) -> str:
    raw = (guid or link or "") + f"|{source}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def _normalize_entry(source: str, e) -> Optional[Dict]:
    title = (getattr(e, "title", None) or "").strip()
    link = (getattr(e, "link", None) or "").strip()
    if not title or not link:
        return None

    published = (
        getattr(e, "published", None)
        or getattr(e, "updated", None)
        or getattr(e, "pubDate", None)
    )
    ts_iso = _to_utc_iso(published)
    guid = getattr(e, "id", None) or getattr(e, "guid", None)

    ticker = getattr(e, "ticker", None) or extract_ticker(title)

    # Pull summary/description if available for richer metadata; leave empty if missing
    summary = ""
    try:
        summary = (
            getattr(e, "summary", None) or getattr(e, "description", None) or ""
        ).strip()
    except Exception:
        summary = ""

    return {
        "id": _stable_id(source, link, guid),
        "title": title,
        "link": link,
        "ts": ts_iso,
        "source": source,
        "ticker": (ticker or None),
        "summary": summary or None,
    }


# --- helpers used by the Finviz block ---------------------------------------
def _hash_id(s: str) -> str:
    """Stable sha1 for building ids from links/keys."""
    try:
        return hashlib.sha1(s.encode("utf-8")).hexdigest()
    except Exception:
        # extremely defensive fallback
        return hashlib.sha1(repr(s).encode("utf-8", "ignore")).hexdigest()


def _parse_finviz_ts(ts: str) -> str:
    """Normalize Finviz timestamp strings to UTC ISO."""
    return _to_utc_iso(ts)


# -------------------------- Public API --------------------------------------


def fetch_pr_feeds() -> List[Dict]:
    """
    Pull all feeds with backoff & per-source alternates.
    Returns normalized list of dicts. If everything fails and DEMO_IF_EMPTY=true,
    injects a single demo item for end-to-end alert validation.
    """
    all_items: List[Dict] = []
    summary = {"sources": len(FEEDS), "items": 0, "t_ms": 0.0, "by_source": {}}
    t0 = time.time()

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

    for src, url_list in FEEDS.items():
        # Optional single-URL override via env
        if ENV_URL_OVERRIDES.get(src):
            url_list = [ENV_URL_OVERRIDES[src]]  # type: ignore[index]

        s = {"ok": 0, "http4": 0, "http5": 0, "errors": 0, "entries": 0, "t_ms": 0.0}
        st = time.time()

        status, text, used_url = _get_multi(url_list)
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
                # Classify
                score, lbl, reason = _sec_classify(
                    src_key, it.get("title"), it.get("summary")
                )
                if lbl:
                    # Attach to the item
                    if "sec_label" not in it:
                        it["sec_label"] = lbl  # type: ignore
                    if "sec_reason" not in it and reason:
                        it["sec_reason"] = reason  # type: ignore
                    # Parse timestamp for record; fall back to now
                    ts_str = it.get("ts")
                    try:
                        dt = datetime.fromisoformat(ts_str)  # type: ignore[arg-type]
                        if dt.tzinfo is None:
                            dt = dt.replace(tzinfo=timezone.utc)
                    except Exception:
                        dt = datetime.now(timezone.utc)
                    _sec_record(tkr_u, dt, lbl, reason or "")
                    # Update watchlist cascade
                    if _sec_update_watchlist:
                        _sec_update_watchlist(tkr_u, lbl)
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
    # Price ceiling: default to 0 (disabled) if not parsable
    try:
        price_ceiling = float(os.getenv("PRICE_CEILING", "0").strip() or "0")
    except Exception:
        price_ceiling = 0.0

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

    settings = None
    try:
        settings = get_settings()
    except Exception:
        settings = None

    # Load watchlist set once per cycle if the feature flag is enabled. If
    # WATCHLIST_CSV cannot be loaded, fall back to an empty set. This is used
    # to bypass the price ceiling for watchlisted tickers during filtering.
    watchlist_set: set[str] = set()
    if settings and getattr(settings, "feature_watchlist", False):
        try:
            wl_path = getattr(settings, "watchlist_csv", "") or ""
            watchlist_set = load_watchlist_set(wl_path)
        except Exception:
            watchlist_set = set()

    for item in all_items:
        ticker = item.get("ticker")
        # Enforce price ceiling filtering only when a ticker is present and ceiling > 0
        if ticker and price_ceiling > 0:
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
                        last_price, _ = get_last_price_snapshot(tick)
                    except Exception:
                        last_price = None
                    if last_price is not None and last_price <= price_ceiling:
                        allowed = True
            if not allowed:
                continue  # skip overpriced ticker
            # Mark item as being on the watchlist for downstream consumers
            if watchlist_set and tick in watchlist_set:
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
    # Emit a concise summary line instead of dumping the entire dictionary.
    try:
        parts: list[str] = []
        by_source = summary.get("by_source") or {}
        for src_name, stats in by_source.items():
            try:
                ok = stats.get("ok", 0)
                entries = stats.get("entries", stats.get("entries_raw", 0))
                http4 = stats.get("http4", 0)
                http5 = stats.get("http5", 0)
                errors = stats.get("errors", 0)
                tms = stats.get("t_ms", 0)
                parts.append(
                    (
                        f"{src_name}=ok:{ok} entries:{entries} err:{errors} "
                        f"h4:{http4} h5:{http5} t_ms:{tms}"
                    )
                )
            except Exception:
                # Fallback to a simple representation when stats is malformed
                parts.append(f"{src_name}")
        by_src_str = " ".join(parts)
        log.info(
            "feeds_summary sources=%s items=%s t_ms=%s %s",
            summary.get("sources"),
            summary.get("items"),
            summary.get("t_ms"),
            by_src_str,
        )
    except Exception:
        # On any error, log only the high-level counts
        log.info(
            "feeds_summary sources=%s items=%s t_ms=%s",
            summary.get("sources"),
            summary.get("items"),
            summary.get("t_ms"),
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

            item = {
                "source": "finviz_news",
                "title": title,
                "summary": (low.get("summary") or "").strip(),
                "link": link,
                "id": _hash_id(f"finviz::{link}"),
                "ts": _parse_finviz_ts(ts),
                "ticker": _primary,
                "tickers": _tkr_list,
            }
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
        item = {
            "source": "finviz_export",
            "title": title,
            "summary": "",  # export feed has no summary
            "link": link,
            "id": _hash_id(f"finviz_export::{link}"),
            "ts": _parse_finviz_ts(ts) if ts else None,
            "ticker": None,
            "tickers": [],
        }
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
