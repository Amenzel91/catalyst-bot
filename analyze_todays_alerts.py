"""Analyze today's alerts from log files to identify patterns in bad alerts."""

import json
from datetime import datetime
from collections import defaultdict, Counter
from typing import List, Dict

# Read the log file
alerts_sent = []
rejected_items = defaultdict(list)
cycle_stats = []

with open("data/logs/bot.jsonl", "r", encoding="utf-8") as f:
    for line in f:
        try:
            entry = json.loads(line.strip())
            msg = entry.get("msg", "")

            # Look for alerts sent
            if "alert_sent" in msg or "discord_post" in msg:
                alerts_sent.append(entry)

            # Look for cycle completion stats
            if "cycle_complete" in msg:
                cycle_stats.append(entry)

            # Look for rejections
            if "rejected" in msg or "skipped" in msg or "filtered" in msg:
                reason = "unknown"
                if "otc" in msg.lower():
                    reason = "otc"
                elif "unit_warrant" in msg.lower():
                    reason = "unit_warrant"
                elif "multi_ticker" in msg.lower():
                    reason = "multi_ticker"
                elif "stale" in msg.lower():
                    reason = "stale"
                elif "low_score" in msg.lower():
                    reason = "low_score"
                elif "sentiment" in msg.lower():
                    reason = "sentiment"

                rejected_items[reason].append(entry)

        except json.JSONDecodeError:
            continue

print("=" * 80)
print("TODAY'S ALERTS ANALYSIS")
print("=" * 80)
print()

# Find alerts from Oct 28
today_alerts = []
for alert in alerts_sent:
    ts_str = alert.get("ts", "")
    if "2025-10-28" in ts_str:
        today_alerts.append(alert)

print(f"Total alerts found from Oct 28: {len(today_alerts)}")
print()

# Print some sample alerts to understand the structure
if today_alerts:
    print("Sample alert log entries (first 5):")
    for i, alert in enumerate(today_alerts[:5]):
        print(f"\n{i+1}. {alert.get('ts', 'N/A')}")
        print(f"   Msg: {alert.get('msg', '')[:200]}")

# Look for today's cycle stats
print("\n" + "=" * 80)
print("CYCLE STATISTICS FROM OCT 28")
print("=" * 80)

today_cycles = []
for cycle in cycle_stats:
    ts_str = cycle.get("ts", "")
    if "2025-10-28" in ts_str:
        today_cycles.append(cycle)

if today_cycles:
    # Print latest few cycle stats
    print(f"\nFound {len(today_cycles)} cycles from Oct 28")
    print("\nLast 3 cycle statistics:")
    for i, cycle in enumerate(today_cycles[-3:]):
        print(f"\n{i+1}. Cycle at {cycle.get('ts', 'N/A')}")
        msg = cycle.get('msg', '')
        print(f"   {msg[:500]}")

# Rejection analysis
print("\n" + "=" * 80)
print("REJECTION REASONS")
print("=" * 80)
print()

for reason, items in rejected_items.items():
    print(f"{reason}: {len(items)} items")

print("\nDone! Check the output above for patterns.")
print("\nNext steps:")
print("1. Look at the actual Discord channel to identify which alerts were bad")
print("2. Map those bad alerts to log entries")
print("3. Identify common patterns (price, volume, keywords, sources, etc.)")
