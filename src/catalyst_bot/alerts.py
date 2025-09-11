# src/catalyst_bot/alerts.py
from __future__ import annotations

import os
import threading
import time
from typing import Any, Dict, Iterable, Optional, Tuple

import requests

from .alerts_rate_limit import limiter_allow, limiter_key_from_payload
from .config import get_settings
from .logging_utils import get_logger
from .market import get_intraday_indicators

log = get_logger("alerts")

alert_lock = threading.Lock()
_alert_downgraded = False


def _mask_webhook(url: str | None) -> str:
    """Return a scrubbed identifier for a Discord webhook (avoid leaking secrets)."""
    if not url:
        return "<unset>"
    try:
        tail = str(url).rsplit("/", 1)[-1]
        return f"...{tail[-8:]}"
    except Exception:
        return "<masked>"


# --- Simple per-webhook rate limiter state ---
_RL_LOCK = threading.Lock()
_RL_STATE: Dict[str, Dict[str, float]] = {}
_DEFAULT_MIN_INTERVAL = 0.45  # seconds between posts as a courtesy buffer
# Debug switch to surface limiter decisions
_RL_DEBUG = os.getenv("ALERTS_RL_DEBUG", "0").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}
# Make the courtesy spacing configurable (milliseconds) via env ALERTS_MIN_INTERVAL_MS
try:
    _ms = float(os.getenv("ALERTS_MIN_INTERVAL_MS", "") or 0.0)
    if _ms > 0:
        _DEFAULT_MIN_INTERVAL = _ms / 1000.0
except Exception:
    pass


def _rl_should_wait(url: str) -> float:
    """
    Return seconds to wait before next post to this webhook (0 if safe to send).
    Uses 'next_ok_at' timestamp and a small default spacing to avoid 429s.
    """
    now = time.time()
    with _RL_LOCK:
        st = _RL_STATE.get(url) or {}
        next_ok_at = float(st.get("next_ok_at", 0.0))
        wait = max(0.0, next_ok_at - now)
        if wait == 0.0:
            # schedule a small spacing even if no header-based limit is active
            st["next_ok_at"] = now + _DEFAULT_MIN_INTERVAL
            _RL_STATE[url] = st
    if _RL_DEBUG and wait > 0:
        log.debug("alerts_rl prewait_s=%.3f url=%s", wait, url[:60])
    return wait


def _rl_note_headers(url: str, headers: Any, is_429: bool = False) -> None:
    """
    Update limiter window using Discord headers.
    - On 429: always wait for Reset-After / Retry-After.
    - On 2xx: *optionally* pace when the bucket is empty (Remaining <= 0),
      controlled by ALERTS_RESPECT_RL_ON_SUCCESS (default ON).
    """
    try:
        reset_after = headers.get("X-RateLimit-Reset-After")
        if reset_after is None and is_429:
            reset_after = headers.get("Retry-After")
        if reset_after is None:
            return

        # Decide if we should pace on success
        should_pace = bool(is_429)
        if not should_pace:
            if os.getenv("ALERTS_RESPECT_RL_ON_SUCCESS", "1").strip().lower() in {
                "1",
                "true",
                "yes",
                "on",
            }:
                rem = headers.get("X-RateLimit-Remaining")
                try:
                    if rem is not None and float(rem) <= 0:
                        should_pace = True
                except Exception:
                    # If the header is malformed, ignore.
                    pass
        if not should_pace:
            return

        wait_s = float(reset_after)
        # Some proxies send ms â€” scale down if value looks like milliseconds.
        if wait_s > 1000:
            wait_s = wait_s / 1000.0

        with _RL_LOCK:
            st = _RL_STATE.get(url) or {}
            st["next_ok_at"] = max(
                float(st.get("next_ok_at", 0.0)), time.time() + wait_s + 0.05
            )
            _RL_STATE[url] = st
        if _RL_DEBUG:
            try:
                rem = headers.get("X-RateLimit-Remaining")
            except Exception:
                rem = None
            log.debug(
                "alerts_rl window set is_429=%s remaining=%s reset_after=%.3fs url=%s",
                bool(is_429),
                rem,
                wait_s,
                url[:60],
            )
    except Exception:
        return


