"""RSS ingestion for the catalyst bot.

This module fetches news and press releases from a set of RSS feeds,
canonicalizes them into a uniform :class:`~catalyst_bot.models.NewsItem`
structure, and persists them to disk. Deduplication is handled by the
caller using the utilities in :mod:`catalyst_bot.dedupe`.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime
from urllib.parse import urlparse
from typing import Generator, Iterable, List, Optional

try:
    import feedparser  # type: ignore
except Exception:  # pragma: no cover
    feedparser = None  # type: ignore

from .config import get_settings
from .models import NewsItem


def fetch_feed(url: str, max_entries: int = 50) -> List[dict]:
    """Fetch and parse an RSS feed.

    Returns a list of raw feed entries. Errors are logged and return
    empty lists.
    """
    if feedparser is None:
        return []
    try:
        feed = feedparser.parse(url)
        return feed.entries[:max_entries] if hasattr(feed, "entries") else []
    except Exception:
        return []


def canonicalize_entry(entry: dict) -> Optional[NewsItem]:
    """Convert a feed entry into a :class:`NewsItem`.

    Attempts to extract the publication time, title, link, and source
    host. If required fields are missing, ``None`` is returned.
    """
    title = entry.get("title") or entry.get("headline")
    link = entry.get("link") or entry.get("id")
    if not title or not link:
        return None
    # Parse publication time; fall back to now
    published_ts = None
    for key in ["published", "pubDate", "updated", "created"]:
        ts = entry.get(key)
        if ts:
            try:
                published_ts = datetime(*entry.get(f"{key}_parsed")[0:6])  # type: ignore[index]
                break
            except Exception:
                try:
                    published_ts = datetime.fromisoformat(ts)
                    break
                except Exception:
                    continue
    if not published_ts:
        published_ts = datetime.utcnow()
    host = urlparse(link).hostname or "unknown"
    # Extract ticker symbol if present in the title in the format "(XYZ)"
    ticker = None
    import re

    match = re.search(r"\(([A-Z]{1,5})\)", title)
    if match:
        ticker = match.group(1).upper()
    return NewsItem(
        ts_utc=published_ts,
        title=title.strip(),
        canonical_url=link,
        source_host=host.lower(),
        ticker=ticker,
        raw_text=entry.get("summary"),
    )


def fetch_all_feeds() -> List[NewsItem]:
    """Fetch all configured RSS feeds and return canonicalized news items."""
    settings = get_settings()
    items: List[NewsItem] = []
    for host in settings.rss_sources.keys():
        # Derive feed URL from host. In this simplified implementation, we
        # assume standard RSS endpoints; override here if needed.
        url = f"https://{host}/rss/"  # Many PR wires follow this pattern
        entries = fetch_feed(url)
        for entry in entries:
            item = canonicalize_entry(entry)
            if item:
                items.append(item)
        time.sleep(0.1)  # brief pause to avoid hammering hosts
    return items