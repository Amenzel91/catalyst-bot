# -*- coding: utf-8 -*-
"""Catalyst Bot runner."""

from __future__ import annotations

# stdlib
import argparse
import json
import logging
import os
import random
import re
import signal
import sys
import threading
import time
from typing import Any, Dict, List, Tuple

# Load .env early so config is available to subsequent imports.
try:
    from dotenv import load_dotenv  # type: ignore
except Exception:
    load_dotenv = None
else:
    # If DOTENV_FILE is set, load that; otherwise default to .env
    env_file = os.getenv("DOTENV_FILE")
    if env_file:
        load_dotenv(env_file)  # set DOTENV_FILE=.env.staging
    else:
        load_dotenv()

from catalyst_bot.accepted_items_logger import log_accepted_item
from catalyst_bot.rejected_items_logger import log_rejected_item
from catalyst_bot.ticker_map import cik_from_text, load_cik_to_ticker
from catalyst_bot.ticker_validation import TickerValidator
from catalyst_bot.title_ticker import extract_tickers_from_title, ticker_from_title, ticker_from_summary
from catalyst_bot.multi_ticker_handler import analyze_multi_ticker_article
from catalyst_bot.utils.event_loop_manager import EventLoopManager, run_async

# Be nice to operators: give a clear error when a runtime dep is missing,
# instead of a scary "<frozen runpy>" stacktrace.
try:
    from . import feeds, market
except ModuleNotFoundError as e:
    missing = getattr(e, "name", None) or "a required module"
    sys.stderr.write(
        "\n[Startup dependency check] Missing Python package: "
        f"{missing}\n"
        "Fix (PowerShell):  py -3.12 -m pip install -r requirements.txt\n"
        "If you're in a venv, make sure it’s activated before installing.\n\n"
    )
    sys.exit(2)
except ImportError as e:
    sys.stderr.write(
        "\n[Startup import error] "
        f"{e.__class__.__name__}: {e}\n"
        "Common fixes (PowerShell):\n"
        "  1) Ensure venv is active:   .\\.venv\\Scripts\\Activate.ps1\n"
        "  2) Install deps:            py -3.12 -m pip install -r requirements.txt\n"
        "  3) Run as a module:         python -m catalyst_bot.runner --once\n\n"
    )
    sys.exit(2)

from datetime import date, datetime, timezone
from pathlib import Path

from . import alerts as _alerts  # used to post log digests as embeds
from .admin_reporter import send_admin_report_if_scheduled  # Nightly admin reports
from .alerts import send_alert_safe
from .analyzer import run_analyzer_once_if_scheduled
from .auto_analyzer import run_scheduled_tasks  # Wave‑4 auto analyzer
from .breakout_feedback import (  # Real-time outcome tracking
    register_alert_for_tracking,
    track_pending_outcomes,
)
from .classify import classify, fast_classify, load_dynamic_keyword_weights
from .config import get_settings
from .enrichment_worker import enqueue_for_enrichment, get_enriched_item  # WAVE 3: Async enrichment
from .config_extras import LOG_REPORT_CATEGORIES
from .health_endpoint import start_health_server, update_health_status
from .llm_usage_monitor import get_monitor
from .log_reporter import deliver_report
from .logging_utils import get_logger, setup_logging
from .market import sample_alpaca_stream
from .market_hours import get_market_info  # WAVE 0.0 Phase 2: Market hours detection
from .moa_price_tracker import (
    track_pending_outcomes as track_moa_outcomes,  # MOA Phase 2: Price tracking for rejected items
)
from .seen_store import SeenStore  # persistent seen store for cross-run dedupe
from .weekly_performance import send_weekly_report_if_scheduled  # Weekly performance

# Paper Trading Integration - Import TradingEngine
try:
    from .trading.trading_engine import TradingEngine
    TRADING_ENGINE_AVAILABLE = True
except ImportError:
    TRADING_ENGINE_AVAILABLE = False
    TradingEngine = None

# WAVE 1.2: Feedback Loop imports
try:
    from .feedback import init_database, score_pending_alerts
    from .feedback.weekly_report import (
        send_weekly_report_if_scheduled as send_feedback_weekly_report,
    )
    from .feedback.weight_adjuster import (
        analyze_keyword_performance,
        apply_weight_adjustments,
    )
    # Phase 2: Paper trading and position management
    from . import paper_trader

    FEEDBACK_AVAILABLE = True
except Exception:
    FEEDBACK_AVAILABLE = False

try:
    import yfinance as yf  # type: ignore
except Exception:
    yf = None

# mute yfinance noise
logging.getLogger("yfinance").setLevel(logging.CRITICAL)

STOP = False
_PX_CACHE: Dict[str, Tuple[float, float]] = {}

# WEEK 1 FIX: Network failure detection - Track consecutive empty cycles
_CONSECUTIVE_EMPTY_CYCLES = 0
_MAX_EMPTY_CYCLES = int(os.getenv("ALERT_CONSECUTIVE_EMPTY_CYCLES", "5"))

# Global log accumulator for auto analyzer & log reporter.  Each entry
# should be a dict with keys ``timestamp`` (datetime) and ``category`` (str).
LOG_ENTRIES: List[Dict[str, object]] = []

# Patch‑2: Expose last cycle statistics for heartbeat embeds.  Each cycle
# updates this mapping with counts of items processed, deduped items,
# skipped events and alerts sent.  When unset (e.g. before the first
# cycle), the heartbeat will display dashes instead of numbers.
LAST_CYCLE_STATS: Dict[str, Any] = {}

# Accumulate totals across all cycles to provide new/total counters on
# heartbeats.  Keys mirror LAST_CYCLE_STATS; values start at zero and
# are incremented at the end of each cycle.  See update in _cycle().
TOTAL_STATS: Dict[str, int] = {"items": 0, "deduped": 0, "skipped": 0, "alerts": 0}

# Enhanced Admin Heartbeat: Feed source tracking
FEED_SOURCE_STATS: Dict[str, int] = {"rss": 0, "sec": 0, "social": 0}
SEC_FILING_TYPES: Dict[str, int] = {}  # "8k": count, "10q": count, etc.
TRADING_ACTIVITY_STATS: Dict[str, Any] = {
    "signals_generated": 0,
    "trades_executed": 0,
}
ERROR_TRACKER: List[Dict[str, Any]] = []  # {"level": "error", "category": "API", "message": "..."}

# MOA Nightly Scheduler: Track last run date to prevent duplicate runs
# This is persisted to data/moa/last_scheduled_run.json to survive restarts
_MOA_LAST_RUN_DATE: date | None = None


def _load_moa_last_run_date() -> date | None:
    """
    Load last MOA scheduled run date from persistent state file.

    Returns:
        Last run date, or None if never run or file doesn't exist

    Note: Silently handles errors since this is called at module load time
    """
    state_path = Path("data/moa/last_scheduled_run.json")
    if not state_path.exists():
        return None

    try:
        with open(state_path, "r", encoding="utf-8") as f:
            state = json.load(f)
            last_run_str = state.get("last_scheduled_run_date")
            if last_run_str:
                return date.fromisoformat(last_run_str)
    except (json.JSONDecodeError, ValueError, KeyError, OSError):
        # Silently handle errors - logging not available at module load time
        pass

    return None


def _save_moa_last_run_date(run_date: date) -> bool:
    """
    Save last MOA scheduled run date to persistent state file.

    Parameters:
        run_date: Date to save

    Returns:
        True if saved successfully
    """
    from .logging_utils import get_logger
    log = get_logger("runner")

    state_path = Path("data/moa/last_scheduled_run.json")
    state_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        state = {
            "last_scheduled_run_date": run_date.isoformat(),
            "last_scheduled_run_timestamp": datetime.now(timezone.utc).isoformat(),
        }

        with open(state_path, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2)

        log.info(f"moa_last_run_date_saved date={run_date.isoformat()}")
        return True

    except Exception as e:
        log.error(f"save_moa_last_run_date_failed err={e}")
        return False


# Load persisted last run date on module import (survives restarts)
_MOA_LAST_RUN_DATE = _load_moa_last_run_date()


class HeartbeatAccumulator:
    """Track cumulative stats between heartbeat messages."""

    def __init__(self):
        self.reset()

    def reset(self):
        """Reset all counters (called after sending heartbeat)."""
        self.total_scanned = 0
        self.total_alerts = 0
        self.total_errors = 0
        self.cycles_completed = 0
        self.last_heartbeat_time = datetime.now(timezone.utc)

    def add_cycle(self, scanned: int, alerts: int, errors: int):
        """Record stats from a completed cycle."""
        self.total_scanned += scanned
        self.total_alerts += alerts
        self.total_errors += errors
        self.cycles_completed += 1

    def should_send_heartbeat(self, interval_minutes: int = 60) -> bool:
        """Check if it's time to send heartbeat."""
        elapsed = (
            datetime.now(timezone.utc) - self.last_heartbeat_time
        ).total_seconds()
        return elapsed >= (interval_minutes * 60)

    def get_stats(self) -> dict:
        """Get cumulative stats for heartbeat message."""
        elapsed_min = (
            datetime.now(timezone.utc) - self.last_heartbeat_time
        ).total_seconds() / 60
        return {
            "total_scanned": self.total_scanned,
            "total_alerts": self.total_alerts,
            "total_errors": self.total_errors,
            "cycles_completed": self.cycles_completed,
            "elapsed_minutes": round(elapsed_min, 1),
            "avg_alerts_per_cycle": round(
                self.total_alerts / max(self.cycles_completed, 1), 1
            ),
        }


# Global heartbeat accumulator instance
_heartbeat_acc = HeartbeatAccumulator()


def _sig_handler(signum, frame):
    """Graceful shutdown handler for SIGINT/SIGTERM signals."""
    global STOP
    sig_name = (
        signal.Signals(signum).name
        if hasattr(signal, "Signals")
        else f"signal_{signum}"
    )
    print(
        f"\n[SHUTDOWN] Received {sig_name}, initiating graceful shutdown...",
        file=sys.stderr,
    )
    STOP = True

    # Log shutdown to file if logger is available
    try:
        log = get_logger("runner")
        log.warning("shutdown_signal_received signal=%s", sig_name)
    except Exception:
        pass


def _px_cache_get(ticker: str) -> float | None:
    if not ticker:
        return None
    now = time.time()
    entry = _PX_CACHE.get(ticker)
    if entry:
        px, exp = entry
        if now < exp:
            return px
        _PX_CACHE.pop(ticker, None)
    return None


def _resolve_main_webhook(settings) -> str:
    """
    Return the primary Discord webhook from (in order):
      - settings.discord_webhook_url
      - settings.discord_webhook
      - env DISCORD_WEBHOOK_URL
    Empty string if none.
    """
    return (
        getattr(settings, "discord_webhook_url", None)
        or getattr(settings, "discord_webhook", None)
        or getattr(settings, "webhook_url", None)
        or os.getenv("DISCORD_WEBHOOK_URL", "").strip()
        or os.getenv("DISCORD_WEBHOOK", "").strip()
        or os.getenv("ALERT_WEBHOOK", "").strip()
    )


def _mask_webhook(url: str) -> str:
    """
    Return a masked fingerprint for a Discord webhook URL like:
      https://discord.com/api/webhooks/{id}/{token}
    Example: id=...1234 token=***REDACTED***

    Security: Token is completely masked to prevent leakage.
    Only the last 4 digits of the webhook ID are shown for identification.
    """
    try:
        if not url:
            return "empty"

        parts = url.strip().split("/")
        wid = parts[-2] if len(parts) >= 2 else ""
        tok = parts[-1] if parts else ""

        # Only show last 4 digits of webhook ID for identification
        wid_tail = wid[-4:] if len(wid) >= 4 else "***"

        # Never show any part of the token - fully redact it
        tok_masked = "***REDACTED***" if tok else "missing"

        return f"id=...{wid_tail} token={tok_masked}"
    except Exception:
        return "unparsable"


def _px_cache_put(ticker: str, price: float, ttl: int = 60) -> None:
    _PX_CACHE[ticker] = (price, time.time() + ttl)


def price_snapshot(ticker: str) -> float | None:
    if not ticker or yf is None:
        return None
    cached = _px_cache_get(ticker)
    if cached is not None:
        return cached
    try:
        hist = yf.Ticker(ticker).history(period="1d", interval="1m")
        if hist.empty:
            return None
        px = float(hist["Close"].iloc[-1])
        _px_cache_put(ticker, px, ttl=60)
        return px
    except Exception:
        return None


# ============================================================================
# Enhanced Admin Heartbeat Helper Functions
# ============================================================================


def _get_trading_engine_data() -> Dict[str, Any]:
    """
    Get TradingEngine portfolio metrics and status.

    Returns:
        Dictionary with portfolio_value, position_count, daily_pnl, status
        Falls back to "—" for missing data
    """
    try:
        # Check if trading engine is available and initialized
        trading_engine = globals().get("trading_engine")
        if not trading_engine or not getattr(trading_engine, "_initialized", False):
            return {
                "portfolio_value": "—",
                "position_count": "—",
                "daily_pnl": "—",
                "status": "Not Initialized",
            }

        # Initialize return values with defaults
        portfolio_value = "—"
        position_count = "—"
        daily_pnl = "—"
        status = "Initialized"

        # Try to get position count (synchronous operation)
        try:
            if trading_engine.position_manager and hasattr(trading_engine.position_manager, "get_all_positions"):
                positions = trading_engine.position_manager.get_all_positions()
                position_count = len(positions)

                # Calculate daily P&L from positions
                total_pnl = sum(float(pos.unrealized_pnl) for pos in positions)
                daily_pnl = f"${total_pnl:,.2f}"
        except Exception:
            pass  # Keep default values

        # Try to get portfolio value (requires alpaca client)
        try:
            if trading_engine.broker and hasattr(trading_engine.broker, "session"):
                # Can't call async method synchronously - use alpaca-py TradingClient directly
                import os
                from alpaca.trading.client import TradingClient

                api_key = os.getenv("ALPACA_API_KEY", "").strip()
                api_secret = os.getenv("ALPACA_SECRET", "").strip() or os.getenv("ALPACA_API_SECRET", "").strip()

                if api_key and api_secret:
                    # Create a sync client for this one-off call
                    sync_client = TradingClient(api_key, api_secret, paper=True)
                    account = sync_client.get_account()
                    portfolio_value = f"${float(account.equity):,.2f}"
        except Exception:
            pass  # Keep default value

        # Check circuit breaker status
        circuit_breaker_status = "Active" if getattr(trading_engine, "circuit_breaker_active", False) else "Inactive"

        return {
            "portfolio_value": portfolio_value,
            "position_count": position_count,
            "daily_pnl": daily_pnl,
            "status": status,
            "circuit_breaker": circuit_breaker_status,
        }
    except Exception:
        return {
            "portfolio_value": "—",
            "position_count": "—",
            "daily_pnl": "—",
            "status": "Error",
        }


def _get_llm_usage_hourly() -> Dict[str, Any]:
    """
    Get LLM usage statistics for the last hour and today.

    Returns:
        Dictionary with request counts, token counts, and cost estimates
    """
    try:
        from datetime import datetime, timedelta, timezone

        # Get hourly stats (last 60 minutes)
        now = datetime.now(timezone.utc)
        hour_ago = now - timedelta(hours=1)
        hourly_stats = get_monitor().get_stats(since=hour_ago, until=now)

        # Get daily stats
        daily_stats = get_monitor().get_daily_stats()

        # Count by provider
        gemini_count = hourly_stats.gemini.total_requests
        claude_count = hourly_stats.anthropic.total_requests
        local_count = hourly_stats.local.total_requests

        return {
            "total_requests": hourly_stats.total_requests,
            "gemini_count": gemini_count,
            "claude_count": claude_count,
            "local_count": local_count,
            "input_tokens": hourly_stats.gemini.total_input_tokens + hourly_stats.anthropic.total_input_tokens,
            "output_tokens": hourly_stats.gemini.total_output_tokens + hourly_stats.anthropic.total_output_tokens,
            "hourly_cost": hourly_stats.total_cost,
            "daily_cost": daily_stats.total_cost,
        }
    except Exception:
        return {
            "total_requests": 0,
            "gemini_count": 0,
            "claude_count": 0,
            "local_count": 0,
            "input_tokens": 0,
            "output_tokens": 0,
            "hourly_cost": 0.0,
            "daily_cost": 0.0,
        }