def _post_discord_with_backoff(
    url: str, payload: dict, session=None
) -> Tuple[bool, int | None]:
    """
    Synchronous post with soft pre-wait, header-aware backoff, and one retry.
    Return (ok, status_code).
    """
    # 0) pre-wait if a previous call asked us to
    wait = _rl_should_wait(url)
    if wait > 0:
        time.sleep(wait)

    def _do_post():
        resp = (session or requests).post(url, json=payload, timeout=10)
        _rl_note_headers(url, resp.headers, is_429=(resp.status_code == 429))
        return resp

    resp = _do_post()
    if 200 <= resp.status_code < 300:
        return True, resp.status_code
    if resp.status_code == 429:
        # sleep based on headers then retry once
        wait = float(
            resp.headers.get("X-RateLimit-Reset-After")
            or resp.headers.get("Retry-After")
            or 1.0
        )
        # If a proxy gave milliseconds, scale to seconds
        if wait > 1000:
            wait = wait / 1000.0
        time.sleep(min(max(wait, 0.5), 5.0))
        resp2 = _do_post()
        return (200 <= resp2.status_code < 300), resp2.status_code
    return False, getattr(resp, "status_code", None)


def _fmt_change(change: Optional[float]) -> str:
    if change is None:
        return "n/a"
    try:
        return f"{change:+.2f}%"
    except Exception:
        return "n/a"


# --- Mentions safety: avoid accidental pings -------------------------------
# DISABLE_MENTIONS_STRICT=1 (default) will also neutralize bare @word tokens.
_STRICT_DEPING = os.getenv("DISABLE_MENTIONS_STRICT", "1").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}


def _deping(text: Any) -> str:
    """Neutralize @everyone/@here and user/role mentions to avoid pings."""
    if text is None:
        return ""
    s = str(text)
    # cheap/safe: break @everyone / @here
    s = s.replace("@everyone", "@\u200beveryone").replace("@here", "@\u200bhere")
    # also break <@...> and <@&...> forms
    s = s.replace("<@", "<@\u200b")
    if _STRICT_DEPING:
        import re

        # break bare @User (but leave emails like foo@bar.com alone)
        s = re.sub(r"(?<!\w)@(?=[A-Za-z])", "@\u200b", s)
    return s


# ---------------- Admin summary + indicators helpers ------------------------


def post_admin_summary_md(summary_path: Optional[str] = None) -> bool:
    """
    Post first ~30 non-empty lines from an analyzer summary markdown file as an
    embed to DISCORD_ADMIN_WEBHOOK when FEATURE_ADMIN_EMBED=1. Returns bool.
    """
    try:
        s = get_settings()
    except Exception:
        return False
    if not getattr(s, "feature_admin_embed", False):
        return False
    webhook = getattr(s, "admin_webhook_url", None)
    if not webhook:
        return False
    import glob
    import os

    path = summary_path or getattr(s, "admin_summary_path", None)
    if not path:
        cands = glob.glob(os.path.join(str(s.out_dir), "analyzer", "summary_*.md"))
        cands += glob.glob(os.path.join(str(s.out_dir), "summary_*.md"))
        path = max(cands, key=os.path.getmtime) if cands else None
    if not path or not os.path.exists(path):
        return False
    try:
        lines = [
            ln.strip()
            for ln in open(path, "r", encoding="utf-8", errors="ignore")
            .read()
            .splitlines()
        ]
    except Exception:
        return False
    preview = "\n".join([ln for ln in lines if ln][:30]).strip()
    if not preview:
        return False
    payload = {
        "username": "Analyzer Admin",
        "embeds": [{"title": "Analyzer Summary", "description": preview[:3900]}],
    }
    return post_discord_json(payload, webhook_url=webhook)


def enrich_with_indicators(
    embed: Dict[str, Any], indicators: Optional[Dict[str, Any]]
) -> Dict[str, Any]:
    """Append VWAP/RSI fields if present."""
    try:
        if indicators:
            fields = embed.setdefault("fields", [])
            if indicators.get("vwap") is not None:
                fields.append(
                    {
                        "name": "VWAP",
                        "value": f"{float(indicators['vwap']):.4f}",
                        "inline": True,
                    }
                )
            if indicators.get("rsi14") is not None:
                fields.append(
                    {
                        "name": "RSI(14)",
                        "value": f"{float(indicators['rsi14']):.1f}",
                        "inline": True,
                    }
                )
    except Exception:
        pass
    return embed


