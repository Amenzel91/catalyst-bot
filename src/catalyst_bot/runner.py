from __future__ import annotations

import argparse
import json
import logging
import os
import signal
import subprocess
import sys
import time
from datetime import datetime, timezone
from typing import Dict, List, Tuple

from . import feeds, market
from .alerts import send_alert_safe
from .analyzer import run_analyzer_once_if_scheduled
from .classify import classify, load_dynamic_keyword_weights
from .config import get_settings
from .logging_utils import get_logger, setup_logging
from catalyst_bot.ticker_map import load_cik_to_ticker, cik_from_text
from catalyst_bot.title_ticker import ticker_from_title

try:
    import yfinance as yf  # type: ignore
except Exception:
    yf = None

# mute yfinance noise
logging.getLogger("yfinance").setLevel(logging.CRITICAL)

STOP = False
_PX_CACHE: Dict[str, Tuple[float, float]] = {}


def _sig_handler(signum, frame):
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
        _CIK_MAP = load_cik_to_ticker()   # uses TICKERS_DB_PATH or data/tickers.db

def enrich_ticker(entry: dict, item: dict):
    """Try to populate item['ticker'] from SEC link/id/summary or PR title."""
    ensure_cik_map()

    # 1) SEC feeds → prefer CIK → ticker
    if item.get("source", "").startswith("sec_"):
        for field in ("link", "id", "summary"):
            cik = cik_from_text(entry.get(field))
            if cik:
                t = _CIK_MAP.get(cik) or _CIK_MAP.get(str(cik).zfill(10))
                if t:
                    item["ticker"] = t
                    return

    # 2) Press releases → parse from title patterns
    if item.get("source") == "globenewswire_public":
        t = ticker_from_title(item.get("title") or "")
        if t:
            item["ticker"] = t

def _cycle(log, settings) -> None:
    """One ingest→dedupe→classify→alert pass with clean skip behavior."""
    # Ingest + dedupe
    items = feeds.fetch_pr_feeds()
    deduped = feeds.dedupe(items)

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

    # Quick metrics
    tickers_present = sum(1 for it in deduped if (it.get("ticker") or "").strip())
    tickers_missing = len(deduped) - tickers_present

    skipped_no_ticker = 0
    skipped_price_gate = 0
    alerted = 0

    for it in deduped:
        ticker = (it.get("ticker") or "").strip()
        source = it.get("source") or "unknown"

        # Do not classify when there's no ticker
        if not ticker:
            skipped_no_ticker += 1
            log.info("item_parse_skip source=%s ticker=%s", source, ticker)
            continue

        # Classify (uses analyzer weights if present)
        try:
            scored = classify(
                item=market.NewsItem.from_feed_dict(it),  # type: ignore[attr-defined]
                keyword_weights=dyn_weights,
            )
        except Exception:
            # Keep running even if classification hiccups
            log.warning("classify_error source=%s ticker=%s", source, ticker)
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

        # Send (or record-only) alert
        ok = send_alert_safe(
            item_dict=it,
            scored=scored,
            last_price=last_px,
            last_change_pct=last_chg,
            record_only=settings.feature_record_only,
            webhook_url=settings.discord_webhook_url,
        )
        if ok:
            alerted += 1
        else:
            # Downgrade to info to avoid spammy warnings for legitimate skips
            log.info("alert_skip source=%s ticker=%s", source, ticker)

    # Final cycle metrics (now with deduped + alerted + correct dyn flags)
    log.info(
        "cycle_metrics items=%s deduped=%s tickers_present=%s tickers_missing=%s "
        "dyn_weights=%s dyn_path_exists=%s dyn_path='%s' skipped_no_ticker=%s "
        "skipped_price_gate=%s alerted=%s",
        len(items),
        len(deduped),
        tickers_present,
        tickers_missing,
        "yes" if dyn_loaded else "no",
        "yes" if dyn_path_exists else "no",
        dyn_path_str,
        skipped_no_ticker,
        skipped_price_gate,
        alerted,
    )

    # Analyzer: run at the scheduled UTC time (no-op if not time)
    try:
        run_analyzer_once_if_scheduled(get_settings())
    except Exception:
        log.warning("analyzer_schedule error=1")


def _maybe_run_analyzer(log, settings) -> None:
    """Run analyzer once per UTC day after (hour, minute)."""
    try:
        now = datetime.now(timezone.utc)
        target_h = int(os.getenv("ANALYZER_UTC_HOUR", settings.analyzer_utc_hour))
        target_m = int(os.getenv("ANALYZER_UTC_MINUTE", settings.analyzer_utc_minute))

        # Only run once per day; store stamp in data/analyzer/last_run.json
        stamp_dir = settings.data_dir / "analyzer"
        stamp_dir.mkdir(parents=True, exist_ok=True)
        stamp_path = stamp_dir / "last_run.json"

        last_day = None
        if stamp_path.exists():
            try:
                last = json.loads(stamp_path.read_text())
                last_day = last.get("utc_date")
            except Exception:
                last_day = None

        today = now.strftime("%Y-%m-%d")
        after_time = (now.hour, now.minute) >= (target_h, target_m)

        if (last_day != today) and after_time:
            log.info(
                "analyzer_schedule trigger date=%s time=%02d:%02dZ",
                today,
                target_h,
                target_m,
            )
            # Run analyzer (prior trading day default; analyzer handles empty)
            try:
                subprocess.run(
                    [sys.executable, "-m", "catalyst_bot.analyzer"],
                    check=False,
                    capture_output=True,
                    text=True,
                )
            finally:
                # Write stamp regardless to avoid tight retry loops
                stamp_path.write_text(json.dumps({"utc_date": today}))
    except Exception:
        # Never crash the runner for scheduler issues
        log.warning("analyzer_schedule_error")


def runner_main(once: bool = False, loop: bool = False) -> int:
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

    log.info(
        "boot_start alerts_enabled=%s webhook=%s record_only=%s finviz_token=%s",
        settings.feature_alerts,
        "set" if settings.discord_webhook_url else "missing",
        settings.feature_record_only,
        finviz_status,
    )

    signal.signal(signal.SIGINT, _sig_handler)
    signal.signal(signal.SIGTERM, _sig_handler)

    do_loop = loop or (not once)
    while True:
        t0 = time.time()
        _cycle(log, settings)  # pass settings
        _maybe_run_analyzer(log, settings)
        log.info("CYCLE_DONE took=%.2fs", time.time() - t0)
        if not do_loop:
            break
        time.sleep(settings.loop_seconds)

    log.info("boot_end")
    return 0


def main(once: bool | None = None, loop: bool | None = None) -> int:
    if once is None and loop is None:
        parser = argparse.ArgumentParser()
        parser.add_argument("--once", action="store_true", help="run a single cycle")
        parser.add_argument(
            "--loop", action="store_true", help="run forever with sleep between cycles"
        )
        args = parser.parse_args()
        return runner_main(once=args.once, loop=args.loop)
    return runner_main(once=bool(once), loop=bool(loop))

if __name__ == "__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--loop", action="store_true")
    p.add_argument("--once", action="store_true")
    args=p.parse_args()
    from catalyst_bot.runner_impl import run_once  # or your cycle func
    if args.once:
        run_once(); sys.exit(0)
    while args.loop:
        run_once(); time.sleep(int(os.getenv("LOOP_SECONDS","60")))

if __name__ == "__main__":
    sys.exit(main())