def _get_market_status_display() -> Dict[str, str]:
    """
    Get formatted market status information.

    Returns:
        Dictionary with status_emoji, status_text, next_event, cycle_time
    """
    try:
        from datetime import datetime, time, timedelta, timezone
        from zoneinfo import ZoneInfo

        market_info = get_market_info()
        status = market_info.get("status", "closed")
        cycle_seconds = market_info.get("cycle_seconds", 180)
        is_holiday = market_info.get("is_holiday", False)
        is_weekend = market_info.get("is_weekend", False)

        # Check if market is closed due to holiday or weekend
        if is_holiday:
            return {
                "status_emoji": "🔴",
                "status_text": "Closed (Holiday)",
                "next_event": "Reopens Next Trading Day",
                "cycle_time_sec": cycle_seconds,
                "market_hours_desc": "Market Closed for Holiday",
            }

        if is_weekend and status == "closed":
            return {
                "status_emoji": "🔴",
                "status_text": "Closed (Weekend)",
                "next_event": "Reopens Monday 9:30 AM ET",
                "cycle_time_sec": cycle_seconds,
                "market_hours_desc": "Market Closed for Weekend",
            }

        # Map status to emoji and text
        status_map = {
            "regular": ("🟢", "Open"),
            "pre_market": ("🟡", "Pre-Market"),
            "after_hours": ("🟠", "After-Hours"),
            "closed": ("🔴", "Closed"),
        }
        emoji, text = status_map.get(status, ("⚪", "Unknown"))

        # Calculate next event time (open/close)
        et = ZoneInfo("America/New_York")
        now_et = datetime.now(timezone.utc).astimezone(et)
        today = now_et.date()

        if status in ("pre_market", "closed"):
            # Next event is market open (9:30 AM ET)
            next_event_dt = datetime.combine(today, time(9, 30), tzinfo=et)
            if next_event_dt <= now_et:
                # Already passed today, next open is tomorrow
                next_event_dt = datetime.combine(today + timedelta(days=1), time(9, 30), tzinfo=et)
            event_name = "Open"
        else:
            # Next event is market close (4:00 PM ET)
            next_event_dt = datetime.combine(today, time(16, 0), tzinfo=et)
            if next_event_dt <= now_et:
                # Already passed, show tomorrow's open
                next_event_dt = datetime.combine(today + timedelta(days=1), time(9, 30), tzinfo=et)
                event_name = "Open"
            else:
                event_name = "Close"

        # Format next event time
        time_until = next_event_dt - now_et
        hours = int(time_until.total_seconds() // 3600)
        minutes = int((time_until.total_seconds() % 3600) // 60)
        next_event_str = f"{event_name} in {hours}h {minutes}m"

        # Market hours description
        if status == "regular":
            hours_desc = "Regular (9:30 AM - 4:00 PM ET)"
        elif status == "pre_market":
            hours_desc = "Pre-Market (4:00 - 9:30 AM ET)"
        elif status == "after_hours":
            hours_desc = "After-Hours (4:00 - 8:00 PM ET)"
        else:
            hours_desc = "Closed (Weekend/Holiday)"

        return {
            "status_emoji": emoji,
            "status_text": text,
            "next_event": next_event_str,
            "cycle_time_sec": cycle_seconds,
            "market_hours_desc": hours_desc,
        }
    except Exception:
        return {
            "status_emoji": "⚪",
            "status_text": "Unknown",
            "next_event": "—",
            "cycle_time_sec": 180,
            "market_hours_desc": "—",
        }


def _get_feed_activity_summary() -> Dict[str, Any]:
    """
    Get feed activity summary from global FEED_SOURCE_STATS.

    Returns:
        Dictionary with rss_count, sec_count, social_count, sec_breakdown
    """
    try:
        global FEED_SOURCE_STATS, SEC_FILING_TYPES

        rss_count = FEED_SOURCE_STATS.get("rss", 0)
        sec_count = FEED_SOURCE_STATS.get("sec", 0)
        social_count = FEED_SOURCE_STATS.get("social", 0)

        # Format SEC breakdown (e.g., "8-K: 5, 10-Q: 2")
        if SEC_FILING_TYPES:
            breakdown_parts = []
            for filing_type, count in sorted(SEC_FILING_TYPES.items()):
                # Format: "8k" -> "8-K"
                formatted_type = filing_type.upper().replace("K", "-K").replace("Q", "-Q").replace("G", "-G").replace("D", "-D")
                breakdown_parts.append(f"{formatted_type}: {count}")
            sec_breakdown = ", ".join(breakdown_parts)
        else:
            sec_breakdown = "—"

        return {
            "rss_count": rss_count,
            "sec_count": sec_count,
            "social_count": social_count,
            "sec_breakdown": sec_breakdown,
        }
    except Exception:
        return {
            "rss_count": 0,
            "sec_count": 0,
            "social_count": 0,
            "sec_breakdown": "—",
        }


def _get_error_summary() -> str:
    """
    Get formatted error summary from global ERROR_TRACKER.

    Returns:
        Multi-line string with color-coded errors (🔴/🟡/🟢)
    """
    try:
        global ERROR_TRACKER

        if not ERROR_TRACKER:
            return "No errors or warnings"

        # Group errors by category
        error_groups: Dict[str, Dict[str, int]] = {}
        for error in ERROR_TRACKER[-50:]:  # Last 50 errors
            level = error.get("level", "info")
            category = error.get("category", "Unknown")
            message = error.get("message", "")

            if category not in error_groups:
                error_groups[category] = {"error": 0, "warning": 0, "info": 0, "sample": ""}

            error_groups[category][level] += 1
            if not error_groups[category]["sample"]:
                error_groups[category]["sample"] = message[:50]

        # Format output with emojis
        lines = []
        for category, counts in sorted(error_groups.items()):
            total_errors = counts["error"]
            total_warnings = counts["warning"]
            total_info = counts["info"]

            if total_errors > 0:
                emoji = "🔴"
                display_count = total_errors
                level_text = "errors"
            elif total_warnings > 0:
                emoji = "🟡"
                display_count = total_warnings
                level_text = "warnings"
            else:
                emoji = "🟢"
                display_count = total_info
                level_text = "info"

            sample = counts["sample"]
            line = f"{emoji} {category}: {display_count} {level_text}"
            if sample:
                line += f" ({sample})"
            lines.append(line)

        return "\n".join(lines) if lines else "No errors or warnings"
    except Exception:
        return "Error retrieving stats"


def _track_feed_source(source: str) -> None:
    """
    Track feed source type and SEC filing type.

    Args:
        source: Source string (e.g., "sec_8k", "globenewswire_public", "twitter")
    """
    try:
        global FEED_SOURCE_STATS, SEC_FILING_TYPES

        if not source:
            return

        source_lower = source.lower()

        # Classify source type
        if source_lower.startswith("sec_"):
            FEED_SOURCE_STATS["sec"] = FEED_SOURCE_STATS.get("sec", 0) + 1

            # Extract filing type (e.g., "sec_8k" -> "8k")
            filing_type = source_lower.replace("sec_", "")
            if filing_type:
                SEC_FILING_TYPES[filing_type] = SEC_FILING_TYPES.get(filing_type, 0) + 1

        elif any(social in source_lower for social in ["twitter", "reddit", "social"]):
            FEED_SOURCE_STATS["social"] = FEED_SOURCE_STATS.get("social", 0) + 1
        else:
            # Default to RSS/news
            FEED_SOURCE_STATS["rss"] = FEED_SOURCE_STATS.get("rss", 0) + 1

    except Exception:
        pass  # Silent fail - tracking is non-critical


def _track_error(level: str, category: str, message: str) -> None:
    """
    Track error in global ERROR_TRACKER.

    Args:
        level: "error", "warning", or "info"
        category: Error category (e.g., "API", "LLM", "Database")
        message: Error message
    """
    try:
        global ERROR_TRACKER
        from datetime import datetime, timezone

        ERROR_TRACKER.append({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": level,
            "category": category,
            "message": message,
        })

        # Keep only last 100 errors (circular buffer)
        if len(ERROR_TRACKER) > 100:
            ERROR_TRACKER = ERROR_TRACKER[-100:]

    except Exception:
        pass  # Silent fail - error tracking shouldn't cause errors


def _reset_cycle_tracking() -> None:
    """Reset feed source tracking at start of each cycle."""
    try:
        global FEED_SOURCE_STATS, SEC_FILING_TYPES

        FEED_SOURCE_STATS = {"rss": 0, "sec": 0, "social": 0}
        SEC_FILING_TYPES = {}
        # Note: ERROR_TRACKER persists across cycles

    except Exception:
        pass


def _send_heartbeat(log, settings, reason: str = "boot") -> None:
    """
    Post a lightweight heartbeat to Discord so we can verify connectivity,
    even when record_only=True (controlled via FEATURE_HEARTBEAT).
    Falls back to direct webhook POST if alerts.post_discord_json is absent.
    """
    if str(os.getenv("FEATURE_HEARTBEAT", "1")).strip().lower() not in {
        "1",
        "true",
        "yes",
        "on",
    }:
        return
    # Prefer an explicit admin/dev webhook (env) if provided,
    # else fall back to the normal alerts webhook from settings/env via resolver.
    admin_url = os.getenv("DISCORD_ADMIN_WEBHOOK", "").strip()
    main_url = _resolve_main_webhook(settings)
    target_url = admin_url or main_url
    if not target_url:
        return

    # Compose message + (optional) rich embed
    rich_on = str(os.getenv("FEATURE_RICH_HEARTBEAT", "1")).strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    content = (
        f"🤖 Catalyst-Bot heartbeat ({reason}) "
        f"| record_only={settings.feature_record_only}"
        f"| skip_sources={os.getenv('SKIP_SOURCES', '')}"
        f"| min_score={os.getenv('MIN_SCORE', '')}"
        f"| min_sent_abs={os.getenv('MIN_SENT_ABS', '')}"
    )
    # Common payload; we add an embed when rich_on is true.
    payload = {
        "content": content,
        "allowed_mentions": {
            "parse": []
        },  # belt & suspenders: no accidental @here/@everyone
    }
    if rich_on:
        from datetime import datetime, timezone

        ts = datetime.now(timezone.utc).isoformat()
        skip_sources = os.getenv("SKIP_SOURCES", "") or "—"
        min_score = os.getenv("MIN_SCORE", "") or "—"
        min_sent = os.getenv("MIN_SENT_ABS", "") or "—"
        target_label = "admin" if admin_url else "main"
        # Compose status fields for the heartbeat embed.  Include additional
        # operational parameters like price ceiling, provider order, watchlist
        # length and active feature flags for easy diagnostics.
        # Price ceiling: show numeric value or em dash when unset.
        # Price ceiling: show value or infinity symbol when unset (None)
        if getattr(settings, "price_ceiling", None) is None:
            price_ceiling = "∞"
        else:
            try:
                price_ceiling = str(settings.price_ceiling)
            except Exception:
                price_ceiling = "—"
        # Watchlist size: always show a count, even when feature_watchlist=0
        watchlist_size = "—"
        try:
            from catalyst_bot.watchlist import load_watchlist_set

            wl_path = getattr(settings, "watchlist_csv", None) or ""
            wl_set = load_watchlist_set(str(wl_path)) if wl_path else set()
            watchlist_size = str(len(wl_set))
        except Exception:
            watchlist_size = "—"
        # Watchlist cascade counts: when enabled, show counts of HOT/WARM/COOL.
        cascade_counts = "—"
        try:
            if getattr(settings, "feature_watchlist_cascade", False):
                from catalyst_bot.watchlist_cascade import get_counts, load_state

                state_path = getattr(settings, "watchlist_state_file", "")
                st = load_state(state_path)
                counts = get_counts(st)
                parts = []
                for key in ("HOT", "WARM", "COOL"):
                    if key in counts:
                        parts.append(f"{key[0]}:{counts[key]}")
                cascade_counts = " ".join(parts) if parts else "0"
        except Exception:
            cascade_counts = "—"
        # Provider order: comma-separated string or em dash when empty
        provider_order = getattr(settings, "market_provider_order", "") or "—"
        # Active feature flags: include QuickChart, Momentum, LocalSentiment and BreakoutScanner
        feature_map = {
            "Tiingo": getattr(settings, "feature_tiingo", False),
            "FMP": getattr(settings, "feature_fmp_sentiment", False),
            "FinvizExport": getattr(settings, "feature_finviz_news_export", False),
            "Watchlist": getattr(settings, "feature_watchlist", False),
            "RichAlerts": getattr(settings, "feature_rich_alerts", False),
            "Indicators": getattr(settings, "feature_indicators", False),
            "Momentum": getattr(settings, "feature_momentum_indicators", False),
            "QuickChart": getattr(settings, "feature_quickchart", False),
            "FinvizChart": getattr(settings, "feature_finviz_chart", False),
            "LocalSent": getattr(settings, "feature_local_sentiment", False),
            "BreakoutScanner": getattr(settings, "feature_breakout_scanner", False),
            "WatchlistCascade": getattr(settings, "feature_watchlist_cascade", False),
            "LowScanner": getattr(settings, "feature_52w_low_scanner", False),
            "AdminEmbed": getattr(settings, "feature_admin_embed", False),
            "ApprovalLoop": getattr(settings, "feature_approval_loop", False),
            "AlpacaStream": getattr(settings, "feature_alpaca_stream", False),
            # External news sentiment flags
            "NewsSent": getattr(settings, "feature_news_sentiment", False),
            "AlphaSent": getattr(settings, "feature_alpha_sentiment", False),
            "MarketauxSent": getattr(settings, "feature_marketaux_sentiment", False),
            "StockNewsSent": getattr(settings, "feature_stocknews_sentiment", False),
            "FinnhubSent": getattr(settings, "feature_finnhub_sentiment", False),
            # Analyst signals flag
            "AnalystSignals": getattr(settings, "feature_analyst_signals", False),
            # SEC filings digester flag
            "SecDigester": getattr(settings, "feature_sec_digester", False),
            # Earnings alerts flag
            "EarningsAlerts": getattr(settings, "feature_earnings_alerts", False),
        }
        # Select which features to display based on the heartbeat reason.  At
        # boot we list all active features; during interval heartbeats we only
        # surface features that were enabled in the config but failed to
        # initialise (e.g. missing deps or keys).  See #heartbeat_verbose.
        active_features = [name for name, enabled in feature_map.items() if enabled]
        if reason == "boot":
            features_value = "\n".join(active_features) if active_features else "—"
        else:
            # Show failing features only: those that are expected to be on
            # (settings.feature_X) but are not active in feature_map.
            failing: list[str] = []
            for name, enabled in feature_map.items():
                # Build the attribute name on settings: feature_momentum for "Momentum"
                attr = f"feature_{name.lower()}"
                try:
                    if getattr(settings, attr, False) and not enabled:
                        failing.append(name)
                except Exception:
                    pass
            features_value = "\n".join(failing) if failing else "—"
        # Gather last cycle metrics from the global LAST_CYCLE_STATS dict.  Do not
        # re-import from this module to avoid stale copies.
        try:
            items_cnt = str(LAST_CYCLE_STATS.get("items", "—"))
            dedup_cnt = str(LAST_CYCLE_STATS.get("deduped", "—"))
            skipped_cnt = str(LAST_CYCLE_STATS.get("skipped", "—"))
            alerted_cnt = str(LAST_CYCLE_STATS.get("alerts", "—"))
        except Exception:
            items_cnt = dedup_cnt = skipped_cnt = alerted_cnt = "—"

        # Build counters that show new and cumulative totals.  Use the global
        # TOTAL_STATS mapping; if unavailable, fall back to the per‑cycle
        # values only.  Format as "new | total" so operators can see both
        # the current cycle and cumulative counts at a glance.  When totals
        # are missing, just display the new value.
        def _fmt_counter(new_val: Any, total_key: str) -> str:
            """Return a formatted string showing the per‑cycle value and the
            cumulative total.  When the TOTAL_STATS mapping is unavailable or
            missing the requested key, only the new value is shown.

            Parameters
            ----------
            new_val : Any
                The count for the current cycle (string or int).
            total_key : str
                The key to look up in the TOTAL_STATS dict for the
                cumulative count.

            Returns
            -------
            str
                A string formatted as ``"new | total"`` or just ``"new"`` if
                totals are unavailable.
            """
            try:
                # Access the module-level TOTAL_STATS dict directly.  No
                # import is needed because this helper lives in the same
                # module.  Use getattr to guard against missing globals.
                tot_map = globals().get("TOTAL_STATS")
                tot = None
                if isinstance(tot_map, dict):
                    tot = tot_map.get(total_key)
            except Exception:
                tot = None
            if tot is None:
                return str(new_val)
            return f"{new_val} | {tot}"

        items_val = _fmt_counter(items_cnt, "items")
        dedup_val = _fmt_counter(dedup_cnt, "deduped")
        skipped_val = _fmt_counter(skipped_cnt, "skipped")
        alerts_val = _fmt_counter(alerted_cnt, "alerts")

        # WAVE ALPHA Agent 1: Get accumulator stats for interval/endday heartbeats
        acc_stats = None
        if reason in ("interval", "endday"):
            try:
                acc = globals().get("_heartbeat_acc")
                if acc and hasattr(acc, "get_stats"):
                    acc_stats = acc.get_stats()
            except Exception:
                acc_stats = None

        embed_fields = [
            {"name": "Target", "value": target_label, "inline": True},
            {
                "name": "Record Only",
                "value": str(settings.feature_record_only),
                "inline": True,
            },
            {"name": "Skip Sources", "value": skip_sources, "inline": False},
            {"name": "Min Score", "value": min_score, "inline": True},
            {"name": "Min |sent|", "value": min_sent, "inline": True},
            {"name": "Price Ceiling", "value": price_ceiling, "inline": True},
            {"name": "Watchlist", "value": watchlist_size, "inline": True},
            {"name": "Cascade", "value": cascade_counts, "inline": True},
            {"name": "Providers", "value": provider_order, "inline": True},
            {"name": "Features", "value": features_value, "inline": False},
        ]

        # Enhanced Boot Heartbeat: Add system info, trading engine, signal enhancement, market status
        if reason == "boot":
            import socket
            import sys

            # System Info
            embed_fields.append({
                "name": "🖥️ System Info",
                "value": (
                    f"Hostname: {socket.gethostname()}\n"
                    f"Python: {sys.version.split()[0]}\n"
                    f"Bot Version: v2.5.1 (TradingEngine+)\n"
                    f"Started: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S %Z')}"
                ),
                "inline": False,
            })

            # TradingEngine Status
            te_data = _get_trading_engine_data()
            feature_paper_trading = getattr(settings, "feature_paper_trading", False)
            data_collection_mode = getattr(settings, "data_collection_mode", True)
            trading_extended_hours = getattr(settings, "trading_extended_hours", True)

            embed_fields.append({
                "name": "💹 Paper Trading (TradingEngine)",
                "value": (
                    f"Status: {'✅ Enabled' if feature_paper_trading else '❌ Disabled'}\n"
                    f"Mode: {'Data Collection' if data_collection_mode else 'Production'}\n"
                    f"Open Positions: {te_data.get('position_count', '—')}\n"
                    f"Portfolio Value: ${te_data.get('portfolio_value', '—')}\n"
                    f"Extended Hours: {'✅ DAY limit orders' if trading_extended_hours else '❌ Disabled'}"
                ),
                "inline": False,
            })

            # Signal Enhancement Features
            feature_google_trends = os.getenv("FEATURE_GOOGLE_TRENDS", "0") == "1"
            feature_reddit = os.getenv("FEATURE_REDDIT_SENTIMENT", "0") == "1"
            feature_news_sent = getattr(settings, "feature_news_sentiment", False)
            feature_rvol = os.getenv("FEATURE_RVOL", "0") == "1"
            feature_market_regime = os.getenv("FEATURE_MARKET_REGIME", "0") == "1"

            embed_fields.append({
                "name": "🎯 Signal Enhancement (NEW!)",
                "value": (
                    f"Google Trends: {'✅ Enabled (10% weight)' if feature_google_trends else '❌ Disabled'}\n"
                    f"Reddit Sentiment: {'✅ Enabled (10% weight)' if (feature_reddit and feature_news_sent) else '❌ Disabled'}\n"
                    f"RVOL Multiplier: {'✅ Enabled (0.8x-1.4x)' if feature_rvol else '❌ Disabled'}\n"
                    f"Market Regime: {'✅ Enabled (0.5x-1.2x)' if feature_market_regime else '❌ Disabled'}"
                ),
                "inline": False,
            })

            # Market Status
            market_status = _get_market_status_display()
            embed_fields.append({
                "name": "🕐 Market Status",
                "value": (
                    f"Current Status: {market_status['status_emoji']} {market_status['status_text']}\n"
                    f"Next Event: {market_status['next_event']}\n"
                    f"Scan Cycle: {market_status['cycle_time_sec']} sec ({market_status['market_hours_desc']})"
                ),
                "inline": False,
            })

        # Enhanced Interval Heartbeat: Add feed activity, LLM usage, trading activity, errors
        if reason in ("interval", "endday"):
            # Feed Activity Summary
            feed_activity = _get_feed_activity_summary()
            embed_fields.append({
                "name": "📰 Feed Activity (Last Hour)",
                "value": (
                    f"RSS Feeds: {feed_activity['rss_count']:,} items\n"
                    f"SEC Filings: {feed_activity['sec_count']} filings ({feed_activity['sec_breakdown']})\n"
                    f"Twitter/Social: {feed_activity['social_count']:,} posts"
                ),
                "inline": False,
            })

            # Classification Summary (based on LAST_CYCLE_STATS)
            try:
                total_classified = int(items_cnt) if items_cnt != "—" else 0
                deduped_count = int(dedup_cnt) if dedup_cnt != "—" else 0
                skipped_count = int(skipped_cnt) if skipped_cnt != "—" else 0
                above_threshold = int(alerted_cnt) if alerted_cnt != "—" else 0

                if total_classified > 0:
                    above_pct = (above_threshold / total_classified) * 100
                    below_pct = ((total_classified - above_threshold) / total_classified) * 100
                else:
                    above_pct = 0.0
                    below_pct = 0.0

                embed_fields.append({
                    "name": "🎯 Classification Summary",
                    "value": (
                        f"Total Classified: {total_classified:,}\n"
                        f"Above MIN_SCORE: {above_threshold} ({above_pct:.1f}%)\n"
                        f"Below Threshold: {total_classified - above_threshold:,} ({below_pct:.1f}%)\n"
                        f"Deduped: {deduped_count}\n"
                        f"Skipped: {skipped_count:,}"
                    ),
                    "inline": False,
                })
            except Exception:
                embed_fields.append({
                    "name": "🎯 Classification Summary",
                    "value": "Data unavailable",
                    "inline": False,
                })

            # Trading Activity
            global TRADING_ACTIVITY_STATS
            te_data = _get_trading_engine_data()

            embed_fields.append({
                "name": "💹 Trading Activity",
                "value": (
                    f"Signals Generated: {TRADING_ACTIVITY_STATS.get('signals_generated', 0)}\n"
                    f"Trades Executed: {TRADING_ACTIVITY_STATS.get('trades_executed', 0)}\n"
                    f"Open Positions: {te_data.get('position_count', '—')}\n"
                    f"P&L (Today): ${te_data.get('daily_pnl', '—')}"
                ),
                "inline": False,
            })

            # LLM Usage
            llm_usage = _get_llm_usage_hourly()
            embed_fields.append({
                "name": "🤖 LLM Usage (Last Hour)",
                "value": (
                    f"Requests: {llm_usage['total_requests']} (Gemini: {llm_usage['gemini_count']}, Claude: {llm_usage['claude_count']})\n"
                    f"Tokens In: {llm_usage['input_tokens']:,}\n"
                    f"Tokens Out: {llm_usage['output_tokens']:,}\n"
                    f"Est. Cost (1hr): ${llm_usage['hourly_cost']:.2f}\n"
                    f"Est. Cost (Today): ${llm_usage['daily_cost']:.2f}"
                ),
                "inline": False,
            })

            # Errors & Warnings
            error_summary = _get_error_summary()
            embed_fields.append({
                "name": "⚠️ Errors & Warnings",
                "value": error_summary,
                "inline": False,
            })

            # Market Status (same as boot)
            market_status = _get_market_status_display()
            embed_fields.append({
                "name": "🕐 Market Status",
                "value": (
                    f"Current Status: {market_status['status_emoji']} {market_status['status_text']}\n"
                    f"Next Event: {market_status['next_event']}\n"
                    f"Scan Cycle: {market_status['cycle_time_sec']} sec"
                ),
                "inline": False,
            })

        # Add accumulator period summary for interval/endday heartbeats
        if acc_stats:
            embed_fields.append(
                {
                    "name": "📊 Period Summary",
                    "value": (
                        f"Last {acc_stats.get('elapsed_minutes', 0)} minutes • "
                        f"{acc_stats.get('cycles_completed', 0)} cycles"
                    ),
                    "inline": False,
                }
            )
            embed_fields.extend(
                [
                    {
                        "name": "Feeds Scanned",
                        "value": f"{acc_stats.get('total_scanned', 0):,}",
                        "inline": True,
                    },
                    {
                        "name": "Alerts Posted",
                        "value": f"{acc_stats.get('total_alerts', 0)}",
                        "inline": True,
                    },
                    {
                        "name": "Avg Alerts/Cycle",
                        "value": f"{acc_stats.get('avg_alerts_per_cycle', 0)}",
                        "inline": True,
                    },
                ]
            )

        # Always show per-cycle and cumulative stats
        embed_fields.extend(
            [
                {"name": "Items", "value": items_val, "inline": True},
                {"name": "Deduped", "value": dedup_val, "inline": True},
                {"name": "Skipped", "value": skipped_val, "inline": True},
                {"name": "Alerts", "value": alerts_val, "inline": True},
            ]
        )

        payload["embeds"] = [
            {
                "title": f"Catalyst-Bot heartbeat ({reason})",
                "color": 0x5865F2,  # discord blurple-ish
                "timestamp": ts,
                "fields": embed_fields,
                "footer": {"text": "Catalyst-Bot"},
            }
        ]

    # If an admin webhook is set, post directly to it (don’t disturb alerts pipeline).
    if admin_url:
        try:
            import json
            from urllib.request import Request, urlopen

            req = Request(
                target_url,
                data=json.dumps(payload).encode("utf-8"),
                headers={
                    "Content-Type": "application/json",
                    "User-Agent": (
                        "Catalyst-Bot/heartbeat (+https://github.com/Amenzel91/catalyst-bot)"
                    ),
                },
                method="POST",
            )
            with urlopen(req, timeout=10) as resp:
                code = getattr(resp, "status", getattr(resp, "code", None))
            log.info(
                "heartbeat_sent reason=%s mode=direct_http status=%s target=admin rich=%s hook=%s",
                reason,
                code,
                int(rich_on),
                _mask_webhook(target_url),
            )
            return
        except Exception as e:
            log.warning(
                "heartbeat_error err=%s target=admin hook=%s",
                e.__class__.__name__,
                _mask_webhook(target_url),
                exc_info=True,
            )
            return

    # 1) Try alerts.post_discord_json if it exists (normal path / main webhook)
    try:
        import catalyst_bot.alerts as _alerts  # type: ignore

        post_fn = getattr(_alerts, "post_discord_json", None)
        if callable(post_fn):
            post_fn(payload)
            log.info(
                "heartbeat_sent reason=%s mode=alerts_fn target=main rich=%s hook=%s",
                reason,
                int(rich_on),
                _mask_webhook(main_url),
            )
            return
    except Exception as e:
        # fall back to direct webhook below
        log.debug(
            "heartbeat_alerts_fn_error %s",
            getattr(e, "__class__", type("E", (object,), {})).__name__,
        )

    # 2) Fallback: direct HTTP POST to the webhook (no requests dep required)
    try:
        import json
        from urllib.request import Request, urlopen

        req = Request(
            target_url,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "User-Agent": "Catalyst-Bot/heartbeat (+https://github.com/Amenzel91/catalyst-bot)",
            },
            method="POST",
        )
        with urlopen(req, timeout=10) as resp:
            # Discord returns 204 No Content for success. Any 2xx we consider OK.
            code = getattr(resp, "status", getattr(resp, "code", None))
        log.info(
            "heartbeat_sent reason=%s mode=direct_http status=%s target=main rich=%s hook=%s",
            reason,
            code,
            int(rich_on),
            _mask_webhook(target_url),
        )
    except Exception as e:
        log.warning(
            "heartbeat_error err=%s target=%s hook=%s",
            e.__class__.__name__,
            "main",
            _mask_webhook(target_url),
            exc_info=True,
        )


def _fallback_classify(
    title: str,
    keyword_categories: Dict[str, List[str]],
    default_weight: float,
    dynamic_weights: Dict[str, float] | None = None,
) -> Dict:
    """
    Lightweight classifier that respects analyzer-updated weights
    when present.
    """
    title_lower = (title or "").lower()

    try:
        from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

        s = SentimentIntensityAnalyzer().polarity_scores(title or "")
        sentiment = float(s.get("compound", 0.0))
    except Exception:
        sentiment = 0.0

    tags: List[str] = []
    score = 0.0
    dw = dynamic_weights or {}
    for category, phrases in (keyword_categories or {}).items():
        try:
            hit = any((p or "").lower() in title_lower for p in phrases)
        except Exception:
            hit = False
        if hit:
            tags.append(category)
            weight = float(dw.get(category, default_weight))
            score += weight
    return {"sentiment": sentiment, "keywords": tags, "score": score}


def _load_dynamic_weights_with_fallback(
    log,
) -> Tuple[Dict[str, float], bool, str, bool]:
    """
    Try classify.load_dynamic_keyword_weights(); if empty, directly
    read the JSON file.
    Returns: (weights, loaded_bool, path_str, path_exists)
    """
    settings = get_settings()
    path = settings.data_dir / "analyzer" / "keyword_stats.json"
    path_exists = path.exists()

    weights: Dict[str, float] = {}
    try:
        # Prefer the library loader
        weights = load_dynamic_keyword_weights()
    except Exception as err:
        log.info("dyn_weights_helper_failed err=%s", str(err))

    if not weights and path_exists:
        try:
            with path.open("r", encoding="utf-8") as f:
                raw = json.load(f)
            if isinstance(raw, dict):
                weights = {
                    str(k): float(v)
                    for k, v in raw.items()
                    if isinstance(v, (int, float))
                }
        except Exception as err:
            log.info("dyn_weights_direct_load_failed err=%s", str(err))

    loaded = bool(weights)
    return weights, loaded, str(path), path_exists


_CIK_MAP = None


def ensure_cik_map():
    global _CIK_MAP
    if _CIK_MAP is None:
        log = get_logger("runner")
        log.debug("ticker_map_init start")
        _CIK_MAP = load_cik_to_ticker()  # uses TICKERS_DB_PATH or data/tickers.db
        log.debug("ticker_map_init done size=%s", len(_CIK_MAP))


def enrich_ticker(entry: dict, item: dict):
    """Populate item['ticker'] from SEC link/id/summary or PR title/summary when missing."""
    ensure_cik_map()

    if not item.get("ticker"):
        # SEC: derive from CIK in link/id/summary
        if item.get("source", "").startswith("sec_"):
            for field in ("link", "id", "summary"):
                cik = cik_from_text((entry or {}).get(field))
                if cik:
                    t = _CIK_MAP.get(cik) or _CIK_MAP.get(str(cik).zfill(10))
                    if t:
                        item["ticker"] = t
                        return

        # PR/News: parse ticker from title or summary patterns for ALL sources
        # This ensures ticker extraction works for prnewswire, businesswire, etc.
        # Strategy: Try title patterns first, then fallback to summary body patterns
        t = ticker_from_title(item.get("title") or "")
        if t:
            item["ticker"] = t
            return

        # Fallback: Try summary text if title extraction failed
        # This catches cases like "(Nasdaq: FRGT)" in the article body
        t = ticker_from_summary(item.get("summary") or "")
        if t:
            item["ticker"] = t
            return


# ---------------- Article freshness check ----------------
def is_article_fresh(
    item_published_at: datetime | None,
    max_age_minutes: int = 30,
    max_sec_age_minutes: int = 240,
    is_sec_filing: bool = False,
) -> tuple[bool, int | None]:
    """
    Check if article is fresh enough to alert on.

    Args:
        item_published_at: When article was published (timezone-aware datetime)
        max_age_minutes: Maximum age for regular articles (default 30 minutes)
        max_sec_age_minutes: Maximum age for SEC filings (default 240 minutes / 4 hours)
        is_sec_filing: True if this is a SEC filing

    Returns:
        Tuple of (is_fresh, age_minutes)
        - is_fresh: True if article is fresh enough
        - age_minutes: Age of article in minutes (None if published_at missing)
    """
    log = get_logger("runner")

    # If no publish time, cannot determine freshness - allow through
    if not item_published_at:
        log.debug("freshness_check_skipped reason=no_publish_time")
        return (True, None)

    # Calculate age
    now = datetime.now(timezone.utc)

    # Ensure published_at is timezone-aware
    if item_published_at.tzinfo is None:
        item_published_at = item_published_at.replace(tzinfo=timezone.utc)

    age_delta = now - item_published_at
    age_minutes = age_delta.total_seconds() / 60.0

    # Determine threshold based on content type
    threshold = max_sec_age_minutes if is_sec_filing else max_age_minutes

    is_fresh = age_minutes <= threshold

    if not is_fresh:
        log.info(
            "stale_article_rejected age_minutes=%.1f threshold=%d is_sec=%s",
            age_minutes,
            threshold,
            is_sec_filing,
        )

    return (is_fresh, int(age_minutes))


# ---------------- Instrument-like detection (refined) ----------------
def _is_instrument_like(t: str) -> bool:
    """
    Heuristic to drop warrants/units/rights while preserving legitimate securities.

    ALLOWED (return False):
      - Preferred shares: CDRpB (lowercase p), ABC-B (hyphen), ABCDP (5-letter ending in P/Q/R)
      - ADRs: 5-letter symbols ending with Y or F (e.g., BYDDY, NSRGY, TCEHY)
      - International tickers: BRK.L (London), SONY.T (Tokyo), SAP.DE (Germany)
      - Class shares: BRK.A, BF.B

    REJECTED (return True):
      - Warrants: -WT, -W, .WS, ending with W
      - Units: -U, .U
      - Rights: -R (when not a class share like ABC-R preferred)
      - Instruments with caret: ABC^D

    These heuristics preserve tradable securities while filtering synthetic instruments
    unlikely to be available on major U.S. brokerages.
    """
    if not t:
        return False
    # Preserve original for lowercase 'p' check, then uppercase for other checks
    original = t.strip().replace(" ", "")
    u = original.upper()

    # ═══════════════════════════════════════════════════════════════════════
    # PREFERRED SHARES: Check these FIRST to allow before warrant filters
    # ═══════════════════════════════════════════════════════════════════════

    # Pattern 1: Lowercase 'p' notation (e.g., CDRpB, ABCpD)
    # Check the original string before uppercasing to detect lowercase 'p'
    if re.match(r"^[A-Za-z]{3,4}p[A-Za-z]$", original):
        return False

    # Pattern 2: Hyphen notation for class/preferred shares (e.g., ABC-B, XYZ-A)
    # Must be 3-4 letters, hyphen, single letter
    # BUT NOT: -W, -WT, -U (these are warrants/units, checked later)
    if re.match(r"^[A-Z]{3,4}-[A-Z]$", u):
        # Exclude warrant/unit suffixes
        if u.endswith(("-W", "-WT", "-U")):
            pass  # Let these fall through to warrant/unit checks below
        else:
            return False  # This is a preferred/class share

    # Pattern 3: NASDAQ 5-letter preferred ending in P, Q, or R (e.g., ABCDP, XYZQQ, DEFGR)
    if len(u) == 5 and u[-1] in ("P", "Q", "R"):
        return False

    # ═══════════════════════════════════════════════════════════════════════
    # WARRANTS: Reject warrant patterns (must check BEFORE international tickers)
    # ═══════════════════════════════════════════════════════════════════════

    # Warrant suffixes with dots (e.g., .WS, .W)
    # Check these as full suffixes, not substrings
    if u.endswith(".WS") or u.endswith(".W"):
        return True

    # Warrant suffixes with hyphens (e.g., -WT, -W)
    if u.endswith("-WT") or u.endswith("-W"):
        return True

    # ═══════════════════════════════════════════════════════════════════════
    # UNITS: Reject unit patterns (must check BEFORE international tickers)
    # ═══════════════════════════════════════════════════════════════════════

    # Unit suffixes - check as full suffixes
    if u.endswith("-U") or u.endswith(".U"):
        return True

    # ═══════════════════════════════════════════════════════════════════════
    # INTERNATIONAL TICKERS: Allow exchange-qualified symbols
    # ═══════════════════════════════════════════════════════════════════════

    # Pattern: 2-4 letters, dot, 1-2 letter exchange code (e.g., BRK.L, SONY.T, SAP.DE)
    # Checked AFTER warrant/unit patterns to avoid false matches
    if "." in u:
        if re.match(r"^[A-Z]{2,4}\.[A-Z]{1,2}$", u):
            return False  # International ticker

    # ═══════════════════════════════════════════════════════════════════════
    # SYNTHETIC INSTRUMENTS: Reject caret notation
    # ═══════════════════════════════════════════════════════════════════════

    if "^" in u:
        return True

    # ═══════════════════════════════════════════════════════════════════════
    # CLASS SHARES: Allow traditional class shares (e.g., BRK.A, BF.B)
    # ═══════════════════════════════════════════════════════════════════════

    # Single-letter class designations with dot
    if "." in u and re.fullmatch(r"[A-Z]{1,4}\.[A-Z]$", u):
        return False

    # ═══════════════════════════════════════════════════════════════════════
    # REMAINING DOT PATTERNS: Reject anything else with dots (not caught above)
    # ═══════════════════════════════════════════════════════════════════════

    if "." in u:
        return True

    # ═══════════════════════════════════════════════════════════════════════
    # WARRANT SUFFIXES: Additional warrant patterns (length-based)
    # ═══════════════════════════════════════════════════════════════════════

    if len(u) >= 5:
        # Multi-character suffixes indicating warrants/units
        suffixes = ("WW", "WS", "WT", "PU", "PD")
        if u.endswith(suffixes):
            return True
        # Single 'W' at end (but not after we've already allowed P/Q/R preferred shares)
        if u.endswith("W"):
            return True

    # ═══════════════════════════════════════════════════════════════════════
    # ADRs: Allow 5-letter ADRs ending in F or Y (e.g., BYDDY, NSRGY, TCEHY)
    # NOTE: This check is now PERMISSIVE (allows these) - old code blocked them
    # ═══════════════════════════════════════════════════════════════════════

    # ADRs ending in Y or F are ALLOWED - no rejection here
    # (Removed the old blocking logic: "if len(u) == 5 and u[-1] in {'F', 'Y'}: return True")

    return False


# ---------------- Scored object helpers (robust to different shapes) -------------
def _get(obj: Any, key: str, default=None):
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(key, default)
    # namedtuple / pydantic / simple objects
    return getattr(obj, key, default)


def _as_list(x: Any) -> List[str]:
    if x is None:
        return []
    if isinstance(x, (list, tuple, set)):
        return [str(v) for v in x]
    return [str(x)]


def _score_of(scored: Any) -> float:
    for name in ("total_score", "score", "relevance", "value"):
        v = _get(scored, name, None)
        if v is not None:
            try:
                return float(v)
            except Exception:
                pass
    return 0.0


def _sentiment_of(scored: Any) -> float:
    for name in ("sentiment", "sentiment_score", "compound"):
        v = _get(scored, name, None)
        if v is not None:
            try:
                return float(v)
            except Exception:
                pass
    return 0.0


def _keywords_of(scored: Any) -> List[str]:
    for name in ("keywords", "tags", "categories"):
        ks = _get(scored, name, None)
        if ks:
            return _as_list(ks)
    return []


# ---------------- SEC LLM Integration Helpers ----------------
def _is_sec_source(source: str) -> bool:
    """Check if source is a SEC filing that should use LLM analysis."""
    SEC_SOURCES = {"sec_8k", "sec_424b5", "sec_fwp", "sec_13d", "sec_13g"}
    return (source or "").lower() in SEC_SOURCES


def _cycle(log, settings, market_info: dict | None = None) -> None:
    """One ingest→dedupe→enrich→classify→alert pass with clean skip behavior.

    Parameters
    ----------
    log : Logger
        Logger instance
    settings : Settings
        Bot settings
    market_info : dict, optional
        Market hours information from get_market_info(). If provided and
        market hours detection is enabled, features will be gated based on
        market status.
    """
    # Enhanced Admin Heartbeat: Reset feed source tracking for this cycle
    _reset_cycle_tracking()

    # Initialize seen store for this cycle (fixed: check-only, mark after success)
    seen_store = None
    try:
        import os
        if os.getenv("FEATURE_PERSIST_SEEN", "true").strip().lower() in {"1", "true", "yes", "on"}:
            seen_store = SeenStore()
    except Exception:
        log.warning("seen_store_init_failed", exc_info=True)

    # Ingest + dedupe
    items = feeds.fetch_pr_feeds()
    deduped = feeds.dedupe(items)

    # ------------------------------------------------------------------
    # WEEK 1 FIX: Network failure detection - Track consecutive empty cycles
    # and alert if feed sources appear to be down.
    global _CONSECUTIVE_EMPTY_CYCLES
    if not items or len(items) == 0:
        _CONSECUTIVE_EMPTY_CYCLES += 1

        if _CONSECUTIVE_EMPTY_CYCLES >= _MAX_EMPTY_CYCLES:
            log.error(
                "feed_outage_detected consecutive_empty=%d max=%d",
                _CONSECUTIVE_EMPTY_CYCLES,
                _MAX_EMPTY_CYCLES
            )
            # Send admin alert about potential feed outage
            try:
                admin_webhook = os.getenv("DISCORD_ADMIN_WEBHOOK", "").strip()
                if admin_webhook:
                    from .alerts import post_discord_json
                    post_discord_json(
                        admin_webhook,
                        {
                            "content": (
                                f"⚠️ **Feed Outage Detected**\n\n"
                                f"No items fetched for **{_CONSECUTIVE_EMPTY_CYCLES}** consecutive cycles.\n"
                                f"Check feed sources and network connectivity."
                            )
                        }
                    )
                    log.info("feed_outage_alert_sent cycles=%d", _CONSECUTIVE_EMPTY_CYCLES)
            except Exception as e:
                log.warning("failed_to_send_outage_alert err=%s", str(e))
    else:
        # Reset counter on successful fetch
        if _CONSECUTIVE_EMPTY_CYCLES > 0:
            log.info("feed_recovery detected after=%d empty_cycles", _CONSECUTIVE_EMPTY_CYCLES)
        _CONSECUTIVE_EMPTY_CYCLES = 0

    # ------------------------------------------------------------------
    # Watchlist cascade decay: demote HOT→WARM→COOL entries based on age
    # before processing any new events.  This uses a JSON state file
    # separate from the static watchlist CSV.  When the cascade feature
    # is disabled, this call is a no‑op.  Any errors are silently ignored.
    try:
        if getattr(settings, "feature_watchlist_cascade", False):
            from catalyst_bot.watchlist_cascade import (
                decay_state,
                load_state,
                save_state,
            )

            state_path = getattr(settings, "watchlist_state_file", "")
            state = load_state(state_path)
            now = __import__(
                "datetime", fromlist=["datetime", "timezone"]
            ).datetime.now(__import__("datetime", fromlist=["timezone"]).timezone.utc)
            state = decay_state(
                state,
                now,
                hot_days=getattr(settings, "watchlist_hot_days", 7),
                warm_days=getattr(settings, "watchlist_warm_days", 21),
                cool_days=getattr(settings, "watchlist_cool_days", 60),
            )
            save_state(state_path, state)
    except Exception:
        # ignore decay errors
        pass

    # ------------------------------------------------------------------
    # 52‑week low scanner: proactively add events for tickers trading
    # near their 52‑week lows.  These events are treated like normal
    # feed items and will be scored/classified below.  When the
    # feature is disabled, this call returns an empty list.  Errors
    # during scanning are caught to avoid crashing the cycle.
    #
    # WAVE 0.0 Phase 2: When market hours detection is enabled, the
    # breakout scanner will be skipped if market_info indicates it
    # should be disabled based on current market status.
    try:
        breakout_enabled = True
        if market_info and getattr(settings, "feature_market_hours_detection", False):
            breakout_enabled = market_info.get("features", {}).get(
                "breakout_enabled", True
            )

        if breakout_enabled and getattr(settings, "feature_52w_low_scanner", False):
            from catalyst_bot.scanner import scan_52week_lows

            low_events = scan_52week_lows(
                min_avg_vol=getattr(settings, "low_min_avg_vol", 300000.0),
                distance_pct=getattr(settings, "low_distance_pct", 5.0),
            )
            if low_events:
                # Extend the deduped list; these events will be scored and
                # classified like any other item.  No dedupe is applied to
                # scanner events because their IDs include a timestamp and
                # ticker, making collisions unlikely.
                deduped.extend(low_events)
        elif not breakout_enabled:
            log.debug("breakout_scanner_skipped reason=market_closed")
    except Exception:
        # Ignore scanner failures
        pass

    # Enrich tickers where missing
    for it in deduped:
        enrich_ticker(it, it)

    # Track article velocity for news momentum detection
    # This records each article to build a time-series of article counts per ticker
    try:
        if os.getenv("FEATURE_NEWS_VELOCITY", "1") == "1":
            from catalyst_bot.news_velocity import get_tracker

            velocity_tracker = get_tracker()

            for it in deduped:
                ticker = (it.get("ticker") or "").strip()
                title = it.get("title") or ""
                url = it.get("link") or it.get("canonical_url") or ""
                source = it.get("source") or "unknown"

                if ticker and title:
                    velocity_tracker.record_article(
                        ticker=ticker,
                        title=title,
                        url=url,
                        source=source,
                    )
    except Exception as e:
        log.debug("news_velocity_tracking_failed err=%s", e.__class__.__name__)

    # Dynamic keyword weights (with on-disk fallback)
    dyn_weights, dyn_loaded, dyn_path_str, dyn_path_exists = (
        _load_dynamic_weights_with_fallback(log)
    )

    # Optional price ceiling (float > 0)
    price_ceiling_env = (os.getenv("PRICE_CEILING") or "").strip()
    price_ceiling = None
    try:
        if price_ceiling_env:
            val = float(price_ceiling_env)
            if val > 0:
                price_ceiling = val
    except Exception:
        price_ceiling = None

    # Optional price floor (float > 0)
    price_floor_env = (os.getenv("PRICE_FLOOR") or "").strip()
    price_floor = None
    try:
        if price_floor_env:
            val = float(price_floor_env)
            if val > 0:
                price_floor = val
    except Exception:
        price_floor = None

    # Optional: source-level skip (CSV)
    skip_sources_env = (os.getenv("SKIP_SOURCES") or "").strip()
    skip_sources = {s.strip() for s in skip_sources_env.split(",") if s.strip()}

    # Optional: classifier gates (all optional; default off)
    def _fparse(name: str) -> float | None:
        raw = (os.getenv(name) or "").strip()
        if not raw:
            return None
        try:
            return float(raw)
        except Exception:
            return None

    min_score = _fparse("MIN_SCORE")  # e.g. 1.0
    min_sent_abs = _fparse("MIN_SENT_ABS")  # e.g. 0.10
    cats_allow_env = (os.getenv("CATEGORIES_ALLOW") or "").strip()
    cats_allow = {c.strip().lower() for c in cats_allow_env.split(",") if c.strip()}

    ignore_instr = os.getenv("IGNORE_INSTRUMENT_TICKERS", "1") == "1"

    # Flow control: optional hard cap and jitter to smooth bursts
    try:
        max_alerts_per_cycle = int(
            (os.getenv("MAX_ALERTS_PER_CYCLE") or "0").strip() or "0"
        )
    except Exception:
        max_alerts_per_cycle = 0
    try:
        jitter_ms = int((os.getenv("ALERTS_JITTER_MS") or "0").strip() or "0")
    except Exception:
        jitter_ms = 0

    # Quick metrics
    tickers_present = sum(1 for it in deduped if (it.get("ticker") or "").strip())
    tickers_missing = len(deduped) - tickers_present

    # PERFORMANCE OPTIMIZATION: Batch-fetch all prices at once (10-20x faster than sequential)
    # Collect all unique tickers that need price lookups
    all_tickers = list(
        set(it.get("ticker") for it in deduped if (it.get("ticker") or "").strip())
    )  # noqa: E501
    price_cache = {}
    if all_tickers and price_ceiling is not None:
        # Only batch-fetch if price ceiling is active (since we need prices for filtering)
        try:
            price_cache = market.batch_get_prices(all_tickers)
            log.info(
                "batch_price_fetch tickers=%d cached=%d",
                len(all_tickers),
                len(price_cache),
            )
        except Exception as e:
            log.warning(
                "batch_price_fetch_failed err=%s falling_back_to_sequential",
                e.__class__.__name__,
            )
            price_cache = {}

    skipped_no_ticker = 0
    skipped_crypto = 0
    skipped_ticker_relevance = 0
    skipped_price_gate = 0
    skipped_instr = 0
    skipped_by_source = 0
    skipped_low_score = 0
    skipped_sent_gate = 0
    skipped_cat_gate = 0
    skipped_multi_ticker = 0
    skipped_data_presentation = 0
    # Track events skipped because they were already seen in a previous cycle.
    skipped_seen = 0
    skipped_stale = 0  # Track stale articles rejected by freshness check
    skipped_otc = 0  # Track OTC stock rejections (WAVE 1.2)
    skipped_unit_warrant = 0  # Track unit/warrant/rights rejections
    skipped_low_volume = 0  # Track low liquidity stocks (Fix 9)
    alerted = 0
    # Track strong negatives that bypass MIN_SCORE threshold
    strong_negatives_bypassed = 0

    # WAVE 1.2: Instantiate TickerValidator for OTC filtering
    ticker_validator = TickerValidator()

    # Load watchlist for crypto filter (allow crypto tickers if on watchlist)
    watchlist_tickers: set = set()
    try:
        from catalyst_bot.watchlist import load_watchlist_set
        wl_path = getattr(settings, "watchlist_csv", None) or ""
        if wl_path:
            watchlist_tickers = load_watchlist_set(str(wl_path))
            log.debug("watchlist_loaded count=%d", len(watchlist_tickers))
    except Exception as e:
        log.debug("watchlist_load_failed err=%s", e.__class__.__name__)
        watchlist_tickers = set()

    # WAVE 4: Batch SEC LLM Processing - Parallel keyword extraction
    # Collect all SEC filings for batch processing (eliminates serial asyncio.run() bottleneck)
    sec_llm_cache = {}
    sec_filings_to_process = []
    sec_filings_skipped_seen = 0
    for it in deduped:
        source = it.get("source") or "unknown"

        # Enhanced Admin Heartbeat: Track feed source type
        _track_feed_source(source)

        if _is_sec_source(source):
            doc_text = it.get("summary") or it.get("title") or ""
            if doc_text and len(doc_text) > 50:  # Only process substantial text
                filing_type = source.replace("sec_", "").upper()
                item_id = it.get("id") or it.get("link") or ""

                # CRITICAL OPTIMIZATION: Skip already-seen SEC filings BEFORE expensive pre-filter
                # This prevents re-processing the same 120 filings every cycle (saves 5min/cycle)
                if item_id and seen_store:
                    try:
                        if seen_store.is_seen(item_id):
                            sec_filings_skipped_seen += 1
                            continue  # Skip this filing entirely
                    except Exception:
                        pass  # Fall through if seen check fails

                ticker = (it.get("ticker") or "").strip()  # Extract ticker for pre-filter
                sec_filings_to_process.append({
                    "item_id": item_id,
                    "document_text": doc_text,
                    "title": it.get("title", ""),
                    "filing_type": filing_type,
                    "ticker": ticker,  # Pass ticker to integration layer
                    "id": item_id,  # Add id field for seen store compatibility
                })

    # Batch process all SEC filings in parallel (one asyncio.run call for ALL filings)
    if sec_filings_to_process:
        try:
            import asyncio
            from .sec_integration import batch_extract_keywords_from_documents

            log.info("sec_batch_processing_start count=%d skipped_seen=%d", len(sec_filings_to_process), sec_filings_skipped_seen)

            # WEEK 1 FIX: Check for existing event loop to prevent deadlock
            try:
                loop = asyncio.get_running_loop()
                # Already in async context, use await (defensive)
                log.warning("async_loop_detected using_existing_loop=True")
                # This shouldn't happen in current codebase, but safety first
                # Note: This branch won't work unless _cycle() is async
                sec_llm_cache = asyncio.run(batch_extract_keywords_from_documents(sec_filings_to_process))
            except RuntimeError:
                # No loop exists, safe to use asyncio.run()
                sec_llm_cache = asyncio.run(batch_extract_keywords_from_documents(sec_filings_to_process))

            log.info("sec_batch_processing_complete cached=%d", len(sec_llm_cache))

            # CRITICAL: Mark ALL SEC filings as seen immediately after processing
            # This prevents reprocessing the same filings on every cycle
            # SEC filings that don't generate alerts would never be marked seen otherwise
            if seen_store:
                sec_marked_count = 0
                for filing in sec_filings_to_process:
                    try:
                        filing_id = filing.get("id")
                        if filing_id:
                            seen_store.mark_seen(filing_id)
                            sec_marked_count += 1
                    except Exception as mark_err:
                        log.debug("sec_mark_seen_failed filing_id=%s err=%s", filing_id, str(mark_err))
                log.info("sec_filings_marked_seen count=%d", sec_marked_count)
        except Exception as e:
            log.error("sec_batch_processing_failed err=%s", str(e), exc_info=True)
            # Fallback to empty results to prevent cycle crash
            sec_llm_cache = {}

    # Sort by timestamp descending (newest first) to prioritize breaking news
    def get_timestamp(item):
        """Extract timestamp for sorting, defaulting to epoch for items without ts."""
        ts_str = item.get("ts")
        if not ts_str:
            return "1970-01-01T00:00:00+00:00"  # Epoch - old items go to end
        return ts_str

    sorted_items = sorted(deduped, key=get_timestamp, reverse=True)

    log.info(
        "articles_sorted_by_timestamp total=%d newest=%s oldest=%s",
        len(sorted_items),
        sorted_items[0].get("ts", "unknown") if sorted_items else "none",
        sorted_items[-1].get("ts", "unknown") if sorted_items else "none"
    )

    for it in sorted_items:  # Changed from 'deduped' to 'sorted_items'
        ticker = (it.get("ticker") or "").strip()
        source = it.get("source") or "unknown"

        # FIXED: Check if we've seen this item recently WITHOUT marking it as seen yet.
        # We only mark as seen AFTER successful alert delivery (below, after send_alert_safe).
        # This prevents the race condition where failed alerts are marked seen and never retry.
        # The persistent seen store uses TTL defined via SEEN_TTL_DAYS and respects
        # the FEATURE_PERSIST_SEEN flag.
        try:
            item_id = it.get("id") or ""
            if item_id and seen_store and seen_store.is_seen(item_id):
                log.info("skipped_seen item_id=%s ticker=%s source=%s", item_id[:16], ticker, source)
                skipped_seen += 1
                continue
        except Exception:
            # If the seen store check fails, fall through and process normally.
            pass

        # WAVE 3: Smart multi-ticker handling (replaces blanket rejection)
        # Score ticker relevance instead of rejecting all multi-ticker articles.
        # This allows true multi-ticker stories (partnerships, acquisitions) while
        # filtering out incidental mentions ("AAPL down, MSFT up").
        try:
            # Check if multi-ticker scoring is enabled (default: True)
            if getattr(settings, "feature_multi_ticker_scoring", True):
                title = it.get("title") or ""
                if title:
                    all_tickers = extract_tickers_from_title(title)
                    if len(all_tickers) > 1:
                        # Multi-ticker article detected - score relevance
                        article_data = {
                            "title": title,
                            "summary": it.get("summary", ""),
                            "text": it.get("text", ""),
                        }

                        # Get configuration
                        min_score = getattr(settings, "multi_ticker_min_relevance_score", 40)
                        max_primary = getattr(settings, "multi_ticker_max_primary", 2)
                        score_diff = getattr(settings, "multi_ticker_score_diff_threshold", 30)

                        # Analyze article and select primary tickers
                        primary_tickers, secondary_tickers, all_scores = analyze_multi_ticker_article(
                            all_tickers,
                            article_data,
                            min_score=min_score,
                            max_primary=max_primary,
                            score_diff_threshold=score_diff,
                        )

                        # If current ticker is not a primary ticker, skip it
                        if ticker not in primary_tickers:
                            # Log as low relevance rejection
                            log.info(
                                "ticker_low_relevance ticker=%s score=%.1f primary_tickers=%s title=%s",
                                ticker,
                                all_scores.get(ticker, 0.0),
                                ",".join(primary_tickers) if primary_tickers else "none",
                                title[:50],
                            )
                            skipped_multi_ticker += 1  # Reuse counter for metrics

                            # MOA Phase 1: Log rejected item for analysis
                            try:
                                px = None
                                if ticker in price_cache:
                                    px, _ = price_cache[ticker]
                                log_rejected_item(
                                    item=it,
                                    rejection_reason="LOW_RELEVANCE",
                                    price=px,
                                    score=all_scores.get(ticker, 0.0),
                                    sentiment=None,
                                    keywords=None,
                                )
                            except Exception:
                                pass
                            continue

                        # Ticker is primary - attach secondary tickers to item metadata
                        # This will be used by alerts.py to display "Also mentions: X, Y, Z"
                        if secondary_tickers:
                            it["secondary_tickers"] = secondary_tickers
                            it["ticker_relevance_score"] = all_scores.get(ticker, 0.0)
                            it["is_multi_ticker_story"] = True
                            log.info(
                                "multi_ticker_primary ticker=%s score=%.1f secondary=%s",
                                ticker,
                                all_scores.get(ticker, 0.0),
                                ",".join(secondary_tickers),
                            )
            else:
                # Legacy behavior: reject all multi-ticker articles
                title = it.get("title") or ""
                if title:
                    all_tickers = extract_tickers_from_title(title)
                    if len(all_tickers) > 1:
                        skipped_multi_ticker += 1
                        # MOA Phase 1: Log rejected item for analysis
                        try:
                            px = None
                            if ticker and ticker in price_cache:
                                px, _ = price_cache[ticker]
                            log_rejected_item(
                                item=it,
                                rejection_reason="MULTI_TICKER",
                                price=px,
                                score=None,
                                sentiment=None,
                                keywords=None,
                            )
                        except Exception:
                            pass
                        log.debug("skip_multi_ticker source=%s title=%s tickers=%s",
                                 source, title[:50], ",".join(all_tickers))
                        continue
        except Exception as e:
            # Don't crash on multi-ticker detection errors
            log.warning("multi_ticker_handler_error ticker=%s err=%s", ticker, str(e))
            pass

        # Filter data presentation and conference/exhibit announcements (rarely lead to sustained movement)
        # These are conference presentations, exhibit announcements, interim data releases, etc. that lack novel catalysts
        # User feedback: "usually these presentation announcements aren't really catalyst news"
        # Exception: Keep truly breakthrough data (FDA breakthrough, pivotal results, etc.)
        try:
            title_lower = (it.get("title") or "").lower()
            summary_lower = (it.get("summary") or "").lower()
            combined_text = f"{title_lower} {summary_lower}"

            # Keywords indicating data presentation or conference/exhibit announcements
            presentation_keywords = [
                "announces presentation",
                "announcement of presentation",
                "presentation of",
                "presents data",
                "presenting at",
                "to present",
                "will present",
                "interim data",
                "updated data",
                "preliminary data",
                "data presentation",
                # Conference/exhibit announcements (user feedback: not catalyst news)
                "to exhibit at",
                "will exhibit at",
                "exhibiting at",
                "exhibit at",
                "presenting data at",
                "present data at",
                "present at",
                "to present at the",
                "will present at the",
            ]

            # Breakthrough keywords that override the filter
            breakthrough_keywords = [
                "breakthrough",
                "pivotal",
                "phase 3",
                "phase iii",
                "fda approval",
                "accelerated approval",
                "positive topline",
                "met primary endpoint",
                "exceeded expectations",
                "novel",
                "first-in-class",
                "statistically significant",
            ]

            is_presentation = any(kw in combined_text for kw in presentation_keywords)
            is_breakthrough = any(kw in combined_text for kw in breakthrough_keywords)

            if is_presentation and not is_breakthrough:
                skipped_data_presentation += 1
                # MOA logging
                try:
                    px = None
                    if ticker and ticker in price_cache:
                        px, _ = price_cache[ticker]
                    log_rejected_item(
                        item=it,
                        rejection_reason="DATA_PRESENTATION",
                        price=px,
                        score=None,
                        sentiment=None,
                        keywords=None,
                    )
                except Exception:
                    pass
                log.debug("skip_data_presentation source=%s title=%s", source, title[:50])
                continue
        except Exception:
            pass  # Don't crash on presentation detection errors

        # Filter Jim Cramer mentions and summary/analysis articles
        # These are commentary/opinion pieces rather than primary news/PR
        # User feedback: CLF alert was "big swing and a miss" - Jim Cramer story, summary article
        try:
            title_lower = (it.get("title") or "").lower()
            summary_lower = (it.get("summary") or "").lower()
            combined_text = f"{title_lower} {summary_lower}"

            # Jim Cramer / CNBC personality keywords
            cramer_keywords = [
                "cramer",
                "jim cramer",
                "mad money",
                "thestreet",  # Cramer's company
            ]

            # Summary/analysis article indicators (vs primary PR/SEC filings)
            summary_keywords = [
                "here's what you need to know",
                "here is what you need to know",
                "what you need to know about",
                "here's what happened",
                "what happened to",
                "why is",
                "why did",
                "explainer:",
                "analysis:",
                "opinion:",
                "commentary:",
                "roundup:",
                "wrap-up:",
                "daily digest",
                "market recap",
                "stocks making moves",
                "movers and shakers",
                "stocks to watch",
            ]

            is_cramer = any(kw in combined_text for kw in cramer_keywords)
            is_summary = any(kw in combined_text for kw in summary_keywords)

            if is_cramer or is_summary:
                skipped_cat_gate += 1  # Reuse category gate counter
                # MOA logging
                try:
                    px = None
                    if ticker and ticker in price_cache:
                        px, _ = price_cache[ticker]
                    reason = "CRAMER_MENTION" if is_cramer else "SUMMARY_ARTICLE"
                    log_rejected_item(
                        item=it,
                        rejection_reason=reason,
                        price=px,
                        score=None,
                        sentiment=None,
                        keywords=None,
                    )
                except Exception:
                    pass
                filter_reason = "cramer_mention" if is_cramer else "summary_article"
                log.debug("skip_%s source=%s title=%s", filter_reason, source, title[:50])
                continue
        except Exception:
            pass  # Don't crash on content filter errors

        # Filter non-substantive news articles
        # Rejects "Why [TICKER] Stock Is Down Today" summaries and "we don't know" press releases
        # These articles lack actionable information and create noise in alerts
        try:
            from catalyst_bot.classify import is_substantive_news

            title = it.get("title") or ""
            summary = it.get("summary") or ""

            if not is_substantive_news(title, summary):
                skipped_cat_gate += 1  # Reuse category gate counter for metrics
                # MOA logging
                try:
                    px = None
                    if ticker and ticker in price_cache:
                        px, _ = price_cache[ticker]
                    log_rejected_item(
                        item=it,
                        rejection_reason="NON_SUBSTANTIVE",
                        price=px,
                        score=None,
                        sentiment=None,
                        keywords=None,
                    )
                except Exception:
                    pass
                log.debug("skip_non_substantive source=%s title=%s", source, title[:50])
                continue
        except Exception as e:
            # Don't crash if filter fails - log and continue
            log.debug("non_substantive_filter_error err=%s", e.__class__.__name__)
            pass

        # Skip whole sources if configured
        if skip_sources and source in skip_sources:
            skipped_by_source += 1
            # MOA Phase 1: Log rejected item for analysis (before classification)
            try:
                # Try to get price from cache (batch fetch happened earlier)
                px = None
                if ticker and ticker in price_cache:
                    px, _ = price_cache[ticker]
                log_rejected_item(
                    item=it,
                    rejection_reason="BY_SOURCE",
                    price=px,
                    score=None,
                    sentiment=None,
                    keywords=None,
                )
            except Exception:
                pass  # Don't crash on logging failures
            continue

        # Do not classify when there's no ticker
        if not ticker:
            skipped_no_ticker += 1
            # Reduce log noise from tickerless items.  Use debug level so
            # these messages do not clutter normal logs.  See issue
            # #noise_filter.  The source and empty ticker are still captured
            # via metrics (skipped_no_ticker) but not logged as info.
            log.debug("item_parse_skip source=%s ticker=%s", source, ticker)
            continue

        # Filter crypto tickers (unless on watchlist)
        # Block alerts on cryptocurrency tickers (BTC, ETH, SOL, etc.) that user doesn't trade.
        # Exception: If ticker is on user's watchlist, allow it through.
        # This prevents crypto news summaries from cluttering stock alerts.
        from catalyst_bot.validation import is_crypto_ticker
        if is_crypto_ticker(ticker, watchlist_tickers):
            skipped_crypto += 1
            log.info("crypto_ticker_rejected ticker=%s", ticker)
            continue

        # Ticker relevance check - verify ticker appears in article content
        # Prevents false positives where feed ticker doesn't match article subject
        # Examples: [AMC] article about BYND, [QMCO] article that never mentions QMCO
        # This catches ticker misidentification by news aggregators
        # NOTE: SEC sources are BYPASSED - they use CIK-to-ticker mapping which is reliable,
        # and SEC filing titles contain CIK numbers (not ticker symbols)
        try:
            title = it.get("title") or ""
            summary = it.get("summary") or ""
            combined_text = f"{title} {summary}".upper()

            # Check if ticker appears in content (case-insensitive)
            # Bypass for SEC sources - they use CIK numbers in titles, not ticker symbols
            if ticker and not _is_sec_source(source) and ticker not in combined_text:
                # Ticker doesn't appear in article - likely misidentified
                skipped_ticker_relevance += 1
                log.info("ticker_not_mentioned ticker=%s title=%s", ticker, title[:60])
                continue
        except Exception as e:
            # Don't crash on relevance check errors - log and continue
            log.debug("ticker_relevance_check_error ticker=%s err=%s", ticker, e.__class__.__name__)

        # WAVE 1.2: OTC Stock Filter
        # Block alerts on illiquid OTC/pink sheet stocks unsuitable for day trading.
        # Uses yfinance to check exchange field (cached for performance).
        # This check happens AFTER ticker extraction but BEFORE classification
        # to save processing on illiquid stocks.
        if getattr(settings, "filter_otc_stocks", True):
            try:
                is_otc_ticker = ticker_validator.is_otc(ticker)

                if is_otc_ticker:
                    log.info(
                        "otc_ticker_rejected ticker=%s title=%s",
                        ticker,
                        (it.get("title") or "")[:50],
                    )
                    skipped_otc += 1

                    # MOA Phase 1: Log rejected item for analysis
                    try:
                        px = None
                        if ticker in price_cache:
                            px, _ = price_cache[ticker]
                        log_rejected_item(
                            item=it,
                            rejection_reason="OTC_EXCHANGE",
                            price=px,
                            score=None,
                            sentiment=None,
                            keywords=None,
                        )
                    except Exception:
                        pass  # Don't crash on MOA logging failures

                    continue  # Skip to next item
            except Exception as e:
                # Don't crash on OTC check failures - log warning and continue processing
                log.warning("otc_check_failed ticker=%s err=%s", ticker, str(e))
                # Fail-open: Continue processing on error to avoid blocking valid alerts

        # Fix 9: Minimum Average Volume Filter
        # Filter low liquidity stocks that are hard to trade (low volume = wide spreads, slippage)
        # Uses yfinance to fetch average volume. Skipped if MIN_AVG_VOLUME not set.
        min_avg_vol = getattr(settings, "min_avg_volume", None)
        if min_avg_vol is not None and ticker:
            try:
                import yfinance as yf
                ticker_obj = yf.Ticker(ticker)
                info = ticker_obj.info
                avg_volume = info.get("averageVolume") or info.get("averageVolume10days") or 0

                if avg_volume < min_avg_vol:
                    log.info(
                        "low_volume_rejected ticker=%s avg_volume=%d threshold=%d",
                        ticker,
                        avg_volume,
                        min_avg_vol,
                    )
                    skipped_low_volume += 1
                    continue  # Skip low volume ticker
            except Exception as e:
                # Don't crash on volume fetch failures - log and continue
                log.debug("volume_fetch_failed ticker=%s err=%s", ticker, e.__class__.__name__)

        # Unit/Warrant/Rights Filter
        # Block alerts on derivative securities (units, warrants, rights) which have
        # low liquidity and are unsuitable for day trading.
        # This check uses ticker suffix patterns (U, W, WS, WT, R).
        try:
            is_unit_or_warrant = ticker_validator.is_unit_or_warrant(ticker)

            if is_unit_or_warrant:
                log.info(
                    "unit_warrant_rejected ticker=%s title=%s",
                    ticker,
                    (it.get("title") or "")[:50],
                )
                skipped_unit_warrant += 1

                # MOA Phase 1: Log rejected item for analysis
                try:
                    px = None
                    if ticker in price_cache:
                        px, _ = price_cache[ticker]
                    log_rejected_item(
                        item=it,
                        rejection_reason="UNIT_WARRANT_RIGHTS",
                        price=px,
                        score=None,
                        sentiment=None,
                        keywords=None,
                    )
                except Exception:
                    pass  # Don't crash on MOA logging failures

                continue  # Skip to next item
        except Exception as e:
            # Don't crash on unit/warrant check failures - log warning and continue processing
            log.warning("unit_warrant_check_failed ticker=%s err=%s", ticker, str(e))
            # Fail-open: Continue processing on error to avoid blocking valid alerts

        # Check article freshness (reject stale news)
        try:
            max_article_age = getattr(settings, "max_article_age_minutes", 30)
            max_sec_age = getattr(settings, "max_sec_filing_age_minutes", 240)
            is_sec = "sec.gov" in (it.get("link") or "").lower()  # Simple SEC detection

            item_published_at = it.get("published_at")
            is_fresh, age_min = is_article_fresh(
                item_published_at,
                max_age_minutes=max_article_age,
                max_sec_age_minutes=max_sec_age,
                is_sec_filing=is_sec,
            )

            if not is_fresh:
                log.info(
                    "item_rejected_stale ticker=%s age_minutes=%d title=%s",
                    ticker,
                    age_min or 0,
                    (it.get("title") or "")[:50],
                )
                skipped_stale += 1
                # MOA Phase 1: Log rejected item for analysis
                try:
                    px = None
                    if ticker in price_cache:
                        px, _ = price_cache[ticker]
                    log_rejected_item(
                        item=it,
                        rejection_reason="STALE_ARTICLE",
                        price=px,
                        score=None,
                        sentiment=None,
                        keywords=None,
                    )
                except Exception:
                    pass
                continue  # Skip to next item
        except Exception as e:
            # Don't crash on freshness check errors - allow through
            log.debug("freshness_check_error err=%s", str(e))

        # DEFENSIVE CHECK: Block OTC and foreign ADR tickers (user requirement)
        # This provides redundant protection in case ticker extraction/validation is bypassed
        # OTC suffixes: OTC, PK, QB, QX (case-insensitive)
        # Foreign ADR: 5+ characters ending in 'F'
        ticker_upper = ticker.upper()
        if ticker_upper.endswith(("OTC", "PK", "QB", "QX")):
            skipped_instr += 1  # Count as instrument-like for metrics
            try:
                px = None
                if ticker in price_cache:
                    px, _ = price_cache[ticker]
                log_rejected_item(
                    item=it,
                    rejection_reason="OTC_TICKER",
                    price=px,
                    score=None,
                    sentiment=None,
                    keywords=None,
                )
            except Exception:
                pass
            log.info("skip_otc_ticker source=%s ticker=%s", source, ticker)
            continue

        # Block foreign ADRs (5+ chars ending in F)
        if ticker_upper.endswith("F") and len(ticker_upper) >= 5:
            skipped_instr += 1  # Count as instrument-like for metrics
            try:
                px = None
                if ticker in price_cache:
                    px, _ = price_cache[ticker]
                log_rejected_item(
                    item=it,
                    rejection_reason="FOREIGN_ADR",
                    price=px,
                    score=None,
                    sentiment=None,
                    keywords=None,
                )
            except Exception:
                pass
            log.info("skip_foreign_adr source=%s ticker=%s", source, ticker)
            continue

        # Drop warrants/units/etc (refined)
        if ignore_instr and _is_instrument_like(ticker):
            skipped_instr += 1
            # MOA Phase 1: Log rejected item for analysis (before classification)
            try:
                # Try to get price from cache (batch fetch happened earlier)
                px = None
                if ticker in price_cache:
                    px, _ = price_cache[ticker]
                log_rejected_item(
                    item=it,
                    rejection_reason="INSTRUMENT_LIKE",
                    price=px,
                    score=None,
                    sentiment=None,
                    keywords=None,
                )
            except Exception:
                pass  # Don't crash on logging failures
            # Use debug level for instrument‑like tickers to reduce log spam.
            log.debug("skip_instrument_like_ticker source=%s ticker=%s", source, ticker)
            continue

        # ========================================================================
        # EARLY PRICE FILTERING - Check price BEFORE expensive ML sentiment analysis
        # This prevents wasting 5+ minutes processing 625 earnings items that will
        # be filtered out anyway. Price check must happen before fast_classify().
        # ========================================================================
        last_px = None
        last_chg = None

        # Use batch-fetched price cache when available
        if ticker in price_cache:
            last_px, last_chg = price_cache[ticker]
        else:
            # Fallback to individual lookup (only if price gates set)
            if price_ceiling is not None or price_floor is not None:
                try:
                    last_px, last_chg = market.get_last_price_change(ticker)
                except Exception as price_err:
                    log.debug(
                        "early_price_fetch_failed ticker=%s source=%s err=%s",
                        ticker,
                        source,
                        str(price_err),
                    )
                    # If ceiling or floor is set and price lookup failed, skip (can't enforce)
                    skipped_price_gate += 1
                    continue

        # Enforce price ceiling EARLY (before ML inference)
        if price_ceiling is not None:
            if last_px is None:
                log.debug(
                    "early_price_skip_no_data ticker=%s source=%s",
                    ticker,
                    source,
                )
                skipped_price_gate += 1
                continue

            # Check for NaN/Inf
            import math
            if math.isnan(last_px) or not math.isfinite(last_px):
                log.debug(
                    "early_price_skip_invalid ticker=%s price=%s source=%s",
                    ticker,
                    last_px,
                    source,
                )
                skipped_price_gate += 1
                continue

            if float(last_px) > float(price_ceiling):
                log.debug(
                    "early_price_skip_ceiling ticker=%s price=%.2f ceiling=%.2f source=%s",
                    ticker,
                    last_px,
                    price_ceiling,
                    source,
                )
                skipped_price_gate += 1
                continue

        # Enforce price floor EARLY (before ML inference)
        if price_floor is not None:
            if last_px is None:
                log.debug(
                    "early_price_skip_no_data_floor ticker=%s source=%s",
                    ticker,
                    source,
                )
                skipped_price_gate += 1
                continue

            import math
            if math.isnan(last_px) or not math.isfinite(last_px):
                log.debug(
                    "early_price_skip_invalid_floor ticker=%s price=%s source=%s",
                    ticker,
                    last_px,
                    source,
                )
                skipped_price_gate += 1
                continue

            if float(last_px) < float(price_floor):
                log.debug(
                    "early_price_skip_floor ticker=%s price=%.2f floor=%.2f source=%s",
                    ticker,
                    last_px,
                    price_floor,
                    source,
                )
                skipped_price_gate += 1
                continue

        # ========================================================================
        # END EARLY PRICE FILTERING
        # ========================================================================

        # ========================================================================
        # EARLY CATEGORY FILTERING - Filter earnings BEFORE expensive ML sentiment
        # This is the CRITICAL fix: earnings calendars waste 5+ minutes on ML inference
        # even though they're all filtered by category gate later. Check category early!
        # ========================================================================

        # DEBUG: Log first few items to see actual values
        if it.get("source") and "Finnhub" in str(it.get("source")):
            log.info(
                "DIAGNOSTIC source=%s category=%s event_type=%s ticker=%s",
                it.get("source"),
                it.get("category"),
                it.get("event_type"),
                ticker,
            )

        is_earnings = (
            source == "Finnhub Earnings" or
            it.get("category") == "earnings" or
            it.get("event_type") == "earnings"
        )

        if is_earnings:
            log.info(
                "early_category_skip_earnings ticker=%s source=%s category=%s event_type=%s",
                ticker,
                source,
                it.get("category", "unknown"),
                it.get("event_type", "unknown"),
            )
            skipped_cat_gate += 1
            continue
        # ========================================================================
        # END EARLY CATEGORY FILTERING
        # ========================================================================

        # WAVE 3: Fast classify (keywords, sentiment, ML) - NO market enrichment
        # Market data (RVOL, float, VWAP, divergence) deferred until after filtering
        try:
            scored = fast_classify(
                item=market.NewsItem.from_feed_dict(it),  # type: ignore[attr-defined]
                keyword_weights=dyn_weights,
            )
        except (AttributeError, KeyError, TypeError, ValueError) as err:
            # CRITICAL FIX: Handle specific exceptions for better debugging
            log.warning(
                "classify_error source=%s ticker=%s err=%s err_type=%s item=%s",
                source,
                ticker,
                str(err),
                err.__class__.__name__,
                json.dumps(
                    {
                        k: it.get(k)
                        for k in ("source", "title", "link", "id", "summary", "ticker")
                    },
                    ensure_ascii=False,
                ),
                exc_info=True,
            )
            try:
                scored = _fallback_classify(
                    title=it.get("title", "") or it.get("summary", ""),
                    keyword_categories=getattr(settings, "keyword_categories", {}),
                    default_weight=float(
                        getattr(settings, "default_keyword_weight", 1.0)
                    ),
                    dynamic_weights=dyn_weights,
                )
            except (AttributeError, KeyError, TypeError, ValueError) as fallback_err:
                # CRITICAL FIX: Log specific fallback errors
                log.error(
                    "fallback_classify_failed source=%s ticker=%s err=%s err_type=%s",
                    source,
                    ticker,
                    str(fallback_err),
                    fallback_err.__class__.__name__,
                    exc_info=True,
                )
                # If even fallback breaks, skip this one
                continue

        # WAVE 4: SEC LLM Integration - Lookup from batch-processed cache
        # Keywords were extracted in parallel during preprocessing (lines 1188-1216)
        if _is_sec_source(source):
            item_id = it.get("id") or it.get("link") or ""
            llm_result = sec_llm_cache.get(item_id, {})

            if llm_result and llm_result.get("keywords"):
                # Merge LLM keywords into scored object
                llm_keywords = llm_result.get("keywords", [])
                existing_keywords = _keywords_of(scored)

                # Combine and deduplicate keywords
                merged_keywords = list(set(existing_keywords + llm_keywords))

                # Update scored object with merged keywords
                if isinstance(scored, dict):
                    scored["keywords"] = merged_keywords
                elif hasattr(scored, "_asdict"):
                    # namedtuple - convert to dict, update, keep as dict
                    scored = scored._asdict()
                    scored["keywords"] = merged_keywords
                elif hasattr(scored, "keywords"):
                    scored.keywords = merged_keywords

                log.info(
                    "sec_llm_keywords_merged source=%s ticker=%s "
                    "original=%d llm=%d merged=%d",
                    source,
                    ticker,
                    len(existing_keywords),
                    len(llm_keywords),
                    len(merged_keywords),
                )

        # NOTE: Price gating moved EARLY (before fast_classify) to avoid wasting
        # 5+ minutes on ML inference for items that will be filtered by price.
        # See "EARLY PRICE FILTERING" section above (lines ~1889-1985).
        # last_px and last_chg are already set from early check.

        # -------- Classifier gating (score / sentiment / category) ----------
        scr = _score_of(scored)
        snt = _sentiment_of(scored)

        # Smart negative threshold: Strong negative catalysts bypass MIN_SCORE
        # This ensures high-impact negative events (dilution, bankruptcy, etc.)
        # always alert even if score is below threshold due to sentiment adjustments
        is_strong_negative = False

        # Check 1: Strong negative sentiment (< -0.30)
        if snt < -0.30:
            is_strong_negative = True
            log.info(
                "strong_negative_detected ticker=%s sentiment=%.3f reason=strong_sentiment",
                ticker, snt
            )

        # Check 2: Critical negative keywords (always alert)
        if not is_strong_negative:
            critical_negative_keywords = [
                "dilution", "offering", "warrant", "delisting", "bankruptcy",
                "trial failed", "fda rejected", "lawsuit", "going concern",
                "chapter 11", "restructuring", "default", "insolvent"
            ]

            title_lower = (it.get("title") or "").lower()
            summary_lower = (it.get("summary") or "").lower()
            combined_text = f"{title_lower} {summary_lower}"

            for keyword in critical_negative_keywords:
                if keyword in combined_text:
                    is_strong_negative = True
                    log.info(
                        "strong_negative_detected ticker=%s keyword='%s' reason=critical_keyword",
                        ticker, keyword
                    )
                    break

        # Apply dual threshold logic
        if (min_score is not None) and (scr < min_score):
            if is_strong_negative:
                # Bypass MIN_SCORE for strong negatives
                strong_negatives_bypassed += 1
                log.info(
                    "min_score_bypassed ticker=%s score=%.3f sentiment=%.3f reason=strong_negative",
                    ticker, scr, snt
                )
                # Continue processing (don't skip)
            else:
                # Normal low score skip
                skipped_low_score += 1
                # MOA Phase 1: Log rejected item for analysis
                try:
                    log_rejected_item(
                        item=it,
                        rejection_reason="LOW_SCORE",
                        price=last_px,
                        score=scr,
                        sentiment=snt,
                        keywords=_keywords_of(scored),
                        scored=scored,
                    )
                except Exception:
                    pass  # Don't crash on logging failures
                continue

        # Sentiment gate (snt already extracted above)
        # Note: Strong negatives should already pass this gate since they have high absolute sentiment,
        # but we check is_strong_negative here for consistency with the score bypass logic
        if (min_sent_abs is not None) and (abs(snt) < min_sent_abs):
            if is_strong_negative:
                # Strong negatives can also bypass sentiment gate (though typically not needed)
                log.info(
                    "sent_gate_bypassed ticker=%s abs_sentiment=%.3f reason=strong_negative",
                    ticker, abs(snt)
                )
                # Continue processing (don't skip)
            else:
                skipped_sent_gate += 1
                # MOA Phase 1: Log rejected item for analysis
                try:
                    log_rejected_item(
                        item=it,
                        rejection_reason="SENT_GATE",
                        price=last_px,
                        score=scr,
                        sentiment=snt,
                        keywords=_keywords_of(scored),
                        scored=scored,
                    )
                except Exception:
                    pass  # Don't crash on logging failures
                continue

        if cats_allow:
            kwords = {k.lower() for k in _keywords_of(scored)}
            if not (kwords & cats_allow):
                skipped_cat_gate += 1
                # MOA Phase 1: Log rejected item for analysis
                try:
                    log_rejected_item(
                        item=it,
                        rejection_reason="CAT_GATE",
                        price=last_px,
                        score=scr,
                        sentiment=snt,
                        keywords=list(kwords),
                        scored=scored,
                    )
                except Exception:
                    pass  # Don't crash on logging failures
                continue

        # WAVE 3: Item passed all filters - Queue for async enrichment and WAIT for it
        # Enrichment (RVOL, float, VWAP, divergence) must complete before alert
        # This ensures alerts show all market data fields
        enriched_scored = scored  # Default to non-enriched if enrichment fails
        try:
            news_item = market.NewsItem.from_feed_dict(it)  # type: ignore[attr-defined]
            enrichment_task_id = enqueue_for_enrichment(scored, news_item)
            log.debug(
                "enrichment_queued ticker=%s task_id=%s",
                ticker,
                enrichment_task_id
            )

            # CRITICAL: Wait for enrichment to complete before sending alert
            # This allows alerts to show Price, Float, Volume, RVol, RSI, etc.
            enriched_result = get_enriched_item(enrichment_task_id, timeout=5.0)
            if enriched_result:
                enriched_scored = enriched_result
                log.debug(
                    "enrichment_completed ticker=%s task_id=%s",
                    ticker,
                    enrichment_task_id
                )
            else:
                log.warning(
                    "enrichment_timeout ticker=%s task_id=%s timeout=5.0s",
                    ticker,
                    enrichment_task_id
                )
        except Exception as enrich_err:
            # Don't block alerts if enrichment fails - send with basic data
            log.warning(
                "enrichment_failed ticker=%s err=%s",
                ticker,
                str(enrich_err)
            )

        # Build a payload the new alerts API understands
        # Use enriched_scored (which has market data) instead of scored
        alert_payload = {
            "item": it,
            "scored": (
                enriched_scored._asdict()
                if hasattr(enriched_scored, "_asdict")
                else (enriched_scored.dict() if hasattr(enriched_scored, "dict") else enriched_scored)
            ),
            "last_price": last_px,
            "last_change_pct": last_chg,
            "record_only": settings.feature_record_only,
            "webhook_url": _resolve_main_webhook(settings),
            # WAVE 0.0 Phase 2: Pass market info to alerts for feature gating
            # The alerts module can use this to skip LLM classification and
            # chart generation when market is closed (if configured).
            "market_info": market_info,
        }

        # Send (or record-only) alert with compatibility shim
        try:
            # Prefer the new signature: send_alert_safe(payload)
            ok = send_alert_safe(alert_payload)
        except TypeError as type_err:
            # Fall back to the legacy keyword-args signature
            log.debug("alert_signature_fallback err=%s", str(type_err))
            try:
                ok = send_alert_safe(
                    item_dict=it,
                    scored=enriched_scored,  # Use enriched version
                    last_price=last_px,
                    last_change_pct=last_chg,
                    record_only=settings.feature_record_only,
                    webhook_url=_resolve_main_webhook(settings),
                )
            except (requests.exceptions.RequestException, ConnectionError, TimeoutError) as req_err:
                # CRITICAL FIX: Handle network-specific errors
                log.error(
                    "alert_network_error source=%s ticker=%s err=%s err_type=%s",
                    source,
                    ticker,
                    str(req_err),
                    req_err.__class__.__name__,
                    exc_info=True,
                )
                ok = False
            except (AttributeError, KeyError, ValueError) as data_err:
                # CRITICAL FIX: Handle data-related errors
                log.error(
                    "alert_data_error source=%s ticker=%s err=%s err_type=%s",
                    source,
                    ticker,
                    str(data_err),
                    data_err.__class__.__name__,
                    exc_info=True,
                )
                ok = False
        except (requests.exceptions.RequestException, ConnectionError, TimeoutError) as req_err:
            # CRITICAL FIX: Handle network-specific errors
            log.error(
                "alert_network_error source=%s ticker=%s err=%s err_type=%s",
                source,
                ticker,
                str(req_err),
                req_err.__class__.__name__,
                exc_info=True,
            )
            ok = False
        except (AttributeError, KeyError, ValueError) as data_err:
            # CRITICAL FIX: Handle data-related errors
            log.error(
                "alert_data_error source=%s ticker=%s err=%s err_type=%s",
                source,
                ticker,
                str(data_err),
                data_err.__class__.__name__,
                exc_info=True,
            )
            ok = False

        if ok:
            alerted += 1

            # FIXED: Mark item as seen ONLY after successful alert delivery.
            # This prevents race condition where failed alerts are marked seen.
            try:
                item_id = it.get("id") or ""
                if item_id and seen_store:
                    seen_store.mark_seen(item_id)
                    log.info("marked_seen item_id=%s ticker=%s", item_id, ticker)
            except Exception as mark_err:
                # Don't crash if marking fails, but log it
                log.warning("mark_seen_failed item_id=%s err=%s", item_id, str(mark_err))

            # FALSE POSITIVE ANALYSIS: Log accepted item for outcome tracking
            # Store classification data, keywords, scores for later analysis
            try:
                log_accepted_item(
                    item=it,
                    price=last_px,
                    score=scr,
                    sentiment=snt,
                    keywords=_keywords_of(scored),
                    scored=scored,
                )
            except Exception:
                pass  # Don't crash on logging failures

            # Optional: tiny jitter after success to avoid draining the bucket at once
            if jitter_ms > 0:
                time.sleep(max(0.0, min(jitter_ms, 1000)) / 1000.0 * random.random())

            # When the watchlist cascade feature is enabled, promote this
            # ticker to HOT in the cascade state after sending an alert.  Any
            # errors while updating the state are ignored.  Promotion
            # timestamp is set by the helper.
            try:
                if getattr(settings, "feature_watchlist_cascade", False) and ticker:
                    from catalyst_bot.watchlist_cascade import (
                        load_state,
                        promote_ticker,
                        save_state,
                    )

                    state_path = getattr(settings, "watchlist_state_file", "")
                    state = load_state(state_path)
                    promote_ticker(state, ticker, state_name="HOT")
                    save_state(state_path, state)
            except Exception:
                # ignore promotion errors
                pass

            # Register alert for breakout feedback tracking
            try:
                if not settings.feature_record_only:
                    # Extract keywords from classification
                    keywords = scored.keywords if hasattr(scored, "keywords") else []
                    confidence = (
                        scored.confidence if hasattr(scored, "confidence") else 0.5
                    )

                    register_alert_for_tracking(
                        ticker=ticker,
                        entry_price=last_px,
                        entry_volume=None,  # Volume not readily available here
                        timestamp=datetime.now(timezone.utc),
                        keywords=keywords,
                        confidence=confidence,
                    )
            except Exception as e:
                # Don't fail the alert if tracking registration fails
                log.debug(f"feedback_registration_failed ticker={ticker} err={e}")

            # Paper Trading Integration - Process scored item for trading signal
            if trading_engine and getattr(settings, "FEATURE_PAPER_TRADING", False):
                try:
                    import asyncio
                    from decimal import Decimal

                    # Convert price to Decimal for TradingEngine
                    current_price = Decimal(str(last_px)) if last_px else None

                    if current_price and ticker:
                        # Run async trading engine call in sync context
                        try:
                            loop = asyncio.get_running_loop()
                            # Already in async context - shouldn't happen
                            log.warning("trading_engine_call_in_async_context ticker=%s", ticker)
                        except RuntimeError:
                            # No loop exists, safe to use asyncio.run()
                            position_id = asyncio.run(
                                trading_engine.process_scored_item(scored, ticker, current_price)
                            )
                            if position_id:
                                log.info("trading_position_opened ticker=%s position_id=%s", ticker, position_id)
                except Exception as e:
                    # Never crash the bot - just log trading errors
                    log.error("trading_engine_error ticker=%s err=%s", ticker, str(e), exc_info=True)

            # Optional: subscribe to Alpaca stream after sending an alert.  Run
            # asynchronously so we do not block the runner loop.  The feature
            # requires FEATURE_ALPACA_STREAM=1, valid credentials and a non‑zero
            # stream_sample_window_sec.  Use getattr on settings to avoid
            # resolving when not needed.
            try:
                if getattr(settings, "feature_alpaca_stream", False):
                    win_secs = getattr(settings, "stream_sample_window_sec", 0) or 0
                    if win_secs and ticker:
                        # Spawn a daemon thread to sample the stream; pass the
                        # ticker in a list.  The helper will handle sleeping.
                        threading.Thread(
                            target=sample_alpaca_stream,
                            args=([ticker], win_secs),
                            daemon=True,
                        ).start()
            except Exception:
                # Ignore all streaming errors
                pass

            # Optional: stop early if we hit the cap
            if max_alerts_per_cycle > 0 and alerted >= max_alerts_per_cycle:
                log.info("alert_cap_reached cap=%s", max_alerts_per_cycle)
                break
        else:
            # Downgrade to info to avoid spammy warnings for legitimate skips
            log.info("alert_skip source=%s ticker=%s", source, ticker)

    # Final cycle metrics
    # Use a single log line for compatibility with upstream monitoring; update
    # LAST_CYCLE_STATS to expose counts for the heartbeat embed.
    log.info(
        "cycle_metrics items=%s deduped=%s tickers_present=%s tickers_missing=%s "
        "dyn_weights=%s dyn_path_exists=%s dyn_path='%s' price_ceiling=%s "
        "skipped_no_ticker=%s skipped_crypto=%s skipped_ticker_relevance=%s skipped_price_gate=%s skipped_instr=%s skipped_by_source=%s "
        "skipped_multi_ticker=%s skipped_data_presentation=%s skipped_stale=%s skipped_otc=%s skipped_unit_warrant=%s skipped_low_volume=%s skipped_low_score=%s skipped_sent_gate=%s skipped_cat_gate=%s "
        "strong_negatives_bypassed=%s alerted=%s",
        len(items),
        len(deduped),
        tickers_present,
        tickers_missing,
        "yes" if dyn_loaded else "no",
        "yes" if dyn_path_exists else "no",
        dyn_path_str,
        price_ceiling,
        skipped_no_ticker,
        skipped_crypto,
        skipped_ticker_relevance,
        skipped_price_gate,
        skipped_instr,
        skipped_by_source,
        skipped_multi_ticker,
        skipped_data_presentation,
        skipped_stale,
        skipped_otc,
        skipped_unit_warrant,
        skipped_low_volume,
        skipped_low_score,
        skipped_sent_gate,
        skipped_cat_gate,
        strong_negatives_bypassed,
        alerted,
    )
    # Patch‑2: update global cycle stats for heartbeat and accumulate totals.
    try:
        global LAST_CYCLE_STATS, TOTAL_STATS
        skipped_total = (
            skipped_no_ticker
            + skipped_crypto
            + skipped_ticker_relevance
            + skipped_price_gate
            + skipped_instr
            + skipped_by_source
            + skipped_multi_ticker
            + skipped_data_presentation
            + skipped_stale
            + skipped_otc
            + skipped_unit_warrant
            + skipped_low_volume
            + skipped_low_score
            + skipped_sent_gate
            + skipped_cat_gate
            + skipped_seen
        )
        # Per‑cycle snapshot for immediate heartbeat display
        LAST_CYCLE_STATS = {
            "items": len(items),
            "deduped": len(deduped),
            "skipped": skipped_total,
            "alerts": alerted,
        }
        # Add this cycle's counts to the cumulative totals
        try:
            TOTAL_STATS["items"] += len(items)
            TOTAL_STATS["deduped"] += len(deduped)
            TOTAL_STATS["skipped"] += skipped_total
            TOTAL_STATS["alerts"] += alerted
        except Exception:
            # ensure totals exist; fallback silently
            pass
        # WAVE ALPHA Agent 1: Update heartbeat accumulator with cycle stats
        try:
            global _heartbeat_acc
            _heartbeat_acc.add_cycle(
                scanned=len(items),
                alerts=alerted,
                errors=0,  # Could track errors in future enhancement
            )
        except Exception:
            # ignore accumulator errors
            pass
    except Exception:
        # ignore any errors when updating stats
        pass

    # ---------------------------------------------------------------------
    # Wave‑4: accumulate per-category log entries for the auto analyzer.
    # Each count is expanded into individual entries with the current
    # timestamp and category.  Categories are filtered against
    # LOG_REPORT_CATEGORIES to avoid populating unused logs.
    try:
        now_utc = datetime.now(timezone.utc)
        counts = {
            "items": len(items),
            "deduped": len(deduped),
            "skipped_no_ticker": skipped_no_ticker,
            "skipped_crypto": skipped_crypto,
            "skipped_ticker_relevance": skipped_ticker_relevance,
            "skipped_price_gate": skipped_price_gate,
            "skipped_instr": skipped_instr,
            "skipped_by_source": skipped_by_source,
            "skipped_multi_ticker": skipped_multi_ticker,
            "skipped_data_presentation": skipped_data_presentation,
            "skipped_stale": skipped_stale,
            "skipped_otc": skipped_otc,
            "skipped_unit_warrant": skipped_unit_warrant,
            "skipped_low_volume": skipped_low_volume,
            "skipped_low_score": skipped_low_score,
            "skipped_sent_gate": skipped_sent_gate,
            "skipped_cat_gate": skipped_cat_gate,
            "skipped_seen": skipped_seen,
        }
        for cat, cnt in counts.items():
            if cat in LOG_REPORT_CATEGORIES and cnt:
                for _ in range(cnt):
                    LOG_ENTRIES.append({"timestamp": now_utc, "category": cat})
    except Exception:
        # do not fail the cycle due to logging errors
        pass

    # ---------------------------------------------------------------------
    # Auto analyzer & log reporter: run scheduled tasks and deliver digest.
    try:

        def _analyze_wrapper() -> None:
            # Wrap analyzer call to use fresh settings each time
            try:
                run_analyzer_once_if_scheduled(get_settings())
            except Exception as e:
                # Log any analyzer error but do not propagate
                log.warning(
                    "analyzer_schedule error=%s",
                    e.__class__.__name__,
                    exc_info=True,
                )

        def _report_wrapper(md: str) -> None:
            """Deliver the log digest via configured destination(s)."""
            # Always delegate to deliver_report to handle file writes.
            try:
                deliver_report(md)
            except Exception:
                pass
            # Post to admin webhook as an embed when destination is not 'file'.
            try:
                s2 = get_settings()
                dest = os.getenv("ADMIN_LOG_DESTINATION", "").strip().lower()
                if not dest:
                    from catalyst_bot.config_extras import (
                        ADMIN_LOG_DESTINATION as _defdest,
                    )

                    dest = _defdest.lower()
                if dest != "file":
                    admin_url = (
                        getattr(s2, "admin_webhook_url", None)
                        or os.getenv("DISCORD_ADMIN_WEBHOOK", "")
                        or os.getenv("ADMIN_WEBHOOK", "")
                    )
                    if admin_url:
                        try:
                            # truncate description to avoid Discord limits
                            desc = md if len(md) <= 3900 else md[:3897] + "..."
                            payload = {
                                "embeds": [
                                    {
                                        "title": "Log Summary",
                                        "description": desc,
                                    }
                                ]
                            }
                            _alerts.post_discord_json(payload, webhook_url=admin_url)
                        except Exception:
                            pass
            except Exception:
                pass

        # Invoke scheduled tasks with current time, log list, analyzer and reporter
        run_scheduled_tasks(
            datetime.now(timezone.utc),
            LOG_ENTRIES,
            analyze_fn=_analyze_wrapper,
            report_fn=_report_wrapper,
        )

        # Check if it's time to send nightly admin report
        try:
            send_admin_report_if_scheduled()
        except Exception as e:
            log.warning("admin_report_check_failed err=%s", str(e))

        # Check if it's time to send weekly performance report
        try:
            send_weekly_report_if_scheduled()
        except Exception as e:
            log.warning("weekly_report_check_failed err=%s", str(e))

        # NOTE: MOA nightly check moved to main loop (before weekend skip logic)
        # to ensure it runs even when scans are skipped on weekends

        # Track pending alert outcomes (15m, 1h, 4h, 1d)
        try:
            track_pending_outcomes()
        except Exception as e:
            log.warning("outcome_tracking_failed err=%s", str(e))

        # MOA Phase 2: Track price outcomes for rejected items (1h, 4h, 1d, 7d)
        try:
            track_moa_outcomes()
        except Exception as e:
            log.warning("moa_tracking_failed err=%s", str(e))

        # WAVE 1.2: Feedback loop periodic tasks
        if FEEDBACK_AVAILABLE:
            s = get_settings()

            # Score pending alerts (check every cycle)
            if getattr(s, "feature_feedback_loop", False):
                try:
                    scored_count = score_pending_alerts()
                    if scored_count > 0:
                        log.info("feedback_alerts_scored count=%d", scored_count)
                except Exception as e:
                    log.warning("feedback_scoring_failed err=%s", str(e))

            # Send weekly report if scheduled
            if getattr(s, "feature_feedback_weekly_report", False):
                try:
                    send_feedback_weekly_report()
                except Exception as e:
                    log.warning("feedback_weekly_report_failed err=%s", str(e))

            # Analyze keyword performance and send recommendations (once per day)
            # Piggybacking on the same time as admin reports
            if getattr(s, "feature_feedback_loop", False):
                try:
                    from datetime import datetime, timezone

                    now = datetime.now(timezone.utc)
                    # Run at same time as analyzer (21:30 UTC by default)
                    if (
                        now.hour == getattr(s, "analyzer_utc_hour", 21)
                        and now.minute >= getattr(s, "analyzer_utc_minute", 30)
                        and now.minute < getattr(s, "analyzer_utc_minute", 30) + 5
                    ):
                        recommendations = analyze_keyword_performance(lookback_days=7)
                        auto_apply = getattr(s, "feedback_auto_adjust", False)

                        if recommendations:
                            applied = apply_weight_adjustments(
                                recommendations, auto_apply=auto_apply
                            )
                            if applied:
                                log.info(
                                    "keyword_weights_adjusted auto=%s count=%d",
                                    auto_apply,
                                    len(recommendations),
                                )
                except Exception as e:
                    log.warning("feedback_keyword_analysis_failed err=%s", str(e))
    except Exception:
        # Ignore auto analyzer errors to keep the main loop alive
        pass

    # ---------------------------------------------------------------------
    # CRITICAL BUG FIX: Clear ML batch scorer to prevent memory leaks
    # The batch scorer accumulates items without proper cleanup, causing
    # unbounded memory growth in long-running processes.
    try:
        from .classify import clear_ml_batch_scorer

        clear_ml_batch_scorer()
    except Exception:
        # Silently ignore errors - don't break the main loop
        pass

    # ---------------------------------------------------------------------
    # WEEK 1 FIX: Clear price cache to prevent memory leak
    # The global _PX_CACHE dict grows unbounded without cleanup.
    # Clear it at the end of each cycle to prevent 10MB+ growth over 24 hours.
    global _PX_CACHE
    cache_size = len(_PX_CACHE)
    if cache_size > 0:
        _PX_CACHE.clear()
        log.debug("price_cache_cleared entries=%d", cache_size)


def _set_process_priority(log, settings) -> None:
    """
    Set process priority on Windows to reduce CPU contention.

    This function attempts to set the process priority using psutil if available.
    On non-Windows platforms or if psutil is not installed, it silently skips.
    """
    try:
        import sys

        import psutil

        if sys.platform != "win32":
            return

        priority_name = getattr(settings, "bot_process_priority", "BELOW_NORMAL")
        priority_map = {
            "IDLE": psutil.IDLE_PRIORITY_CLASS,
            "BELOW_NORMAL": psutil.BELOW_NORMAL_PRIORITY_CLASS,
            "NORMAL": psutil.NORMAL_PRIORITY_CLASS,
            "ABOVE_NORMAL": psutil.ABOVE_NORMAL_PRIORITY_CLASS,
            "HIGH": psutil.HIGH_PRIORITY_CLASS,
            "REALTIME": psutil.REALTIME_PRIORITY_CLASS,
        }

        priority = priority_map.get(
            priority_name.upper(), psutil.BELOW_NORMAL_PRIORITY_CLASS
        )
        proc = psutil.Process()
        proc.nice(priority)
        log.info("process_priority_set priority=%s", priority_name)
    except ImportError:
        # psutil not available, skip silently
        log.debug("process_priority_skip reason=psutil_not_available")
    except Exception as e:
        # Any other error, log but don't fail
        log.warning("process_priority_failed err=%s", e.__class__.__name__)


def _run_moa_nightly_if_scheduled(log, settings) -> None:
    """
    Run MOA (Missed Opportunities Analyzer) and False Positive Analyzer nightly.

    Checks if it's time to run the nightly MOA analysis at the configured hour
    (default 2 AM UTC). Prevents duplicate runs by tracking last run date.
    Runs asynchronously in a background thread to avoid blocking the main loop.

    The MOA analyzer identifies rejected catalysts that became profitable and
    generates keyword weight recommendations. The false positive analyzer
    identifies patterns in accepted alerts that failed and generates penalty
    recommendations.

    Parameters
    ----------
    log : Logger
        Logger instance for recording execution status
    settings : Settings
        Bot settings (checks moa_nightly_enabled, moa_nightly_hour)
    """
    global _MOA_LAST_RUN_DATE

    # Feature flag check: MOA_NIGHTLY_ENABLED (default True)
    moa_enabled = os.getenv("MOA_NIGHTLY_ENABLED", "1").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }

    if not moa_enabled:
        log.debug("moa_check_skipped reason=disabled")
        return

    # Get configured hour (default 1 = 1 AM UTC = 7 PM CST)
    try:
        moa_hour = int(os.getenv("MOA_NIGHTLY_HOUR", "1").strip() or "1")
    except Exception:
        moa_hour = 1

    # Get configured minute (default 30 = 7:30 PM CST)
    try:
        moa_minute = int(os.getenv("MOA_NIGHTLY_MINUTE", "30").strip() or "30")
    except Exception:
        moa_minute = 30

    now = datetime.now(timezone.utc)
    today = now.date()

    # Already ran today? Skip immediately
    if _MOA_LAST_RUN_DATE == today:
        return

    # Skip weekends (Saturday=5, Sunday=6) - no point analyzing weekend data
    if now.weekday() >= 5:
        return

    # ROBUST SCHEDULING LOGIC:
    # Strategy: Use a 3-hour window with multiple trigger conditions to ensure reliable execution
    #
    # 1. PRIMARY TRIGGER (±10 minute window around exact time):
    #    Run if we're within 10 minutes of target time (1:20-1:40 AM for 1:30 target)
    #
    # 2. FALLBACK TRIGGER (hourly window):
    #    Run anytime during target hour+0 or target hour+1 (1:00-2:59 AM)
    #    if minute >= target minute
    #
    # 3. CATCH-UP TRIGGER (missed window recovery):
    #    Run immediately if we're past target hour+2 (after 3:00 AM) and haven't run today
    #
    # This ensures MOA fires even if:
    # - Bot restarts during target window
    # - Cycles are slow/delayed
    # - System clock drifts slightly

    current_hour = now.hour
    current_minute = now.minute

    # Calculate target time in minutes since midnight for easier comparison
    target_minutes_since_midnight = (moa_hour * 60) + moa_minute
    current_minutes_since_midnight = (current_hour * 60) + current_minute

    # PRIMARY TRIGGER: Within ±10 minutes of exact target time
    time_diff = abs(current_minutes_since_midnight - target_minutes_since_midnight)
    if time_diff <= 10:
        log.info(
            "moa_trigger_primary exact_match=True target=%02d:%02d now=%02d:%02d diff_min=%d",
            moa_hour, moa_minute, current_hour, current_minute, time_diff
        )
    # FALLBACK TRIGGER: Within 3-hour window after target time
    elif (moa_hour <= current_hour < moa_hour + 3) and (current_minute >= moa_minute or current_hour > moa_hour):
        log.info(
            "moa_trigger_fallback window_match=True target=%02d:%02d now=%02d:%02d",
            moa_hour, moa_minute, current_hour, current_minute
        )
    # CATCH-UP TRIGGER: Past 3-hour window but haven't run today
    elif current_hour >= moa_hour + 3:
        log.warning(
            "moa_trigger_catchup missed_window=True target=%02d:%02d now=%02d:%02d last_run=%s",
            moa_hour, moa_minute, current_hour, current_minute,
            _MOA_LAST_RUN_DATE.isoformat() if _MOA_LAST_RUN_DATE else "never"
        )
    # NO TRIGGER: Before target time
    else:
        return

    # Mark as run for today (do this before starting thread to avoid duplicate triggers)
    _MOA_LAST_RUN_DATE = today
    _save_moa_last_run_date(today)  # Persist to survive restarts

    log.info("moa_nightly_scheduled hour=%d minute=%d date=%s", moa_hour, moa_minute, today.isoformat())

    def _run_moa_analysis():
        """Background thread function to run MOA and FP analyzers."""
        try:
            log.info("moa_nightly_start")

            # 1. Run MOA Historical Analyzer
            try:
                from .moa_historical_analyzer import run_historical_moa_analysis

                moa_result = run_historical_moa_analysis()
                if moa_result.get("status") == "success":
                    log.info(
                        "moa_analysis_complete "
                        f"outcomes={moa_result['summary'].get('total_outcomes', 0)} "
                        f"missed={moa_result['summary'].get('missed_opportunities', 0)} "
                        f"recommendations={moa_result.get('recommendations_count', 0)}"
                    )

                    # AUTO-APPLY KEYWORD WEIGHT UPDATES
                    # Read recommendations from the analysis report and apply them to keyword_stats.json
                    # This creates a closed-loop system where nightly analysis automatically updates weights
                    try:
                        from pathlib import Path
                        import json
                        from .moa_historical_analyzer import update_keyword_stats_file

                        # Load recommendations from the analysis report
                        report_path = Path("data/moa/analysis_report.json")
                        if report_path.exists():
                            with open(report_path, 'r', encoding='utf-8') as f:
                                report = json.load(f)
                                recommendations = report.get("recommendations", [])

                                if recommendations:
                                    # Apply recommendations with min confidence threshold (0.6)
                                    stats_path = update_keyword_stats_file(
                                        recommendations, min_confidence=0.6
                                    )
                                    log.info(
                                        "moa_keyword_weights_applied path=%s count=%d",
                                        stats_path,
                                        len(recommendations)
                                    )
                                else:
                                    log.info("moa_no_recommendations_to_apply")
                        else:
                            log.warning("moa_report_not_found path=%s", report_path)
                    except Exception as e:
                        # Don't fail the nightly run if weight update fails
                        log.warning(
                            "moa_keyword_weight_update_failed err=%s",
                            e.__class__.__name__,
                            exc_info=True
                        )
                else:
                    log.warning(
                        "moa_analysis_failed status=%s msg=%s",
                        moa_result.get("status"),
                        moa_result.get("message", "unknown"),
                    )
            except Exception as e:
                log.error(
                    "moa_analysis_error err=%s", e.__class__.__name__, exc_info=True
                )

            # 2. Run False Positive Analyzer
            try:
                from .false_positive_analyzer import run_false_positive_analysis

                fp_result = run_false_positive_analysis()
                if fp_result.get("status") == "success":
                    log.info(
                        "false_positive_analysis_complete "
                        f"accepts={fp_result['summary'].get('total_accepts', 0)} "
                        f"failures={fp_result['summary'].get('failures', 0)} "
                        f"penalties={fp_result.get('penalties_count', 0)}"
                    )
                else:
                    log.warning(
                        "false_positive_analysis_failed status=%s msg=%s",
                        fp_result.get("status"),
                        fp_result.get("message", "unknown"),
                    )
            except Exception as e:
                log.error(
                    "false_positive_analysis_error err=%s",
                    e.__class__.__name__,
                    exc_info=True,
                )

            log.info("moa_nightly_complete")

            # 3. Post Discord completion report
            try:
                from .moa_reporter import post_moa_completion_report

                # Get top_n from env (default: 10)
                top_n = int(os.getenv("MOA_REPORT_TOP_N", "10") or "10")

                # Post report (will check if moa_result/fp_result exist)
                post_moa_completion_report(
                    moa_result=locals().get("moa_result"),
                    fp_result=locals().get("fp_result"),
                    top_n=top_n,
                )
                log.info("moa_discord_report_posted")
            except Exception as e:
                log.warning(
                    "moa_discord_report_failed err=%s", e.__class__.__name__
                )
                # Don't crash MOA thread if Discord posting fails

        except Exception as e:
            log.error(
                "moa_nightly_thread_error err=%s", e.__class__.__name__, exc_info=True
            )

    # Run in background thread (daemon=True so it doesn't block shutdown)
    import threading

    moa_thread = threading.Thread(
        target=_run_moa_analysis,
        daemon=True,
        name="MOA-Nightly",
    )
    moa_thread.start()
    log.info("moa_nightly_thread_started")


