#!/usr/bin/env python3
"""
Manual lookup tool for high-scoring N/A items.
Traces items from classification back to their source for investigation.
"""

import json
from datetime import datetime, timezone
from collections import defaultdict

def find_high_score_na_items(log_path="data/logs/bot.jsonl", min_score=0.6):
    """Find high-scoring items with ticker=N/A and trace to source."""

    logs = []
    with open(log_path, "r", encoding="utf-8") as f:
        for line in f:
            try:
                logs.append(json.loads(line))
            except:
                pass

    # Filter to last 3 hours for performance
    start_time = datetime(2025, 12, 11, 12, 0, 0, tzinfo=timezone.utc)
    recent = [log for log in logs if datetime.fromisoformat(log["ts"].replace("Z", "+00:00")) >= start_time]

    print("=" * 80)
    print("HIGH-SCORING ITEMS WITH NO TICKER (ticker=N/A)")
    print("=" * 80)
    print()

    # Find high-scoring N/A items
    high_scores = []
    for log in recent:
        msg = log.get("msg", "")
        if "regime_adjustment_applied" in msg and "ticker=N/A" in msg and "post_score=" in msg:
            try:
                score = float(msg.split("post_score=")[1].split()[0])
                if score >= min_score:
                    ts = log.get("ts", "")
                    high_scores.append((score, ts, log))
            except:
                pass

    print(f"Found {len(high_scores)} items scoring >= {min_score} with ticker=N/A\n")

    # Group by score for cleaner output
    by_score = defaultdict(list)
    for score, ts, log in high_scores:
        by_score[score].append((ts, log))

    # For each unique score, try to find the source item
    for score in sorted(by_score.keys(), reverse=True):
        items = by_score[score]
        print(f"\n{'='*80}")
        print(f"SCORE: {score:.3f} ({len(items)} occurrences)")
        print(f"{'='*80}")

        # Take first occurrence to investigate
        ts, log = items[0]
        print(f"\nTimestamp: {ts}")
        print(f"Full message: {log.get('msg', '')}\n")

        # Try to find related logs near this timestamp
        ts_dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))

        # Look for logs within 5 seconds before this classification
        window_start = ts_dt.timestamp() - 5
        window_end = ts_dt.timestamp()

        related = []
        for rlog in recent:
            rts = rlog.get("ts", "")
            try:
                rts_dt = datetime.fromisoformat(rts.replace("Z", "+00:00"))
                if window_start <= rts_dt.timestamp() <= window_end:
                    related.append(rlog)
            except:
                pass

        print(f"Related logs in 5s window before classification ({len(related)} found):")
        print("-" * 80)

        # Look for feed source, keywords, titles
        for rlog in related[-20:]:  # Last 20 logs before classification
            msg = rlog.get("msg", "")
            name = rlog.get("name", "")

            # Filter for interesting logs
            if any(x in msg for x in ["source=", "keyword", "freshness_filter", "sec_", "feeds_summary"]):
                print(f"[{rlog.get('ts', '')[11:19]}] {name}: {msg[:120]}")

        print()
        print("All occurrences of this score:")
        for occ_ts, _ in items:
            print(f"  - {occ_ts}")
        print()

    print("\n" + "="*80)
    print("INVESTIGATION TIPS")
    print("="*80)
    print("""
1. Check SEC filings by CIK:
   - Extract CIK from item_id or link (format: /edgar/data/0001234567/)
   - Lookup: https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK=XXXXXXXX

2. Check if ticker exists in CIK map:
   - Load: src/catalyst_bot/ticker_map.py load_cik_to_ticker()
   - Check: cik_map.get("0001234567") or cik_map.get("1234567")

3. Check title_ticker.py patterns:
   - src/catalyst_bot/title_ticker.py has extraction patterns
   - Test title against patterns manually

4. Check if item is from non-SEC source:
   - GlobeNewswire, PRNewswire, BusinessWire
   - May need additional pattern support
    """)

if __name__ == "__main__":
    find_high_score_na_items()
