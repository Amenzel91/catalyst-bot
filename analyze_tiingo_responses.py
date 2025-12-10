#!/usr/bin/env python3
"""
Analyze what Tiingo is actually returning when we get invalid JSON errors.
"""

import json
import re
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(r"C:\Users\menza\OneDrive\Desktop\Catalyst-Bot\catalyst-bot")
LOG_FILES = [
    BASE_DIR / "data" / "logs" / "bot.jsonl",
    BASE_DIR / "data" / "logs" / "bot.jsonl.1",
]

START_TIME = datetime(2025, 12, 9, 10, 0, 0)
END_TIME = datetime(2025, 12, 9, 23, 0, 0)


def parse_timestamp(ts_str):
    """Parse ISO timestamp string to datetime object."""
    try:
        return datetime.fromisoformat(ts_str.replace("Z", "+00:00")).replace(
            tzinfo=None
        )
    except Exception:
        return None


# Track unique ticker patterns
failed_tickers = Counter()
retry_patterns = []
response_time_progression = []

for log_file in LOG_FILES:
    if not log_file.exists():
        continue

    with open(log_file, "r", encoding="utf-8") as f:
        for line in f:
            try:
                entry = json.loads(line.strip())
                ts = parse_timestamp(entry.get("ts", ""))

                if not ts or ts < START_TIME or ts > END_TIME:
                    continue

                msg = entry.get("msg", "")

                # Track failed tickers
                if "tiingo_invalid_json ticker=" in msg:
                    match = re.search(r"ticker=(\S+)", msg)
                    if match:
                        ticker = match.group(1).strip()
                        failed_tickers[ticker] += 1

                # Track fallback retry patterns with timestamps
                if "tiingo_fallback_retry" in msg:
                    match_count = re.search(r"failed_count=(\d+)", msg)
                    match_tickers = re.search(r"tickers=([^\s]+)", msg)
                    retry_patterns.append(
                        {
                            "time": ts,
                            "count": int(match_count.group(1)) if match_count else 0,
                            "tickers": match_tickers.group(1) if match_tickers else "",
                        }
                    )

                # Track response time progression
                if "provider_usage" in msg and "tiingo" in msg:
                    match_time = re.search(r"t_ms=([\d.]+)", msg)
                    match_status = re.search(r"status=(\S+)", msg)
                    if match_time:
                        response_time_progression.append(
                            {
                                "time": ts,
                                "t_ms": float(match_time.group(1)),
                                "status": (
                                    match_status.group(1) if match_status else "unknown"
                                ),
                            }
                        )

            except: Exception:
                continue

print("=" * 80)
print("TOP 30 TICKERS WITH INVALID JSON RESPONSES")
print("=" * 80)
print(f"{'Ticker':<15} {'Failure Count':<15} {'Pattern':<20}")
print("-" * 80)

for ticker, count in failed_tickers.most_common(30):
    # Analyze ticker pattern
    pattern = "normal"
    if "-" in ticker or "." in ticker:
        pattern = "special_chars"
    if ticker.endswith("W"):
        pattern = "warrant"
    if ticker.endswith("U"):
        pattern = "unit"
    if "-P" in ticker:
        pattern = "preferred"

    print(f"{ticker:<15} {count:<15} {pattern:<20}")

print(f"\nTotal unique tickers with failures: {len(failed_tickers)}")
print(f"Total invalid JSON errors: {sum(failed_tickers.values())}")

# Analyze retry patterns
print("\n" + "=" * 80)
print("TIINGO RETRY PATTERN ANALYSIS")
print("=" * 80)

if retry_patterns:
    # Group by hour
    hourly_retries = defaultdict(list)
    for retry in retry_patterns:
        hourly_retries[retry["time"].hour].append(retry)

    print(f"{'Hour (UTC)':<12} {'Retry Events':<15} {'Avg Failed Count':<20}")
    print("-" * 80)

    for hour in sorted(hourly_retries.keys()):
        retries = hourly_retries[hour]
        avg_failed = sum(r["count"] for r in retries) / len(retries)
        cst_hour = hour - 6
        if cst_hour < 0:
            cst_hour += 24
        print(
            f"{hour:02d}:00 ({cst_hour:02d}:00 CST) {len(retries):<15} {avg_failed:<20.1f}"
        )

    print(f"\nTotal retry events: {len(retry_patterns)}")
    print(
        f"Max failed count in single retry: {max(r['count'] for r in retry_patterns)}"
    )

