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
from typing import Dict, List, Optional, Tuple, Union
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

import feedparser  # type: ignore
import requests
from dateutil import parser as dtparse

from .logging_utils import get_logger
from .market import get_last_price_snapshot, get_volatility

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
                summary.setdefault("by_source", {})
                summary["by_source"]["finviz_news"] = {
                    "ok": 0,
                    "http4": 0,
                    "http5": 0,
                    "errors": 1,
                    "entries_raw": 0,
                    "entries": 0,
                    "t_ms": round((time.time() - st) * 1000.0, 1),
                }
                log.warning(
                    "finviz_news_error err=%s", e.__class__.__name__, exc_info=True
                )

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

    # Prepare keyword weights for classification once
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

    for item in all_items:
        ticker = item.get("ticker")
        # Enforce price ceiling filtering only when a ticker is present and ceiling > 0
        if ticker and price_ceiling > 0:
            tick = ticker.strip().upper()
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
        # Preliminary sentiment classification
        try:
            cls = (
                classify(item["title"], kw_weights or {})
                if callable(classify)
                else {"relevance_score": 0.0, "sentiment_score": 0.0, "tags": []}
            )
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
    log.info("%s", {"feeds_summary": summary})
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
    Env:
      FINVIZ_AUTH_TOKEN           (required)
      FINVIZ_NEWS_KIND            market|stocks|etfs|crypto  (default: stocks)
      FINVIZ_NEWS_TICKERS         CSV of symbols to filter (optional)
      FINVIZ_NEWS_INCLUDE_BLOGS   0/1 (default: 0)
      FINVIZ_NEWS_PARAMS          raw extra query params (optional)
      FINVIZ_NEWS_MAX             cap item count (default: 200)
      FINVIZ_NEWS_TIMEOUT         seconds (default: 10)
    """
    token = (os.getenv("FINVIZ_AUTH_TOKEN") or "").strip()
    if not token:
        return []
    kind = (os.getenv("FINVIZ_NEWS_KIND") or "stocks").strip().lower()
    tickers_env = (os.getenv("FINVIZ_NEWS_TICKERS") or "").strip()
    tickers = (
        [t.strip().upper() for t in tickers_env.split(",") if t.strip()]
        if tickers_env
        else None
    )
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
        last_exc = None
        for attempt in range(3):
            try:
                resp = requests.get(
                    url, timeout=timeout, headers={"User-Agent": USER_AGENT}
                )
                if resp.status_code == 404:
                    # toggle .ashx on/off once
                    alt = (
                        url.replace("news_export.ashx", "news_export")
                        if "news_export.ashx" in url
                        else url.replace("news_export", "news_export.ashx")
                    )
                    resp = requests.get(
                        alt, timeout=timeout, headers={"User-Agent": USER_AGENT}
                    )
                if resp.status_code in (401, 403):
                    raise RuntimeError(f"finviz_auth_failed status={resp.status_code}")
                if resp.status_code >= 500:
                    raise RuntimeError(f"finviz_server_error status={resp.status_code}")
                if not (200 <= resp.status_code < 300):
                    raise RuntimeError(f"finviz_http status={resp.status_code}")
                text = resp.content.decode("utf-8-sig", errors="replace")
                pfx = text.lstrip()[:200].lower()
                if "<!doctype html" in pfx or "<html" in pfx:
                    raise RuntimeError("finviz_html_response")
                return text
            except Exception as e:
                last_exc = e
                time.sleep(0.5 * (attempt + 1))
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
    """
    Best-effort probe to see if the Finviz Elite cookie looks valid.
    We call a lightweight page that requires auth and check for 200.
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
