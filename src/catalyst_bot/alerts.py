# src/catalyst_bot/alerts.py
from __future__ import annotations

import asyncio
import base64
import os
import threading
import time
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional, Tuple

import requests

from .alerts_rate_limit import limiter_allow, limiter_key_from_payload
from .catalyst_badges import extract_catalyst_badges
from .charts import CHARTS_OK, get_quickchart_url, render_intraday_chart
from .config import get_settings
from .discord_upload import post_embed_with_attachment
from .indicator_utils import compute_composite_score
from .logging_utils import get_logger
from .market import get_intraday, get_intraday_indicators, get_momentum_indicators
from .ml_utils import extract_features, load_model, score_alerts
from .quickchart_post import get_quickchart_png_path

# Paper trading integration - MIGRATED TO TradingEngine (2025-11-26)
try:
    from .adapters.trading_engine_adapter import execute_with_trading_engine

    HAS_PAPER_TRADING = True

    # Legacy execute_paper_trade() is now a wrapper around TradingEngine
    def execute_paper_trade(*args, **kwargs):
        """Legacy wrapper - redirects to TradingEngine via adapter."""
        log.warning(
            "execute_paper_trade_legacy_called - use execute_with_trading_engine directly"
        )
        return None  # Legacy signature incompatible, use new adapter

    def paper_trading_enabled():
        """Check if paper trading is enabled via settings."""
        try:
            s = get_settings()
            return getattr(s, "feature_paper_trading", False)
        except Exception:
            return False

except ImportError:
    HAS_PAPER_TRADING = False

    def execute_with_trading_engine(*args, **kwargs):
        return False

    def execute_paper_trade(*args, **kwargs):
        return None

    def paper_trading_enabled():
        return False


# Advanced charts with timeframe buttons
try:
    from .chart_cache import get_cache
    from .charts_advanced import generate_multi_panel_chart
    from .discord_interactions import add_components_to_payload
    from .sentiment_gauge import generate_sentiment_gauge, log_sentiment_score
    from .trade_plan import calculate_trade_plan, get_embed_color_from_rr

    HAS_ADVANCED_CHARTS = True
except Exception:
    HAS_ADVANCED_CHARTS = False

log = get_logger("alerts")

alert_lock = threading.Lock()
_alert_downgraded = False

# Cached ML model to avoid reloading on every alert (GPU optimization)
_cached_ml_model = None
_cached_ml_model_path = None

# Webhook validation cache: stores validated webhooks to avoid repeated checks
_validated_webhooks = set()
_validation_lock = threading.Lock()


def get_alert_downgraded() -> bool:
    """Thread-safe getter for alert downgrade flag.

    CRITICAL BUG FIX: Always access _alert_downgraded within lock context
    to prevent race conditions in multi-threaded environments.

    Returns
    -------
    bool
        True if alerts are currently downgraded to record-only mode
    """
    with alert_lock:
        return _alert_downgraded


def set_alert_downgraded(val: bool) -> None:
    """Thread-safe setter for alert downgrade flag.

    CRITICAL BUG FIX: Always access _alert_downgraded within lock context
    to prevent race conditions in multi-threaded environments.

    Parameters
    ----------
    val : bool
        New value for the alert downgrade flag
    """
    global _alert_downgraded
    with alert_lock:
        _alert_downgraded = val


def _mask_webhook(url: str | None) -> str:
    """Return a scrubbed identifier for a Discord webhook (avoid leaking secrets)."""
    if not url:
        return "<unset>"
    try:
        tail = str(url).rsplit("/", 1)[-1]
        return f"...{tail[-8:]}"
    except Exception:
        return "<masked>"


def validate_webhook(url: str, force_revalidate: bool = False) -> bool:
    """
    Validate a Discord webhook URL before attempting to post.

    Sends a HEAD request to the webhook URL to verify it's reachable and valid.
    Results are cached to avoid repeated validation of the same webhook.

    Parameters
    ----------
    url : str
        The Discord webhook URL to validate
    force_revalidate : bool, optional
        If True, bypass cache and revalidate (default: False)

    Returns
    -------
    bool
        True if webhook is valid and reachable, False otherwise

    Notes
    -----
    This function prevents silent failures by checking webhooks on startup or
    when the webhook URL changes. Validation results are cached for performance.
    """
    if not url or not isinstance(url, str):
        log.error(
            "webhook_validation_failed reason=invalid_url url=%s", _mask_webhook(url)
        )
        return False

    # Check cache first (unless forcing revalidation)
    if not force_revalidate:
        with _validation_lock:
            if url in _validated_webhooks:
                log.debug("webhook_validation_cached url=%s", _mask_webhook(url))
                return True

    # Validate webhook format (must be Discord webhook URL)
    if (
        "discord.com/api/webhooks/" not in url
        and "discordapp.com/api/webhooks/" not in url
    ):
        log.error(
            "webhook_validation_failed reason=invalid_format url=%s", _mask_webhook(url)
        )
        return False

    try:
        # Send HEAD request to check if webhook is reachable
        # Use a short timeout to avoid blocking startup
        log.info("webhook_validation_testing url=%s", _mask_webhook(url))

        response = requests.head(url, timeout=5)

        # Discord webhooks should return 200 OK for HEAD requests
        if response.status_code == 200:
            # Cache successful validation
            with _validation_lock:
                _validated_webhooks.add(url)
            log.info(
                "webhook_validation_success url=%s status=%d",
                _mask_webhook(url),
                response.status_code,
            )
            return True
        elif response.status_code == 404:
            log.error(
                "webhook_validation_failed reason=not_found url=%s status=%d",
                _mask_webhook(url),
                response.status_code,
            )
            return False
        elif response.status_code == 401:
            log.error(
                "webhook_validation_failed reason=unauthorized url=%s status=%d",
                _mask_webhook(url),
                response.status_code,
            )
            return False
        else:
            log.warning(
                "webhook_validation_unexpected url=%s status=%d",
                _mask_webhook(url),
                response.status_code,
            )
            # Accept other 2xx codes as valid
            if 200 <= response.status_code < 300:
                with _validation_lock:
                    _validated_webhooks.add(url)
                return True
            return False

    except requests.exceptions.Timeout:
        log.error("webhook_validation_failed reason=timeout url=%s", _mask_webhook(url))
        return False
    except requests.exceptions.ConnectionError as e:
        log.error(
            "webhook_validation_failed reason=connection_error url=%s err=%s",
            _mask_webhook(url),
            str(e)[:100],
        )
        return False
    except requests.exceptions.RequestException as e:
        log.error(
            "webhook_validation_failed reason=request_error url=%s err=%s",
            _mask_webhook(url),
            str(e)[:100],
        )
        return False
    except Exception as e:
        log.error(
            "webhook_validation_failed reason=unexpected_error url=%s err=%s",
            _mask_webhook(url),
            str(e)[:100],
            exc_info=True,
        )
        return False


