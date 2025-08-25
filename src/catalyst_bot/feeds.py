from __future__ import annotations

import hashlib
import random
import re
import time
from datetime import datetime, timezone
from typing import Dict, Iterable, List, Optional, Tuple

import feedparser
import requests
from dateutil import parser as date_parser

from .logging_utils import get_logger

log = get_logger("feeds")

USER_AGENT = "CatalystBot/1.0 (+https://example.local)"

PR_FEEDS: List[Tuple[str, str]] = [
    ("businesswire", "https://www.businesswire.com/portal/site/home/news/industry/?vnsId=31392&rss=1"),
    ("globenewswire", "https://www.globenewswire.com/RssFeed/orgs/5560/feedTitle/Newswire"),
    ("accesswire", "https://www.accesswire.com/rss/latest"),
    ("prnewswire", "https://www.prnewswire.com/rss/news-releases-list.rss"),
]

def _sha1(s: str) -> str:
    return hashlib.sha1(s.encode("utf-8")).hexdigest()

def _to_utc(ts: Optional[str]) -> str:
    if not ts:
        return datetime.now(timezone.utc).isoformat()
    dt = date_parser.parse(ts)
    if not dt.tzinfo:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat()

def stable_id(source: str, guid: Optional[str], title: str, pub: Optional[str]) -> str:
    return _sha1("|".join([source, guid or "", title.strip(), pub or ""]))

def parse_entry(source: str, e) -> Dict:
    title = (e.get("title") or "").strip()
    link = (e.get("link") or "").strip()
    guid = e.get("id") or e.get("guid")
    pub = e.get("published") or e.get("updated") or ""
    ts = _to_utc(pub)
    return {
        "id": stable_id(source, guid, title, pub),
        "source": source,
        "title": title,
        "link": link,
        "ts": ts,
        "ticker": extract_ticker(title),
    }

# Ticker extraction (tight): explicit formats only to avoid false positives.
_EXCH = r"(?:NASDAQ|NYSE|AMEX|NYSEMKT|NYSE\s*American)"
TICKER_PATTERNS = [
    re.compile(rf"\(({_EXCH}):\s*([A-Z]{{1,5}})\)"),  # (NYSE: ABC)
    re.compile(rf"\b{_EXCH}\s*:\s*([A-Z]{{1,5}})\b"),  # NYSE: ABC
    re.compile(r"\$([A-Z]{1,5})\b"),  # $ABC
]

def extract_ticker(text: str) -> Optional[str]:
    t = (text or "").upper()
    for pat in TICKER_PATTERNS:
        m = pat.search(t)
        if m:
            return m.group(m.lastindex or 1)
    return None

def _make_session() -> requests.Session:
    s = requests.Session()
    s.headers.update(
        {
            "User-Agent": USER_AGENT,
            "Accept": "application/rss+xml, application/xml, text/xml;q=0.9, */*;q=0.5",
        }
    )
    try:
        from requests.adapters import HTTPAdapter
        from urllib3.util.retry import Retry

        retry = Retry(
            total=2,
            backoff_factor=0.4,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=frozenset({"GET", "HEAD"}),
            raise_on_status=False,
        )
        adapter = HTTPAdapter(max_retries=retry)
        s.mount("https://", adapter)
        s.mount("http://", adapter)
    except Exception:
        pass
    return s

def fetch_pr_feeds(timeout: int = 15) -> List[Dict]:
    session = _make_session()
    items: List[Dict] = []
    metrics: Dict[str, Dict[str, int | float]] = {}
    t_cycle_start = time.perf_counter()

    for name, url in PR_FEEDS:
        m = metrics.setdefault(
            name, {"ok": 0, "http4": 0, "http5": 0, "errors": 0, "entries": 0, "t_ms": 0.0}
        )
        t0 = time.perf_counter()

        max_attempts = 3
        for attempt in range(1, max_attempts + 1):
            try:
                resp = session.get(url, timeout=timeout)
            except Exception as e:
                m["errors"] += 1
                if attempt >= max_attempts:
                    log.warning(f"feed_http_error source={name} attempt={attempt} err={e!s}")
                    break
                _sleep_with_jitter(attempt)
                continue

            status = resp.status_code
            if status == 200:
                m["ok"] += 1
                try:
                    feed = feedparser.parse(resp.content)
                    count = 0
                    for e in feed.entries:
                        items.append(parse_entry(name, e))
                        count += 1
                    m["entries"] += count
                except Exception as e:
                    m["errors"] += 1
                    log.warning(f"feed_parse_error source={name} err={e!s}")
                break

            if 400 <= status < 500 and status != 429:
                m["http4"] += 1
                log.warning(f"feed_http status={status} source={name} url={url}")
                break

            if status == 429 or 500 <= status < 600:
                if attempt >= max_attempts:
                    if status == 429:
                        m["http4"] += 1  # count 429 under http4
                    else:
                        m["http5"] += 1
                    log.warning(f"feed_http status={status} source={name} url={url} attempts={attempt}")
                    break
                ra = _parse_retry_after(resp.headers.get("Retry-After"))
                if ra is not None:
                    time.sleep(min(ra, 10))
                else:
                    _sleep_with_jitter(attempt)
                continue

            log.warning(f"feed_http status={status} source={name} url={url}")
            break

        m["t_ms"] = round((time.perf_counter() - t0) * 1000.0, 1)
        time.sleep(0.05)

    t_cycle_ms = round((time.perf_counter() - t_cycle_start) * 1000.0, 1)
    summary = {"feeds_summary": {"sources": len(PR_FEEDS), "items": len(items), "t_ms": t_cycle_ms, "by_source": metrics}}
    log.info(summary)
    return items

def _sleep_with_jitter(attempt: int) -> None:
    base = min(2 ** attempt, 8)
    time.sleep(base + random.uniform(0, 0.25))

def _parse_retry_after(value: Optional[str]) -> Optional[float]:
    if not value:
        return None
    try:
        return float(value)
    except Exception:
        return None

def dedupe(items: Iterable[Dict]) -> List[Dict]:
    seen: set[str] = set()
    out: List[Dict] = []
    for it in items:
        i = it.get("id")
        if not i:
            i = stable_id(it.get("source", ""), "", it.get("title", ""), it.get("ts", ""))
            it["id"] = i
        if i not in seen:
            out.append(it)
            seen.add(i)
    return out

def validate_finviz_token(cookie: str, timeout: int = 10) -> Tuple[bool, int]:
    if not cookie:
        return False, 0
    try:
        r = requests.get(
            "https://finviz.com/news.ashx",
            headers={"Cookie": cookie, "User-Agent": USER_AGENT},
            timeout=timeout,
            allow_redirects=False,
        )
        return (r.status_code == 200, r.status_code)
    except Exception:
        return False, 0
