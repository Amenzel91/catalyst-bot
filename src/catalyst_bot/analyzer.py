from __future__ import annotations
import argparse, csv, json, os
from datetime import date, datetime, timedelta, timezone
from collections import defaultdict
from .logging_utils import setup_logging, get_logger
from .classifier import load_keyword_weights, save_keyword_weights

def prior_trading_day_utc() -> date:
    d = datetime.now(timezone.utc).date() - timedelta(days=1)
    # crude weekend adjust
    if d.weekday() == 6:  # Sunday
        d -= timedelta(days=2)
    elif d.weekday() == 5:  # Saturday
        d -= timedelta(days=1)
    return d

def run_for(day: date):
    os.makedirs("out/analyzer", exist_ok=True)
    weights = load_keyword_weights()
    by_ticker = defaultdict(list)

    # read events
    if not os.path.exists("data/events.jsonl"):
        return {"count": 0, "updated": False}
    with open("data/events.jsonl", "r", encoding="utf-8") as f:
        for line in f:
            e = json.loads(line)
            ts = e.get("ts") or ""
            if not ts.startswith(str(day)):
                continue
            tick = e.get("ticker") or "UNK"
            by_ticker[tick].append(e)

    # naive scoring: positive sentiment+relevance => +1 weight for seen tags; negative => -1
    tag_delta = defaultdict(int)
    total = 0
    for tick, events in by_ticker.items():
        for e in events:
            total += 1
            cls = e.get("cls") or {}
            sent = float(cls.get("sentiment_score") or 0.0)
            rel = float(cls.get("relevance_score") or 0.0)
            for tag in cls.get("tags") or []:
                if sent + rel > 0.5:
                    tag_delta[tag] += 1
                elif sent + rel < -0.5:
                    tag_delta[tag] -= 1

    # apply deterministic weight updates (bounded, sorted by key for stable output)
    changed = False
    for tag in sorted(tag_delta.keys()):
        delta = tag_delta[tag]
        if delta == 0:
            continue
        w = weights.get(tag, 0.0)
        nw = max(min(w + 0.1 * delta, 5.0), -5.0)
        if nw != w:
            weights[tag] = round(nw, 3)
            changed = True

    # persist artifacts
    with open(f"out/analyzer/summary_{day}.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["tag", "delta"])
        for k in sorted(tag_delta.keys()):
            w.writerow([k, tag_delta[k]])
    if changed:
        save_keyword_weights(weights)
    return {"count": total, "updated": changed}

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", help="YYYY-MM-DD; default = prior trading day")
    args = parser.parse_args()
    setup_logging()
    log = get_logger("analyzer")
    d = prior_trading_day_utc() if not args.date else datetime.strptime(args.date, "%Y-%m-%d").date()
    res = run_for(d)
    log.info(f"analyzer_done date={d} events={res['count']} weights_updated={res['updated']}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
