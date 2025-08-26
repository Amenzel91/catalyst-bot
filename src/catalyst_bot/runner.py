from __future__ import annotations

import argparse
import json
import logging
import os
import signal
import sys
import time
from datetime import datetime, timezone
from typing import Dict, List, Tuple

from . import feeds
from .config import get_settings
from .logging_utils import get_logger, setup_logging
from .universe import get_universe_tickers

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
        from .classify import load_dynamic_keyword_weights

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


def _cycle(log) -> Tuple[int, int, int, int]:
    """
    ingest -> dedupe -> (opt classify/price) -> alert (gated) -> persist
    """
    settings = get_settings()
    record_only = settings.feature_record_only
    keyword_categories = settings.keyword_categories
    default_kw_weight = settings.keyword_default_weight

    dynamic_weights, loaded_weights, weights_path, weights_exists = (
        _load_dynamic_weights_with_fallback(log)
    )

    _PX_CACHE.clear()

    # Universe (graceful fallback)
    universe: set[str] = set()
    u_total = 0
    if settings.finviz_auth_token:
        try:
            universe, u_total = get_universe_tickers(
                settings.price_ceiling,
                settings.finviz_auth_token,
            )
            log.info(
                "universe: rows=%s tickers=%s (gating alerts)",
                u_total,
                len(universe),
            )
        except Exception as err:
            log.info(
                "universe_fetch_failed err=%s (alerts not gated)",
                str(err),
            )
    else:
        log.info("universe: finviz_token_missing (alerts not gated)")

    raw = feeds.fetch_pr_feeds()
    items = feeds.dedupe(raw)

    with_ticker = sum(1 for it in items if (it.get("ticker") or "").strip())
    without_ticker = len(items) - with_ticker
    log.info(
        "cycle_metrics items=%s tickers_present=%s tickers_missing=%s "
        "dyn_weights=%s dyn_path_exists=%s dyn_path='%s'",
        len(items),
        with_ticker,
        without_ticker,
        "yes" if loaded_weights else "no",
        weights_exists,
        weights_path,
    )

    enriched: List[Dict] = []
    for it in items:
        title = it.get("title") or ""

        if not record_only:
            it["cls"] = _fallback_classify(
                title,
                keyword_categories,
                default_kw_weight,
                dynamic_weights=dynamic_weights,
            )
            tick = it.get("ticker")
            px = price_snapshot(tick) if tick else None
            it["price"] = px
            if px is not None and px > settings.price_ceiling:
                continue
        else:
            it["cls"] = None
            it["price"] = None

        enriched.append(it)

    # persist
    try:
        os.makedirs("data", exist_ok=True)
        with open("data/events.jsonl", "a", encoding="utf-8") as f:
            for e in enriched:
                f.write(json.dumps(e) + "\n")
    except Exception as err:
        log.warning("persist_events_failed err=%s", str(err))

    # alerts (gated by universe AND requires ticker present)
    alerted = 0
    if not record_only and settings.feature_alerts:
        webhook = settings.discord_webhook_url
        if not webhook:
            log.info(
                "alerts_skipped reason=no_webhook count=%s",
                len(enriched),
            )
        else:

            def has_ticker(e: Dict) -> bool:
                return bool((e.get("ticker") or "").strip())

            def in_universe(e: Dict) -> bool:
                if not universe:
                    return True
                t = (e.get("ticker") or "").upper().strip()
                return bool(t) and t in universe

            eligible = [e for e in enriched if has_ticker(e) and in_universe(e)]

            for e in eligible[:20]:
                tick = e.get("ticker") or "UNK"
                px = e.get("price")
                if isinstance(px, (int, float)):
                    px_str = f"${px:.2f}"
                else:
                    px_str = "n/a"
                msg = (
                    f"[{tick}] {e.get('title') or ''} • {e.get('source')} • "
                    f"{e.get('ts')} • px={px_str}"
                )
                try:
                    from .alerts import send_discord

                    if send_discord(webhook, msg):
                        alerted += 1
                except Exception as err:
                    log.warning("send_discord_failed err=%s", str(err))

            if universe:
                log.info(
                    "alerts_gating universe_tickers=%s " "alerted_from=%s/%s",
                    len(universe),
                    len(eligible),
                    len(enriched),
                )

    log.info(
        "CYCLE ts=%s ingested=%s deduped=%s eligible=%s alerted=%s",
        datetime.now(timezone.utc).isoformat(),
        len(raw),
        len(items),
        len(enriched),
        alerted,
    )
    return len(raw), len(items), len(enriched), alerted


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
        "boot_start alerts_enabled=%s webhook=%s record_only=%s " "finviz_token=%s",
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
        _cycle(log)
        took = round(time.time() - t0, 2)
        log.info("CYCLE_DONE took=%ss", took)

        if not do_loop or STOP:
            break
        time.sleep(max(1, settings.loop_seconds))

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
    sys.exit(main())