# ---------------------------------------------------------------------------
# Per-cycle alert downgrade reset
# The runner invokes ``reset_cycle_downgrade()`` at the start of each cycle.
# Provide a simple no‑op implementation so the import doesn’t fail.
def reset_cycle_downgrade() -> None:
    """Clear per-cycle downgrade flags (no-op stub)."""
    # If there is per-cycle state to reset (e.g., _alert_downgraded), do it here.
    global _alert_downgraded
    _alert_downgraded = False
    return None


def _format_discord_content(
    item: Dict[str, Any],
    last_price: Optional[float],
    last_change_pct: Optional[float],
    scored: Optional[Any] = None,
) -> str:
    """Compose a compact, readable Discord message body."""
    ticker = (item.get("ticker") or "n/a").upper()
    title = _deping(item.get("title") or "(no title)")
    source = item.get("source") or "unknown"
    ts = item.get("ts") or ""
    link = _deping(item.get("link") or "")

    # Avoid showing $0.00 when price is unknown/missing
    if last_price in (None, "", 0, 0.0, "0", "0.0"):
        px = "n/a"
    else:
        px = f"{float(last_price):.2f}"
    chg = _fmt_change(last_change_pct)
    # Prefer ASCII separators for Windows consoles
    sep = " | "

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
    tags_part = f" | tags: {', '.join(map(str, tags))}" if tags else ""

    line1 = _deping(f"[{ticker}] {title}")
    line2 = _deping(f"{source}{sep}{ts}{sep}px={px} ({chg}){tags_part}")
    line3 = _deping(link)

    # Keep under Discord's limits; three short lines is plenty.
    body = f"{line1}\n{line2}\n{line3}".strip().strip()
    # Discord hard limit: 2000 chars (be safe at ~1900)
    if len(body) > 1900:
        body = body[:1870] + "\n... (truncated)"
    return body


def post_discord_json(
    payload: dict,
    webhook_url: str | None = None,
    *,
    max_retries: int = 2,
) -> bool:
    """
    Minimal, reusable Discord poster with polite retry/backoff.
    - Uses webhook_url if provided, else payload.get('_webhook_url'),
      else env DISCORD_WEBHOOK_URL.
    - Retries on 429 and 5xx with headers-based / exponential backoff.
    """
    # Resolve webhook with generous aliases
    url = (
        webhook_url
        or payload.pop("_webhook_url", None)
        or os.getenv("DISCORD_WEBHOOK_URL", "").strip()
        or os.getenv("DISCORD_WEBHOOK", "").strip()
        or os.getenv("ALERT_WEBHOOK", "").strip()
    )
    if not url:
        return False
    status: int | None = None
    for attempt in range(1, max_retries + 1):
        ok, status = _post_discord_with_backoff(url, payload)
        if ok:
            return True
        # Retry on rate-limit or transient 5xx; small exponential backoff.
        if status is None or status == 429 or (500 <= status < 600):
            time.sleep(min(0.5 * attempt, 3.0))
            continue
        # Non-retryable error (4xx other than 429)
        log.warning("alert_error http_status=%s", status)
        return False
    log.warning("alert_error http_status=%s retries_exhausted", status)
    return False


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

    # If a prior error downgraded alerts, record-only
    if _alert_downgraded:
        log.info("alert_record_only source=%s ticker=%s downgraded", source, ticker)
        return True

    # Log where the webhook came from (explicit arg vs env fallback)
    if webhook_url:
        try:
            _env_w = os.getenv("DISCORD_WEBHOOK_URL") or ""
            _src = "env" if (_env_w and webhook_url == _env_w) else "arg"
            log.debug(
                "discord_post_target source=%s webhook=%s",
                _src,
                _mask_webhook(webhook_url),
            )
        except Exception:
            pass
    # Allow env fallback: only bail if neither an explicit webhook nor the
    # DISCORD_WEBHOOK_URL env var is available.
    if not (webhook_url or os.getenv("DISCORD_WEBHOOK_URL", "").strip()):
        return False

    # --- Optional per-key (ticker/title/link) rate limiting (opt-in) ---
    # Enable with: ALERTS_KEY_RATE_LIMIT=1 (or legacy HOOK_ALERTS_RATE_LIMIT=1)
    _truthy = {"1", "true", "yes", "on"}
    key_rl_enabled = (
        os.getenv("ALERTS_KEY_RATE_LIMIT", "0").strip().lower() in _truthy
    ) or (os.getenv("HOOK_ALERTS_RATE_LIMIT", "0").strip().lower() in _truthy)
    if key_rl_enabled:
        rl_key = limiter_key_from_payload(
            {
                "ticker": ticker,
                "title": item_dict.get("title"),
                "canonical_link": item_dict.get("link") or item_dict.get("url"),
            }
        )
        if not limiter_allow(rl_key):
            # Treat as a benign skip; don't warn or hit the network
            log.info(
                "alert_skip rate_limited key=%s source=%s ticker=%s",
                rl_key,
                source,
                ticker,
            )
            return True

    content = _format_discord_content(item_dict, last_price, last_change_pct, scored)
    payload = {"content": content, "allowed_mentions": {"parse": []}}
    try:
        _use = str(os.getenv("FEATURE_RICH_ALERTS", "0")).strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }
        if _use:
            payload["embeds"] = [
                _build_discord_embed(
                    item_dict=item_dict,
                    scored=scored,
                    last_price=last_price,
                    last_change_pct=last_change_pct,
                )
            ]
    except Exception:
        pass
    # Post via the shared primitive with polite retries
    ok = post_discord_json(payload, webhook_url=webhook_url, max_retries=2)
    if not ok:
        # Add source/ticker context on failure to aid triage
        log.warning("alert_error source=%s ticker=%s", source, ticker)
    return ok


