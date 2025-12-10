#!/usr/bin/env python3
"""
Analyze Dec 9, 2025 LLM/Gemini API patterns.
"""

import json
import re
from collections import defaultdict
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


# Track metrics
hourly_llm_calls = defaultdict(int)
hourly_sec_batches = defaultdict(list)
hourly_llm_failures = defaultdict(int)
hourly_llm_success = defaultdict(int)

llm_json_parse_errors = []
sec_enrichment_rate = []
llm_timeouts = []

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
                hour = ts.hour

                # Track SEC LLM batch processing
                if "sec_llm_batch_complete" in msg:
                    match_total = re.search(r"total=(\d+)", msg)
                    match_enriched = re.search(r"enriched=(\d+)", msg)
                    match_rate = re.search(r"success_rate=([\d.]+)%", msg)

                    if match_total and match_enriched and match_rate:
                        total = int(match_total.group(1))
                        enriched = int(match_enriched.group(1))
                        rate = float(match_rate.group(1))

                        hourly_sec_batches[hour].append(
                            {
                                "time": ts,
                                "total": total,
                                "enriched": enriched,
                                "rate": rate,
                            }
                        )

                        sec_enrichment_rate.append(
                            {
                                "time": ts,
                                "total": total,
                                "enriched": enriched,
                                "rate": rate,
                            }
                        )

                # Track LLM JSON parse failures
                if "llm_json_parse_failed" in msg:
                    hourly_llm_failures[hour] += 1
                    llm_json_parse_errors.append({"time": ts, "msg": msg})

                # Track LLM successes
                if "sec_llm_enrich_success" in msg or "sec_analysis_complete" in msg:
                    hourly_llm_success[hour] += 1
                    hourly_llm_calls[hour] += 1

                # Track LLM timeouts
                if (
                    "timeout" in msg.lower() or "timed out" in msg.lower()
                ) and "llm" in msg.lower():
                    llm_timeouts.append({"time": ts, "msg": msg})

            except Exception:
                continue

print("=" * 80)
print("SEC LLM ENRICHMENT PERFORMANCE BY HOUR")
print("=" * 80)
print(
    f"{'Hour (UTC)':<12} {'Batches':<10} {'Total Docs':<12} {'Enriched':<12} {'Avg Success %':<15}"
)
print("-" * 80)

for hour in range(10, 24):
    if hour in hourly_sec_batches:
        batches = hourly_sec_batches[hour]
        total_docs = sum(b["total"] for b in batches)
        total_enriched = sum(b["enriched"] for b in batches)
        avg_rate = sum(b["rate"] for b in batches) / len(batches) if batches else 0

        cst_hour = hour - 6
        if cst_hour < 0:
            cst_hour += 24

        print(
            f"{hour:02d}:00 ({cst_hour:02d}:00 CST) {len(batches):<10} "
            f"{total_docs:<12} {total_enriched:<12} {avg_rate:<15.1f}"
        )

print("\n" + "=" * 80)
print("LLM CALL SUCCESS VS FAILURE BY HOUR")
print("=" * 80)
print(
    f"{'Hour (UTC)':<12} {'Successes':<12} {'JSON Errors':<12} {'Success Rate %':<15}"
)
print("-" * 80)

for hour in range(10, 24):
    successes = hourly_llm_success.get(hour, 0)
    failures = hourly_llm_failures.get(hour, 0)
    total = successes + failures

    if total > 0:
        success_rate = (successes / total) * 100
    else:
        success_rate = 0

    cst_hour = hour - 6
    if cst_hour < 0:
        cst_hour += 24

    if total > 0:
        print(
            f"{hour:02d}:00 ({cst_hour:02d}:00 CST) {successes:<12} "
            f"{failures:<12} {success_rate:<15.1f}"
        )

print("\n" + "=" * 80)
print("LLM JSON PARSE ERROR SAMPLES")
print("=" * 80)

if llm_json_parse_errors:
    print(f"Total JSON parse errors: {len(llm_json_parse_errors)}")
    print("\nFirst 20 errors:")
    for error in llm_json_parse_errors[:20]:
        time_str = error["time"].strftime("%H:%M:%S")
        msg_preview = error["msg"][:70]
        print(f"  {time_str}: {msg_preview}")
