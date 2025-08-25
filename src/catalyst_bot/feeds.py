from __future__ import annotations
import hashlib, time, re
from datetime import datetime, timezone
from typing import Dict, Iterable, List, Optional, Tuple
import requests
import feedparser
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
    import hashlib as _h
    return _h.sha1(s.encode("utf-8")).hexdigest()

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

TICKER_PATTERNS = [
    re.compile(r"\((?:NASDAQ|NYSE|AMEX|NYSEMKT|NYSE American):\s*([A-Z]{1,5})\)"),
    re.compile(r"\b([A-Z]{1,5})\b\s*(?:receives|announces|reports|grants|award|FDA|NDA|IND)"),
]

def extract_ticker(text: str) -> Optional[str]:
    for pat in TICKER_PATTERNS:
        m = pat.search(text.upper())
        if m:
            return m.group(1)
    return None

def fetch_pr_feeds(timeout: int = 15) -> List[Dict]:
    items: List[Dict] = []
    for name, url in PR_FEEDS:
        try:
            resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=timeout)
        except Exception as e:
            log.warning(f"feed_http_error source={name} err={e!s}")
            continue

        if resp.status_code != 200:
            log.warning(f"feed_http status={resp.status_code} source={name} url={url}")
            continue  # <-- do NOT raise during tests; just skip

        try:
            feed = feedparser.parse(resp.text)
            for e in feed.entries:
                items.append(parse_entry(name, e))
        except Exception as e:
            log.warning(f"feed_parse_error source={name} err={e!s}")
            continue

        time.sleep(0.1)  # be polite
    return items

def dedupe(items: Iterable[Dict]) -> List[Dict]:
    seen: set[str] = set()
    out: List[Dict] = []
    for it in items:
        i = it["id"]
        if i not in seen:
            out.append(it)
            seen.add(i)
    return out

def validate_finviz_token(cookie: str, timeout: int = 10) -> tuple[bool, int]:
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