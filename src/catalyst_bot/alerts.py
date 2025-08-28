# src/catalyst_bot/alerts.py
from __future__ import annotations

import os
from typing import Any, Dict, Optional

import requests

from .logging_utils import get_logger

log = get_logger("alerts")


# -----------------------------
# Helpers
# -----------------------------
def _fmt_change(change: Optional[float]) -> str:
    if change is None:
        return "n/a"
    try:
        return f"{float(change):+.2f}%"
    except Exception:
        return "n/a"


def _format_discord_content(
    item: Dict[str, Any],
    last_price: Optional[float],
    last_change_pct: Optional[float],
    scored: Optional[Any] = None,
) -> str:
    """Compose a compact Discord message body (3 short lines)."""
    ticker = (item.get("ticker") or "n/a").upper()
    title = item.get("title") or "(no title)"
    source = item.get("source") or (item.get("channel") or "unknown")
    ts = item.get("ts") or ""
    link = item.get("link") or item.get("url") or ""

    px = "n/a" if last_price is None else f"{float(last_price):.2f}"
    chg = _fmt_change(last_change_pct)

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
    return f"{line1}\n{line2}\n{line3}".strip()


def _redact(url: Optional[str]) -> str:
    if not url:
        return ""
    # Keep scheme + host only; redact token part.
    try:
        # Typical webhook looks like:
        # https://discord.com/api/webhooks/<id>/<token>
        parts = url.split("/")
        if len(parts) >= 5:
            return "/".join(parts[:5] + ["***redacted***"])
    except Exception:
        pass
    return "***redacted***"


def _env_webhook_for_channel(channel: Optional[str]) -> Optional[str]:
    """
    Choose a Discord webhook from env by channel, with sensible fallbacks.
    Supported envs (checked in order):
      - DISCORD_WEBHOOK_<CHANNEL>  (uppercased channel name, e.g. FILINGS, NEWS)
      - DISCORD_WEBHOOK_ALERTS
      - DISCORD_WEBHOOK_URL
    """
    ch = (channel or "").strip().upper()
    if ch:
        by_channel = os.getenv(f"DISCORD_WEBHOOK_{ch}")
        if by_channel:
            return by_channel

    return os.getenv("DISCORD_WEBHOOK_ALERTS") or os.getenv("DISCORD_WEBHOOK_URL")


# -----------------------------
# Public API
# -----------------------------
def send_alert_safe(
    item_dict: Dict[str, Any],
    scored: Optional[Any] = None,
    last_price: Optional[float] = None,
    last_change_pct: Optional[float] = None,
    record_only: bool = False,
    webhook_url: Optional[str] = None,
) -> bool:
    """
    Post a Discord alert. Returns True on success, False on skip/error.

    Call with just the payload:
        send_alert_safe({"channel": "filings", "ticker": "MSFT", "title": "MSFT filed 8-K"})

    Args (all optional except item_dict):
      - scored: optional scoring object with .tags
      - last_price, last_change_pct: enrich message if available
      - record_only: if True, log and return True (no network post)
      - webhook_url: override destination; otherwise selected by channel via env
    """
    channel = item_dict.get("channel") or item_dict.get("source") or "alerts"
    ticker = (item_dict.get("ticker") or "").upper()

    if record_only:
        log.info("alert_record_only channel=%s ticker=%s", channel, ticker)
        return True

    # Resolve destination if not provided explicitly.
    dest = webhook_url or _env_webhook_for_channel(channel)
    if not dest:
        # No destination; treat as skip so callers can proceed without crashing.
        log.info("alert_skip_no_webhook channel=%s ticker=%s", channel, ticker)
        return False

    content = _format_discord_content(item_dict, last_price, last_change_pct, scored)

    timeout = float(os.getenv("ALERTS_HTTP_TIMEOUT", "10"))
    try:
        resp = requests.post(dest, json={"content": content}, timeout=timeout)
        # Discord webhooks usually return 204 No Content on success.
        if resp.status_code in (200, 201, 202, 204):
            return True

        log.warning(
            "alert_http_error channel=%s ticker=%s status=%s dest=%s",
            channel,
            ticker,
            resp.status_code,
            _redact(dest),
        )
        return False
    except Exception as e:
        log.warning(
            "alert_post_exception channel=%s ticker=%s err=%s dest=%s",
            channel,
            ticker,
            str(e),
            _redact(dest),
        )
        return False
