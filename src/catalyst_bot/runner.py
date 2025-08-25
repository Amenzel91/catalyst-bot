from __future__ import annotations
import argparse, json, os, signal, sys, time
from typing import List, Dict
from .config import SETTINGS
from .logging_utils import setup_logging, get_logger
from . import feeds, classifier
from datetime import datetime, timezone
import pandas as pd

try:
    import yfinance as yf  # optional
except Exception:
    yf = None

STOP = False
def _sig_handler(signum, frame):
    global STOP
    STOP = True

def price_snapshot(ticker: str) -> float | None:
    if not ticker:
        return None
    if yf is None:
        return None
    try:
        px = yf.Ticker(ticker).history(period="1d", interval="1m").tail(1)["Close"].iloc[0]
        return float(px)
    except Exception:
        return None

def cycle(log):
    weights = classifier.load_keyword_weights()
    raw = feeds.fetch_pr_feeds()
    items = feeds.dedupe(raw)
    enriched: List[Dict] = []
    alerted = 0

    for it in items:
        tick = it.get("ticker")
        it["cls"] = classifier.classify(it["title"], weights)
        # price filter (≤ ceiling) – only if we have a ticker + yfinance
        px = price_snapshot(tick) if tick else None
        it["price"] = px
        if px is not None and px > SETTINGS.price_ceiling:
            continue
        enriched.append(it)

    enriched.sort(key=classifier.sort_key)
    # persist raw data
    os.makedirs("data", exist_ok=True)
    with open("data/events.jsonl", "a", encoding="utf-8") as f:
        for e in enriched:
            f.write(json.dumps(e) + "\n")

    # alerts (respect record-only)
    if not SETTINGS.feature_record_only and SETTINGS.feature_alerts:
        for e in enriched[:20]:  # send only first N to avoid spam
            msg = f"[{e.get('ticker') or 'UNK'}] {e['title']} • {e['source']} • {e['ts']}"
            if SETTINGS.discord_webhook:
                ok = False
                try:
                    from .alerts import send_discord
                    ok = send_discord(SETTINGS.discord_webhook, msg)
                except Exception as ex:
                    log.warning(f"send_discord_failed err={ex!s}")
                if ok:
                    alerted += 1

    # cycle summary
    log.info(json.dumps({
        "CYCLE": True,
        "ingested": len(raw),
        "deduped": len(items),
        "eligible": len(enriched),
        "alerted": alerted,
        "took_s": 0,  # filled by caller
    }))
    return len(raw), len(items), len(enriched), alerted

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true", help="run a single cycle")
    parser.add_argument("--loop", action="store_true", help="run forever with sleep between cycles")
    args = parser.parse_args()

    setup_logging(SETTINGS.log_level)
    log = get_logger("runner")
    signal.signal(signal.SIGINT, _sig_handler)
    signal.signal(signal.SIGTERM, _sig_handler)
    log.info("boot_start")

    do_loop = args.loop or not args.once
    while True:
        t0 = time.time()
        raw, ded, elig, alerted = cycle(log)
        took = round(time.time() - t0, 2)
        log.info(f"CYCLE ts={datetime.now(timezone.utc).isoformat()} ingested={raw} deduped={ded} eligible={elig} alerted={alerted} took={took}s")
        if not do_loop:
            break
        if STOP:
            log.info("graceful_stop")
            break
        time.sleep(max(1, SETTINGS.loop_seconds))
    log.info("boot_end")
    return 0

if __name__ == "__main__":
    sys.exit(main())