# --- Simple per-webhook rate limiter state ---
# WARNING: SINGLE-PROCESS LIMITATION
# This rate limiter uses in-memory state (_RL_STATE dict) which is NOT shared
# across multiple bot processes. If you run multiple instances of the bot
# (e.g., for redundancy or load balancing), each process will have its own
# independent rate limit state.
#
# IMPLICATION: Multiple bot instances can collectively exceed Discord's rate
# limits because they don't coordinate with each other. This can lead to 429
# errors and temporary service degradation.
#
# SOLUTION FOR MULTI-INSTANCE DEPLOYMENTS:
# For production deployments with multiple bot processes, implement a
# Redis-based rate limiter that shares state across all instances. Example:
#
#   import redis
#   client = redis.Redis(host='localhost', port=6379)
#
#   def _rl_should_wait_distributed(url: str) -> float:
#       key = f"rl:{hashlib.md5(url.encode()).hexdigest()}"
#       next_ok = client.get(key)
#       if next_ok:
#           return max(0, float(next_ok) - time.time())
#       return 0
#
# Until Redis integration is implemented, this limiter is suitable for:
# - Single-process deployments (most common use case)
# - Development/testing environments
# - Low-volume production deployments with a single bot instance
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

    WARNING: This function uses in-memory state that is NOT shared across
    multiple bot processes. For multi-instance deployments, implement a
    Redis-based solution (see module-level comments above).
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
) -> Tuple[bool, int | None, str | None]:
    """
    Synchronous post with soft pre-wait, header-aware backoff, and one retry.
    Return (ok, status_code, error_details).

    The error_details will contain Discord's response text for 4xx errors,
    making it possible to diagnose validation failures.
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
        return True, resp.status_code, None
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
        ok = 200 <= resp2.status_code < 300
        error_text = None if ok else resp2.text[:500]  # Limit error text to 500 chars
        return ok, resp2.status_code, error_text
    # Capture error details for 4xx errors
    error_text = resp.text[:500] if 400 <= resp.status_code < 500 else None
    return False, getattr(resp, "status_code", None), error_text


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


def _format_time_ago(published_at: str) -> str:
    """
    Convert timestamp to '2min ago' format for clean display.

    Args:
        published_at: ISO timestamp string

    Returns:
        Human-readable time ago string (e.g., "2min ago", "3h ago")
    """
    try:
        from dateutil import parser as date_parser

        # Parse the timestamp
        if isinstance(published_at, str):
            pub_time = date_parser.isoparse(published_at)
        else:
            pub_time = published_at

        # Ensure timezone aware
        if pub_time.tzinfo is None:
            pub_time = pub_time.replace(tzinfo=timezone.utc)

        now = datetime.now(timezone.utc)
        diff = (now - pub_time).total_seconds()

        if diff < 60:
            return "just now"
        elif diff < 3600:
            mins = int(diff / 60)
            return f"{mins}min ago"
        elif diff < 86400:
            hours = int(diff / 3600)
            return f"{hours}h ago"
        else:
            days = int(diff / 86400)
            return f"{days}d ago"
    except Exception:
        return "recently"


# ---------------- Admin summary + indicators helpers ------------------------


def post_admin_summary_md(summary_path: Optional[str] = None) -> bool:
    """
    Post a digest of an analyzer summary Markdown file to the admin webhook.

    When FEATURE_ADMIN_EMBED is enabled, this helper reads the specified
    ``summary_path`` (or the most recent summary under ``out/analyzer``),
    extracts the first ~30 non-empty lines, and composes a Discord embed
    containing the preview.  If a pending analyzer plan exists and the
    approval loop is active, the embed will include information about the
    plan and interactive Approve/Reject buttons.  Returns True on
    successful post, False otherwise.
    """
    try:
        s = get_settings()
    except Exception:
        return False
    # Feature flag must be enabled
    if not getattr(s, "feature_admin_embed", False):
        return False
    webhook = getattr(s, "admin_webhook_url", None)
    if not webhook:
        return False
    import glob
    import os

    # Resolve summary path: explicit argument → ADMIN_SUMMARY_PATH → latest file
    path = summary_path or getattr(s, "admin_summary_path", None)
    if not path:
        cands = glob.glob(os.path.join(str(s.out_dir), "analyzer", "summary_*.md"))
        cands += glob.glob(os.path.join(str(s.out_dir), "summary_*.md"))
        path = max(cands, key=os.path.getmtime) if cands else None
    if not path or not os.path.exists(path):
        return False
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as fh:
            lines = [ln.strip() for ln in fh.read().splitlines()]
    except Exception:
        return False
    # Grab first 30 non-empty lines for preview
    preview_lines = [ln for ln in lines if ln][:30]
    preview = "\n".join(preview_lines).strip()
    if not preview:
        return False

    # Build base embed
    embed: Dict[str, Any] = {
        "title": "Analyzer Summary",
        "description": preview[:3900],
    }

    # Include pending plan details when approval loop is active and a plan exists
    # Avoid circular import by importing inside the function
    try:
        from .approval import get_pending_plan

        # Only include pending info when the user has enabled approval loop
        enable_loop = getattr(s, "feature_approval_loop", False) or (
            os.getenv("FEATURE_APPROVAL_LOOP", "").strip().lower()
            in {"1", "true", "yes", "on"}
        )
        if enable_loop:
            pending = get_pending_plan()
            if pending:
                plan_id = str(
                    pending.get("planId") or pending.get("plan_id") or ""
                ).strip()
                plan = pending.get("plan") or {}
                weights = plan.get("weights") or {}
                new_keywords = plan.get("new_keywords") or {}
                # Summarize weights and new keywords in a field
                summary_parts = []  # type: ignore[var-annotated]
                if weights:
                    # Only show up to 5 entries to avoid long embeds
                    for idx, (k, v) in enumerate(sorted(weights.items())):
                        if idx >= 5:
                            summary_parts.append("...")
                            break
                        try:
                            summary_parts.append(f"{k}: {float(v):.3f}")
                        except Exception:
                            summary_parts.append(f"{k}: {v}")
                if new_keywords:
                    kw_list = ", ".join(list(new_keywords.keys())[:5])
                    summary_parts.append(f"New keywords: {kw_list}")
                pending_desc = (
                    "\n".join(summary_parts)
                    if summary_parts
                    else "Pending changes available."
                )
                fields = embed.setdefault("fields", [])
                fields.append(
                    {
                        "name": "Pending Plan",
                        "value": f"ID: `{plan_id}`\n{pending_desc}",
                        "inline": False,
                    }
                )
                # Prepare interactive buttons for approval if supported by Discord
                components = [
                    {
                        "type": 1,  # action row
                        "components": [
                            {
                                "type": 2,
                                "label": "Approve Plan",
                                "style": 3,  # success (green)
                                "custom_id": f"approve_{plan_id}",
                            },
                            {
                                "type": 2,
                                "label": "Reject Plan",
                                "style": 4,  # danger (red)
                                "custom_id": f"reject_{plan_id}",
                            },
                        ],
                    }
                ]
            else:
                components = []
        else:
            components = []
    except Exception:
        components = []

    payload: Dict[str, Any] = {
        "username": "Analyzer Admin",
        "embeds": [embed],
    }
    # Add components only if present (discord rejects empty components)
    if components:
        payload["components"] = components
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
    with alert_lock:
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
    error_details: str | None = None
    for attempt in range(1, max_retries + 1):
        ok, status, error_details = _post_discord_with_backoff(url, payload)
        if ok:
            return True
        # Retry on rate-limit or transient 5xx; small exponential backoff.
        if status is None or status == 429 or (500 <= status < 600):
            time.sleep(min(0.5 * attempt, 3.0))
            continue
        # Non-retryable error (4xx other than 429)
        if error_details:
            log.warning(
                "alert_error http_status=%s discord_error=%s", status, error_details
            )
        else:
            log.warning("alert_error http_status=%s", status)
        return False
    if error_details:
        log.warning(
            "alert_error http_status=%s retries_exhausted discord_error=%s",
            status,
            error_details,
        )
    else:
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
        market_info = payload.get("market_info") or {}
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
        market_info = kwargs.get("market_info") or {}

    # Extract feature flags from market_info (WAVE 0.0 Phase 2)
    features = market_info.get("features", {})
    features.get("llm_enabled", True)
    charts_enabled = features.get("charts_enabled", True)

    source = item_dict.get("source") or "unknown"
    ticker = (item_dict.get("ticker") or "").upper()

    if record_only:
        log.info("alert_record_only source=%s ticker=%s", source, ticker)
        return True

    # If a prior error downgraded alerts, record-only
    with alert_lock:
        downgraded = _alert_downgraded
    if downgraded:
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

    # Set webhook_url from env if not provided
    if not webhook_url:
        webhook_url = os.getenv("DISCORD_WEBHOOK_URL", "").strip()

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

    # Calculate trade plan for alerts (entry/stop/target levels)
    trade_plan_for_embed = None
    try:
        if HAS_ADVANCED_CHARTS and last_price and ticker:
            # Get daily data for ATR and S/R calculations
            trade_df = get_intraday(ticker, interval="1d", output_size="full")
            if trade_df is not None and len(trade_df) >= 14:
                trade_plan_for_embed = calculate_trade_plan(
                    ticker=ticker,
                    current_price=float(last_price),
                    df=trade_df,
                    atr_multiplier=2.0,
                    min_rr_ratio=1.5,
                )
                log.debug(
                    "trade_plan_for_embed ticker=%s success=%s",
                    ticker,
                    trade_plan_for_embed is not None,
                )
    except Exception as e:
        log.debug("trade_plan_for_embed_failed ticker=%s err=%s", ticker, str(e))

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
                    trade_plan=trade_plan_for_embed,
                )
            ]
    except Exception as e:
        log.warning("embed_build_failed ticker=%s err=%s", ticker, str(e))
    # Optional QuickChart Route-A: POST /chart -> attach PNG (fully local)
    try:
        use_post = os.getenv("FEATURE_QUICKCHART_POST", "0").strip().lower() in (
            "1",
            "true",
            "yes",
            "on",
        )
        # Only attempt when we already built a rich embed (same condition as legacy)
        if (
            use_post
            and charts_enabled
            and "embeds" in payload
            and payload["embeds"]
            and ticker
        ):
            # Try to render and save a PNG locally
            img_path = get_quickchart_png_path(
                ticker,
                bars=int(os.getenv("QUICKCHART_BARS", "50")),
                out_dir=os.getenv("QUICKCHART_IMAGE_DIR", "out/charts"),
            )
            if img_path:
                # Point the embed to the attachment URI and post multipart
                embed0 = payload["embeds"][0]
                embed0["image"] = {"url": f"attachment://{img_path.name}"}
                if webhook_url:
                    # Post file + payload_json in one multipart request
                    ok_file = post_embed_with_attachment(webhook_url, embed0, img_path)
                    if ok_file:
                        return True
                # If multipart failed, fall through to legacy JSON poster
        elif use_post and not charts_enabled:
            log.debug("quickchart_skipped ticker=%s reason=charts_disabled", ticker)
    except Exception as e:
        log.warning("quickchart_post_failed ticker=%s err=%s", ticker, str(e))

    # Optional Sentiment Gauge Visual
    gauge_path = None
    try:
        use_gauge = os.getenv("FEATURE_SENTIMENT_GAUGE", "1").strip().lower() in (
            "1",
            "true",
            "yes",
            "on",
        )
        # Respect market hours chart gating
        use_gauge = use_gauge and charts_enabled

        log.debug(
            "sentiment_gauge_check use_gauge=%s has_advanced=%s "
            "embeds_in_payload=%s payload_embeds=%s scored=%s ticker=%s charts_enabled=%s",
            use_gauge,
            HAS_ADVANCED_CHARTS,
            "embeds" in payload,
            bool(payload.get("embeds")),
            bool(scored),
            ticker,
            charts_enabled,
        )

        if (
            use_gauge
            and HAS_ADVANCED_CHARTS
            and "embeds" in payload
            and payload["embeds"]
            and scored
        ):
            # Extract aggregate score - handle both dict and ScoredItem types
            aggregate_score = 0
            if isinstance(scored, dict):
                aggregate_score = (
                    scored.get("aggregate_score")
                    or scored.get("score")
                    or scored.get("sentiment")
                    or 0
                )
            else:
                # ScoredItem dataclass - use sentiment attribute
                aggregate_score = getattr(scored, "sentiment", 0)

            if isinstance(aggregate_score, (int, float)):
                # Scale score to -100 to +100 range if needed
                if -1 <= aggregate_score <= 1:
                    aggregate_score = aggregate_score * 100

                gauge_path = generate_sentiment_gauge(
                    aggregate_score, ticker, style="dark"
                )

                if gauge_path:
                    log.info(
                        "sentiment_gauge_generated ticker=%s score=%.1f",
                        ticker,
                        aggregate_score,
                    )

                    # Log score for calibration
                    try:
                        log_sentiment_score(
                            ticker,
                            aggregate_score,
                            last_price,
                            metadata={
                                "source": source,
                                "timestamp": datetime.now(timezone.utc).isoformat(),
                            },
                        )
                    except Exception:
                        pass
    except Exception as e:
        log.warning("sentiment_gauge_failed ticker=%s err=%s", ticker, str(e))

    # Optional Advanced Multi-Panel Charts with Timeframe Buttons
    # Gate charts based on market_info when available
    try:
        use_advanced = os.getenv("FEATURE_ADVANCED_CHARTS", "0").strip().lower() in (
            "1",
            "true",
            "yes",
            "on",
        )
        # Respect market hours chart gating
        use_advanced = use_advanced and charts_enabled

        log.debug(
            "advanced_charts_check use_advanced=%s has_advanced=%s "
            "embeds_in_payload=%s payload_embeds=%s ticker=%s charts_enabled=%s",
            use_advanced,
            HAS_ADVANCED_CHARTS,
            "embeds" in payload,
            bool(payload.get("embeds")),
            ticker,
            charts_enabled,
        )

        if (
            use_advanced
            and charts_enabled
            and HAS_ADVANCED_CHARTS
            and "embeds" in payload
            and payload["embeds"]
            and ticker
        ):
            log.debug("generating_advanced_chart_start ticker=%s", ticker)
            # Get default timeframe from env (default: 1D)
            default_tf = os.getenv("CHART_DEFAULT_TIMEFRAME", "1D").upper()

            # Try cache first
            cache = get_cache()
            chart_path = cache.get_cached_chart(ticker, default_tf)
            log.info(
                "CHART_DEBUG cache_check ticker=%s tf=%s cached_path=%s from_cache=%s",
                ticker,
                default_tf,
                chart_path,
                chart_path is not None,
            )

            if chart_path is None:
                log.info(
                    "CHART_DEBUG cache_miss ticker=%s tf=%s generating_new_chart=True",
                    ticker,
                    default_tf,
                )
                # Generate new multi-panel chart
                log.info(
                    "generating_advanced_chart ticker=%s tf=%s", ticker, default_tf
                )
                log.debug(
                    "calling_generate_multi_panel_chart ticker=%s tf=%s",
                    ticker,
                    default_tf,
                )

                # Build catalyst event annotation data
                catalyst_event = None
                try:
                    # Extract news title and timestamp for annotation
                    event_title = item_dict.get("title", "")
                    event_ts = item_dict.get("ts")  # ISO timestamp from feed

                    # Determine event type (positive or negative)
                    event_type = "positive"
                    if scored:
                        if isinstance(scored, dict):
                            if scored.get("alert_type") == "NEGATIVE":
                                event_type = "negative"
                        else:
                            if getattr(scored, "alert_type", None) == "NEGATIVE":
                                event_type = "negative"

                    # Truncate title to fit on chart
                    if event_title and event_ts:
                        label = event_title[:40]  # Keep it concise
                        if len(event_title) > 40:
                            label += "..."

                        catalyst_event = {
                            "timestamp": event_ts,
                            "label": label,
                            "type": event_type,
                        }
                except Exception as e:
                    log.debug("catalyst_event_build_failed err=%s", str(e))

                # Calculate trade plan for entry/stop/target annotations
                trade_plan_data = None
                try:
                    # Fetch intraday data for trade plan calculations
                    current_price = item_dict.get("price")
                    if current_price:
                        # Get 1-month daily data for ATR and S/R calculations
                        trade_df = get_intraday(
                            ticker, interval="1d", output_size="full"
                        )
                        if trade_df is not None and len(trade_df) >= 14:
                            trade_plan_data = calculate_trade_plan(
                                ticker=ticker,
                                current_price=float(current_price),
                                df=trade_df,
                                atr_multiplier=2.0,
                                min_rr_ratio=1.5,
                            )
                            log.debug(
                                "trade_plan_calculated ticker=%s plan=%s",
                                ticker,
                                trade_plan_data,
                            )
                except Exception as e:
                    log.debug(
                        "trade_plan_calculation_failed ticker=%s err=%s", ticker, str(e)
                    )

                log.info(
                    "CHART_DEBUG generating chart ticker=%s tf=%s", ticker, default_tf
                )
                chart_path = generate_multi_panel_chart(
                    ticker,
                    timeframe=default_tf,
                    style="dark",
                    catalyst_event=catalyst_event,
                    trade_plan=trade_plan_data,
                )

                # Enhanced chart generation logging
                if chart_path:
                    log.info(
                        "CHART_DEBUG chart_generated ticker=%s path=%s exists=%s",
                        ticker,
                        chart_path,
                        chart_path.exists(),
                    )
                    if chart_path.exists():
                        file_stat = chart_path.stat()
                        log.info(
                            "CHART_DEBUG chart_file_stats ticker=%s size=%d modified=%s absolute_path=%s",
                            ticker,
                            file_stat.st_size,
                            file_stat.st_mtime,
                            chart_path.absolute(),
                        )
                    else:
                        log.error(
                            "CHART_ERROR chart_path_does_not_exist ticker=%s path=%s",
                            ticker,
                            chart_path,
                        )
                else:
                    log.error(
                        "CHART_ERROR chart_generation_returned_none ticker=%s", ticker
                    )

                if chart_path:
                    cache.cache_chart(ticker, default_tf, chart_path)

            log.debug(
                "chart_path_exists ticker=%s exists=%s",
                ticker,
                chart_path and chart_path.exists(),
            )
            if chart_path and chart_path.exists():
                # Update embed to reference the chart by filename
                log.info(
                    "CHART_DEBUG attaching_chart_to_embed ticker=%s chart_filename=%s",
                    ticker,
                    chart_path.name,
                )

                embed0 = payload["embeds"][0]

                # Log embed BEFORE modification
                log.info(
                    "EMBED_DEBUG before_modification ticker=%s embed_has_image=%s embed_has_thumbnail=%s",
                    ticker,
                    "image" in embed0,
                    "thumbnail" in embed0,
                )

                embed0["image"] = {"url": f"attachment://{chart_path.name}"}

                # Log embed AFTER modification
                log.info(
                    "EMBED_DEBUG after_modification ticker=%s image_url=%s",
                    ticker,
                    embed0.get("image", {}).get("url"),
                )
                log.info(
                    "EMBED_DEBUG chart_path=%s image_url=%s",
                    chart_path.name,
                    embed0.get("image", {}).get("url"),
                )
                log.info("EMBED_DEBUG embed_keys=%s", list(embed0.keys()))

                # Add sentiment gauge as thumbnail if available
                if gauge_path and gauge_path.exists():
                    embed0["thumbnail"] = {"url": f"attachment://{gauge_path.name}"}

                # Add footer with timeframe info
                if "footer" not in embed0:
                    embed0["footer"] = {}
                embed0["footer"][
                    "text"
                ] = f"Chart: {default_tf} | Click buttons to switch timeframes"

                log.info(
                    "PRE_COMPONENTS ticker=%s about to call add_components_to_payload",
                    ticker,
                )
                # Add interactive timeframe buttons
                payload = add_components_to_payload(
                    payload, ticker, current_timeframe=default_tf
                )
                log.info(
                    "POST_COMPONENTS ticker=%s payload_keys=%s",
                    ticker,
                    list(payload.keys()),
                )

                # Extract components from payload
                components = payload.get("components")
                log.info(
                    "components_extracted ticker=%s count=%d webhook_url=%s",
                    ticker,
                    len(components) if components else 0,
                    bool(webhook_url),
                )

                if webhook_url:
                    # Enhanced debugging before posting
                    log.info(
                        "CHART_DEBUG calling_post_embed_with_attachment ticker=%s",
                        ticker,
                    )
                    log.info(
                        "CHART_DEBUG pre_post ticker=%s chart_path=%s chart_exists=%s chart_size=%d",
                        ticker,
                        chart_path,
                        chart_path.exists(),
                        chart_path.stat().st_size if chart_path.exists() else 0,
                    )
                    log.info(
                        "CHART_DEBUG pre_post ticker=%s embed_image=%s embed_thumbnail=%s",
                        ticker,
                        embed0.get("image", {}).get("url"),
                        embed0.get("thumbnail", {}).get("url"),
                    )

                    # Post with multipart attachment (includes components if bot token configured)
                    # Include gauge as additional file if available
                    additional_files = (
                        [gauge_path] if gauge_path and gauge_path.exists() else None
                    )

                    if additional_files:
                        log.info(
                            "CHART_DEBUG additional_files_count=%d gauge_path=%s gauge_exists=%s",
                            len(additional_files),
                            gauge_path,
                            gauge_path.exists(),
                        )

                    ok_file = post_embed_with_attachment(
                        webhook_url,
                        embed0,
                        chart_path,
                        components=components,
                        additional_files=additional_files,
                    )

                    # Enhanced debugging after posting
                    log.info(
                        "CHART_DEBUG post_embed_result ticker=%s success=%s",
                        ticker,
                        ok_file,
                    )
                    if not ok_file:
                        log.error(
                            "CHART_ERROR post_embed_failed ticker=%s chart_path=%s webhook_url_present=%s",
                            ticker,
                            chart_path,
                            bool(webhook_url),
                        )
                    if ok_file:
                        log.info(
                            "alert_sent_advanced_chart ticker=%s tf=%s",
                            ticker,
                            default_tf,
                        )
                        return True
                    # If multipart failed, fall through
                else:
                    log.warning("NO_WEBHOOK_URL ticker=%s cannot upload chart", ticker)
    except Exception as e:
        log.warning(
            "advanced_chart_failed ticker=%s err=%s", ticker, str(e), exc_info=True
        )

    # Clean up attachment references before JSON-only fallback
    # Discord returns 400 if embed references attachments that aren't included
    try:
        if "embeds" in payload and payload["embeds"]:
            for embed in payload["embeds"]:
                # Remove image/thumbnail references that start with "attachment://"
                if "image" in embed and isinstance(embed.get("image"), dict):
                    url = embed["image"].get("url", "")
                    if url.startswith("attachment://"):
                        log.debug(
                            "removing_attachment_reference type=image url=%s", url
                        )
                        del embed["image"]
                if "thumbnail" in embed and isinstance(embed.get("thumbnail"), dict):
                    url = embed["thumbnail"].get("url", "")
                    if url.startswith("attachment://"):
                        log.debug(
                            "removing_attachment_reference type=thumbnail url=%s", url
                        )
                        del embed["thumbnail"]
    except Exception as e:
        log.warning("attachment_cleanup_failed ticker=%s err=%s", ticker, str(e))

    # Post via the shared primitive with polite retries (legacy behavior)
    ok = post_discord_json(payload, webhook_url=webhook_url, max_retries=2)
    if not ok:
        # Add source/ticker context on failure to aid triage
        # Enhanced logging for debugging RANI-style failures
        webhook_status = "present" if webhook_url else "missing"
        env_webhook = os.getenv("DISCORD_WEBHOOK_URL", "").strip()
        env_status = "present" if env_webhook else "missing"
        has_embeds = (
            "yes"
            if (payload.get("embeds") and len(payload.get("embeds", [])) > 0)
            else "no"
        )
        log.warning(
            "alert_error source=%s ticker=%s webhook=%s env_webhook=%s has_embeds=%s payload_keys=%s",
            source,
            ticker,
            webhook_status,
            env_status,
            has_embeds,
            list(payload.keys()),
        )

    # WAVE 1.2: Record alert for feedback tracking
    if ok:
        try:
            s = get_settings()
            if getattr(s, "feature_feedback_loop", False):
                # Import feedback module
                try:
                    # Generate alert ID from ticker, title, and link
                    import hashlib

                    from .feedback.database import record_alert

                    title = item_dict.get("title", "")
                    link = item_dict.get("link", "")
                    alert_content = f"{ticker}:{title}:{link}"
                    alert_id = hashlib.md5(alert_content.encode()).hexdigest()[:16]

                    # Extract keywords from scored item
                    keywords = []
                    if scored:
                        if isinstance(scored, dict):
                            keywords = (
                                scored.get("keywords")
                                or scored.get("tags")
                                or scored.get("categories")
                                or []
                            )
                        else:
                            keywords = (
                                getattr(scored, "keywords", None)
                                or getattr(scored, "tags", None)
                                or getattr(scored, "categories", None)
                                or []
                            )

                    # Determine catalyst type from scored data
                    catalyst_type = "unknown"
                    if scored:
                        if isinstance(scored, dict):
                            catalyst_type = (
                                scored.get("category")
                                or scored.get("catalyst_type")
                                or "unknown"
                            )
                        else:
                            catalyst_type = (
                                getattr(scored, "category", None)
                                or getattr(scored, "catalyst_type", None)
                                or "unknown"
                            )

                    # Record the alert
                    record_alert(
                        alert_id=alert_id,
                        ticker=ticker,
                        source=source,
                        catalyst_type=str(catalyst_type),
                        keywords=list(keywords) if keywords else None,
                        posted_price=last_price,
                    )

                    # Execute trade using TradingEngine (MIGRATED 2025-11-26)
                    if HAS_PAPER_TRADING and paper_trading_enabled():
                        try:
                            # Import extended hours detection
                            from decimal import Decimal

                            from .market_hours import is_extended_hours
                            from .runner import TRADING_ACTIVITY_STATS

                            # Get current settings
                            s = get_settings()

                            # Track signal generation attempt
                            TRADING_ACTIVITY_STATS["signals_generated"] = (
                                TRADING_ACTIVITY_STATS.get("signals_generated", 0) + 1
                            )

                            # Execute trade via TradingEngine adapter
                            success = execute_with_trading_engine(
                                item=scored,  # ScoredItem from classify()
                                ticker=ticker,
                                current_price=(
                                    Decimal(str(last_price)) if last_price else None
                                ),
                                extended_hours=is_extended_hours(),
                                settings=s,
                            )

                            if success:
                                # Track successful trade execution
                                TRADING_ACTIVITY_STATS["trades_executed"] = (
                                    TRADING_ACTIVITY_STATS.get("trades_executed", 0) + 1
                                )
                                log.info(
                                    "trading_engine_signal_executed ticker=%s extended_hours=%s",
                                    ticker,
                                    is_extended_hours(),
                                )
                            else:
                                log.debug(
                                    "trading_engine_signal_skipped ticker=%s reason=low_confidence_or_hold",
                                    ticker,
                                )
                        except Exception as trade_err:
                            log.error(
                                "trading_engine_execution_failed ticker=%s error=%s",
                                ticker,
                                str(trade_err),
                                exc_info=True,
                            )

                except Exception as feedback_err:
                    # Don't fail the alert if feedback recording fails
                    log.debug("feedback_recording_failed error=%s", str(feedback_err))
        except Exception:
            pass

    return ok


# ============================================================================
# WAVE 2: Progressive Alerts - Send First, Update Later Pattern
# ============================================================================


async def send_progressive_alert(
    alert_data: dict,
    webhook_url: str,
) -> Optional[dict]:
    """
    Send alert in 2 phases: immediate basic info, then update with LLM sentiment.

    Phase 1: Post immediately with VADER + keywords + price data
    Phase 2: Update embed with LLM sentiment when available (background)

    This pattern ensures traders see critical price data in 100-200ms, while
    LLM sentiment analysis (2-5s) is delivered asynchronously without blocking.

    Args:
        alert_data: Alert payload with item, scored, last_price, etc.
        webhook_url: Discord webhook URL

    Returns:
        Message dict with 'id' for editing later, or None on failure

    Environment Variables:
        FEATURE_PROGRESSIVE_ALERTS: Enable progressive alerts (default: 0)
    """
    try:
        import aiohttp
        import discord
        from discord import Webhook
    except ImportError:
        log.warning(
            "progressive_alerts_unavailable reason=discord_py_missing "
            "install with: pip install discord.py"
        )
        return None

    item = alert_data.get("item", {})
    scored = alert_data.get("scored", {})
    ticker = item.get("ticker", "???")
    title = item.get("title", "")

    # Build basic embed (no LLM yet)
    embed = discord.Embed(
        title=f"📈 {ticker} Alert",
        description=_deping(title[:200]),
        color=0xFFA500,  # Orange for pending
    )

    # Add price data (always available)
    last_price = alert_data.get("last_price")
    last_change = alert_data.get("last_change_pct")
    if last_price:
        embed.add_field(
            name="Price",
            value=(
                f"${last_price:,.2f} ({last_change:+.2f}%)"
                if last_change
                else f"${last_price:,.2f}"
            ),
            inline=True,
        )

    # Add fast sentiment (VADER + keywords)
    vader_sentiment = scored.get("sentiment", 0.0) if scored else 0.0
    keywords = scored.get("keywords", []) or scored.get("tags", []) if scored else []

    sentiment_emoji = (
        "🟢" if vader_sentiment > 0.1 else ("🔴" if vader_sentiment < -0.1 else "⚪")
    )
    kw_text = ", ".join(keywords[:3]) if keywords else "none"
    embed.add_field(
        name=f"{sentiment_emoji} Initial Sentiment",
        value=f"**Score:** {vader_sentiment:.3f}\n**Keywords:** {kw_text}",
        inline=False,
    )

    # LLM processing indicator
    embed.add_field(
        name="🤖 AI Analysis",
        value="⏳ **Processing...** *(2-5 seconds)*",
        inline=False,
    )

    embed.set_footer(text="Real-time alert • AI analysis pending")
    from datetime import datetime, timezone

    embed.timestamp = datetime.now(timezone.utc)

    # Phase 1: Send immediately
    try:
        async with aiohttp.ClientSession() as session:
            webhook = Webhook.from_url(webhook_url, session=session)
            message = await webhook.send(embed=embed, wait=True)

        # Phase 2: Queue for LLM processing (background task)
        asyncio.create_task(
            _enrich_alert_with_llm(
                message_id=message.id,
                webhook_url=webhook_url,
                alert_data=alert_data,
                initial_embed=embed,
            )
        )

        return {"id": message.id, "channel_id": message.channel_id}
    except Exception as e:
        log.error("progressive_alert_send_failed err=%s", str(e))
        return None


async def _enrich_alert_with_llm(
    message_id: int, webhook_url: str, alert_data: dict, initial_embed: Any
):
    """
    Background task: Add LLM sentiment to existing alert.

    Runs after initial alert is posted, updates embed when LLM completes.
    """
    try:
        # Call LLM (async, with timeout)
        from .llm_async import query_llm_async

        item = alert_data.get("item", {})
        title = item.get("title", "")

        llm_prompt = (
            "Analyze this financial news headline. "
            "Is it bullish, bearish, or neutral? Be concise.\n\n"
            f"Headline: {title}"
        )

        llm_result = await asyncio.wait_for(
            query_llm_async(llm_prompt, priority="normal"), timeout=10.0
        )

        # Update embed with LLM result
        if llm_result:
            # Parse LLM sentiment
            llm_sentiment = _parse_llm_sentiment(llm_result)

            sentiment_emoji = (
                "🟢"
                if "bullish" in llm_sentiment.lower()
                else ("🔴" if "bearish" in llm_sentiment.lower() else "⚪")
            )

            # Update AI Analysis field
            initial_embed.set_field_at(
                index=2,  # AI Analysis field
                name=f"{sentiment_emoji} AI Analysis Complete",
                value=f"**Result:** {llm_sentiment[:150]}...",
                inline=False,
            )

            # Update color based on sentiment
            if "bullish" in llm_sentiment.lower():
                initial_embed.color = 0x00FF00  # Green
            elif "bearish" in llm_sentiment.lower():
                initial_embed.color = 0xFF0000  # Red
            else:
                initial_embed.color = 0xFFFF00  # Yellow

            # Edit message
            import aiohttp
            from discord import Webhook

            async with aiohttp.ClientSession() as session:
                webhook = Webhook.from_url(webhook_url, session=session)
                await webhook.edit_message(message_id, embed=initial_embed)

            log.info("llm_enrichment_success message_id=%d", message_id)
        else:
            # LLM failed - update with timeout indicator
            await _handle_llm_timeout(message_id, webhook_url, initial_embed)

    except asyncio.TimeoutError:
        await _handle_llm_timeout(message_id, webhook_url, initial_embed)
    except Exception as e:
        log.warning("llm_enrichment_failed message_id=%d err=%s", message_id, str(e))


async def _handle_llm_timeout(message_id: int, webhook_url: str, embed: Any):
    """Update message with timeout indicator."""
    try:
        embed.set_field_at(
            index=2,
            name="⏱️ AI Analysis Timeout",
            value="*Analysis took longer than expected*\n*Price data above remains accurate*",
            inline=False,
        )
        embed.color = 0xFFA500  # Orange

        import aiohttp
        from discord import Webhook

        async with aiohttp.ClientSession() as session:
            webhook = Webhook.from_url(webhook_url, session=session)
            await webhook.edit_message(message_id, embed=embed)
    except Exception as e:
        log.error("timeout_update_failed message_id=%d err=%s", message_id, str(e))


def _parse_llm_sentiment(llm_text: str) -> str:
    """Extract sentiment direction from LLM response."""
    text_lower = llm_text.lower()
    if "bullish" in text_lower:
        return "Bullish"
    elif "bearish" in text_lower:
        return "Bearish"
    else:
        return "Neutral"


def _build_discord_embed(
    *,
    item_dict: dict,
    scored: dict | None,
    last_price,
    last_change_pct,
    trade_plan: dict | None = None,
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
    _ = primary  # Alias for compatibility (some code may reference ticker)

    # Price / change (treat 0/empty as missing to avoid "$0.00").
    if last_price in (None, "", 0, 0.0, "0", "0.0"):
        price_str = "n/a"
    elif isinstance(last_price, (int, float)):
        price_str = f"${last_price:0.2f}"
    else:
        price_str = str(last_price)
    # Format the percentage change using the helper defined in this module.
    # Use +/-0.00% format when a numeric value is provided; otherwise return "n/a".
    chg_str = _fmt_change(last_change_pct)

    # Score / sentiment (best‑effort).  Use classifier scores and, when
    # available, FMP sentiment and local fallback.
    # Convert ScoredItem dataclass to dict if needed
    if scored is None:
        sc = {}
    elif isinstance(scored, dict):
        sc = scored
    else:
        # Handle ScoredItem dataclass - convert to dict
        try:
            from dataclasses import asdict, is_dataclass

            if is_dataclass(scored):
                sc = asdict(scored)
            else:
                # Fallback: try to access as object attributes
                sc = {
                    "relevance": getattr(scored, "relevance", None),
                    "sentiment": getattr(scored, "sentiment", None),
                    "tags": getattr(scored, "tags", [])
                    or getattr(scored, "keywords", []),
                    "keywords": getattr(scored, "keyword_hits", [])
                    or getattr(scored, "keywords", []),
                    "score": getattr(scored, "total", None)
                    or getattr(scored, "relevance", None),
                }
        except Exception:
            sc = {}
    # Local sentiment: prioritise the discrete label from local sentiment fallback.
    # We look first for `sentiment_local_label` on the item or scored dict.
    local_label: str | None = None
    try:
        # Prefer a pre‑attached sentiment label on the item.  When
        # present, this comes from local_sentiment.attach_local_sentiment().
        lbl_item = item_dict.get("sentiment_local_label")
        if isinstance(lbl_item, str) and lbl_item:
            local_label = lbl_item
    except Exception:
        pass
    if not local_label:
        try:
            lbl_sc = sc.get("sentiment_local_label")
            if isinstance(lbl_sc, str) and lbl_sc:
                local_label = lbl_sc
        except Exception:
            pass
    # Fallback: derive discrete label from the sentiment score if present.
    if not local_label:
        local_sent_raw = sc.get("score") or sc.get("sentiment") or sc.get("sent")
        if local_sent_raw is not None and local_sent_raw != "n/a":
            try:
                # Attempt to convert to float
                ls_val = float(local_sent_raw)
                if ls_val >= 0.05:
                    local_label = "Bullish"
                elif ls_val <= -0.05:
                    local_label = "Bearish"
                else:
                    local_label = "Neutral"
            except Exception:
                # If it's already a string, trust it
                if isinstance(local_sent_raw, str) and local_sent_raw:
                    local_label = local_sent_raw
    # If still None, set to n/a
    if not local_label:
        local_label = "n/a"

    # FMP sentiment attached on the event (from fmp_sentiment.py).  Display as
    # signed two‑decimal value when present; otherwise omit.  Some FMP feeds use
    # integer sentiment values scaled 1–5; convert to float when possible.
    fmp_raw = item_dict.get("sentiment_fmp")
    fmp_sent = None
    if fmp_raw is not None:
        try:
            fmp_val = float(fmp_raw)
            fmp_sent = f"{fmp_val:+.2f}"
        except Exception:
            if str(fmp_raw).strip():
                fmp_sent = str(fmp_raw)
    # Determine any external news sentiment label attached on the event.
    ext_label: str | None = None
    try:
        lbl_ext = item_dict.get("sentiment_ext_label")
        if isinstance(lbl_ext, str) and lbl_ext:
            ext_label = lbl_ext
    except Exception:
        ext_label = None
    # Build the sentiment string.  Start with the local label when present,
    # append the external label when available, then append the FMP score.  The
    # ``fmp_sent`` variable has already been computed above from
    # ``sentiment_fmp``.
    parts: List[str] = []
    if local_label and local_label != "n/a":
        parts.append(local_label)
    if ext_label and ext_label != "n/a":
        parts.append(ext_label)
    # Append SEC sentiment label when present.  Prefer the aggregated
    # sec_sentiment_label over per‑filing sec_label to avoid multiple
    # entries.  Only include when non‑empty and not "n/a".
    try:
        sec_lbl = item_dict.get("sec_sentiment_label") or item_dict.get("sec_label")
        if isinstance(sec_lbl, str) and sec_lbl and sec_lbl.lower() != "n/a":
            parts.append(sec_lbl)
    except Exception:
        pass
    if fmp_sent:
        parts.append(fmp_sent)
    if parts:
        sent = " / ".join(parts)
    else:
        # Fall back to n/a when nothing present
        sent = "n/a"
    # Build a numeric sentiment score string from available sources.  When
    # local or external sentiment scores exist, we display them; otherwise
    # fall back to the classifier relevance score.  Each value is shown
    # with sign and two decimal places.  This helps troubleshoot when
    # sentiments appear blank in embeds.
    score_values: List[str] = []
    # Local sentiment score (try multiple keys: score, sentiment, sent)
    try:
        local_sent_raw = (
            sc.get("score") or sc.get("sentiment") or sc.get("sent") or None
        )
        if local_sent_raw is not None and local_sent_raw != "n/a":
            ls_val = float(local_sent_raw)
            score_values.append(f"{ls_val:+.2f}")
    except Exception:
        pass
    # External sentiment score attached on the event
    try:
        ext_score = item_dict.get("sentiment_ext_score")
        if ext_score is not None:
            # ext_score can be a tuple (score, label, n_articles, details)
            if isinstance(ext_score, (int, float)):
                score_values.append(f"{float(ext_score):+.2f}")
            elif isinstance(ext_score, (list, tuple)) and ext_score:
                try:
                    score_val = float(ext_score[0])
                    score_values.append(f"{score_val:+.2f}")
                except Exception:
                    pass
    except Exception:
        pass
    # FMP sentiment score (when present) has been formatted above as fmp_sent
    # We add it here as an additional numeric component when available.
    if fmp_sent:
        try:
            score_values.append(str(fmp_sent))
        except Exception:
            pass
    # Fallback: classifier relevance score when no sentiments are present.
    if not score_values:
        raw_score = sc.get("score", sc.get("raw_score", None))
        if isinstance(raw_score, (int, float)):
            score_values.append(f"{raw_score:.2f}")
        elif raw_score is not None:
            score_values.append(str(raw_score))
    score_str = " / ".join(score_values) if score_values else "n/a"

    # --- NEGATIVE ALERT DETECTION ---
    # Check if this is a negative catalyst alert (offerings, dilution, distress)
    # Negative alerts use red/orange colors and warning emojis regardless of price movement
    is_negative_alert = False
    try:
        if scored:
            # Check alert_type on scored item (set by classify.py)
            alert_type = None
            if isinstance(scored, dict):
                alert_type = scored.get("alert_type")
            else:
                alert_type = getattr(scored, "alert_type", None)

            if alert_type == "NEGATIVE":
                is_negative_alert = True
    except Exception:
        pass

    # Color logic priority (Fix 6: Sentiment-based border colors):
    # 1. NEGATIVE ALERTS (offerings, dilution) → always RED
    # 2. Sentiment analysis (Bullish/Bearish/Neutral) → green/red/yellow
    # 3. Fallback to price movement → green if up, red if down
    # 4. Momentum indicators can override (applied later)
    color = 0x5865F2  # Discord blurple default

    if is_negative_alert:
        # Use bright red for negative catalysts (offerings, dilution, distress)
        color = 0xFF0000
    else:
        # Prioritize sentiment label over price movement
        sentiment_color_set = False
        if local_label and local_label.lower() not in ["n/a", "neutral"]:
            if "bull" in local_label.lower() or "positive" in local_label.lower():
                color = 0x2ECC71  # Green for bullish sentiment
                sentiment_color_set = True
            elif "bear" in local_label.lower() or "negative" in local_label.lower():
                color = 0xE74C3C  # Red for bearish sentiment
                sentiment_color_set = True

        # Fallback to price movement if sentiment is neutral or unavailable
        if not sentiment_color_set:
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

    # Compute additional momentum indicators when enabled.  This uses
    # get_momentum_indicators() which returns a dictionary of values such
    # as RSI14, MACD, signal line, EMA cross and VWAP delta.  When any
    # momentum signals are present, we will summarise them in the
    # embed and adjust the colour accordingly.  Use best‑effort and
    # ignore errors silently.
    momentum: Dict[str, Optional[float]] = {}
    try:
        s = get_settings()
        # Only compute when both indicator flags are on and a ticker is present
        if (
            getattr(s, "feature_indicators", False)
            and getattr(s, "feature_momentum_indicators", False)
            and primary
        ):
            momentum = get_momentum_indicators(primary)
    except Exception:
        momentum = {}

    # If momentum signals exist, override colour when a cross is detected.
    # EXCEPTION: Do NOT override color for negative alerts - they must stay red
    try:
        if momentum and not is_negative_alert:
            # EMA cross: +1 bullish, -1 bearish
            ec = momentum.get("ema_cross")
            mc = momentum.get("macd_cross")
            # Prefer EMA cross over MACD cross to determine colour
            sig = None
            if isinstance(ec, int) and ec != 0:
                sig = ec
            elif isinstance(mc, int) and mc != 0:
                sig = mc
            if sig:
                color = 0x2ECC71 if sig > 0 else 0xE74C3C
    except Exception:
        pass

    # -----------------------------------------------------------------
    # Patch A/C: Compute composite indicator score and ML confidence tier
    composite_score = None
    ml_score = None
    alert_tier = None
    try:
        # Compute composite indicator when enabled
        comp_flag = os.getenv("FEATURE_COMPOSITE_INDICATORS", "0").strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }
        if comp_flag and primary:
            hi_res = os.getenv("FEATURE_HIGH_RES_DATA", "0").strip().lower() in {
                "1",
                "true",
                "yes",
                "on",
            }
            interval = "1min" if hi_res else "5min"
            try:
                intraday_df = get_intraday(
                    primary, interval=interval, output_size="compact"
                )
            except Exception:
                intraday_df = None
            if intraday_df is not None:
                composite_score = compute_composite_score(intraday_df)
            # Apply composite threshold gating (no suppression here; only note)
        # Compute ML confidence and tier when enabled
        ml_flag = os.getenv("FEATURE_ML_ALERT_RANKING", "0").strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }
        # Skip ML scoring for earnings calendar events (simple date announcements)
        skip_ml_earnings = os.getenv("SKIP_ML_FOR_EARNINGS", "1").strip().lower() in (
            "1",
            "true",
            "yes",
            "on",
        )
        is_earnings = (
            item_dict.get("event_type") == "earnings"
            or item_dict.get("category") == "earnings"
        )
        if skip_ml_earnings and is_earnings:
            ml_flag = False

        if ml_flag:
            # Derive price change in decimal form from last_change_pct
            price_change_pct = 0.0
            try:
                if last_change_pct is not None and last_change_pct not in (
                    "n/a",
                    "",
                    None,
                ):
                    # last_change_pct may be a float or formatted string (e.g., "+2.00%")
                    if isinstance(last_change_pct, (float, int)):
                        price_change_pct = float(last_change_pct) / 100.0
                    else:
                        # strip percent sign and convert
                        v = (
                            str(last_change_pct)
                            .replace("%", "")
                            .replace("+", "")
                            .strip()
                        )
                        price_change_pct = float(v) / 100.0
            except Exception:
                price_change_pct = 0.0
            # Sentiment numeric score: take first element of score_values when available
            sent_score_val = 0.0
            try:
                if score_values:
                    sv = str(score_values[0]).replace("+", "").replace("%", "").strip()
                    sent_score_val = float(sv) if sv not in ("n/a", "", None) else 0.0
            except Exception:
                sent_score_val = 0.0
            ind_score_val = float(composite_score or 0.0)
            feature_df, _ = extract_features(
                [
                    {
                        "price_change": price_change_pct,
                        "sentiment_score": sent_score_val,
                        "indicator_score": ind_score_val,
                    }
                ]
            )
            model_path = os.getenv("ML_MODEL_PATH", "data/models/trade_classifier.pkl")
            # Use cached model if path matches (GPU optimization)
            global _cached_ml_model, _cached_ml_model_path
            if _cached_ml_model is not None and _cached_ml_model_path == model_path:
                model = _cached_ml_model
            else:
                try:
                    model = load_model(model_path)
                    _cached_ml_model = model
                    _cached_ml_model_path = model_path
                    log.debug("ml_model_loaded_and_cached path=%s", model_path)
                except Exception as e:
                    log.debug("ml_model_load_failed path=%s err=%s", model_path, str(e))
                    model = None
            if model:
                try:
                    scores = score_alerts(model, feature_df)
                    if scores:
                        ml_score = float(scores[0])
                except Exception:
                    ml_score = None
            # Determine tier based on confidence thresholds
            if ml_score is not None:
                try:
                    high_thr = float(os.getenv("CONFIDENCE_HIGH", "0.8"))
                    mod_thr = float(os.getenv("CONFIDENCE_MODERATE", "0.6"))
                except Exception:
                    high_thr = 0.8
                    mod_thr = 0.6
                if ml_score >= high_thr:
                    alert_tier = "Strong Alert"
                elif ml_score >= mod_thr:
                    alert_tier = "Moderate Alert"
                else:
                    alert_tier = "Heads‑Up Alert"
    except Exception:
        composite_score = None
        ml_score = None
        alert_tier = None

    # Override colour based on ML tier (if present)
    try:
        if alert_tier:
            if alert_tier == "Strong Alert":
                color = 0x2ECC71  # green
            elif alert_tier == "Moderate Alert":
                color = 0xE69E00  # amber
            else:
                color = 0x95A5A6  # grey
    except Exception:
        pass

    # Override color based on trade plan R/R ratio (only when favorable)
    # Don't override price-based color with poor R/R - that would turn
    # positive price movement red just because the trade setup isn't ideal
    try:
        if trade_plan and HAS_ADVANCED_CHARTS:
            rr_ratio = trade_plan.get("rr_ratio", 0)
            # Only override if R/R is favorable (>= 1.0)
            # This preserves green for positive news even with poor trade setups
            if rr_ratio >= 1.0:
                color = get_embed_color_from_rr(rr_ratio)
    except Exception:
        pass

    # ========================================================================
    # WAVE 2: EMBED FIELD RESTRUCTURE - Cleaner, More Scannable Layout
    # ========================================================================
    # This section consolidates related metrics into fewer, more meaningful
    # fields to reduce visual clutter and improve information hierarchy.
    #
    # Field Structure:
    # 1. Trading Metrics (full-width) - Price, Volume, Float
    # 2. Momentum Indicators (2-column) - RSI/MACD + Support/Resistance
    # 3. Sentiment Section (full-width) - Reserved for Agent 2.4 gauge
    # 4. Catalyst Section (full-width) - Reserved for Agent 2.2 badges
    # 5. Additional Context (conditional) - Trade Plan, Earnings, SEC
    # ========================================================================

    fields = []

    # ========================================================================
    # WAVE 3: MULTI-TICKER CONTEXT (Conditional)
    # ========================================================================
    # Display secondary tickers when this article mentions multiple tickers
    # This helps users understand the full context and avoid confusion about
    # why they received an alert for a ticker that's not the primary focus
    try:
        secondary_tickers = item_dict.get("secondary_tickers", [])
        ticker_relevance_score = item_dict.get("ticker_relevance_score")
        is_multi_ticker = item_dict.get("is_multi_ticker_story", False)

        if secondary_tickers and is_multi_ticker:
            # Format secondary tickers as comma-separated list
            secondary_str = ", ".join(secondary_tickers)

            # Build value with optional relevance score
            value_parts = [f"Also mentions: **{secondary_str}**"]
            if ticker_relevance_score:
                value_parts.append(f"Relevance score: {ticker_relevance_score:.0f}/100")

            fields.append(
                {
                    "name": "📊 Multi-Ticker Article",
                    "value": "\n".join(value_parts),
                    "inline": False,  # Full width for visibility
                }
            )
    except Exception:
        # Don't break the embed if multi-ticker display fails
        pass

    # ========================================================================
    # SECTION 1: PRIMARY TRADING METRICS (Full-Width)
    # ========================================================================
    # Consolidate Price, Float, Volume, and % of Float into single field
    # This provides traders with the most critical entry data at a glance

    trading_metrics_parts = []

    # Price with change
    trading_metrics_parts.append(f"**Price:** {price_str} ({chg_str})")

    # Float (from existing float logic around line 2411-2455)
    try:
        float_shares = None
        if hasattr(scored, "float_shares"):
            float_shares = getattr(scored, "float_shares", None)
        elif hasattr(scored, "shares_outstanding"):
            float_shares = getattr(scored, "shares_outstanding", None)
        elif isinstance(scored, dict):
            float_shares = scored.get("float_shares") or scored.get(
                "shares_outstanding"
            )

        if float_shares is not None and float_shares > 0:
            float_millions = float_shares / 1_000_000
            trading_metrics_parts.append(f"**Float:** {float_millions:.1f}M")
    except Exception:
        pass

    # Volume and RVol (from existing RVol logic around line 2364-2409)
    try:
        current_volume = None

        if hasattr(scored, "rvol"):
            getattr(scored, "rvol", None)
            current_volume = getattr(scored, "current_volume", None)
            getattr(scored, "avg_volume_20d", None)
        elif isinstance(scored, dict):
            scored.get("rvol")
            current_volume = scored.get("current_volume")
            scored.get("avg_volume_20d")

        if current_volume:
            vol_millions = current_volume / 1_000_000
            trading_metrics_parts.append(f"**Volume:** {vol_millions:.1f}M")

            if float_shares and float_shares > 0:
                pct_of_float = (current_volume / float_shares) * 100
                trading_metrics_parts.append(f"**% of Float:** {pct_of_float:.1f}%")
    except Exception:
        pass

    if trading_metrics_parts:
        fields.append(
            {
                "name": "📊 Trading Metrics",
                "value": " | ".join(trading_metrics_parts),
                "inline": False,
            }
        )

    # ========================================================================
    # SECTION 2: TECHNICAL INDICATORS (Two-Column Layout)
    # ========================================================================
    # Left column: Momentum (RSI, MACD)
    # Right column: Key Levels (Support, Resistance, VWAP)

    # LEFT COLUMN: Momentum Indicators
    momentum_parts = []

    # RSI from momentum data
    if momentum:
        rsi_val = momentum.get("rsi14")
        if isinstance(rsi_val, (int, float)):
            rsi_label = ""
            if rsi_val >= 70:
                rsi_label = " (Overbought)"
            elif rsi_val <= 30:
                rsi_label = " (Oversold)"
            momentum_parts.append(f"**RSI:** {rsi_val:.0f}{rsi_label}")

        # MACD
        macd_val = momentum.get("macd")
        macd_sig = momentum.get("macd_signal")
        macd_cross = momentum.get("macd_cross")
        if isinstance(macd_val, (int, float)) and isinstance(macd_sig, (int, float)):
            macd_direction = ""
            if isinstance(macd_cross, int):
                if macd_cross > 0:
                    macd_direction = " (Bullish)"
                elif macd_cross < 0:
                    macd_direction = " (Bearish)"
            momentum_parts.append(f"**MACD:** {macd_val:+.2f}{macd_direction}")

    if momentum_parts:
        fields.append(
            {"name": "📈 Momentum", "value": "\n".join(momentum_parts), "inline": True}
        )

    # RIGHT COLUMN: Key Levels
    levels_parts = []

    # VWAP (from existing VWAP logic around line 2645-2692)
    try:
        vwap = None
        vwap_distance_pct = None

        if hasattr(scored, "vwap"):
            vwap = getattr(scored, "vwap", None)
            vwap_distance_pct = getattr(scored, "vwap_distance_pct", None)
        elif isinstance(scored, dict):
            vwap = scored.get("vwap")
            vwap_distance_pct = scored.get("vwap_distance_pct")

        if vwap is not None:
            vwap_str = f"**VWAP:** ${vwap:.2f}"
            if vwap_distance_pct is not None:
                sign = "+" if vwap_distance_pct >= 0 else ""
                vwap_str += f" ({sign}{vwap_distance_pct:.1f}%)"
            levels_parts.append(vwap_str)
    except Exception:
        pass

    # Support/Resistance from trade plan
    if trade_plan:
        try:
            support = trade_plan.get("stop")
            resistance = trade_plan.get("target_1")
            if support and resistance:
                levels_parts.append(f"**Support:** ${support:.2f}")
                levels_parts.append(f"**Resistance:** ${resistance:.2f}")
        except Exception:
            pass

    if levels_parts:
        fields.append(
            {"name": "🎯 Levels", "value": "\n".join(levels_parts), "inline": True}
        )

    # ========================================================================
    # SECTION 3: SENTIMENT GAUGE (Full-Width)
    # ========================================================================
    # INTEGRATION POINT FOR AGENT 2.4: Sentiment Gauge Enhancement
    # This section will be expanded by Agent 2.4 to include:
    # - Larger sentiment gauge visual
    # - Multi-dimensional sentiment breakdown
    # - Confidence intervals
    #
    # Current implementation: Basic sentiment display as placeholder
    # ========================================================================

    sentiment_parts = []
    sentiment_parts.append(f"**Overall:** {sent}")
    sentiment_parts.append(f"**Score:** {score_str}")

    # Add bullishness gauge if available (from existing logic around line 2162-2169)
    try:
        if s and getattr(s, "feature_bullishness_gauge", False):
            # This block is handled later in the original code
            # We'll keep a placeholder here for Agent 2.4
            pass
    except Exception:
        pass

    fields.append(
        {
            "name": "💭 Sentiment Analysis",
            "value": " | ".join(sentiment_parts),
            "inline": False,
        }
    )

    # ========================================================================
    # SECTION 4: CATALYST INDICATORS (Full-Width)
    # ========================================================================
    # WAVE 2 - AGENT 2.2: Catalyst Badge System
    # Visual badges for key catalysts to make important triggers instantly
    # recognizable in Discord alerts.
    #
    # Badge Types: FDA, Earnings, M&A, Offerings, Guidance, Analyst,
    #              SEC Filings, Contracts, Partnerships, Products,
    #              Clinical, Regulatory
    # Priority: FDA > Earnings > M&A > Others (max 3 badges)
    # ========================================================================

    # Extract catalyst badges from classification and text
    try:
        badges = extract_catalyst_badges(
            classification=scored,
            title=title,
            text=item_dict.get("summary", ""),
            max_badges=3,
        )

        # Format badges for display (space-separated on single line)
        badge_display = "  ".join(badges)

        fields.append(
            {"name": "🎯 Key Catalysts", "value": badge_display, "inline": False}
        )

        log.debug(
            "catalyst_badges_extracted ticker=%s badges=%s",
            (item_dict.get("ticker") or "").upper(),
            badges,
        )
    except Exception as e:
        # Fallback to basic keyword display on error
        log.warning("catalyst_badge_extraction_failed err=%s", str(e))
        catalyst_text = ""
        if reason:
            catalyst_text = reason[:200]
        else:
            kw = item_dict.get("keywords")
            if isinstance(kw, (list, tuple)) and kw:
                catalyst_text = ", ".join([str(x) for x in kw[:5]])

        if catalyst_text:
            fields.append(
                {"name": "🔥 Catalysts", "value": catalyst_text, "inline": False}
            )

    # ========================================================================
    # CONDITIONAL SECTIONS: Additional Context
    # ========================================================================
    # These sections only appear when relevant data is available

    # Composite Score and ML Confidence (for high-confidence alerts)
    advanced_metrics_parts = []
    try:
        if composite_score is not None:
            advanced_metrics_parts.append(
                f"**Composite:** {float(composite_score):.2f}"
            )
    except Exception:
        pass

    try:
        if ml_score is not None:
            advanced_metrics_parts.append(f"**ML Confidence:** {float(ml_score):.2f}")
            if alert_tier:
                advanced_metrics_parts.append(f"**Tier:** {alert_tier}")
    except Exception:
        pass

    if advanced_metrics_parts:
        fields.append(
            {
                "name": "🤖 Advanced Metrics",
                "value": " | ".join(advanced_metrics_parts),
                "inline": False,
            }
        )

    # -----------------------------------------------------------------
    # Patch‑Wave‑1: Bullishness gauge
    #
    # When FEATURE_BULLISHNESS_GAUGE=1, compute a single combined
    # sentiment score by aggregating local, external, SEC, analyst and
    # earnings signals.  The score is normalised to the range [‑1, 1]
    # according to per‑component weights defined in config.py.  The
    # resulting value and discrete label are displayed in the embed.  If
    # FEATURE_SENTIMENT_LOGGING=1, the individual components and final
    # score are appended to a JSONL log under data/sentiment_logs.
    try:
        s = get_settings()
    except Exception:
        s = None
    try:
        if s and getattr(s, "feature_bullishness_gauge", False):
            # Helper to normalise analyst implied return into [-1,1].  We
            # scale by twice the return threshold so that a move of
            # ±threshold results in ±0.5 and ±2×threshold saturates at ±1.
            def _analyst_to_score(
                ret: Optional[float], thresh: float
            ) -> Optional[float]:
                if ret is None:
                    return None
                try:
                    r = float(ret)
                    t = float(thresh) if thresh > 0 else 1.0
                    # scale by 2 * threshold; clamp to [-1,1]
                    val = r / (t * 2.0)
                    if val > 1.0:
                        return 1.0
                    if val < -1.0:
                        return -1.0
                    return val
                except Exception:
                    return None

            # Extract per‑component scores
            # Extend the sentiment components with an options entry.  The options
            # scanner attaches a score to the event under ``sentiment_options_score``;
            # when present, it will be combined into the bullishness gauge.
            comp: Dict[str, Optional[float]] = {
                "local": None,
                "ext": None,
                "sec": None,
                "analyst": None,
                "earnings": None,
                "options": None,
            }

            # Populate options sentiment from the event.  The options scanner
            # attaches a numeric score under ``sentiment_options_score``.  When
            # present and not "n/a", assign it to the options component.
            try:
                os_val = item_dict.get("sentiment_options_score")  # type: ignore
                if os_val is not None and os_val != "n/a":
                    comp["options"] = float(os_val)
            except Exception:
                comp["options"] = None
            # Local sentiment – prefer the numeric score on the item/scored dict
            try:
                # item_dict may already contain a numeric local score
                ls = item_dict.get("sentiment_local")
                if ls is None and isinstance(scored, dict):
                    ls = scored.get("sentiment") or scored.get("sent")
                if ls is not None and ls != "n/a":
                    comp["local"] = float(ls)
            except Exception:
                comp["local"] = None
            # External sentiment, SEC and earnings – derive from the details dict
            details = item_dict.get("sentiment_ext_details")
            if isinstance(details, dict):
                # External providers: alpha, marketaux, stocknews, finnhub
                ext_sum = 0.0
                ext_wt = 0.0
                # provider‑specific weights from settings
                prov_weights: Dict[str, float] = {
                    "alpha": getattr(s, "sentiment_weight_alpha", 0.0),
                    "marketaux": getattr(s, "sentiment_weight_marketaux", 0.0),
                    "stocknews": getattr(s, "sentiment_weight_stocknews", 0.0),
                    "finnhub": getattr(s, "sentiment_weight_finnhub", 0.0),
                }
                for prov, info in details.items():
                    try:
                        if prov in prov_weights:
                            score = float(info.get("score"))
                            w = float(prov_weights.get(prov, 0.0))
                            if w > 0:
                                ext_sum += score * w
                                ext_wt += w
                        elif prov == "sec":
                            comp["sec"] = float(info.get("score"))
                        elif prov == "earnings":
                            comp["earnings"] = float(info.get("score"))
                    except Exception:
                        continue
                if ext_wt > 0.0:
                    comp["ext"] = ext_sum / ext_wt
            # Fallback: when details unavailable, use the aggregated external score
            if comp["ext"] is None:
                try:
                    es = item_dict.get("sentiment_ext_score")
                    if isinstance(es, (int, float)):
                        comp["ext"] = float(es)
                    elif isinstance(es, (list, tuple)) and es:
                        comp["ext"] = float(es[0])
                except Exception:
                    comp["ext"] = None
            # Analyst – derive from implied return and threshold
            try:
                imp_ret = item_dict.get("analyst_implied_return")
                thr = getattr(s, "analyst_return_threshold", 10.0)
                if isinstance(imp_ret, (int, float)):
                    comp["analyst"] = _analyst_to_score(float(imp_ret), thr)
                elif isinstance(imp_ret, str) and imp_ret.strip():
                    comp["analyst"] = _analyst_to_score(float(imp_ret), thr)
            except Exception:
                comp["analyst"] = None
            # Weights for the final aggregation
            try:
                w_local = float(getattr(s, "sentiment_weight_local", 0.0))
            except Exception:
                w_local = 0.0
            try:
                w_ext = float(getattr(s, "sentiment_weight_ext", 0.0))
            except Exception:
                w_ext = 0.0
            try:
                w_sec = float(getattr(s, "sentiment_weight_sec", 0.0))
            except Exception:
                w_sec = 0.0
            try:
                w_an = float(getattr(s, "sentiment_weight_analyst", 0.0))
            except Exception:
                w_an = 0.0
            try:
                w_earn = float(getattr(s, "sentiment_weight_earnings", 0.0))
            except Exception:
                w_earn = 0.0
            # Weight for options sentiment.  Use getattr on settings when
            # available; fall back to the SENTIMENT_WEIGHT_OPTIONS env var.
            try:
                w_opts = float(getattr(s, "sentiment_weight_options", 0.0))
            except Exception:
                try:
                    import os as _os  # type: ignore

                    w_opts = float(_os.getenv("SENTIMENT_WEIGHT_OPTIONS", "0") or "0")
                except Exception:
                    w_opts = 0.0
            # Combine weighted components
            weighted_total = 0.0
            total_w = 0.0
            if comp["local"] is not None and w_local > 0:
                weighted_total += comp["local"] * w_local
                total_w += w_local
            if comp["ext"] is not None and w_ext > 0:
                weighted_total += comp["ext"] * w_ext
                total_w += w_ext
            if comp["sec"] is not None and w_sec > 0:
                weighted_total += comp["sec"] * w_sec
                total_w += w_sec
            if comp["analyst"] is not None and w_an > 0:
                weighted_total += comp["analyst"] * w_an
                total_w += w_an
            if comp["earnings"] is not None and w_earn > 0:
                weighted_total += comp["earnings"] * w_earn
                total_w += w_earn
            # Options sentiment: include when a score is present and weight > 0
            if comp.get("options") is not None and w_opts > 0:
                try:
                    weighted_total += float(comp["options"]) * w_opts
                    total_w += w_opts
                except Exception:
                    pass
            bullish_score: Optional[float] = None
            bullish_label: str = "n/a"
            if total_w > 0:
                bullish_score = weighted_total / total_w
                # classify into Bullish/Neutral/Bearish using simple thresholds
                try:
                    val = float(bullish_score)
                    # Determine neutral threshold.  Default to 0.05 (5%), but
                    # when the low‑beta relaxation feature is enabled, expand
                    # the band based on the ticker's sector.  We import
                    # config_extras and sector_info lazily to avoid
                    # unnecessary overhead when the gauge is off.
                    neutral_th = 0.05
                    try:
                        from .config_extras import FEATURE_SECTOR_RELAX

                        if FEATURE_SECTOR_RELAX:
                            from .sector_info import (
                                get_neutral_band_bps,
                                get_sector_info,
                            )

                            sec_name = None
                            try:
                                tk = primary or ""
                                if isinstance(tk, str) and tk:
                                    info = get_sector_info(tk)
                                    sec_name = info.get("sector")
                            except Exception:
                                sec_name = None
                            try:
                                bps = get_neutral_band_bps(sec_name)
                                neutral_th = 0.05 + (float(bps) / 10000.0)
                            except Exception:
                                neutral_th = 0.05
                    except Exception:
                        neutral_th = 0.05
                    if val >= neutral_th:
                        bullish_label = "Bullish"
                    elif val <= -neutral_th:
                        bullish_label = "Bearish"
                    else:
                        bullish_label = "Neutral"
                except Exception:
                    bullish_label = "Neutral"
            # Add the Bullishness field to the embed when a score was computed
            # WAVE 2 AGENT 2.4: Enhanced Sentiment Gauge Visualization
            if bullish_score is not None:
                # Convert -1 to +1 score to 0-100 range for enhanced gauge
                gauge_score = (bullish_score + 1.0) * 50.0  # Maps -1..+1 to 0..100

                try:
                    # Import and use enhanced sentiment gauge
                    from .sentiment_gauge import create_enhanced_sentiment_gauge

                    gauge = create_enhanced_sentiment_gauge(gauge_score)

                    # Create visually enhanced sentiment field (full width for impact)
                    fields.append(
                        {
                            "name": f"{gauge['emoji']} Sentiment Analysis: {gauge['label']}",
                            "value": (
                                f"{gauge['bar']}\n"
                                f"*{gauge['description']}*\n"
                                f"Score: {bullish_score:+.2f}"
                            ),
                            "inline": False,  # Full width for maximum visibility
                        }
                    )
                except Exception as gauge_err:
                    # Fallback to original display if enhanced gauge fails
                    log.debug("enhanced_gauge_failed err=%s", str(gauge_err))
                    fields.append(
                        {
                            "name": "Bullishness",
                            "value": f"{bullish_score:+.2f} • {bullish_label}",
                            "inline": True,
                        }
                    )
            # Append sector and session fields when enabled.  Insert near the
            # end of the sentiment section so that price, sentiment and score
            # remain at the top of the embed.  The sector field shows the
            # primary ticker's sector and industry (when available) or a
            # fallback label.  The session field displays Pre‑Mkt/Regular/
            # After‑Hours/Closed based on the alert timestamp.
            try:
                import os as _os  # type: ignore
                from datetime import datetime as _dt
                from datetime import timezone as _tz

                from .config_extras import (
                    FEATURE_MARKET_TIME,
                    FEATURE_SECTOR_INFO,
                    SECTOR_FALLBACK_LABEL,
                )
                from .sector_info import get_sector_info, get_session

                add_sector = bool(FEATURE_SECTOR_INFO)
                add_session = bool(FEATURE_MARKET_TIME)
                if add_sector or add_session:
                    tk = (primary or "").strip()
                    sec_label: str = ""
                    ind_label: str | None = None
                    if tk:
                        try:
                            info = get_sector_info(tk)
                            sec_label = info.get("sector") or SECTOR_FALLBACK_LABEL
                            ind_label = info.get("industry")
                            if not sec_label:
                                sec_label = SECTOR_FALLBACK_LABEL
                        except Exception:
                            sec_label = SECTOR_FALLBACK_LABEL
                            ind_label = None
                    else:
                        sec_label = SECTOR_FALLBACK_LABEL
                        ind_label = None
                    sector_val = sec_label
                    try:
                        if (
                            add_sector
                            and ind_label
                            and isinstance(ind_label, str)
                            and ind_label.strip()
                        ):
                            sector_val = f"{sec_label} • {ind_label}"
                    except Exception:
                        pass
                    if add_sector:
                        fields.append(
                            {
                                "name": "Sector",
                                "value": str(sector_val)[:1024],
                                "inline": True,
                            }
                        )
                    if add_session:
                        sess_name: str | None = None
                        try:
                            ts_val = ts
                            dt_obj = None
                            if isinstance(ts_val, str):
                                if ts_val.endswith("Z"):
                                    ts_val = ts_val[:-1] + "+00:00"
                                dt_obj = _dt.fromisoformat(ts_val)
                            if dt_obj:
                                if dt_obj.tzinfo is None:
                                    dt_obj = dt_obj.replace(tzinfo=_tz.utc)
                                sess_name = get_session(dt_obj, tz=_tz.utc)
                        except Exception:
                            sess_name = None
                        if not sess_name:
                            sess_name = "-"
                        fields.append(
                            {
                                "name": "Session",
                                "value": str(sess_name)[:1024],
                                "inline": True,
                            }
                        )
            except Exception:
                pass
            # Optionally log the components and final score when sentiment logging is on
            try:
                if s and getattr(s, "feature_sentiment_logging", False):
                    import json
                    from datetime import datetime as _dt
                    from datetime import timezone as _tz

                    # Prepare log record
                    rec = {
                        "timestamp": _dt.now(_tz.utc).isoformat(),
                        "ticker": primary,
                        "local": comp["local"],
                        "ext": comp["ext"],
                        "sec": comp["sec"],
                        "analyst": comp["analyst"],
                        "earnings": comp["earnings"],
                        "score": bullish_score,
                        "label": bullish_label,
                    }
                    # Determine path under data_dir/sentiment_logs/YYYY-MM-DD.jsonl
                    try:
                        base_dir = getattr(s, "data_dir", None)
                        if not base_dir:
                            # fallback to current working directory
                            from pathlib import Path

                            base_dir = Path(os.getcwd())
                        day_str = _dt.now(_tz.utc).strftime("%Y-%m-%d")
                        log_dir = (base_dir / "sentiment_logs").resolve()
                        try:
                            log_dir.mkdir(parents=True, exist_ok=True)
                        except Exception:
                            pass
                        log_path = log_dir / f"{day_str}.jsonl"
                        with open(log_path, "a", encoding="utf-8") as lf:
                            lf.write(json.dumps(rec, ensure_ascii=False))
                            lf.write("\n")
                    except Exception:
                        pass
            except Exception:
                pass
    except Exception:
        # If any unexpected error occurs, do not break the embed builder
        pass

    # Analyst signals: attach when analyst target and implied return are present.
    try:
        tar = item_dict.get("analyst_target")
        imp_ret = item_dict.get("analyst_implied_return")
        albl = item_dict.get("analyst_label")
        if tar is not None and imp_ret is not None:
            # Format target as currency when numeric
            try:
                t_float = float(tar)
                t_str = f"${t_float:.2f}"
            except Exception:
                t_str = str(tar)
            # Format return with sign and one decimal place
            try:
                r_float = float(imp_ret)
                r_str = f"{r_float:+.1f}%"
            except Exception:
                r_str = str(imp_ret)
            lbl_str = f" ({albl})" if isinstance(albl, str) and albl else ""
            fields.append(
                {
                    "name": "Analyst Target / Return",
                    "value": f"{t_str} / {r_str}{lbl_str}",
                    "inline": True,
                }
            )
    except Exception:
        pass
    # Market Regime Field - Add regime indicator before momentum
    try:
        # Extract market regime data from scored object
        regime = None
        vix = None

        if hasattr(scored, "market_regime"):
            regime = getattr(scored, "market_regime", None)
            vix = getattr(scored, "market_vix", None)
        elif isinstance(scored, dict):
            regime = scored.get("market_regime")
            vix = scored.get("market_vix")

        if regime and vix is not None:
            # Emoji mapping for visual clarity
            regime_emojis = {
                "BULL_MARKET": "🐂",
                "BEAR_MARKET": "🐻",
                "HIGH_VOLATILITY": "⚡",
                "NEUTRAL": "⚖️",
                "CRASH": "💥",
            }
            emoji = regime_emojis.get(regime, "❓")

            # Format regime name (convert BULL_MARKET -> Bull Market)
            regime_display = regime.replace("_", " ").title()

            fields.append(
                {
                    "name": "🌍 Market Regime",
                    "value": f"{emoji} {regime_display} (VIX: {vix:.1f})",
                    "inline": True,
                }
            )
    except Exception:
        # Don't break the embed if regime data is missing
        pass

    # ========================================================================
    # WAVE 2: RVol and Float fields DISABLED
    # ========================================================================
    # These metrics are now consolidated into "Trading Metrics" section above
    # (See Section 1 around line 1920)
    # This avoids duplicate fields and reduces visual clutter
    # ========================================================================

    # OLD CODE DISABLED: RVol field - now in Trading Metrics
    # OLD CODE DISABLED: Float field - now in Trading Metrics

    # Add Squeeze Metrics (combines Short Interest + Days to Cover)
    try:
        short_interest_pct = None
        shares_outstanding = None
        avg_volume = None

        # Extract data from scored item
        if hasattr(scored, "short_interest_pct"):
            short_interest_pct = getattr(scored, "short_interest_pct", None)
            shares_outstanding = getattr(scored, "shares_outstanding", None)
            avg_volume = getattr(scored, "avg_volume_20d", None) or getattr(
                scored, "current_volume", None
            )
        elif isinstance(scored, dict):
            short_interest_pct = scored.get("short_interest_pct")
            shares_outstanding = scored.get("shares_outstanding")
            avg_volume = scored.get("avg_volume_20d") or scored.get("current_volume")

        if short_interest_pct is not None and short_interest_pct > 0:
            # Build squeeze metrics value
            value_parts = []

            # Short Interest classification
            if short_interest_pct >= 20:
                si_emoji = "🔥"
                si_class = "Very High"
            elif short_interest_pct >= 10:
                si_emoji = "⚠️"
                si_class = "High"
            elif short_interest_pct >= 5:
                si_emoji = "📊"
                si_class = "Moderate"
            else:
                si_emoji = "📉"
                si_class = "Low"

            value_parts.append(f"SI: {si_emoji} {si_class} ({short_interest_pct:.2f}%)")

            # Calculate Days to Cover if we have the data
            if shares_outstanding and avg_volume and avg_volume > 0:
                short_shares = (short_interest_pct / 100) * shares_outstanding
                days_to_cover = short_shares / avg_volume

                # DTC classification
                if days_to_cover >= 10:
                    dtc_emoji = "🚀"
                    dtc_class = "Extreme"
                elif days_to_cover >= 7:
                    dtc_emoji = "🔥"
                    dtc_class = "Very High"
                elif days_to_cover >= 3:
                    dtc_emoji = "⚠️"
                    dtc_class = "High"
                elif days_to_cover >= 1:
                    dtc_emoji = "📊"
                    dtc_class = "Moderate"
                else:
                    dtc_emoji = "📉"
                    dtc_class = "Low"

                value_parts.append(
                    f"DTC: {dtc_emoji} {dtc_class} ({days_to_cover:.1f}d)"
                )
            else:
                # Show data unavailable message when we can't calculate DTC
                value_parts.append("Days to Cover: n/a (float data unavailable)")

            fields.append(
                {
                    "name": "Squeeze Metrics",
                    "value": "\n".join(value_parts),
                    "inline": True,
                }
            )
    except Exception:
        # Don't break the embed if squeeze metrics fail
        pass

    # Add SEC Filing Details for 8-K and other material filings
    try:
        form_type = item_dict.get("form_type")
        classification = item_dict.get("classification")
        sec_link = item_dict.get("link")

        if form_type and classification:
            value_parts = []

            # Form type and classification
            value_parts.append(f"**{form_type}** - {classification.title()}")

            # Item numbers for 8-K filings (if available)
            items = item_dict.get("items", [])
            if items:
                items_str = ", ".join(f"Item {item}" for item in items)
                value_parts.append(f"Items: {items_str}")

            # Direct link to filing
            if sec_link:
                value_parts.append(f"[View Filing →]({sec_link})")

            fields.append(
                {
                    "name": "📄 SEC Filing",
                    "value": "\n".join(value_parts),
                    "inline": True,
                }
            )
    except Exception:
        # Don't break the embed if SEC details fail
        pass

    # Add LLM Analysis field (trading thesis and reasoning)
    try:
        # Check if LLM analysis is available
        llm_reasoning = item_dict.get("llm_reasoning")
        trading_thesis = item_dict.get("trading_thesis")
        event_context = item_dict.get("event_context")
        expected_action = item_dict.get("expected_price_action")
        key_stats = item_dict.get("key_stats")  # NEW: Extract key stats

        # Only add if we have meaningful LLM output
        if trading_thesis or llm_reasoning or key_stats:
            value_parts = []

            # KEY STATS - Most important, show first (Fix 8)
            if key_stats and isinstance(key_stats, list) and len(key_stats) > 0:
                # Filter out placeholder messages
                real_stats = [
                    s
                    for s in key_stats
                    if s
                    and not any(
                        phrase in s.lower()
                        for phrase in [
                            "no financial details",
                            "details pending",
                            "routine filing",
                        ]
                    )
                ]
                if real_stats:
                    stats_str = " • ".join(
                        real_stats[:3]
                    )  # Limit to 3 stats for brevity
                    value_parts.append(f"💰 **Stats:** {stats_str}")

            # Event context (for delisting scenarios)
            if event_context and event_context not in ("null", "None", ""):
                context_emoji = {
                    "extension_granted": "🟢",
                    "compliance_achieved": "✅",
                    "notice_received": "🔴",
                    "warning_issued": "⚠️",
                }.get(event_context, "📊")
                value_parts.append(
                    f"{context_emoji} {event_context.replace('_', ' ').title()}"
                )

            # Trading thesis (1 sentence explanation)
            if trading_thesis:
                value_parts.append(f"**Thesis:** {trading_thesis}")

            # Expected price action
            if expected_action and expected_action != "neutral":
                action_emoji = {
                    "relief_rally": "📈",
                    "momentum_breakout": "🚀",
                    "selloff": "📉",
                    "volatility_spike": "⚡",
                }.get(expected_action, "📊")
                value_parts.append(
                    f"{action_emoji} Expected: {expected_action.replace('_', ' ').title()}"
                )

            if value_parts:
                fields.append(
                    {
                        "name": "🤖 AI Analysis",
                        "value": "\n".join(value_parts),
                        "inline": False,  # Full width for readability
                    }
                )
    except Exception:
        # Don't break the embed if LLM analysis fails
        pass

    # Add Trade Plan field (Entry/Stop/Target/R:R)
    try:
        if trade_plan:
            value_parts = []

            # Entry, Stop, Target on one line
            entry = trade_plan.get("entry", 0)
            stop = trade_plan.get("stop", 0)
            target = trade_plan.get("target_1", 0)
            value_parts.append(
                f"Entry: ${entry:.2f} | Stop: ${stop:.2f} | Target: ${target:.2f}"
            )

            # R:R ratio with quality indicator
            rr_ratio = trade_plan.get("rr_ratio", 0)
            quality_emoji = trade_plan.get("quality_emoji", "")
            trade_quality = trade_plan.get("trade_quality", "")
            value_parts.append(
                f"R:R: {rr_ratio:.2f}:1 {quality_emoji} ({trade_quality})"
            )

            # ATR for reference
            atr = trade_plan.get("atr", 0)
            risk_per_share = trade_plan.get("risk_per_share", 0)
            value_parts.append(f"ATR: ${atr:.2f} | Risk/Share: ${risk_per_share:.2f}")

            fields.append(
                {
                    "name": "📋 Trade Plan",
                    "value": "\n".join(value_parts),
                    "inline": False,  # Full width for better readability
                }
            )
    except Exception:
        # Don't break the embed if trade plan fails
        pass

    # ========================================================================
    # WAVE 2: VWAP and Momentum Indicators fields DISABLED
    # ========================================================================
    # VWAP is now in "Levels" section (Section 2, right column)
    # Momentum indicators (RSI, MACD) are in "Momentum" section (Section 2, left column)
    # This avoids duplicate fields
    # ========================================================================

    # OLD CODE DISABLED: VWAP field - now in Levels section
    # OLD CODE DISABLED: Momentum indicators - now in Momentum section
    # Earnings information: attach next earnings date and surprise metrics when
    # the earnings alerts feature is enabled.  When FEATURE_EARNINGS_ALERTS=0
    # the earnings field is suppressed entirely.  Missing data or parsing
    # errors are silently ignored to avoid breaking the embed.
    try:
        settings_local = None
        try:
            settings_local = get_settings()
        except Exception:
            settings_local = None
        # If the feature is disabled, skip adding the earnings field
        if settings_local and not getattr(
            settings_local, "feature_earnings_alerts", False
        ):
            pass
        else:
            # Next earnings date (if any and within lookahead window)
            next_dt = item_dict.get("next_earnings_date")
            eps_est = item_dict.get("earnings_eps_estimate")
            eps_rep = item_dict.get("earnings_reported_eps")
            surprise = item_dict.get("earnings_surprise_pct")
            earn_lbl = item_dict.get("earnings_label")
            # Build a human‑readable next earnings string (relative days)
            next_str: Optional[str] = None
            if isinstance(next_dt, datetime):
                try:
                    now = datetime.now(timezone.utc)
                    delta = next_dt - now
                    if delta.total_seconds() >= 0:
                        # upcoming
                        days = delta.days
                        if days >= 1:
                            next_str = f"{next_dt.date()} ({days}d)"
                        else:
                            next_str = f"{next_dt.date()} (today)"
                    else:
                        # past but still within lookback: show days ago
                        days_ago = abs(delta.days)
                        next_str = f"{next_dt.date()} ({days_ago}d ago)"
                except Exception:
                    try:
                        next_str = next_dt.isoformat()[:10]
                    except Exception:
                        next_str = None
            # Build surprise string: estimate vs reported
            surprise_str: Optional[str] = None
            try:
                if eps_est is not None or eps_rep is not None:
                    est_str = (
                        f"{float(eps_est):.2f}"
                        if isinstance(eps_est, (int, float))
                        else str(eps_est)
                    )
                    rep_str = (
                        f"{float(eps_rep):.2f}"
                        if isinstance(eps_rep, (int, float))
                        else str(eps_rep)
                    )
                    # Combine estimate/actual
                    surprise_str = f"Est/Rep: {est_str} / {rep_str}"
                    # Add surprise percentage when available
                    if surprise is not None and surprise == surprise:
                        try:
                            s_pct = float(surprise) * 100.0
                            sign = "+" if s_pct >= 0 else ""
                            surprise_str += f" | Surprise: {sign}{s_pct:.1f}%"
                        except Exception:
                            pass
                    # Append label when present
                    if isinstance(earn_lbl, str) and earn_lbl:
                        surprise_str += f" ({earn_lbl})"
            except Exception:
                surprise_str = None
            if next_str or surprise_str:
                val_lines: List[str] = []
                if next_str:
                    val_lines.append(f"Next: {next_str}")
                if surprise_str:
                    val_lines.append(surprise_str)
                fields.append(
                    {
                        "name": "Earnings",
                        "value": "\n".join(val_lines),
                        "inline": True,
                    }
                )
    except Exception:
        pass
        # VWAP delta
        vwap_d = momentum.get("vwap_delta")
        if isinstance(vwap_d, (int, float)):
            sign = "+" if vwap_d >= 0 else ""
            parts.append(f"VWAP Δ: {sign}{vwap_d:.2f}")
        if parts:
            fields.append(
                {"name": "Indicators", "value": "; ".join(parts), "inline": False}
            )

    # Summarise recent SEC filings when present.  To avoid exceeding Discord
    # embed length limits (6 kB total, 1024 characters per field), we
    # truncate both the number of filings and the length of each line.  At
    # most two filings are shown.  Each reason is shortened to ~80
    # characters and suffixed with a relative age (days or hours).  See
    # https://discord.com/developers/docs/resources/channel#embed-object
    try:
        recs = item_dict.get("recent_sec_filings")
        if isinstance(recs, list) and recs:
            lines: List[str] = []
            now_ts = datetime.now(timezone.utc)
            for entry in recs[:2]:
                ts_str = entry.get("ts")  # type: ignore[attr-defined]
                lbl = entry.get("label")  # type: ignore[attr-defined]
                reason = entry.get("reason")  # type: ignore[attr-defined]
                ago = ""
                try:
                    dt = (
                        datetime.fromisoformat(ts_str)
                        if isinstance(ts_str, str)
                        else None
                    )
                    if dt is not None:
                        if dt.tzinfo is None:
                            dt = dt.replace(tzinfo=timezone.utc)
                        delta = now_ts - dt
                        if delta.days >= 1:
                            ago = f"{delta.days}d"
                        else:
                            hrs = int(delta.total_seconds() // 3600)
                            if hrs > 0:
                                ago = f"{hrs}h"
                except Exception:
                    ago = ""
                text = str(reason or lbl or "Filing").strip()
                # Truncate long reasons to ~80 characters (Discord truncation is
                # per-field; we truncate manually to avoid 400 errors)
                if len(text) > 80:
                    text = text[:77] + "..."
                if ago:
                    text = f"{text} ({ago} ago)"
                lines.append(text)
            if lines:
                value = "\n".join(lines)
                # Discord fields cannot exceed 1024 characters
                if len(value) > 1024:
                    value = value[:1021] + "..."
                fields.append({"name": "SEC Filings", "value": value, "inline": False})
    except Exception:
        pass
    # Source and timestamp moved to footer (no longer as fields)

    # --- NEGATIVE ALERT WARNING FIELD ---
    # Add prominent warning field for negative catalyst alerts
    if is_negative_alert:
        # Extract negative keywords that triggered the alert
        negative_keywords = []
        try:
            if scored:
                if isinstance(scored, dict):
                    negative_keywords = scored.get("negative_keywords", [])
                else:
                    negative_keywords = getattr(scored, "negative_keywords", [])
        except Exception:
            pass

        # Format warning message with categories that were hit
        if negative_keywords:
            # Convert category names to human-readable labels
            category_labels = {
                "offering_negative": "Dilutive Offering",
                "warrant_negative": "Warrant Exercise",
                "dilution_negative": "Share Dilution",
                "distress_negative": "Financial Distress",
            }
            warning_labels = [
                category_labels.get(cat, cat.replace("_", " ").title())
                for cat in negative_keywords
            ]
            warning_text = "🚨 " + " | ".join(warning_labels)
        else:
            warning_text = "🚨 Potential Exit Signal Detected"

        # Insert warning field at the top (index 0) for visibility
        fields.insert(
            0,
            {
                "name": "⚠️ WARNING - NEGATIVE CATALYST",
                "value": warning_text,
                "inline": False,
            },
        )

        # FIX 10: Add educational footer for offering alerts
        # Detect offering stage from title/summary and provide context
        if any(
            cat in ["offering_negative", "dilution_negative"]
            for cat in negative_keywords
        ):
            title_lower = title.lower() if title else ""
            summary_lower = str(item_dict.get("summary", "")).lower()
            combined = f"{title_lower} {summary_lower}"

            # Detect offering stage
            offering_education = None
            if "announced" in combined or "announces" in combined:
                offering_education = (
                    "📚 **Offering Stage: Announced**\n"
                    "Company has announced intent to raise capital but hasn't priced the offering yet. "
                    "Price may drop as market anticipates dilution. Wait for pricing details."
                )
            elif "priced" in combined or "pricing" in combined:
                offering_education = (
                    "📚 **Offering Stage: Priced**\n"
                    "Offering has been priced. Typically 5-15% discount to market. "
                    "Short-term bearish as new shares hit market. Price often bottoms at offering price."
                )
            elif "closing" in combined or "closed" in combined or "closes" in combined:
                offering_education = (
                    "📚 **Offering Stage: Closed**\n"
                    "Offering has completed. Capital is now in company's bank. "
                    "Initial selling pressure over. If stock held offering price, may signal strength. "
                    "Watch for post-offering bounce if fundamentals improve."
                )
            elif "exercise" in combined and "warrant" in combined:
                offering_education = (
                    "📚 **Warrant Exercise**\n"
                    "Warrants exercised = new shares created at strike price. "
                    "Dilutive but generates cash for company. Impact depends on % of float."
                )
            else:
                # Generic offering education
                offering_education = (
                    "📚 **About Offerings**\n"
                    "Offerings raise capital but dilute existing shareholders. "
                    "Announced → Priced (discount set) → Closed (shares hit market). "
                    "Price typically bottoms near offering price, then may recover if use-of-proceeds is strong."
                )

            if offering_education:
                fields.append(
                    {
                        "name": "📖 Educational Context",
                        "value": offering_education,
                        "inline": False,
                    }
                )

    # Include reason when available
    if reason:
        fields.append({"name": "Reason", "value": reason[:1024], "inline": False})

    # --- SEC FILING ENHANCEMENTS (Wave 3) ---
    # When source starts with "sec_", enhance alert with SEC-specific data
    # This provides metrics, guidance, and SEC sentiment while maintaining
    # all standard alert fields (price, float, short interest, etc.)
    is_sec_source = src.startswith("sec_") if isinstance(src, str) else False
    if is_sec_source:
        try:
            # Import SEC-specific modules on-demand to avoid circular imports
            from .sec_filing_alerts import PRIORITY_CONFIG

            # Extract SEC-specific data from item_dict (attached by sec_feed_adapter)
            sec_metrics = item_dict.get("sec_metrics")  # NumericMetrics object
            sec_guidance = item_dict.get("sec_guidance")  # GuidanceAnalysis object
            sec_sentiment = item_dict.get("sec_sentiment")  # SECSentimentOutput object
            sec_priority = item_dict.get("sec_priority")  # PriorityScore object
            filing_type = item_dict.get("filing_type")  # e.g., "8-K", "10-Q"
            item_code = item_dict.get("item_code")  # e.g., "2.02" for 8-K

            # Add filing type badge to make it clear this is an SEC filing
            if filing_type:
                filing_badge = filing_type
                if item_code and filing_type == "8-K":
                    filing_badge += f" Item {item_code}"
                fields.insert(
                    0,
                    {
                        "name": "📄 SEC Filing Type",
                        "value": filing_badge,
                        "inline": True,
                    },
                )

            # Add priority tier with color coding (DISPLAY ONLY - does not bypass filters)
            if sec_priority:
                tier = getattr(sec_priority, "tier", "medium")
                priority_cfg = PRIORITY_CONFIG.get(tier, PRIORITY_CONFIG["medium"])
                priority_emoji = priority_cfg["emoji"]
                priority_label = priority_cfg["label"]
                priority_total = getattr(sec_priority, "total", 0)

                priority_value = (
                    f"{priority_emoji} **{priority_label}** ({priority_total:.2f})"
                )

                # Add top reason if available
                reasons = getattr(sec_priority, "reasons", [])
                if reasons:
                    # Show first reason only (truncated)
                    priority_value += f"\n{reasons[0][:80]}"

                fields.insert(
                    0, {"name": "🎯 Priority", "value": priority_value, "inline": True}
                )

                # Override embed color based on priority tier
                # EXCEPTION: Do NOT override color for negative alerts - they must stay red
                if not is_negative_alert:
                    if tier == "critical":
                        color = PRIORITY_CONFIG["critical"]["color"]
                    elif tier == "high":
                        color = PRIORITY_CONFIG["high"]["color"]
                    elif tier == "medium":
                        color = PRIORITY_CONFIG["medium"]["color"]

            # Add key financial metrics (revenue, EPS, margins)
            if sec_metrics:
                metrics_parts = []

                # Revenue with YoY change
                if hasattr(sec_metrics, "revenue") and sec_metrics.revenue:
                    rev = sec_metrics.revenue
                    if hasattr(rev, "value") and rev.value:
                        metrics_parts.append(f"**Revenue:** ${rev.value:,.0f}M")
                        if hasattr(rev, "yoy_change") and rev.yoy_change:
                            change_emoji = "📈" if rev.yoy_change > 0 else "📉"
                            metrics_parts[
                                -1
                            ] += f" ({change_emoji} {rev.yoy_change:+.1f}%)"

                # EPS with YoY change
                if hasattr(sec_metrics, "eps") and sec_metrics.eps:
                    eps = sec_metrics.eps
                    if hasattr(eps, "value") and eps.value:
                        metrics_parts.append(f"**EPS:** ${eps.value:.2f}")
                        if hasattr(eps, "yoy_change") and eps.yoy_change:
                            change_emoji = "📈" if eps.yoy_change > 0 else "📉"
                            metrics_parts[
                                -1
                            ] += f" ({change_emoji} {eps.yoy_change:+.1f}%)"

                # Margins
                if hasattr(sec_metrics, "margins") and sec_metrics.margins:
                    margins = sec_metrics.margins
                    if hasattr(margins, "gross_margin") and margins.gross_margin:
                        metrics_parts.append(
                            f"**Gross Margin:** {margins.gross_margin:.1f}%"
                        )
                    if (
                        hasattr(margins, "operating_margin")
                        and margins.operating_margin
                    ):
                        metrics_parts.append(
                            f"**Operating Margin:** {margins.operating_margin:.1f}%"
                        )

                if metrics_parts:
                    fields.append(
                        {
                            "name": "💰 Key Metrics",
                            "value": "\n".join(metrics_parts),
                            "inline": False,
                        }
                    )

            # Add forward guidance (raised/lowered/maintained)
            if (
                sec_guidance
                and hasattr(sec_guidance, "has_guidance")
                and sec_guidance.has_guidance
            ):
                guidance_parts = []

                for item in getattr(sec_guidance, "guidance_items", []):
                    # Determine emoji based on change direction
                    change_dir = getattr(item, "change_direction", "new")
                    if change_dir == "raised":
                        emoji = "✅"
                        label = "Raised"
                    elif change_dir == "lowered":
                        emoji = "❌"
                        label = "Lowered"
                    elif change_dir == "maintained":
                        emoji = "⚖️"
                        label = "Maintained"
                    else:
                        emoji = "🆕"
                        label = "New"

                    # Format guidance item
                    guidance_type = getattr(item, "guidance_type", "guidance")
                    guidance_str = (
                        f"{emoji} **{label}** {guidance_type.replace('_', ' ').title()}"
                    )

                    # Add target range if available
                    target_low = getattr(item, "target_low", None)
                    target_high = getattr(item, "target_high", None)
                    if target_low or target_high:
                        targets = []
                        if target_low:
                            targets.append(f"${target_low:,.0f}M")
                        if target_high:
                            targets.append(f"${target_high:,.0f}M")
                        guidance_str += f": {' - '.join(targets)}"

                    # Add confidence level
                    confidence = getattr(item, "confidence_level", "unknown")
                    if confidence != "unknown":
                        guidance_str += f" ({confidence})"

                    guidance_parts.append(guidance_str)

                if guidance_parts:
                    fields.append(
                        {
                            "name": "📈 Forward Guidance",
                            "value": "\n".join(guidance_parts[:3]),  # Limit to 3 items
                            "inline": False,
                        }
                    )

            # Add SEC sentiment breakdown (different from standard sentiment)
            if sec_sentiment:
                sec_score = getattr(sec_sentiment, "score", 0)
                sec_weighted = getattr(sec_sentiment, "weighted_score", sec_score)
                sec_justification = getattr(sec_sentiment, "justification", "")

                # Determine sentiment emoji and label
                if sec_score >= 0.3:
                    sec_emoji = "🟢"
                    sec_label = "Bullish"
                elif sec_score <= -0.3:
                    sec_emoji = "🔴"
                    sec_label = "Bearish"
                else:
                    sec_emoji = "⚪"
                    sec_label = "Neutral"

                sec_sentiment_value = f"{sec_emoji} **{sec_label}** ({sec_score:+.2f})"

                # Add weighted score if different
                if abs(sec_weighted - sec_score) > 0.05:
                    sec_sentiment_value += f"\nWeighted: {sec_weighted:+.2f}"

                # Add justification (truncated)
                if sec_justification:
                    just_text = sec_justification[:150]
                    sec_sentiment_value += f"\n*{just_text}...*"

                fields.append(
                    {
                        "name": "🎯 SEC Sentiment",
                        "value": sec_sentiment_value,
                        "inline": False,
                    }
                )
        except Exception as e:
            # Don't break the alert if SEC enhancements fail
            # Log error for debugging but continue with standard alert
            log.warning(
                "sec_alert_enhancement_failed ticker=%s err=%s", primary, str(e)
            )

    # --- NEGATIVE ALERT TITLE FORMATTING ---
    # Add warning emoji and label for negative catalyst alerts
    # Use red square (🟥) + warning triangle (⚠️) for maximum visibility
    if is_negative_alert:
        alert_title = _deping(f"🟥 ⚠️ NEGATIVE CATALYST - [{primary or '?'}] {title}")[
            :256
        ]
    else:
        alert_title = _deping(f"[{primary or '?'}] {title}")[:256]

    # Extract summary/description for context (from RSS feed or API)
    # This provides users with more context about the news event
    summary_text = ""
    try:
        raw_summary = item_dict.get("summary") or item_dict.get("description") or ""
        if isinstance(raw_summary, str) and raw_summary.strip():
            # Truncate to Discord's 4096 character limit for descriptions
            # Use first 300 chars for clean embed layout
            summary_text = _deping(raw_summary.strip()[:300])
            if len(raw_summary) > 300:
                summary_text += "..."
    except Exception:
        summary_text = ""

    # --- WAVE 2: FOOTER REDESIGN ---
    # Build consolidated footer with source and timeframe
    # Get chart timeframe from environment (used if chart is attached)
    chart_timeframe = os.getenv("CHART_DEFAULT_TIMEFRAME", "1D").upper()

    # Footer text: Source name only (clean and simple)
    footer_text = src if src else "Catalyst-Bot"

    # Build consolidated details field (placed at bottom)
    details_parts = []
    if ts:
        time_ago = _format_time_ago(ts)
        details_parts.append(f"Published: {time_ago}")
    if src:
        details_parts.append(f"Source: {src}")
    # Check if chart will be attached (based on settings and ticker presence)
    try:
        s = get_settings()
        has_ticker = bool((item_dict.get("ticker") or "").strip())
        chart_enabled = (
            getattr(s, "feature_rich_alerts", False)
            or getattr(s, "feature_quickchart", False)
            or getattr(s, "feature_finviz_chart", False)
        )
        if has_ticker and chart_enabled:
            details_parts.append(f"Chart: {chart_timeframe}")
    except Exception:
        pass

    # Add consolidated details field to bottom of embed
    if details_parts:
        details_value = " | ".join(details_parts)
        fields.append({"name": "ℹ️ Details", "value": details_value, "inline": False})

    # CRITICAL FIX: Filter out any fields with empty/invalid values
    # Discord rejects embeds with empty field names or values
    valid_fields = []
    for field in fields:
        fname = field.get("name", "")
        fvalue = field.get("value", "")
        # Ensure both name and value are non-empty strings
        if fname and isinstance(fname, str) and fvalue and isinstance(fvalue, str):
            # Ensure inline is a proper boolean (Discord is strict about this)
            if "inline" not in field or not isinstance(field.get("inline"), bool):
                field["inline"] = False
            valid_fields.append(field)

    # Ensure title is never empty (Discord requirement)
    if not alert_title or not isinstance(alert_title, str) or not alert_title.strip():
        alert_title = "Market Alert"

    # Build embed with validated fields
    embed = {
        "title": alert_title[:256],  # Discord limit: 256 chars
        "color": color,
        "fields": valid_fields,  # Use filtered fields
    }

    # Only add footer if footer_text is valid (Discord rejects null/empty values)
    if footer_text and isinstance(footer_text, str) and footer_text.strip():
        embed["footer"] = {"text": footer_text}

    # Only add URL if it exists (Discord rejects null values in optional fields)
    if link and isinstance(link, str) and link.strip():
        embed["url"] = link

    # Only add timestamp if it's valid ISO 8601 format
    if ts and isinstance(ts, str) and len(ts) > 10:
        embed["timestamp"] = ts

    # Add description when summary is available (appears below title in Discord)
    if summary_text and isinstance(summary_text, str) and summary_text.strip():
        embed["description"] = summary_text
    # Optionally add intraday indicators (VWAP/RSI14)
    try:
        s = get_settings()
        if getattr(s, "feature_indicators", False) and (item_dict.get("ticker")):
            ind = get_intraday_indicators(str(item_dict.get("ticker")))
            embed = enrich_with_indicators(embed, ind)
        # Optionally attach an intraday chart when rich alerts are enabled.
        # Use QuickChart if FEATURE_QUICKCHART is enabled; otherwise fall
        # back to local mpl charts.  Only render charts when a ticker is
        # present.
        img_attached = False
        try:
            t = (item_dict.get("ticker") or "").strip()
            if t:
                if getattr(s, "feature_quickchart", False):
                    # QuickChart integration: fetch a hosted chart URL
                    try:
                        qc_url = get_quickchart_url(t)
                        # Validate URL format (Discord rejects invalid URLs)
                        if (
                            qc_url
                            and isinstance(qc_url, str)
                            and qc_url.startswith(("http://", "https://"))
                        ):
                            embed["image"] = {"url": qc_url}
                            img_attached = True
                    except Exception:
                        pass
                # Only attempt local charts when QuickChart is disabled.  When
                # QuickChart is enabled but fails, skip mplfinance and fall
                # back to Finviz instead of raising repeated import errors.
                # IMPORTANT: Respect FEATURE_ADVANCED_CHARTS master switch
                if (
                    not img_attached
                    and not getattr(s, "feature_quickchart", False)
                    and getattr(s, "feature_rich_alerts", False)
                    and getattr(s, "feature_advanced_charts", False)
                    and CHARTS_OK
                ):
                    try:
                        chart_path = render_intraday_chart(t)
                        if (
                            chart_path
                            and chart_path.exists()
                            and chart_path.suffix.lower() in {".png", ".jpg", ".jpeg"}
                        ):
                            with chart_path.open("rb") as cf:
                                bdata = cf.read()
                            b64 = base64.b64encode(bdata).decode("ascii")
                            embed["image"] = {"url": f"data:image/png;base64,{b64}"}
                            img_attached = True
                    except Exception:
                        pass
                # Finviz static chart fallback when no image attached
                if (
                    not img_attached
                    and getattr(s, "feature_finviz_chart", False)
                    and "image" not in embed
                ):
                    try:
                        tt = t.upper()
                        if tt:
                            # daily candlestick: ty=c, ta=1, p=d, s=l
                            finviz_url = (
                                f"https://charts2.finviz.com/chart.ashx?"
                                f"t={tt}&ty=c&ta=1&p=d&s=l"
                            )
                            embed["image"] = {"url": finviz_url}
                            img_attached = True
                    except Exception:
                        pass
        except Exception:
            pass
    except Exception:
        pass

    # DEBUG: Log embed structure before returning
    import json

    log.info("embed_structure=%s", json.dumps(embed, indent=2, default=str))

    return embed
