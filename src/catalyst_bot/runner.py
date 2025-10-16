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
from catalyst_bot.title_ticker import ticker_from_title

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

from . import alerts as _alerts  # used to post log digests as embeds
from .admin_reporter import send_admin_report_if_scheduled  # Nightly admin reports
from .alerts import send_alert_safe
from .analyzer import run_analyzer_once_if_scheduled
from .auto_analyzer import run_scheduled_tasks  # Wave‑4 auto analyzer
from .breakout_feedback import (  # Real-time outcome tracking
    register_alert_for_tracking,
    track_pending_outcomes,
)
from .classify import classify, load_dynamic_keyword_weights
from .config import get_settings
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
from .seen_store import should_filter  # persistent seen store for cross-run dedupe
from .weekly_performance import send_weekly_report_if_scheduled  # Weekly performance

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

# MOA Nightly Scheduler: Track last run date to prevent duplicate runs
_MOA_LAST_RUN_DATE: date | None = None


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
    Example: id=...123456 token=abcdef...
    """
    try:
        parts = url.strip().split("/")
        wid = parts[-2] if len(parts) >= 2 else ""
        tok = parts[-1] if parts else ""
        wid_tail = wid[-6:] if wid else ""
        tok_head = tok[:6] if tok else ""
        return f"id=...{wid_tail} token={tok_head}..."
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
        for field in ("title", "summary"):
            t = ticker_from_title(item.get(field) or "")
            if t:
                item["ticker"] = t
                return


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
    # Ingest + dedupe
    items = feeds.fetch_pr_feeds()
    deduped = feeds.dedupe(items)

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
    skipped_price_gate = 0
    skipped_instr = 0
    skipped_by_source = 0
    skipped_low_score = 0
    skipped_sent_gate = 0
    skipped_cat_gate = 0
    # Track events skipped because they were already seen in a previous cycle.
    skipped_seen = 0
    alerted = 0

    for it in deduped:
        ticker = (it.get("ticker") or "").strip()
        source = it.get("source") or "unknown"

        # Suppress alerts for events we've seen recently (persisted store).  This helps
        # prevent duplicate notifications across cycles.  The persistent seen store
        # uses a TTL defined via SEEN_TTL_DAYS/SEEN_TTL_SECONDS and respects the
        # FEATURE_PERSIST_SEEN flag.  If should_filter() returns True, skip this item.
        try:
            item_id = it.get("id") or ""
            if item_id and should_filter(item_id):
                skipped_seen += 1
                continue
        except Exception:
            # If the seen store fails, fall through and process normally.
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

        # Classify (uses analyzer weights if present); fallback if needed
        try:
            scored = classify(
                item=market.NewsItem.from_feed_dict(it),  # type: ignore[attr-defined]
                keyword_weights=dyn_weights,
            )
        except Exception as err:
            log.warning(
                "classify_error source=%s ticker=%s err=%s item=%s",
                source,
                ticker,
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
            except Exception:
                # If even fallback breaks, skip this one
                continue

        # Optional price gating
        last_px = None
        last_chg = None

        # PERFORMANCE: Use batch-fetched price cache when available
        if ticker in price_cache:
            last_px, last_chg = price_cache[ticker]
        else:
            # Fallback to individual lookup (only if price_ceiling not set or cache failed)
            try:
                last_px, last_chg = market.get_last_price_change(ticker)
            except Exception:
                # If ceiling is set and price lookup failed, skip (can't enforce)
                if price_ceiling is not None:
                    skipped_price_gate += 1
                    continue

        # Enforce price ceiling if active and we have a price
        if price_ceiling is not None and last_px is not None:
            if float(last_px) > float(price_ceiling):
                skipped_price_gate += 1
                # MOA Phase 1: Log rejected item for analysis
                try:
                    log_rejected_item(
                        item=it,
                        rejection_reason="HIGH_PRICE",
                        price=last_px,
                        score=_score_of(scored),
                        sentiment=_sentiment_of(scored),
                        keywords=_keywords_of(scored),
                        scored=scored,
                    )
                except Exception:
                    pass  # Don't crash on logging failures
                continue

        # -------- Classifier gating (score / sentiment / category) ----------
        scr = _score_of(scored)
        if (min_score is not None) and (scr < min_score):
            skipped_low_score += 1
            # MOA Phase 1: Log rejected item for analysis
            try:
                log_rejected_item(
                    item=it,
                    rejection_reason="LOW_SCORE",
                    price=last_px,
                    score=scr,
                    sentiment=_sentiment_of(scored),
                    keywords=_keywords_of(scored),
                    scored=scored,
                )
            except Exception:
                pass  # Don't crash on logging failures
            continue

        snt = _sentiment_of(scored)
        if (min_sent_abs is not None) and (abs(snt) < min_sent_abs):
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

        # Build a payload the new alerts API understands
        alert_payload = {
            "item": it,
            "scored": (
                scored._asdict()
                if hasattr(scored, "_asdict")
                else (scored.dict() if hasattr(scored, "dict") else scored)
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
        except TypeError:
            # Fall back to the legacy keyword-args signature
            ok = send_alert_safe(
                item_dict=it,
                scored=scored,
                last_price=last_px,
                last_change_pct=last_chg,
                record_only=settings.feature_record_only,
                webhook_url=_resolve_main_webhook(settings),
            )
        except Exception as err:
            log.warning(
                "alert_error source=%s ticker=%s err=%s",
                source,
                ticker,
                err.__class__.__name__,
                exc_info=True,
            )
            ok = False

        if ok:
            alerted += 1

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
        "skipped_no_ticker=%s skipped_price_gate=%s skipped_instr=%s skipped_by_source=%s "
        "skipped_low_score=%s skipped_sent_gate=%s skipped_cat_gate=%s alerted=%s",
        len(items),
        len(deduped),
        tickers_present,
        tickers_missing,
        "yes" if dyn_loaded else "no",
        "yes" if dyn_path_exists else "no",
        dyn_path_str,
        price_ceiling,
        skipped_no_ticker,
        skipped_price_gate,
        skipped_instr,
        skipped_by_source,
        skipped_low_score,
        skipped_sent_gate,
        skipped_cat_gate,
        alerted,
    )
    # Patch‑2: update global cycle stats for heartbeat and accumulate totals.
    try:
        global LAST_CYCLE_STATS, TOTAL_STATS
        skipped_total = (
            skipped_no_ticker
            + skipped_price_gate
            + skipped_instr
            + skipped_by_source
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
            "skipped_price_gate": skipped_price_gate,
            "skipped_instr": skipped_instr,
            "skipped_by_source": skipped_by_source,
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

        # Check if it's time to run MOA nightly analysis
        try:
            _run_moa_nightly_if_scheduled(log, get_settings())
        except Exception as e:
            log.warning("moa_nightly_check_failed err=%s", str(e))

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
        return

    # Get configured hour (default 2 AM UTC)
    try:
        moa_hour = int(os.getenv("MOA_NIGHTLY_HOUR", "2").strip() or "2")
    except Exception:
        moa_hour = 2

    now = datetime.now(timezone.utc)
    today = now.date()

    # Check if it's the right hour and we haven't already run today
    if now.hour != moa_hour:
        return

    if _MOA_LAST_RUN_DATE == today:
        return

    # Mark as run for today (do this before starting thread to avoid duplicate triggers)
    _MOA_LAST_RUN_DATE = today

    log.info("moa_nightly_scheduled hour=%d date=%s", moa_hour, today.isoformat())

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

    # Send a simple "I'm alive" message to Discord (even in record-only),
    # controlled by FEATURE_HEARTBEAT
    _send_heartbeat(log, settings, reason="boot")

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
