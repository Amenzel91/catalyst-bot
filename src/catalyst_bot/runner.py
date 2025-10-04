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

from datetime import datetime, timezone

from . import alerts as _alerts  # used to post log digests as embeds
from .alerts import send_alert_safe
from .analyzer import run_analyzer_once_if_scheduled
from .auto_analyzer import run_scheduled_tasks  # Wave‑4 auto analyzer
from .classify import classify, load_dynamic_keyword_weights
from .config import get_settings
from .config_extras import LOG_REPORT_CATEGORIES
from .log_reporter import deliver_report
from .logging_utils import get_logger, setup_logging
from .market import sample_alpaca_stream
from .seen_store import should_filter  # persistent seen store for cross-run dedupe
from .health_endpoint import start_health_server, update_health_status

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


def _sig_handler(signum, frame):
    """Graceful shutdown handler for SIGINT/SIGTERM signals."""
    global STOP
    sig_name = signal.Signals(signum).name if hasattr(signal, 'Signals') else f"signal_{signum}"
    print(f"\n[SHUTDOWN] Received {sig_name}, initiating graceful shutdown...", file=sys.stderr)
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

        payload["embeds"] = [
            {
                "title": f"Catalyst-Bot heartbeat ({reason})",
                "color": 0x5865F2,  # discord blurple-ish
                "timestamp": ts,
                "fields": [
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
                    # Patch‑2: include counts from the most recent cycle and cumulative totals
                    {"name": "Items", "value": items_val, "inline": True},
                    {"name": "Deduped", "value": dedup_val, "inline": True},
                    {"name": "Skipped", "value": skipped_val, "inline": True},
                    {"name": "Alerts", "value": alerts_val, "inline": True},
                ],
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

        # PR: parse ticker from title or summary patterns
        if item.get("source") == "globenewswire_public":
            for field in ("title", "summary"):
                t = ticker_from_title(item.get(field) or "")
                if t:
                    item["ticker"] = t
                    return


# ---------------- Instrument-like detection (refined) ----------------
def _is_instrument_like(t: str) -> bool:
    """
    Heuristic to drop warrants/units/series/OTC tickers without nuking legit tickers like DNOW.

    Rules:
      - Hyphen '-' or caret '^' => drop (synthetic instruments)
      - A dot '.' is OK **only** for class shares like BRK.A / BF.B
        All other dotted symbols are dropped.
      - Length >= 5 and endswith one of {'W', 'WW', 'WS', 'WT', 'U', 'PU', 'PD'}
        => drop (warrants/units)
      - New: 5‑letter symbols ending with 'F' or 'Y' => drop (common OTC/cross‑listed suffixes)

    These heuristics are conservative: they attempt to strip out ticker variants that are
    unlikely to be tradable on major U.S. brokerages (e.g. Webull, Robinhood) while
    preserving legitimate class-share tickers.
    """
    if not t:
        return False
    u = t.strip().upper().replace(" ", "")
    # Hard drop on explicit instrument separators
    if "-" in u or "^" in u:
        return True
    # Allow legit class-share patterns (e.g., BRK.A, BF.B).
    # Other symbols containing '.' are likely instrument-ish variants.
    if "." in u:
        if re.fullmatch(r"[A-Z]{1,4}\.[A-Z]$", u):
            return False
        return True
    # Warrants/units by suffix or U/E etc
    if len(u) >= 5:
        suffixes = ("WW", "WS", "WT", "PU", "PD", "U")
        if u.endswith(suffixes):
            return True
        if u.endswith("W"):
            return True
        # OTC/cross‑listed tickers often end with F or Y (e.g. TDOMF, VODPF).
        # Filter 5‑letter symbols ending with F or Y to avoid thinly‑traded OTC names.
        if len(u) == 5 and u[-1] in {"F", "Y"}:
            return True
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


def _cycle(log, settings) -> None:
    """One ingest→dedupe→enrich→classify→alert pass with clean skip behavior."""
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
    try:
        if getattr(settings, "feature_52w_low_scanner", False):
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
                continue

        # -------- Classifier gating (score / sentiment / category) ----------
        scr = _score_of(scored)
        if (min_score is not None) and (scr < min_score):
            skipped_low_score += 1
            continue

        snt = _sentiment_of(scored)
        if (min_sent_abs is not None) and (abs(snt) < min_sent_abs):
            skipped_sent_gate += 1
            continue

        if cats_allow:
            kwords = {k.lower() for k in _keywords_of(scored)}
            if not (kwords & cats_allow):
                skipped_cat_gate += 1
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
        # Add this cycle’s counts to the cumulative totals
        try:
            TOTAL_STATS["items"] += len(items)
            TOTAL_STATS["deduped"] += len(deduped)
            TOTAL_STATS["skipped"] += skipped_total
            TOTAL_STATS["alerts"] += alerted
        except Exception:
            # ensure totals exist; fallback silently
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
    except Exception:
        # Ignore auto analyzer errors to keep the main loop alive
        pass


def runner_main(
    once: bool = False, loop: bool = False, sleep_s: float | None = None
) -> int:
    settings = get_settings()
    setup_logging(settings.log_level)
    log = get_logger("runner")

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
    if os.getenv("FEATURE_HEALTH_ENDPOINT", "1").strip().lower() in ("1", "true", "yes", "on"):
        try:
            health_port = int(os.getenv("HEALTH_CHECK_PORT", "8080"))
            start_health_server(port=health_port)
            log.info("health_endpoint_enabled port=%d", health_port)
            update_health_status(status="starting")
        except Exception as e:
            log.warning("health_endpoint_failed err=%s", str(e))

    do_loop = loop or (not once)
    sleep_interval = float(sleep_s if sleep_s is not None else settings.loop_seconds)

    heartbeat_interval_min_env = os.getenv("HEARTBEAT_INTERVAL_MIN", "").strip()
    try:
        HEARTBEAT_INTERVAL_S = (
            int(heartbeat_interval_min_env) * 60 if heartbeat_interval_min_env else 0
        )
    except Exception:
        HEARTBEAT_INTERVAL_S = 0
    next_heartbeat_ts = (
        time.time() + HEARTBEAT_INTERVAL_S if HEARTBEAT_INTERVAL_S > 0 else None
    )

    while True:
        # Start of cycle: clear any per-cycle alert downgrade
        from .alerts import reset_cycle_downgrade

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
        _cycle(log, settings)
        cycle_time = time.time() - t0
        log.info("CYCLE_DONE took=%.2fs", cycle_time)

        # Update health status after successful cycle
        try:
            update_health_status(
                status="healthy",
                last_cycle_time=datetime.now(timezone.utc),
                total_cycles=TOTAL_STATS.get("items", 0),
                total_alerts=TOTAL_STATS.get("alerts", 0)
            )
        except Exception:
            pass
        if not do_loop or STOP:
            break
        # sleep between cycles, but wake early if STOP flips
        end = time.time() + sleep_interval
        while time.time() < end:
            if STOP:
                break
            time.sleep(0.2)
            # periodic heartbeat (loop mode only)
            if next_heartbeat_ts and time.time() >= next_heartbeat_ts:
                _send_heartbeat(log, settings, reason="interval")
                next_heartbeat_ts = time.time() + HEARTBEAT_INTERVAL_S

    log.info("boot_end")
    # At the end of the run, send a final heartbeat summarising totals.  This
    # "endday" heartbeat includes the same metrics as the interval heartbeat
    # but signals that the loop has finished.  Useful when running once or
    # when shutting down after a scheduled end‑of‑day analyzer run.
    try:
        _send_heartbeat(log, settings, reason="endday")
    except Exception:
        pass
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
