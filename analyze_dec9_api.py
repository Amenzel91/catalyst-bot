#!/usr/bin/env python3
"""
Analyze Dec 9, 2025 API call patterns and performance.
Focus on rate limiting, retries, and performance degradation.
"""

import json
import re
from collections import defaultdict
from datetime import datetime
from pathlib import Path

# File paths
BASE_DIR = Path(r"C:\Users\menza\OneDrive\Desktop\Catalyst-Bot\catalyst-bot")
LOG_FILES = [
    BASE_DIR / "data" / "logs" / "bot.jsonl",
    BASE_DIR / "data" / "logs" / "bot.jsonl.1",
]

# Dec 9, 2025 time range (CST = UTC-6)
# 4 AM CST = 10:00 UTC
# 5 PM CST = 23:00 UTC
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


def analyze_logs():
    """Analyze all log entries for Dec 9, 2025."""

    # Metrics tracking
    hourly_api_calls = defaultdict(lambda: defaultdict(int))
    hourly_errors = defaultdict(lambda: defaultdict(int))
    hourly_retries = defaultdict(lambda: defaultdict(int))
    hourly_response_times = defaultdict(list)

    tiingo_failures = []
    yfinance_fallbacks = []
    rate_limit_events = []
    gemini_events = []
    timeout_events = []

    api_patterns = {
        "tiingo": defaultdict(int),
        "yfinance": defaultdict(int),
        "gemini": defaultdict(int),
        "finnhub": defaultdict(int),
        "alpha_vantage": defaultdict(int),
        "google_trends": defaultdict(int),
    }

    total_lines = 0
    parsed_lines = 0

    print("Analyzing log files...")
    for log_file in LOG_FILES:
        if not log_file.exists():
            print(f"  Skipping {log_file} (not found)")
            continue

        print(f"  Processing {log_file.name}...")
        with open(log_file, "r", encoding="utf-8") as f:
            for line in f:
                total_lines += 1
                try:
                    entry = json.loads(line.strip())
                    ts = parse_timestamp(entry.get("ts", ""))

                    if not ts or ts < START_TIME or ts > END_TIME:
                        continue

                    parsed_lines += 1
                    hour = ts.hour
                    msg = entry.get("msg", "")
                    level = entry.get("level", "")

                    # Tiingo API tracking
                    if "tiingo" in msg.lower():
                        hourly_api_calls[hour]["tiingo"] += 1

                        if "tiingo_invalid_json" in msg:
                            hourly_errors[hour]["tiingo_invalid_json"] += 1
                            api_patterns["tiingo"]["invalid_json"] += 1
                            tiingo_failures.append(
                                {"time": ts, "msg": msg, "type": "invalid_json"}
                            )

                        if "tiingo_fallback_retry" in msg:
                            hourly_retries[hour]["tiingo"] += 1
                            api_patterns["tiingo"]["retry"] += 1
                            # Extract failed count
                            match = re.search(r"failed_count=(\d+)", msg)
                            if match:
                                count = int(match.group(1))
                                tiingo_failures.append(
                                    {
                                        "time": ts,
                                        "msg": msg,
                                        "type": "fallback_retry",
                                        "count": count,
                                    }
                                )

                        if "provider_usage" in msg and "tiingo" in msg:
                            # Extract response time
                            match = re.search(r"t_ms=([\d.]+)", msg)
                            if match:
                                t_ms = float(match.group(1))
                                hourly_response_times[hour].append(("tiingo", t_ms))

                            # Track status
                            if "status=no_data" in msg:
                                api_patterns["tiingo"]["no_data"] += 1
                            elif "status=ok" in msg or "status=success" in msg:
                                api_patterns["tiingo"]["success"] += 1

                    # yfinance fallback tracking
                    if "yfinance" in msg.lower():
                        hourly_api_calls[hour]["yfinance"] += 1

                        if "role=BACKUP" in msg or "fallback" in msg.lower():
                            yfinance_fallbacks.append({"time": ts, "msg": msg})
                            api_patterns["yfinance"]["fallback"] += 1
                        else:
                            api_patterns["yfinance"]["direct"] += 1

                    # Gemini/LLM tracking
                    if "gemini" in msg.lower() or "llm" in msg.lower():
                        hourly_api_calls[hour]["gemini"] += 1
                        gemini_events.append({"time": ts, "msg": msg, "level": level})

                        if "timeout" in msg.lower():
                            timeout_events.append(
                                {"time": ts, "msg": msg, "api": "gemini"}
                            )

                        # Extract response time if available
                        match = re.search(r"t_ms=([\d.]+)", msg)
                        if match:
                            t_ms = float(match.group(1))
                            hourly_response_times[hour].append(("gemini", t_ms))

                    # Finnhub tracking
                    if "finnhub" in msg.lower():
                        hourly_api_calls[hour]["finnhub"] += 1
                        api_patterns["finnhub"]["calls"] += 1

                    # Alpha Vantage tracking
                    if "alpha" in msg.lower() or "alphavantage" in msg.lower():
                        hourly_api_calls[hour]["alpha_vantage"] += 1
                        api_patterns["alpha_vantage"]["calls"] += 1

                    # Google Trends tracking
                    if "google_trends" in msg.lower() or "trends" in msg.lower():
                        hourly_api_calls[hour]["google_trends"] += 1
                        api_patterns["google_trends"]["calls"] += 1

                    # Rate limiting detection
                    if (
                        "429" in msg
                        or "rate limit" in msg.lower()
                        or "too many requests" in msg.lower()
                    ):
                        rate_limit_events.append({"time": ts, "msg": msg})

                    # Timeout detection
                    if "timeout" in msg.lower() and "gemini" not in msg.lower():
                        timeout_events.append({"time": ts, "msg": msg})

                except json.JSONDecodeError:
                    continue
                except Exception:
                    continue

    print(
        f"\nProcessed {total_lines} total lines, {parsed_lines} within Dec 9 time range\n"
    )

    # Generate report
    print("=" * 80)
    print("API CALL VOLUME BY HOUR (Dec 9, 2025 - 4 AM to 5 PM CST)")
    print("=" * 80)
    print(
        f"{'Hour (UTC)':<12} {'Tiingo':<10} {'yfinance':<10} "
        f"{'Gemini':<10} {'Finnhub':<10} {'Other':<10}"
    )
    print("-" * 80)

    for hour in range(10, 24):  # 10:00 UTC to 23:00 UTC (4 AM - 5 PM CST)
        tiingo = hourly_api_calls[hour]["tiingo"]
        yfinance = hourly_api_calls[hour]["yfinance"]
        gemini = hourly_api_calls[hour]["gemini"]
        finnhub = hourly_api_calls[hour]["finnhub"]
        other = (
            hourly_api_calls[hour]["alpha_vantage"]
            + hourly_api_calls[hour]["google_trends"]
        )

        # Convert UTC to CST for display
        cst_hour = hour - 6
        if cst_hour < 0:
            cst_hour += 24

        print(
            f"{hour:02d}:00 ({cst_hour:02d}:00 CST) {tiingo:<10} "
            f"{yfinance:<10} {gemini:<10} {finnhub:<10} {other:<10}"
        )

    print("\n" + "=" * 80)
    print("TIINGO API PATTERN SUMMARY")
    print("=" * 80)
    for pattern, count in sorted(
        api_patterns["tiingo"].items(), key=lambda x: x[1], reverse=True
    ):
        print(f"  {pattern:<20}: {count:>6}")

    print("\n" + "=" * 80)
    print("YFINANCE FALLBACK PATTERN")
    print("=" * 80)
    for pattern, count in sorted(
        api_patterns["yfinance"].items(), key=lambda x: x[1], reverse=True
    ):
        print(f"  {pattern:<20}: {count:>6}")

    print("\n" + "=" * 80)
    print("ERROR & RETRY RATES BY HOUR")
    print("=" * 80)
    print(f"{'Hour (UTC)':<12} {'Tiingo Errors':<15} {'Tiingo Retries':<15}")
    print("-" * 80)

    for hour in range(10, 24):
        errors = hourly_errors[hour]["tiingo_invalid_json"]
        retries = hourly_retries[hour]["tiingo"]

        cst_hour = hour - 6
        if cst_hour < 0:
            cst_hour += 24

        if errors > 0 or retries > 0:
            print(f"{hour:02d}:00 ({cst_hour:02d}:00 CST) {errors:<15} {retries:<15}")

    print("\n" + "=" * 80)
    print("AVERAGE RESPONSE TIMES BY HOUR (milliseconds)")
    print("=" * 80)
    print(f"{'Hour (UTC)':<12} {'Tiingo Avg':<15} {'Gemini Avg':<15}")
    print("-" * 80)

    for hour in range(10, 24):
        if hour in hourly_response_times:
            tiingo_times = [
                t for api, t in hourly_response_times[hour] if api == "tiingo"
            ]
            gemini_times = [
                t for api, t in hourly_response_times[hour] if api == "gemini"
            ]

            tiingo_avg = sum(tiingo_times) / len(tiingo_times) if tiingo_times else 0
            gemini_avg = sum(gemini_times) / len(gemini_times) if gemini_times else 0

            cst_hour = hour - 6
            if cst_hour < 0:
                cst_hour += 24

            if tiingo_avg > 0 or gemini_avg > 0:
                print(
                    f"{hour:02d}:00 ({cst_hour:02d}:00 CST) {tiingo_avg:<15.1f} {gemini_avg:<15.1f}"
                )

    # Rate limiting evidence
    print("\n" + "=" * 80)
    print("RATE LIMITING EVENTS")
    print("=" * 80)
    if rate_limit_events:
        for event in rate_limit_events[:10]:
            print(f"  {event['time'].strftime('%H:%M:%S')}: {event['msg']}")
        if len(rate_limit_events) > 10:
            print(f"  ... and {len(rate_limit_events) - 10} more")
    else:
        print("  No explicit rate limit (429) errors detected")

    # Timeout events
    print("\n" + "=" * 80)
    print("TIMEOUT EVENTS")
    print("=" * 80)
    if timeout_events:
        for event in timeout_events[:20]:
            api = event.get("api", "unknown")
            print(
                f"  {event['time'].strftime('%H:%M:%S')} [{api}]: {event['msg'][:80]}"
            )
        if len(timeout_events) > 20:
            print(f"  ... and {len(timeout_events) - 20} more")
    else:
        print("  No timeout events detected")

    # Top Tiingo failures
    print("\n" + "=" * 80)
    print("TOP 20 TIINGO FAILURE PATTERNS")
    print("=" * 80)
    if tiingo_failures:
        # Show time distribution
        for failure in tiingo_failures[:20]:
            time_str = failure["time"].strftime("%H:%M:%S")
            ftype = failure.get("type", "unknown")
            msg_preview = failure["msg"][:70]
            print(f"  {time_str} [{ftype}]: {msg_preview}")

        if len(tiingo_failures) > 20:
            print(f"  ... and {len(tiingo_failures) - 20} more failures")

        print(f"\nTotal Tiingo failures: {len(tiingo_failures)}")
    else:
        print("  No Tiingo failures detected")

    # Gemini events summary
    print("\n" + "=" * 80)
    print("GEMINI/LLM EVENTS SUMMARY")
    print("=" * 80)
    print(f"Total Gemini events: {len(gemini_events)}")

    gemini_errors = [e for e in gemini_events if e["level"] in ["ERROR", "WARNING"]]
    if gemini_errors:
        print(f"Gemini errors/warnings: {len(gemini_errors)}")
        for event in gemini_errors[:10]:
            time_str = event["time"].strftime("%H:%M:%S")
            print(f"  {time_str} [{event['level']}]: {event['msg'][:70]}")
    else:
        print("No Gemini errors/warnings detected")


if __name__ == "__main__":
    analyze_logs()
