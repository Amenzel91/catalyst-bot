# src/catalyst_bot/alerts.py
from __future__ import annotations

import os
import time
from typing import Any, Dict, Iterable, Optional

import requests

from .logging_utils import get_logger

log = get_logger("alerts")


def _fmt_change(change: Optional[float]) -> str:
    if change is None:
        return "n/a"
    try:
        return f"{change:+.2f}%"
    except Exception:
        return "n/a"


def _format_discord_content(
    item: Dict[str, Any],
    last_price: Optional[float],
    last_change_pct: Optional[float],
    scored: Optional[Any] = None,
) -> str:
    """Compose a compact, readable Discord message body."""
    ticker = (item.get("ticker") or "n/a").upper()
    title = item.get("title") or "(no title)"
    source = item.get("source") or "unknown"
    ts = item.get("ts") or ""
    link = item.get("link") or ""

    px = "n/a" if last_price is None else f"{float(last_price):.2f}"
    chg = _fmt_change(last_change_pct)

    # Show a couple of high-signal tags if available
    def _coerce_tags(obj: Any) -> Iterable[str]:
        try:
            if obj is None:
                return []
            if isinstance(obj, dict):
                return (
                    obj.get("keywords")
                    or obj.get("tags")
                    or obj.get("categories")
                    or []
                )
            # pydantic / namedtuple / simple object
            return (
                getattr(obj, "keywords", None)
                or getattr(obj, "tags", None)
                or getattr(obj, "categories", None)
                or []
            )
        except Exception:
            return []

    tags = list(_coerce_tags(scored))[:3]
    tags_part = f" • tags: {', '.join(map(str, tags))}" if tags else ""

    line1 = f"[{ticker}] {title}"
    line2 = f"{source} • {ts} • px={px} ({chg}){tags_part}"
    line3 = link

    # Keep under Discord's limits; three short lines is plenty.
    body = f"{line1}\n{line2}\n{line3}".strip()
    # Discord hard limit: 2000 chars (be safe at ~1900)
    if len(body) > 1900:
        body = body[:1870] + "\n… (truncated)"
    return body


def post_discord_json(
    payload: Dict[str, Any],
    webhook_url: Optional[str] = None,
    max_retries: int = 2,
) -> bool:
    """
    Minimal, reusable Discord poster with polite retry/backoff.
    - Uses webhook_url if provided, else payload.get('_webhook_url'),
      else env DISCORD_WEBHOOK_URL.
    - Retries on 429 and 5xx with headers-based or exponential backoff.
    """
    url = (
        webhook_url
        or payload.pop("_webhook_url", None)
        or os.getenv("DISCORD_WEBHOOK_URL")
    )
    if not url:
        return False
    attempt = 0
    while True:
        attempt += 1
        try:
            resp = requests.post(url, json=payload, timeout=10)
            # 204 is the common success for Discord webhooks, accept any 2xx.
            if 200 <= resp.status_code < 300:
                return True
            # Handle rate limits / transient errors
            if resp.status_code == 429 or 500 <= resp.status_code < 600:
                if attempt > max_retries:
                    log.warning(
                        "alert_error http_status=%s retries_exhausted", resp.status_code
                    )
                    return False
                # Respect headers if present
                retry_after_hdr = resp.headers.get("Retry-After") or resp.headers.get(
                    "X-RateLimit-Reset-After"
                )
                try:
                    # Discord sometimes sends Retry-After in ms; be lenient
                    sleep_s = (
                        float(retry_after_hdr) if retry_after_hdr else 0.5 * attempt
                    )
                    # If the header looks like milliseconds, scale down
                    if sleep_s > 60 and sleep_s > 1000:
                        sleep_s = sleep_s / 1000.0
                except Exception:
                    sleep_s = 0.5 * attempt
                time.sleep(min(max(sleep_s, 0.2), 10.0))
                continue
            log.warning("alert_error http_status=%s", resp.status_code)
            return False
        except Exception as e:
            if attempt > max_retries:
                log.warning(
                    "alert_error err=%s retries_exhausted",
                    e.__class__.__name__,
                    exc_info=True,
                )
                return False
            time.sleep(0.5 * attempt)
            continue


def send_alert_safe(*args, **kwargs) -> bool:
    """
    Post a Discord alert. Returns True on success, False on skip/error.

    - If record_only=True: log and return True (treated as success, but no post).
    - If webhook is missing: return False (caller may log a skip).
    - Network or non-2xx/204 responses: log a warning and return False.
    """
    # Back-compat: accept either a single payload dict OR the legacy signature.
    if len(args) == 1 and not kwargs and isinstance(args[0], dict):
        payload = args[0]
        item_dict = payload.get("item") or payload.get("item_dict") or {}
        scored = payload.get("scored")
        last_price = payload.get("last_price")
        last_change_pct = payload.get("last_change_pct")
        record_only = bool(payload.get("record_only", False))
        webhook_url = payload.get("webhook_url")
    else:
        item_dict = kwargs.get("item_dict") or (args[0] if len(args) > 0 else {})
        scored = kwargs.get("scored") or (args[1] if len(args) > 1 else None)
        last_price = kwargs.get("last_price") or (args[2] if len(args) > 2 else None)
        last_change_pct = kwargs.get("last_change_pct") or (
            args[3] if len(args) > 3 else None
        )
        record_only = bool(
            kwargs.get("record_only")
            if "record_only" in kwargs
            else (args[4] if len(args) > 4 else False)
        )
        webhook_url = kwargs.get("webhook_url") or (args[5] if len(args) > 5 else None)

    source = item_dict.get("source") or "unknown"
    ticker = (item_dict.get("ticker") or "").upper()

    if record_only:
        log.info("alert_record_only source=%s ticker=%s", source, ticker)
        return True
    if not webhook_url:
        return False

    content = _format_discord_content(item_dict, last_price, last_change_pct, scored)
    # Post via the shared primitive with polite retries
    ok = post_discord_json({"content": content}, webhook_url=webhook_url, max_retries=2)
    if not ok:
        # Add source/ticker context on failure to aid triage
        log.warning("alert_error source=%s ticker=%s", source, ticker)
    return ok
