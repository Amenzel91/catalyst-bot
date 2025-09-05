# src/catalyst_bot/feeds.py
from __future__ import annotations

import hashlib
import os
import random
import re
import time
import csv
from io import StringIO
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple, Union
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

import feedparser  # type: ignore
import requests
from dateutil import parser as dtparse

from .logging_utils import get_logger

log = get_logger("feeds")

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
    "globenewswire": os.getenv("GLOBENEWSWIRE_RSS_URL") or "",
    "accesswire": os.getenv("ACCESSWIRE_RSS_URL") or "",
    "prnewswire": os.getenv("PRNEWSWIRE_RSS_URL") or "",
    "prweb": os.getenv("PRWEB_RSS_URL") or "",
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
        for sep in (": ", ":", ") ", ")-", ") – "):
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

    return {
        "id": _stable_id(source, link, guid),
        "title": title,
        "link": link,
        "ts": ts_iso,
        "source": source,
        "ticker": (ticker or None),
    }


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
    if str(os.getenv("FEATURE_FINVIZ_NEWS", "1")).strip().lower() in {"1", "true", "yes", "on"}:
        st = time.time()
        try:
            # Prebuild seen sets to avoid dupes across sources (by id/link).
            _seen_ids   = {i.get("id")   for i in all_items if i.get("id")}
            _seen_links = {i.get("link") for i in all_items if i.get("link")}
            finviz_items = _fetch_finviz_news_from_env()
            finviz_unique = [
                it for it in finviz_items
                if ( (it.get("id")   not in _seen_ids) and
                     (it.get("link") not in _seen_links) )
            ]
            all_items.extend(finviz_unique)
            summary["by_source"]["finviz_news"] = {
                "ok": 1,
                "http4": 0,
                "http5": 0,
                "errors": 0,
                # count what we actually added after cross-source uniq
                "entries": len(finviz_unique),
                "t_ms": round((time.time() - st) * 1000.0, 1),
            }
        except Exception as e:
            summary.setdefault("by_source", {})
            summary["by_source"]["finviz_news"] = {
                "ok": 0, "http4": 0, "http5": 0, "errors": 1, "entries": 0,
                "t_ms": round((time.time() - st) * 1000.0, 1),
            }
            log.warning("finviz_news_error err=%s", e.__class__.__name__, exc_info=True)


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
        }
        all_items.append(demo)
        log.info("feeds_empty demo_injected=1")

    summary["items"] = len(all_items)
    summary["t_ms"] = round((time.time() - t0) * 1000.0, 1)
    log.info("%s", {"feeds_summary": summary})
    return all_items

# ===================== Finviz Elite news helpers =====================

def _finviz_build_news_url(
    token: str,
    *,
    kind: str = "stocks",          # market|stocks|etfs|crypto
    tickers: list[str] | None = None,
    include_blogs: bool = False,
    extra_params: str | None = None,
) -> str:
    """
    Compose a Finviz Elite export URL. See screenshots/docs you shared.
    """
    # Allow overriding the export base via env (useful for testing/mocks).
    # Default must include .ashx to avoid 404s on Elite.
    base = (os.getenv("FINVIZ_NEWS_BASE") or "https://elite.finviz.com/news_export.ashx")
    kind = (kind or "stocks").strip().lower()
    v_map = {"market": "1", "stocks": "3", "etfs": "4", "crypto": "5"}
    v = v_map.get(kind, "3")
    # News-only by default (exclude blogs), unless include_blogs=True
    c_part = "" if include_blogs else "&c=1"
    t_part = ""
    if tickers:
        tickers = [t.strip().upper() for t in tickers if t and t.strip()]
        if tickers:
            t_part = "&t=" + ",".join(tickers)
    extra = (extra_params or "")
    # FINVIZ_NEWS_LIMIT: ask server to cap rows (default 100; clamp 10..500).
    try:
        _limit_env = os.getenv("FINVIZ_NEWS_LIMIT") or os.getenv("FINVIZ_NEWS_MAX")
        _limit = int(_limit_env) if _limit_env else 100
    except Exception:
        _limit = 100
    _limit = max(10, min(_limit, 500))
    if "limit=" not in extra:
        extra += f"&limit={_limit}"
    return f"{base}?v={v}{c_part}{t_part}{extra}&auth={token}"


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
    tickers = [t.strip().upper() for t in tickers_env.split(",") if t.strip()] if tickers_env else None
    include_blogs = str(os.getenv("FINVIZ_NEWS_INCLUDE_BLOGS", "0")).strip().lower() in {"1","true","yes","on"}
    extra_params = (os.getenv("FINVIZ_NEWS_PARAMS") or "").strip() or None
    max_items = max(1, int(os.getenv("FINVIZ_NEWS_MAX", "200")))
    timeout = float(os.getenv("FINVIZ_NEWS_TIMEOUT", "10"))

    url = _finviz_build_news_url(
        token,
        kind=kind,
        tickers=tickers,
        include_blogs=include_blogs,
        extra_params=extra_params,
    )
    # Be polite and explicit with headers; some setups are picky about UA.
    def _do(u: str):
        return requests.get(u, timeout=timeout, headers={"User-Agent": USER_AGENT})

    resp = _do(url)
    if resp.status_code == 404:
        # Retry once by toggling .ashx on/off in case the base path was wrong.
        if "news_export.ashx" in url:
            alt = url.replace("news_export.ashx", "news_export")
        else:
            alt = url.replace("news_export", "news_export.ashx")
        resp = _do(alt)
    # Finviz returns 200 with CSV body on success
    if resp.status_code == 401 or resp.status_code == 403:
        raise RuntimeError(f"finviz_auth_failed status={resp.status_code}")
    if resp.status_code >= 500:
        raise RuntimeError(f"finviz_server_error status={resp.status_code}")
    if resp.status_code < 200 or resp.status_code >= 300:
        raise RuntimeError(f"finviz_http status={resp.status_code}")

    text = resp.content.decode("utf-8-sig", errors="replace")
    # CSV with header row; use DictReader for robustness
    rdr = csv.DictReader(StringIO(text))
    out: list[dict] = []
    for row in rdr:
        # Case-insensitive header access
        low = {k.lower(): v for k, v in row.items()}
        title = (low.get("title") or low.get("headline") or "").strip()
        link = (low.get("url") or low.get("link") or low.get("href") or "").strip()
        source = (low.get("source") or "finviz").strip()
        ts_raw = (low.get("time") or low.get("datetime") or low.get("date") or "").strip()
        # Symbols may come in various keys
        syms_raw = (low.get("ticker") or low.get("tickers") or low.get("symbol") or low.get("symbols") or "").strip()
        syms = [s.strip().upper() for s in syms_raw.replace(";", ",").split(",") if s.strip()] if syms_raw else []
        # first symbol as primary ticker (runner’s pipeline expects .get('ticker'))
        primary = syms[0] if syms else ""

        if not (title and link):
            continue

        item = {
            "source": "finviz_news",
            "title": title,
            "summary": "",
            "link": link,
            "id": _stable_id("finviz_news", link, None),
            "ts": _to_utc_iso(ts_raw),
            "ticker": primary,
            "tickers": syms,    # keep all if needed in the future
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
        resp = requests.get(
            "https://elite.finviz.com/screener.ashx",
            headers={"Cookie": cookie, "User-Agent": USER_AGENT},
            timeout=10,
        )
        ok = resp.status_code == 200
        return ok, resp.status_code
    except Exception:
        return False, 0