else:
    print("No LLM JSON parse errors detected")

print("\n" + "=" * 80)
print("LLM TIMEOUT EVENTS")
print("=" * 80)

if llm_timeouts:
    print(f"Total LLM timeouts: {len(llm_timeouts)}")
    for timeout in llm_timeouts[:10]:
        time_str = timeout["time"].strftime("%H:%M:%S")
        print(f"  {time_str}: {timeout['msg'][:70]}")
else:
    print("No LLM timeout events detected")

# Performance trends
print("\n" + "=" * 80)
print("SEC ENRICHMENT TREND ANALYSIS")
print("=" * 80)

if sec_enrichment_rate:
    # Split into time periods
    early = [r for r in sec_enrichment_rate if 10 <= r["time"].hour < 13]
    mid = [r for r in sec_enrichment_rate if 13 <= r["time"].hour < 17]
    late = [r for r in sec_enrichment_rate if 17 <= r["time"].hour < 24]

    def calc_avg_rate(records):
        if not records:
            return 0, 0, 0
        total_docs = sum(r["total"] for r in records)
        total_enriched = sum(r["enriched"] for r in records)
        avg_rate = sum(r["rate"] for r in records) / len(records)
        return total_docs, total_enriched, avg_rate

    early_docs, early_enriched, early_rate = calc_avg_rate(early)
    mid_docs, mid_enriched, mid_rate = calc_avg_rate(mid)
    late_docs, late_enriched, late_rate = calc_avg_rate(late)

    print("\nEarly morning (4-7 AM CST):")
    print(
        f"  Batches: {len(early)}, Docs: {early_docs}, "
        f"Enriched: {early_enriched}, Avg Rate: {early_rate:.1f}%"
    )

    print("\nMid-day (7-11 AM CST):")
    print(
        f"  Batches: {len(mid)}, Docs: {mid_docs}, "
        f"Enriched: {mid_enriched}, Avg Rate: {mid_rate:.1f}%"
    )

    print("\nAfternoon (11 AM-5 PM CST):")
    print(
        f"  Batches: {len(late)}, Docs: {late_docs}, "
        f"Enriched: {late_enriched}, Avg Rate: {late_rate:.1f}%"
    )

    # Check for degradation
    if early and late:
        rate_change = late_rate - early_rate
        print(f"\nEnrichment rate change: {rate_change:+.1f} percentage points")

        if abs(rate_change) < 5:
            print("VERDICT: LLM enrichment rate remained STABLE")
        elif rate_change > 5:
            print("VERDICT: LLM enrichment rate IMPROVED")
        else:
            print("VERDICT: LLM enrichment rate DEGRADED")

print("\n" + "=" * 80)
print("SUMMARY: LLM/GEMINI API PERFORMANCE")
print("=" * 80)

total_successes = sum(hourly_llm_success.values())
total_failures = sum(hourly_llm_failures.values())
total_calls = total_successes + total_failures

if total_calls > 0:
    overall_success_rate = (total_successes / total_calls) * 100
else:
    overall_success_rate = 0

print(f"\nTotal LLM calls: {total_calls}")
print(f"Successes: {total_successes}")
print(f"JSON parse failures: {total_failures}")
print(f"Overall success rate: {overall_success_rate:.1f}%")
print(f"Timeout events: {len(llm_timeouts)}")

print("\nKey findings:")
if overall_success_rate > 95:
    print("  • EXCELLENT - LLM API performing very well")
elif overall_success_rate > 85:
    print("  • GOOD - LLM API performing acceptably")
elif overall_success_rate > 70:
    print("  • FAIR - Some LLM issues, but functional")
else:
    print("  • POOR - Significant LLM API problems")

if len(llm_timeouts) > 10:
    print("  • WARNING - Multiple LLM timeout events detected")
elif len(llm_timeouts) > 0:
    print("  • NOTICE - Some LLM timeout events detected")
else:
    print("  • No LLM timeouts detected")

# Calculate if LLM could be a bottleneck
if total_failures > 100:
    print("  • LLM JSON parsing issues are significant")
    print("  • Recommend investigating prompt/response format")