def _build_discord_embed(
    *, item_dict: dict, scored: dict | None, last_price, last_change_pct
):
    """Build a compact, actionable Discord embed for an alert."""
    title = _deping((item_dict.get("title") or "").strip()[:240])
    link = _deping((item_dict.get("link") or "").strip())
    ts = item_dict.get("ts") or None
    src = (item_dict.get("source") or "").strip()

    # Tickers
    tkr = (item_dict.get("ticker") or "").strip().upper()
    tickers = item_dict.get("tickers") or ([tkr] if tkr else [])
    primary = tkr or (tickers[0] if tickers else "")

    # Price / change (treat 0/empty as missing to avoid "$0.00")
    if last_price in (None, "", 0, 0.0, "0", "0.0"):
        price_str = "n/a"
    elif isinstance(last_price, (int, float)):
        price_str = f"${last_price:0.2f}"
    else:
        price_str = str(last_price)
    chg_str = last_change_pct or ""

    # Score / sentiment (best-effort)
    sc = (scored or {}) if isinstance(scored, dict) else {}
    sent = (sc.get("sentiment") or sc.get("sent") or "") or "n/a"
    score = sc.get("score", sc.get("raw_score", None))
    if isinstance(score, (int, float)):
        score_str = f"{score:.2f}"
    else:
        score_str = "n/a" if score is None else str(score)

    # Color: green for up, red for down; fallback to Discord blurple
    color = 0x5865F2
    try:
        v = str(chg_str).replace("%", "").replace("+", "").strip()
        if v:
            color = 0x2ECC71 if float(v) >= 0 else 0xE74C3C
    except Exception:
        pass

    tval = ", ".join(tickers) if tickers else (primary or "-")
    tval = _deping(tval)
    # Try to surface a compact reason/rationale (best-effort)
    reason = ""
    kw = item_dict.get("keywords")
    if isinstance(item_dict.get("reason"), str):
        reason = item_dict["reason"].strip()
    elif isinstance(kw, (list, tuple)) and kw:
        reason = ", ".join([str(x) for x in kw[:6]])
    else:
        reason = str(sc.get("category") or sc.get("why") or "").strip()

    embed = {
        "title": _deping(f"[{primary or '?'}] {title}")[:256],
        "url": link,
        "color": color,
        "timestamp": ts,  # ISO-8601 preferred
        "fields": [
            {"name": "Price", "value": price_str or "n/a", "inline": True},
            {"name": "Change", "value": chg_str or "n/a", "inline": True},
            {"name": "Sentiment", "value": sent, "inline": True},
            {"name": "Score", "value": score_str, "inline": True},
            {"name": "Source", "value": src or "-", "inline": True},
            {"name": "Tickers", "value": tval, "inline": False},
        ],
        "footer": {"text": "Catalyst-Bot"},
    }
    if reason:
        embed["fields"].append(
            {"name": "Reason", "value": reason[:1024], "inline": False}
        )
    # Optionally add intraday indicators (VWAP/RSI14)
    try:
        s = get_settings()
        if getattr(s, "feature_indicators", False) and (item_dict.get("ticker")):
            ind = get_intraday_indicators(str(item_dict.get("ticker")))
            embed = enrich_with_indicators(embed, ind)
    except Exception:
        pass
    return embed
