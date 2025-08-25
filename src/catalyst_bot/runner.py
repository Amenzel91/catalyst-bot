from __future__ import annotations
import argparse, json, os, signal, sys, time
from typing import List, Dict
from datetime import datetime, timezone

from .config import get_settings
from .logging_utils import setup_logging, get_logger
from . import feeds, classifier

try:
    import yfinance as yf  # optional
except Exception:
    yf = None

STOP = False

def _sig_handler(signum, frame):
    global STOP
    STOP = True

def price_snapshot(ticker: str) -> float | None:
    if not ticker or yf is None:
        return None
    try:
        px = yf.Ticker(ticker).history(period="1d", interval="1m").tail(1)["Close"].iloc[0]
        return float(px)
    except Exception:
        return None

def _cycle(log, settings) -> tuple[int, int, int, int]:
    weights = settings.keyword_categories  # simple mapping expected by tests
    raw = feeds.fetch_pr_feeds()
    items = feeds.dedupe(raw)

    enriched: List[Dict] = []
    alerted = 0

    for it in items:
        tick = it.get("ticker")
        # use legacy classify signature if present; else fallback
        try:
            from .classify import classify as legacy_classify  # repo's original
            cls = legacy_classify(it)  # expects dict-like item with 'title'
        except Exception:
            # fallback to our lightweight classifier if needed
            from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
            s = SentimentIntensityAnalyzer().polarity_scores(it["title"])["compound"]
            wscore = 0.0
            tags = []
            lt = it["title"].lower()
            for k, w in weights.items():
                if k in lt:
                    wscore += w
                    tags.append(k)
            cls = {"sentiment": s, "keywords": tags, "score": wscore}
        it["cls"] = cls

        px = price_snapshot(tick) if tick else None
        it["price"] = px
        if px is not None and px > settings.price_ceiling:
            continue
        enriched.append(it)

    # persist
    os.makedirs("data", exist_ok=True)
    with open("data/events.jsonl", "a", encoding="utf-8") as f:
        for e in enriched:
            f.write(json.dumps(e) + "\n")

    # alerts (respect record-only)
    if not settings.feature_record_only and settings.feature_alerts:
        for e in enriched[:20]:
            msg = f"[{e.get('ticker') or 'UNK'}] {e['title']} • {e['source']} • {e['ts']}"
            try:
                from .alerts import send_discord
                ok = send_discord(settings.discord_webhook_url, msg)
            except Exception:
                ok = False
            if ok:
                alerted += 1

    log.info(
        f"CYCLE ts={datetime.now(timezone.utc).isoformat()} "
        f"ingested={len(raw)} deduped={len(items)} eligible={len(enriched)} "
        f"alerted={alerted}"
    )
    return len(raw), len(items), len(enriched), alerted

def runner_main(once: bool = False, loop: bool = False) -> int:
    """Entry used by tests: run once or loop based on arguments."""
    settings = get_settings()
    setup_logging(settings.log_level)
    log = get_logger("runner")

    signal.signal(signal.SIGINT, _sig_handler)
    signal.signal(signal.SIGTERM, _sig_handler)
    log.info("boot_start")

    do_loop = loop or (not once)  # default behavior matches CLI if neither is specified
    while True:
        t0 = time.time()
        _cycle(log, settings)
        took = round(time.time() - t0, 2)
        log.info(f"CYCLE_DONE took={took}s")

        if not do_loop or STOP:
            break
        time.sleep(max(1, settings.loop_seconds))

    log.info("boot_end")
    return 0

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true", help="run a single cycle")
    parser.add_argument("--loop", action="store_true", help="run forever with sleep between cycles")
    args = parser.parse_args()
    return runner_main(once=args.once, loop=args.loop)

if __name__ == "__main__":
    sys.exit(main())
