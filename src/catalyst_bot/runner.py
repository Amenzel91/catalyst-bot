# -*- coding: utf-8 -*-
"""Catalyst Bot runner."""

from __future__ import annotations

# Load .env early so config is available to subsequent imports.
try:
    from dotenv import load_dotenv  # type: ignore
except Exception:  # if python-dotenv isn't installed, just continue
    load_dotenv = None
else:
    load_dotenv()

import argparse
import json
import logging
import os
import signal
import sys
import time
from typing import Dict, List, Tuple

# Make console output immediate and UTF-8 (helps on Windows)
try:
    sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)
    sys.stderr.reconfigure(encoding="utf-8", line_buffering=True)
except Exception:
    pass

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

    ignore_instr = os.getenv("IGNORE_INSTRUMENT_TICKERS", "0") == "1"
    skipped_instr = 0

    # Quick metrics
    tickers_present = sum(1 for it in deduped if (it.get("ticker") or "").strip())
    tickers_missing = len(deduped) - tickers_present

    skipped_no_ticker = 0
    skipped_price_gate = 0
    alerted = 0

    for it in deduped:
        ticker = (it.get("ticker") or "").strip()
        source = it.get("source") or "unknown"

        if ignore_instr and ticker:
            if any(sep in ticker for sep in ("-", ".", "^")) or ticker.endswith(
                ("W", "WS", "WT")
            ):
                skipped_instr += 1
                log.info(
                    "skip_instrument_like_ticker source=%s ticker=%s", source, ticker
                )
                continue

        # Do not classify when there's no ticker
        if not ticker:
            skipped_no_ticker += 1
            log.info("item_parse_skip source=%s ticker=%s", source, ticker)
            continue

        # Classify (uses analyzer weights if present)
        # Classify (uses analyzer weights if present)
        try:
            scored = classify(
                item=market.NewsItem.from_feed_dict(it),  # type: ignore[attr-defined]
                keyword_weights=dyn_weights,
            )
        except Exception as err:
            # Rich debug so we can see *why* it's failing
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
            # Soft fallback so the pipeline keeps flowing
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

    # Final cycle metrics
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
        skipped_instr,
        alerted,
    )

    # Analyzer: run at the scheduled UTC time (no-op if not time)
    try:
        run_analyzer_once_if_scheduled(get_settings())
    except Exception:
        log.warning("analyzer_schedule error=1")


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

    log.info(
        "boot_start alerts_enabled=%s webhook=%s record_only=%s finviz_token=%s",
        settings.feature_alerts,
        "set" if settings.discord_webhook_url else "missing",
        settings.feature_record_only,
        finviz_status,
    )

    # signals
    try:
        signal.signal(signal.SIGINT, _sig_handler)
        signal.signal(signal.SIGTERM, _sig_handler)
    except Exception:
        pass  # Windows quirks shouldn't crash startup

    do_loop = loop or (not once)
    sleep_interval = float(sleep_s if sleep_s is not None else settings.loop_seconds)

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
