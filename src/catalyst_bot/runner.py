# -*- coding: utf-8 -*-
"""Catalyst Bot runner."""

from __future__ import annotations

# stdlib
import argparse
import json
import logging
import os
import signal
import sys
import time
import random
from typing import Dict, List, Tuple, Iterable, Any
import re

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

from . import feeds, market
from .alerts import send_alert_safe
from .analyzer import run_analyzer_once_if_scheduled
from .classify import classify, load_dynamic_keyword_weights
from .config import get_settings
from .logging_utils import get_logger, setup_logging

try:
    import yfinance as yf  # type: ignore
except Exception:
    yf = None

# mute yfinance noise
logging.getLogger("yfinance").setLevel(logging.CRITICAL)

STOP = False
_PX_CACHE: Dict[str, Tuple[float, float]] = {}

def _sig_handler(signum, frame):
    # graceful exit on Ctrl+C / SIGTERM
    global STOP
    STOP = True

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
        or os.getenv("DISCORD_WEBHOOK_URL", "").strip()
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
    if str(os.getenv("FEATURE_HEARTBEAT", "1")).strip().lower() not in {"1", "true", "yes", "on"}:
        return
    # Prefer an explicit admin/dev webhook (env) if provided,
    # else fall back to the normal alerts webhook from settings/env via resolver.
    admin_url = os.getenv("DISCORD_ADMIN_WEBHOOK", "").strip()
    main_url = _resolve_main_webhook(settings)
    target_url = admin_url or main_url
    if not target_url:
        return

    content = (
        f"🤖 Catalyst-Bot heartbeat ({reason}) "
        f"| record_only={settings.feature_record_only} "
        f"| skip_sources={os.getenv('SKIP_SOURCES','')} "
        f"| min_score={os.getenv('MIN_SCORE','')} "
        f"| min_sent_abs={os.getenv('MIN_SENT_ABS','')}"
    )
    payload = {"content": content}

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
                    "User-Agent": "Catalyst-Bot/heartbeat (+https://github.com/Amenzel91/catalyst-bot)"
                },
                method="POST",
            )
            with urlopen(req, timeout=10) as resp:
                code = getattr(resp, "status", getattr(resp, "code", None))
            log.info(
                "heartbeat_sent reason=%s mode=direct_http status=%s target=admin hook=%s",
                reason, code, _mask_webhook(target_url)
            )
            return
        except Exception as e:
            log.warning(
                "heartbeat_error err=%s target=admin hook=%s",
                e.__class__.__name__, _mask_webhook(target_url), exc_info=True
            )
            return

    # 1) Try alerts.post_discord_json if it exists (normal path / main webhook)
    try:
        import catalyst_bot.alerts as _alerts  # type: ignore
        post_fn = getattr(_alerts, "post_discord_json", None)
        if callable(post_fn):
            post_fn(payload)
            log.info(
                "heartbeat_sent reason=%s mode=alerts_fn target=main hook=%s",
                reason, _mask_webhook(main_url)
            )
            return
    except Exception as e:
        # fall back to direct webhook below
        log.debug("heartbeat_alerts_fn_error %s", getattr(e, "__class__", type("E",(object,),{})).__name__)
 

    # 2) Fallback: direct HTTP POST to the webhook (no requests dep required)
    try:
        import json
        from urllib.request import Request, urlopen
        req = Request(
            target_url,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "User-Agent": "Catalyst-Bot/heartbeat (+https://github.com/Amenzel91/catalyst-bot)"
            },
            method="POST",
        )
        with urlopen(req, timeout=10) as resp:
            # Discord returns 204 No Content for success. Any 2xx we consider OK.
            code = getattr(resp, "status", getattr(resp, "code", None))
        log.info(
            "heartbeat_sent reason=%s mode=direct_http status=%s target=main hook=%s",
            reason, code, _mask_webhook(target_url)
        )
    except Exception as e:
        log.warning(
            "heartbeat_error err=%s target=%s hook=%s",
            e.__class__.__name__, "main", _mask_webhook(target_url), exc_info=True
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
        _CIK_MAP = load_cik_to_ticker()  # uses TICKERS_DB_PATH or data/tickers.db


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
    Heuristic to drop warrants/units/series/etc without nuking legit tickers like DNOW.
    Rules:
      - Hyphen '-' or caret '^' -> drop
      - A dot '.' is OK **only** for class shares like BRK.A / BF.B
      - Length >= 5 and endswith one of {'W','WW','WS','WT','U','PU','PD'} -> drop
    """
    if not t:
        return False
    u = t.strip().upper().replace(" ", "")
    # Hard drop on explicit instrument separators
    if "-" in u or "^" in u:
        return True
    # Allow legit class-share pattern (e.g., BRK.A, BF.B). Anything else with '.' is likely an instrument-ish variant.
    if "." in u:
        if re.fullmatch(r"[A-Z]{1,4}\.[A-Z]$", u):
            return False
        return True
    if len(u) >= 5:
        if u.endswith(("WW", "WS", "WT", "PU", "PD", "U")):
            return True
        if u.endswith("W"):
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

    min_score = _fparse("MIN_SCORE")      # e.g. 1.0
    min_sent_abs = _fparse("MIN_SENT_ABS")  # e.g. 0.10
    cats_allow_env = (os.getenv("CATEGORIES_ALLOW") or "").strip()
    cats_allow = {c.strip().lower() for c in cats_allow_env.split(",") if c.strip()}

    ignore_instr = os.getenv("IGNORE_INSTRUMENT_TICKERS", "1") == "1"

    # Flow control: optional hard cap and jitter to smooth bursts
    try:
        max_alerts_per_cycle = int((os.getenv("MAX_ALERTS_PER_CYCLE") or "0").strip() or "0")
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
    alerted = 0

    for it in deduped:
        ticker = (it.get("ticker") or "").strip()
        source = it.get("source") or "unknown"

        # Skip whole sources if configured
        if skip_sources and source in skip_sources:
            skipped_by_source += 1
            continue

        # Do not classify when there's no ticker
        if not ticker:
            skipped_no_ticker += 1
            log.info("item_parse_skip source=%s ticker=%s", source, ticker)
            continue

        # Drop warrants/units/etc (refined)
        if ignore_instr and _is_instrument_like(ticker):
            skipped_instr += 1
            log.info("skip_instrument_like_ticker source=%s ticker=%s", source, ticker)
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
                scored._asdict() if hasattr(scored, "_asdict")
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
                source, ticker, err.__class__.__name__, exc_info=True
            )
            ok = False

        if ok:
            alerted += 1
            # Optional: tiny jitter after success to avoid draining the bucket at once
            if jitter_ms > 0:
                time.sleep(max(0.0, min(jitter_ms, 1000)) / 1000.0 * random.random())

            # Optional: stop early if we hit the cap
            if max_alerts_per_cycle > 0 and alerted >= max_alerts_per_cycle:
                log.info("alert_cap_reached cap=%s", max_alerts_per_cycle)
                break
        else:
            # Downgrade to info to avoid spammy warnings for legitimate skips
            log.info("alert_skip source=%s ticker=%s", source, ticker)

    # Final cycle metrics
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

    # Analyzer: run at the scheduled UTC time (no-op if not time)
    try:
        run_analyzer_once_if_scheduled(get_settings())
    except Exception as err:
        # keep the traceback so we can fix root cause
        log.warning("analyzer_schedule error=%s", err.__class__.__name__, exc_info=True)

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
    admin_env = os.getenv("DISCORD_ADMIN_WEBHOOK", "").strip()
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

    # Send a simple “I’m alive” message to Discord (even in record-only), controlled by FEATURE_HEARTBEAT
    _send_heartbeat(log, settings, reason="boot")

    # signals
    try:
        signal.signal(signal.SIGINT, _sig_handler)
        signal.signal(signal.SIGTERM, _sig_handler)
    except Exception:
        pass  # Windows quirks shouldn't crash startup

    do_loop = loop or (not once)
    sleep_interval = float(sleep_s if sleep_s is not None else settings.loop_seconds)

    heartbeat_interval_min_env = os.getenv("HEARTBEAT_INTERVAL_MIN", "").strip()
    try:
        HEARTBEAT_INTERVAL_S = int(heartbeat_interval_min_env) * 60 if heartbeat_interval_min_env else 0
    except Exception:
        HEARTBEAT_INTERVAL_S = 0
    next_heartbeat_ts = time.time() + HEARTBEAT_INTERVAL_S if HEARTBEAT_INTERVAL_S > 0 else None

    while True:
        if STOP:
            break
        t0 = time.time()
        _cycle(log, settings)
        log.info("CYCLE_DONE took=%.2fs", time.time() - t0)
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
    return 0


def main(argv: List[str] | None = None) -> int:
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