# Analyze response time progression
print("\n" + "=" * 80)
print("TIINGO RESPONSE TIME PROGRESSION (by hour)")
print("=" * 80)

if response_time_progression:
    hourly_times = defaultdict(list)
    for resp in response_time_progression:
        hourly_times[resp["time"].hour].append(resp["t_ms"])

    print(
        f"Retries (4-7 AM):     {early_retries} retries, "
        f"Avg: {avg_early_retry:.0f} failed tickers/retry"
    )
    print("-" * 80)

    for hour in sorted(hourly_times.keys()):
        times = sorted(hourly_times[hour])
        count = len(times)
        avg = sum(times) / count
        min_t = min(times)
        max_t = max(times)
        p95_idx = int(0.95 * count)
        p95 = times[p95_idx] if p95_idx < count else max_t

        cst_hour = hour - 6
        if cst_hour < 0:
            cst_hour += 24

        print(
        f"Retries (4-6 PM):     {late_retries} retries, "
        f"Avg: {avg_late_retry:.0f} failed tickers/retry"
        )

# Check for progressive degradation
print("\n" + "=" * 80)
print("PERFORMANCE DEGRADATION ANALYSIS")
print("=" * 80)

if response_time_progression:
    # Split into early (10-13), mid (13-17), late (17-23)
    early = [r["t_ms"] for r in response_time_progression if 10 <= r["time"].hour < 13]
    mid = [r["t_ms"] for r in response_time_progression if 13 <= r["time"].hour < 17]
    late = [r["t_ms"] for r in response_time_progression if 17 <= r["time"].hour < 24]

    print("Early morning (4-7 AM CST):")
    if early:
        print(f"  Count: {len(early)}, Avg: {sum(early)/len(early):.1f}ms")
    else:
        print("  No data")

    print("\nMid-day (7-11 AM CST):")
    if mid:
        print(f"  Count: {len(mid)}, Avg: {sum(mid)/len(mid):.1f}ms")
    else:
        print("  No data")

    print("\nAfternoon (11 AM-5 PM CST):")
    if late:
        print(f"  Count: {len(late)}, Avg: {sum(late)/len(late):.1f}ms")
    else:
        print("  No data")

    # Statistical significance
    if early and late:
        early_avg = sum(early) / len(early)
        late_avg = sum(late) / len(late)
        pct_change = ((late_avg - early_avg) / early_avg) * 100
        print(f"\nPerformance change: {pct_change:+.1f}%")

        if pct_change < -10:
            print("VERDICT: Performance IMPROVED throughout the day")
        elif pct_change > 10:
            print("VERDICT: Performance DEGRADED throughout the day")
        else:
            print("VERDICT: Performance remained STABLE")

# Analyze status codes
status_distribution = Counter()
for resp in response_time_progression:
    # Find corresponding status from original data
    pass  # Would need more detailed log parsing

print("\n" + "=" * 80)
print("SUMMARY: LIKELY ROOT CAUSES")
print("=" * 80)

# Evidence summary
print("\nEvidence:")
print(f"  1. {len(failed_tickers)} unique tickers experienced invalid JSON responses")
print(f"  2. {sum(failed_tickers.values())} total invalid JSON errors")
print(f"  3. {len(retry_patterns)} retry/fallback events")

# Check for patterns
otc_pattern_count = sum(
    count
    for ticker, count in failed_tickers.items()
    if ticker.endswith("W") or "-" in ticker or ticker.endswith("U")
)
regular_ticker_count = sum(failed_tickers.values()) - otc_pattern_count

print(f"  4. OTC/special tickers: {otc_pattern_count} failures")
print(f"  5. Regular tickers: {regular_ticker_count} failures")

print("\nLikely causes:")
if otc_pattern_count > regular_ticker_count * 0.8:
    print("  • Tiingo returning empty/invalid responses for OTC/warrant/unit tickers")
    print("  • This is EXPECTED behavior - Tiingo doesn't support OTC well")
    print("  • NOT a rate limiting issue")
else:
    print("  • Mix of OTC and regular ticker failures")
    print("  • Could indicate rate limiting OR Tiingo API issues")
    print("  • Further investigation needed")

if len(retry_patterns) > 100:
    print("  • HIGH retry rate suggests persistent API issues")
else:
    print("  • Moderate retry rate - within normal range")