def runner_main(
    once: bool = False, loop: bool = False, sleep_s: float | None = None
) -> int:
    global FEEDBACK_AVAILABLE
    global trading_engine

    settings = get_settings()
    setup_logging(settings.log_level)
    log = get_logger("runner")

    # Set process priority (Windows only)
    _set_process_priority(log, settings)

    # Finviz token probe
    finviz_cookie = settings.finviz_auth_token
    if finviz_cookie:
        ok, status = feeds.validate_finviz_token(finviz_cookie)
        finviz_status = f"ok(status={status})" if ok else f"invalid(status={status})"
    else:
        finviz_status = "missing"

    main_webhook = _resolve_main_webhook(settings)
    log.info(
        "boot_start alerts_enabled=%s webhook=%s record_only=%s finviz_token=%s",
        settings.feature_alerts,
        "set" if main_webhook else "missing",
        settings.feature_record_only,
        finviz_status,
    )
    # extra boot context (safe, masked)
    admin_env = (
        os.getenv("DISCORD_ADMIN_WEBHOOK", "") or os.getenv("ADMIN_WEBHOOK", "")
    ).strip()
    target = "admin" if admin_env else ("main" if main_webhook else "none")
    chosen = admin_env or main_webhook or ""
    log.info(
        "boot_ctx target=%s hook=%s skip_sources=%s min_score=%s min_sent_abs=%s",
        target,
        _mask_webhook(chosen),
        os.getenv("SKIP_SOURCES", ""),
        os.getenv("MIN_SCORE", ""),
        os.getenv("MIN_SENT_ABS", ""),
    )

    # Boot heartbeat moved to after TradingEngine initialization (see line ~3868)
    # This ensures portfolio data is available when heartbeat is sent

    # Start position monitor if paper trading is enabled
    try:
        if paper_trader.is_enabled():
            paper_trader.start_position_monitor()
            log.info("paper_trading_monitor_enabled")
    except Exception as e:
        log.error("position_monitor_startup_failed error=%s", str(e))

    # signals
    try:
        signal.signal(signal.SIGINT, _sig_handler)
        signal.signal(signal.SIGTERM, _sig_handler)
    except Exception:
        pass  # Windows quirks shouldn't crash startup

    # Start health check server if enabled
    if os.getenv("FEATURE_HEALTH_ENDPOINT", "1").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    ):
        try:
            health_port = int(os.getenv("HEALTH_CHECK_PORT", "8080"))
            start_health_server(port=health_port)
            log.info("health_endpoint_enabled port=%d", health_port)
            update_health_status(status="starting")
        except Exception as e:
            log.warning("health_endpoint_failed err=%s", str(e))

    # WAVE 1.2: Initialize feedback loop database
    if FEEDBACK_AVAILABLE and getattr(settings, "feature_feedback_loop", False):
        try:
            from pathlib import Path

            init_database()

            # Verify database was created successfully
            db_path = Path("data/feedback/alert_performance.db")
            if not db_path.exists():
                log.error("feedback_database_not_created path=%s", db_path)
                FEEDBACK_AVAILABLE = False
            else:
                log.info("feedback_loop_database_initialized path=%s", db_path)

                # Only start tracker if database is ready and tracking interval is set
                if getattr(settings, "feedback_tracking_interval", 0) > 0:
                    import threading

                    from .feedback.price_tracker import run_tracker_loop

                    tracker_thread = threading.Thread(
                        target=run_tracker_loop,
                        daemon=True,
                        name="FeedbackTracker",
                    )
                    tracker_thread.start()
                    log.info(
                        "feedback_tracker_started interval=%ds",
                        settings.feedback_tracking_interval,
                    )
        except Exception as e:
            log.error("feedback_init_failed err=%s", str(e), exc_info=True)
            FEEDBACK_AVAILABLE = False

    # Quick Win #2: Start SEC EDGAR real-time monitor
    if getattr(settings, "feature_sec_monitor", False):
        try:
            from .sec_monitor import _build_watchlist, start_sec_monitor

            watchlist = _build_watchlist()
            start_sec_monitor(watchlist)

            log.info(
                "sec_monitor_started watchlist_size=%d interval=5min", len(watchlist)
            )
        except ImportError:
            log.warning("sec_monitor_module_not_available")
        except Exception as e:
            log.error("sec_monitor_startup_failed err=%s", str(e))

    # Paper Trading Integration - Initialize TradingEngine
    trading_engine = None
    if TRADING_ENGINE_AVAILABLE and getattr(settings, "feature_paper_trading", False):
        try:
            # Start persistent event loop for trading engine
            started = EventLoopManager.get_instance().start()
            if started:
                log.info("event_loop_manager_started for trading engine")
            else:
                log.warning("event_loop_manager_already_running")

            trading_engine = TradingEngine()

            # Initialize async using run_async (persistent event loop)
            success = run_async(trading_engine.initialize(), timeout=30.0)
            if success:
                log.info("trading_engine_initialized successfully")
            else:
                log.error("trading_engine_init_failed")
                trading_engine = None
        except Exception as e:
            log.error("trading_engine_startup_failed err=%s", str(e), exc_info=True)
            trading_engine = None

    # Send boot heartbeat AFTER TradingEngine initialization
    # This ensures portfolio data is available when heartbeat is sent
    _send_heartbeat(log, settings, reason="boot")

    # Send startup test alert to verify alert pipeline is working
    # This runs through the full pipeline: scoring, enrichment, embed building
    # Uses a synthetic ticker and never gets marked as "seen" so it fires on every restart
    test_alert_enabled = os.getenv("STARTUP_TEST_ALERT", "1").strip() == "1"
    if test_alert_enabled and settings.feature_alerts and main_webhook:
        try:
            from .startup_test_alert import send_startup_test_alert

            log.info("startup_test_alert_triggering")
            send_startup_test_alert(webhook_url=main_webhook)
        except Exception as test_err:
            log.error("startup_test_alert_exception err=%s", str(test_err), exc_info=True)

    do_loop = loop or (not once)
    sleep_interval = float(sleep_s if sleep_s is not None else settings.loop_seconds)

    heartbeat_interval_min_env = os.getenv("HEARTBEAT_INTERVAL_MIN", "").strip()
    try:
        HEARTBEAT_INTERVAL_S = (
            int(heartbeat_interval_min_env) * 60 if heartbeat_interval_min_env else 0
        )
    except Exception:
        HEARTBEAT_INTERVAL_S = 0

    # Track whether market hours detection is enabled
    market_hours_enabled = getattr(settings, "feature_market_hours_detection", False)

    # WAVE ALPHA Agent 3: Track last market status for transition logging
    last_market_status = None

    while True:
        # Start of cycle: clear any per-cycle alert downgrade
        from .alerts import reset_cycle_downgrade

        # WAVE 0.0 Phase 2: Check market status and adjust cycle parameters
        current_market_info = None
        if market_hours_enabled:
            try:
                current_market_info = get_market_info()
                market_status = current_market_info["status"]
                market_features = current_market_info["features"]
                market_cycle_sec = current_market_info["cycle_seconds"]

                # Override sleep_interval with market-aware cycle time
                sleep_interval = float(market_cycle_sec)

                # WAVE ALPHA Agent 3: Log market status transitions
                if (
                    last_market_status is not None
                    and last_market_status != market_status
                ):
                    log.info(
                        "market_status_changed from=%s to=%s cycle_sec=%d features=%s",
                        last_market_status,
                        market_status,
                        market_cycle_sec,
                        ",".join([k for k, v in market_features.items() if v])
                        or "none",
                    )
                last_market_status = market_status

                # Log market status and feature configuration
                enabled_features = [k for k, v in market_features.items() if v]
                log.info(
                    "market_status status=%s cycle=%ds features=%s warmup=%s weekend=%s holiday=%s",
                    market_status,
                    market_cycle_sec,
                    ",".join(enabled_features) if enabled_features else "none",
                    current_market_info["is_warmup"],
                    current_market_info["is_weekend"],
                    current_market_info["is_holiday"],
                )
            except Exception as e:
                log.warning(
                    "market_hours_check_failed err=%s",
                    e.__class__.__name__,
                    exc_info=True,
                )
                current_market_info = None

        # Optional: poll approval marker → promote analyzer plan (no-op if disabled)
        try:
            # Determine approval loop via settings or env fallback
            enable_loop = False
            try:
                enable_loop = getattr(settings, "feature_approval_loop", False)
            except Exception:
                enable_loop = False
            if not enable_loop:
                env_val = (os.getenv("FEATURE_APPROVAL_LOOP", "") or "").strip().lower()
                if env_val in {"1", "true", "yes", "on"}:
                    enable_loop = True
            if enable_loop:
                from .approval import promote_if_approved

                promoted = promote_if_approved()
                if promoted:
                    log.info("approval_promoted %s", str(promoted))
        except Exception:
            pass

        reset_cycle_downgrade()
        if STOP:
            break

        # Run MOA nightly check BEFORE weekend skip logic
        # This allows MOA to run even on weekends when scans are skipped
        try:
            _run_moa_nightly_if_scheduled(log, get_settings())
        except Exception as e:
            log.warning("moa_nightly_check_failed err=%s", str(e))

        # Check for expired MOA reviews and auto-apply after timeout
        try:
            settings = get_settings()
            if getattr(settings, 'moa_review_enabled', False):
                from .keyword_review import expire_old_reviews
                timeout_hours = getattr(settings, 'moa_review_timeout_hours', 48)
                expired_count = expire_old_reviews(timeout_hours=timeout_hours)
                if expired_count > 0:
                    log.info(f"moa_reviews_expired_and_applied count={expired_count}")
        except Exception as e:
            log.warning(f"moa_review_expiry_check_failed err={e}")

        # Skip scanning during no-scan periods (configurable)
        if market_hours_enabled and current_market_info:
            market_status = current_market_info["status"]
            skip_scan = False
            skip_reason = ""

            # Check if we should skip based on status
            if market_status == "closed":
                # Check if weekends should be skipped
                skip_on_weekends = os.getenv("SKIP_SCAN_WEEKENDS", "1") == "1"
                if skip_on_weekends and current_market_info["is_weekend"]:
                    skip_scan = True
                    skip_reason = "weekend"

                # Check if closed hours should be skipped (non-weekend/holiday)
                skip_on_closed = os.getenv("SKIP_SCAN_CLOSED", "0") == "1"
                if skip_on_closed and not current_market_info["is_weekend"] and not current_market_info["is_holiday"]:
                    skip_scan = True
                    skip_reason = "market_closed"

                # Always log holidays
                if current_market_info["is_holiday"]:
                    skip_on_holidays = os.getenv("SKIP_SCAN_HOLIDAYS", "1") == "1"
                    if skip_on_holidays:
                        skip_scan = True
                        skip_reason = "holiday"

            # Skip after-hours if configured
            if market_status == "after_hours":
                skip_after_hours = os.getenv("SKIP_SCAN_AFTER_HOURS", "0") == "1"
                if skip_after_hours:
                    skip_scan = True
                    skip_reason = "after_hours"

            if skip_scan:
                log.info(
                    "scan_skipped reason=%s status=%s next_scan_in=%ds",
                    skip_reason,
                    market_status,
                    int(sleep_interval)
                )
                time.sleep(sleep_interval)
                continue

        t0 = time.time()
        _cycle(log, settings, market_info=current_market_info)
        cycle_time = time.time() - t0
        log.info("CYCLE_DONE took=%.2fs", cycle_time)

        # Update health status after successful cycle
        try:
            update_health_status(
                status="healthy",
                last_cycle_time=datetime.now(timezone.utc),
                total_cycles=TOTAL_STATS.get("items", 0),
                total_alerts=TOTAL_STATS.get("alerts", 0),
            )
        except Exception:
            pass

        # Paper Trading Integration - Update positions at end of cycle
        if trading_engine and getattr(settings, "FEATURE_PAPER_TRADING", False):
            try:
                # Run async position update using run_async (persistent event loop)
                metrics = run_async(trading_engine.update_positions(), timeout=10.0)
                if metrics.get("positions", 0) > 0:
                    log.info(
                        "portfolio_update positions=%d exposure=$%.2f pnl=$%.2f",
                        metrics.get("positions", 0),
                        metrics.get("exposure", 0.0),
                        metrics.get("pnl", 0.0),
                    )
            except Exception as e:
                # Never crash the bot - just log position update errors
                log.error("position_update_error err=%s", str(e), exc_info=True)

        # WAVE ALPHA Agent 1: Check if it's time to send heartbeat with cumulative stats
        try:
            global _heartbeat_acc
            # Get interval from env (default 60 minutes)
            heartbeat_interval = (
                HEARTBEAT_INTERVAL_S // 60 if HEARTBEAT_INTERVAL_S > 0 else 60
            )
            if _heartbeat_acc.should_send_heartbeat(
                interval_minutes=heartbeat_interval
            ):
                # Send heartbeat with cumulative stats instead of just last cycle
                _send_heartbeat(log, settings, reason="interval")
                _heartbeat_acc.reset()
        except Exception as e:
            log.debug("heartbeat_check_failed err=%s", e.__class__.__name__)

        if not do_loop or STOP:
            break
        # sleep between cycles, but wake early if STOP flips
        end = time.time() + sleep_interval
        while time.time() < end:
            if STOP:
                break
            time.sleep(0.2)

    log.info("boot_end")
    # At the end of the run, send a final heartbeat summarising totals.  This
    # "endday" heartbeat includes the same metrics as the interval heartbeat
    # but signals that the loop has finished.  Useful when running once or
    # when shutting down after a scheduled end‑of‑day analyzer run.
    try:
        _send_heartbeat(log, settings, reason="endday")
    except Exception:
        pass

    # Stop SEC monitor gracefully
    try:
        from .sec_monitor import stop_sec_monitor

        stop_sec_monitor()
        log.info("sec_monitor_stopped")
    except Exception:
        pass

    # Paper Trading Integration - Shutdown TradingEngine gracefully
    if trading_engine:
        try:
            log.info("trading_engine_shutdown_started")
            run_async(trading_engine.shutdown(), timeout=10.0)
            log.info("trading_engine_shutdown_complete")

            # Shutdown event loop manager
            EventLoopManager.get_instance().stop(timeout=5.0)
            log.info("event_loop_manager_stopped")
        except Exception as e:
            log.error("trading_engine_shutdown_failed err=%s", str(e), exc_info=True)

    # Generate LLM usage report at end of day
    log.info("=" * 70)
    log.info("LLM USAGE REPORT")
    log.info("=" * 70)
    try:
        monitor = get_monitor()
        summary = monitor.get_daily_stats()
        monitor.print_summary(summary)
    except Exception as e:
        log.warning("llm_usage_report_failed err=%s", str(e))

    return 0


def main(
    *,
    once: bool = False,
    loop: bool = False,
    sleep: float | None = None,
    argv: List[str] | None = None,
) -> int:
    """
    Entry point for the Catalyst Bot runner.

    Supports programmatic invocation via keyword args (``once``, ``loop``, ``sleep``),
    or command-line invocation via ``argv``.  When any of the keyword flags are
    provided, argument parsing is bypassed and values are forwarded to
    ``runner_main``.  This allows tests to call ``main(once=True, loop=False)``.
    """
    if once or loop or sleep is not None:
        return runner_main(once=once, loop=loop, sleep_s=sleep)
    # CLI path
    ap = argparse.ArgumentParser()
    ap.add_argument("--once", action="store_true", help="Run a single cycle and exit")
    ap.add_argument("--loop", action="store_true", help="Run continuously")
    ap.add_argument(
        "--sleep",
        type=float,
        default=None,
        help="Seconds between cycles when looping (default: settings.loop_seconds)",
    )
    args = ap.parse_args(argv)
    return runner_main(once=args.once, loop=args.loop, sleep_s=args.sleep)


if __name__ == "__main__":
    sys.exit(main())
