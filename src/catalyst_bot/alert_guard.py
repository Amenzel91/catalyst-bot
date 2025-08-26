"""
Alert Guard helpers

- build_alert_id(payload): create a stable ID for dedupe/persistence when upstream
  didn't provide one. Prefers explicit 'id' in payload; otherwise hashes a canonical
  URL + normalized title (UTM scrubbed).

This is used by sitecustomize.py to suppress re-alerts via SeenStore.
"""

from __future__ import annotations

import hashlib
import re
from typing import Any, Dict, Optional
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse


def _clean_query(query: str) -> str:
    """Remove tracking params like utm_*, gclid, fbclid; preserve order for stability."""
    if not query:
        return ""
    pairs = [
        (k, v)
        for k, v in parse_qsl(query, keep_blank_values=True)
        if not _is_tracking(k)
    ]
    if not pairs:
        return ""
    return urlencode(pairs)


def _is_tracking(k: str) -> bool:
    k = k.lower()
    if k.startswith("utm_"):
        return True
    if k in {"gclid", "fbclid", "mc_cid", "mc_eid"}:
        return True
    return False


def canonicalize_url(url: Optional[str]) -> Optional[str]:
    if not url:
        return None
    try:
        p = urlparse(url)
        host = (p.netloc or "").lower()
        path = p.path or "/"
        path = path if path.startswith("/") else "/" + path
        # strip trailing slash except root
        if len(path) > 1 and path.endswith("/"):
            path = path[:-1]
        query = _clean_query(p.query)
        return urlunparse((p.scheme.lower(), host, path, "", query, ""))
    except Exception:
        return url


_WHITESPACE_RE = re.compile(r"\s+")


def normalize_title(title: Optional[str]) -> str:
    if not title:
        return ""
    t = title.strip()
    t = _WHITESPACE_RE.sub(" ", t)
    return t


def build_alert_id(payload: Dict[str, Any]) -> Optional[str]:
    """
    Precedence:
      1) payload.get('id') if it's a non-empty str
      2) hash(canonical_url + "||" + normalized_title)
      3) None if insufficient fields
    """
    if not isinstance(payload, dict):
        return None

    # 1) explicit id
    v = payload.get("id")
    if isinstance(v, str) and v.strip():
        return v.strip()

    # 2) derive from link + title variants
    candidates = [
        payload.get("canonical_link"),
        payload.get("url"),
        payload.get("link"),
    ]
    url = next((u for u in candidates if isinstance(u, str) and u.strip()), None)
    title = payload.get("title") if isinstance(payload.get("title"), str) else None

    if not url and not title:
        return None

    can_url = canonicalize_url(url) if url else ""
    norm_title = normalize_title(title) if title else ""
    if not can_url and not norm_title:
        return None

    raw = f"{can_url}||{norm_title}"
    h = hashlib.sha1(
        raw.encode("utf-8")
    ).hexdigest()  # stable, short enough for SQLite PK
    return f"aid:{h}"
