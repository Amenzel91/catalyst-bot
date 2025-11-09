#!/usr/bin/env python3
"""Analyze bot latency from logs"""
import json
from datetime import datetime
from collections import defaultdict

def analyze_logs():
    log_file = "data/logs/bot.jsonl"

    # Read last 1000 lines
    with open(log_file, 'r', encoding='utf-8') as f:
        lines = f.readlines()[-1000:]

    # Parse JSON
    events = []
    for line in lines:
        try:
            event = json.loads(line.strip())
            if event.get('ts'):
                events.append(event)
        except:
            continue

    print(f"=== LATENCY ANALYSIS ===\n")
    print(f"Events analyzed: {len(events)}")

    if not events:
        print("No events found in logs")
        return

    # Calculate time between events (proxy for cycle time)
    cycle_times = []
    prev_ts = None

    for event in events:
        ts_str = event.get('ts')
        if not ts_str:
            continue

        try:
            ts = datetime.fromisoformat(ts_str.replace('Z', '+00:00'))
            if prev_ts:
                diff = (ts - prev_ts).total_seconds()
                if 0 < diff < 120:  # Filter outliers
                    cycle_times.append(diff)
            prev_ts = ts
        except:
            continue

    if cycle_times:
        avg = sum(cycle_times) / len(cycle_times)
        print(f"\n=== CYCLE TIMING ===")
        print(f"Average time between events: {avg:.2f}s")
        print(f"Min: {min(cycle_times):.2f}s")
        print(f"Max: {max(cycle_times):.2f}s")
        print(f"Samples: {len(cycle_times)}")

    # Look for specific event types
    event_types = defaultdict(int)
    for event in events:
        msg = event.get('msg', '')
        if msg:
            # Extract event type from message
            event_type = msg.split()[0] if msg else 'unknown'
            event_types[event_type] += 1

    print(f"\n=== TOP EVENT TYPES ===")
    for event_type, count in sorted(event_types.items(), key=lambda x: x[1], reverse=True)[:10]:
        print(f"{event_type}: {count}")

    # Look for errors or warnings
    warnings = [e for e in events if e.get('level') == 'WARNING']
    errors = [e for e in events if e.get('level') == 'ERROR']

    print(f"\n=== ISSUES ===")
    print(f"Warnings: {len(warnings)}")
    print(f"Errors: {len(errors)}")

    if warnings:
        print("\nRecent warnings:")
        for w in warnings[-5:]:
            print(f"  {w.get('ts')}: {w.get('msg', '')[:80]}")

    if errors:
        print("\nRecent errors:")
        for e in errors[-5:]:
            print(f"  {e.get('ts')}: {e.get('msg', '')[:80]}")

if __name__ == "__main__":
    analyze_logs()
