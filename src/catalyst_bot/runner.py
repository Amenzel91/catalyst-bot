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

from .config import get_settings
from .logging_utils import setup_logging, get_logger
from . import feeds

try:
    import yfinance as yf  # type: ignore
except Exception:
    yf = None

# Silence noisy yfinance logger
logging.getLogger("yfinance").setLevel(logging.CRITICAL)

STOP = False
# simple in-process cache for price snapshots (ticker -> (price, expires_epoch))
_PX_CACHE: Dict[str, Tuple[float, float]] = {}

def _sig_handler(signum, frame):
    global STOP
    STOP = True

def _px_cache_get(ticker: str) -> float | None:
    if not ticker:
        return None
    now = time.time()
    price_expires = _PX_CACHE.get(ticker)
    if price_expires:
        price, expires = price_expires
        if now < expires:
            return price
        else:
            _PX_CACHE.pop(ticker, None)
    return None

def _px_cache_put(ticker: str, price: float, ttl: int = 60) -> None:
    _PX_CACHE[ticker] = (price, time.time() + ttl)

def price_snapshot(ticker: str) -> float | None:
    """Return a recent price snapshot via yfinance; memoized per cycle."""
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

def _fallback_classify(title: str, keyword_categories: Dict[str, List[str]], default_weight: float) -> Dict:
    title_lower = (title or "").lower()
    try:
        from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
        s = SentimentIntensityAnalyzer().polarity_scores(title or "")
        sentiment = float(s.get("compound", 0.0))
    except Exception:
        sentiment = 0.0

    tags: List[str] = []
    score = 0.0
    for category, phrases in (keyword_categories or {}).items():
        try:
            if any((p or "").lower() in title_lower for p in phrases):
                tags.append(category)
                score += float(default_weight)
        except Exception:
            continue
    return {"sentiment": sentiment, "keywords": tags, "score": score}

def _cycle(log) -> Tuple[int, int, int, int]:
    settings = get_settings()
    keyword_categories = settings.keyword_categories
    default_kw_weight = settings.keyword_default_weight

    # reset per-cycle price cache
    _PX_CACHE.clear()

    raw = feeds.fetch_pr_feeds()
    items = feeds.dedupe(raw)

    enriched: List[Dict] = []
    alerted = 0

    for it in items:
        title = it.get("title") or ""
        it["cls"] = _fallback_classify(title, keyword_categories, default_kw_weight)

        tick = it.get("ticker")
        px = price_snapshot(tick) if tick else None
        it["price"] = px

        if px is not None and px > settings.price_ceiling:
            continue
        enriched.append(it)

    # persist
    try:
        os.makedirs("data", exist_ok=True)
        with open("data/events.jsonl", "a", encoding="utf-8") as f:
            for e in enriched:
                f.write(json.dumps(e) + "\n")
    except Exception as e:
        log.warning(f"persist_events_failed err={e!s}")

    # alerts
    if not settings.feature_record_only and settings.feature_alerts:
        webhook = settings.discord_webhook_url
        if not webhook:
            log.info(f"alerts_skipped reason=no_webhook count={len(enriched)}")
        else:
            for e in enriched[:20]:
                msg = f"[{e.get('ticker') or 'UNK'}] {e.get('title') or ''} • {e.get('source')} • {e.get('ts')}"
                try:
                    from .alerts import send_discord
                    if send_discord(webhook, msg):
                        alerted += 1
                except Exception as ex:
                    log.warning(f"send_discord_failed err={ex!s}")

    log.info(
        f"CYCLE ts={datetime.now(timezone.utc).isoformat()} "
        f"ingested={len(raw)} deduped={len(items)} eligible={len(enriched)} alerted={alerted}"
    )
    return len(raw), len(items), len(enriched), alerted

def runner_main(once: bool = False, loop: bool = False) -> int:
    settings = get_settings()
    setup_logging(settings.log_level)
    log = get_logger("runner")
    # boot-time visibility
    log.info(f"boot_start alerts_enabled={settings.feature_alerts} webhook={'set' if settings.discord_webhook_url else 'missing'}")

    signal.signal(signal.SIGINT, _sig_handler)
    signal.signal(signal.SIGTERM, _sig_handler)

    do_loop = loop or (not once)
    while True:
        t0 = time.time()
        _cycle(log)
        took = round(time.time() - t0, 2)
        log.info(f"CYCLE_DONE took={took}s")

        if not do_loop or STOP:
            break
        time.sleep(max(1, settings.loop_seconds))

    log.info("boot_end")
    return 0

def main(once: bool | None = None, loop: bool | None = None) -> int:
    if once is None and loop is None:
        parser = argparse.ArgumentParser()
        parser.add_argument("--once", action="store_true", help="run a single cycle")
        parser.add_argument("--loop", action="store_true", help="run forever with sleep between cycles")
        args = parser.parse_args()
        return runner_main(once=args.once, loop=args.loop)
    return runner_main(once=bool(once), loop=bool(loop))

if __name__ == "__main__":
    sys.exit(main())
