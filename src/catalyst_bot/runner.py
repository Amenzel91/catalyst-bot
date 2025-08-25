from __future__ import annotations

import argparse
import json
import os
import signal
import sys
import time
from datetime import datetime, timezone
from typing import Dict, List, Tuple

from .config import get_settings
from .logging_utils import setup_logging, get_logger
from . import feeds

# yfinance is optional; we guard all uses
try:
    import yfinance as yf  # type: ignore
except Exception:
    yf = None

STOP = False


def _sig_handler(signum, frame):
    """Graceful stop on Ctrl+C / SIGTERM."""
    global STOP
    STOP = True


def price_snapshot(ticker: str) -> float | None:
    """Return a recent price snapshot via yfinance if available; else None."""
    if not ticker or yf is None:
        return None
    try:
        hist = yf.Ticker(ticker).history(period="1d", interval="1m")
        if hist.empty:
            return None
        return float(hist["Close"].iloc[-1])
    except Exception:
        return None


def _fallback_classify(title: str, keyword_categories: Dict[str, List[str]], default_weight: float) -> Dict:
    """
    Dependency-light classifier used by the runner to avoid import mismatch
    with the repo's classify() (which expects a NewsItem dataclass).

    - Treats keyword_categories as dict[str, list[str]] (category -> phrases)
    - Adds default_weight once per category if any phrase matches.
    - Tries VADER sentiment if installed; else 0.0

    Returns: {"sentiment": float, "keywords": List[str], "score": float}
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
    for category, phrases in (keyword_categories or {}).items():
        try:
            if any((p or "").lower() in title_lower for p in phrases):
                tags.append(category)
                score += float(default_weight)
        except Exception:
            # If phrases isn't iterable or contains unexpected types, just skip
            continue

    return {"sentiment": sentiment, "keywords": tags, "score": score}


def _cycle(log) -> Tuple[int, int, int, int]:
    """
    One end-to-end run:
      ingest -> dedupe -> score (fallback) -> price filter -> (optional alerts) -> persist
    Returns tuple: (ingested_count, deduped_count, eligible_count, alerted_count)
    """
    settings = get_settings()
    keyword_categories = settings.keyword_categories
    default_kw_weight = settings.keyword_default_weight

    # Ingest & dedupe
    raw = feeds.fetch_pr_feeds()
    items = feeds.dedupe(raw)

    enriched: List[Dict] = []
    alerted = 0

    for it in items:
        # it fields are produced by feeds.parse_entry()
        title = it.get("title") or ""
        it["cls"] = _fallback_classify(title, keyword_categories, default_kw_weight)

        tick = it.get("ticker")
        px = price_snapshot(tick) if tick else None
        it["price"] = px

        # Price ceiling filter (only if we got a snapshot)
        if px is not None and px > settings.price_ceiling:
            continue

        enriched.append(it)

    # Persist events snapshot (append JSONL)
    try:
        os.makedirs("data", exist_ok=True)
        with open("data/events.jsonl", "a", encoding="utf-8") as f:
            for e in enriched:
                f.write(json.dumps(e) + "\n")
    except Exception as e:
        log.warning(f"persist_events_failed err={e!s}")

    # Alerts: respect record-only and feature flag
    if not settings.feature_record_only and settings.feature_alerts:
        for e in enriched[:20]:  # light cap to reduce spam
            msg = f"[{e.get('ticker') or 'UNK'}] {e.get('title') or ''} • {e.get('source')} • {e.get('ts')}"
            try:
                from .alerts import send_discord  # lazy import to avoid hard dep
                if send_discord(settings.discord_webhook_url, msg):
                    alerted += 1
            except Exception as ex:
                log.warning(f"send_discord_failed err={ex!s}")

    log.info(
        f"CYCLE ts={datetime.now(timezone.utc).isoformat()} "
        f"ingested={len(raw)} deduped={len(items)} eligible={len(enriched)} alerted={alerted}"
    )
    return len(raw), len(items), len(enriched), alerted


def runner_main(once: bool = False, loop: bool = False) -> int:
    """Entry used by tests and CLI wrapper."""
    settings = get_settings()
    setup_logging(settings.log_level)
    log = get_logger("runner")

    signal.signal(signal.SIGINT, _sig_handler)
    signal.signal(signal.SIGTERM, _sig_handler)
    log.info("boot_start")

    do_loop = loop or (not once)  # default matches CLI if neither is set
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
    """
    CLI entrypoint. Also accepts optional keyword args for test harness
    that may call main(once=True, loop=False).
    """
    if once is None and loop is None:
        parser = argparse.ArgumentParser()
        parser.add_argument("--once", action="store_true", help="run a single cycle")
        parser.add_argument("--loop", action="store_true", help="run forever with sleep between cycles")
        args = parser.parse_args()
        return runner_main(once=args.once, loop=args.loop)
    # If kwargs provided, bypass argparse.
    return runner_main(once=bool(once), loop=bool(loop))


if __name__ == "__main__":
    sys.exit(main())
