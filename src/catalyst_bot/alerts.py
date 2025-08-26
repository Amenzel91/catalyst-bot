# src/catalyst_bot/alerts.py
from __future__ import annotations

from typing import Any, Dict, Optional

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

    # Try to show a couple high-signal tags if available
    tags_part = ""
    try:
        tags = getattr(scored, "tags", None) or []
        if tags:
            tags_part = " • tags: " + ", ".join(tags[:3])
    except Exception:
        pass

    line1 = f"[{ticker}] {title}"
    line2 = f"{source} • {ts} • px={px} ({chg}){tags_part}"
    line3 = link

    # Keep under Discord's limits; three short lines is plenty.
    return f"{line1}\n{line2}\n{line3}".strip()


def send_alert_safe(
    item_dict: Dict[str, Any],
    scored: Optional[Any],
    last_price: Optional[float],
    last_change_pct: Optional[float],
    record_only: bool,
    webhook_url: Optional[str],
) -> bool:
    """
    Post a Discord alert. Returns True on success, False on skip/error.

    - If record_only=True: log and return True (treated as success, but no post).
    - If webhook is missing: return False (caller may log a skip).
    - Network or non-2xx/204 responses: log a warning and return False.
    """
    source = item_dict.get("source") or "unknown"
    ticker = (item_dict.get("ticker") or "").upper()

    if record_only:
        log.info("alert_record_only source=%s ticker=%s", source, ticker)
        return True

    if not webhook_url:
        # No destination; let caller count it as a skip.
        return False

    content = _format_discord_content(item_dict, last_price, last_change_pct, scored)

    try:
        resp = requests.post(
            webhook_url,
            json={"content": content},
            timeout=10,
        )
        # Discord webhooks usually return 204 No Content on success.
        if resp.status_code in (200, 201, 202, 204):
            return True

        log.warning(
            "alert_error source=%s ticker=%s http_status=%s",
            source,
            ticker,
            resp.status_code,
        )
        return False
    except Exception:
        log.warning("alert_error source=%s ticker=%s", source, ticker)
        return False
