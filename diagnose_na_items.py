#!/usr/bin/env python3
"""
Real-time diagnostic tool to catch high-scoring N/A items.
This patches the classification system to log full details of ticker=N/A items.
"""

import json
import sys
from datetime import datetime

# Patch strategy: Monitor bot.jsonl for new high-score N/A items
# Then immediately look for what was processed in that cycle

def tail_follow(filename):
    """Generator that yields new lines from a file as they're written."""
    import time
    with open(filename, 'r', encoding='utf-8') as f:
        # Go to end of file
        f.seek(0, 2)

        while True:
            line = f.readline()
            if line:
                yield line
            else:
                time.sleep(0.1)

def extract_score_from_msg(msg):
    """Extract post_score from regime_adjustment_applied message."""
    if "post_score=" not in msg:
        return None
    try:
        return float(msg.split("post_score=")[1].split()[0])
    except:
        return None

def main():
    print("=" * 80)
    print("REAL-TIME DIAGNOSTIC: Monitoring for high-scoring ticker=N/A items")
    print("=" * 80)
    print()
    print("Watching: data/logs/bot.jsonl")
    print("Threshold: score >= 0.6 with ticker=N/A")
    print()
    print("Press Ctrl+C to stop")
    print()
    print("-" * 80)

    cycle_items = []  # Accumulate items in current cycle
    last_cycle_time = None

    try:
        for line in tail_follow("data/logs/bot.jsonl"):
            try:
                log = json.loads(line)
            except:
                continue

            ts = log.get("ts", "")
            msg = log.get("msg", "")
            name = log.get("name", "")

            # Detect new cycle
            if "cycle_metrics" in msg:
                last_cycle_time = ts
                cycle_items = []  # Reset
                continue

            # Collect items entering this cycle
            if msg.startswith("skipped_") or msg.startswith("accepted_"):
                cycle_items.append(log)

            # Detect high-scoring N/A classification
            if "regime_adjustment_applied" in msg and "ticker=N/A" in msg:
                score = extract_score_from_msg(msg)
                if score and score >= 0.6:
                    print(f"\n{'='*80}")
                    print(f"HIGH SCORE N/A DETECTED!")
                    print(f"{'='*80}")
                    print(f"Time: {ts}")
                    print(f"Score: {score:.3f}")
                    print(f"Full msg: {msg}")
                    print()

                    # Show items from this cycle
                    print("Items in this cycle:")
                    items_without_ticker = [
                        item for item in cycle_items
                        if "ticker= " in item.get("msg", "") or "ticker=N/A" in item.get("msg", "")
                    ]

                    if items_without_ticker:
                        print(f"  Found {len(items_without_ticker)} items without tickers:")
                        for item in items_without_ticker[:10]:
                            print(f"    {item.get('msg', '')[:150]}")
                    else:
                        print("  (No items without tickers in skipped/accepted logs)")
                        print("  This suggests item is from a different source or processing path")

                    print()
                    print("ANALYSIS:")
                    print("  - If no items shown above: Item is likely Finviz/GlobeNewswire")
                    print("  - If SEC items shown: CIK extraction failed for these")
                    print()
                    print("-" * 80)

            # Show feed summaries for context
            if "feeds_summary" in msg:
                print(f"\n[{ts[11:19]}] Feed summary: {msg[:120]}")

            if "ticker_extraction_summary" in msg:
                print(f"[{ts[11:19]}] Ticker extraction: {msg}")

    except KeyboardInterrupt:
        print("\n\nStopped by user")
        sys.exit(0)

if __name__ == "__main__":
    main()
