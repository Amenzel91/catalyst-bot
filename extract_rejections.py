"""
Extract rejected SEC filings from bot logs.
"""
import re
from collections import defaultdict

# Read the latest bot log
with open("logs/catalyst_bot.log", "r", encoding="utf-8", errors="ignore") as f:
    log_content = f.read()

# Find all filing_prefilter_rejected entries
pattern = r"filing_prefilter_rejected item_id=([^\s]+) reason=([^\s]+) ticker=([^\s]+)"
matches = re.findall(pattern, log_content)

# Deduplicate and organize
rejections = defaultdict(lambda: {"count": 0, "reason": None, "ticker": None})

for item_id, reason, ticker in matches:
    # Truncate long item_ids for readability
    short_id = item_id[:50] if len(item_id) > 50 else item_id
    rejections[short_id]["count"] += 1
    rejections[short_id]["reason"] = reason
    rejections[short_id]["ticker"] = ticker

# Generate report
print("\n" + "=" * 80)
print("SEC FILING REJECTIONS REPORT")
print("=" * 80)
print(f"\nTotal unique filings rejected: {len(rejections)}")
print(f"Total rejection events: {sum(r['count'] for r in rejections.values())}")
print("\n" + "-" * 80)
print(f"{'Filing ID (truncated)':<52} {'Reason':<25} {'Ticker':<10} {'Count'}")
print("-" * 80)

# Sort by count (most rejected first)
sorted_rejections = sorted(rejections.items(), key=lambda x: x[1]["count"], reverse=True)

for item_id, data in sorted_rejections:
    print(f"{item_id:<52} {data['reason']:<25} {data['ticker']:<10} {data['count']}")

print("-" * 80)

# Summary by rejection reason
print("\nREJECTION REASONS SUMMARY:")
print("-" * 40)
reason_counts = defaultdict(int)
for data in rejections.values():
    reason_counts[data["reason"]] += data["count"]

for reason, count in sorted(reason_counts.items(), key=lambda x: x[1], reverse=True):
    print(f"  {reason:<30} {count:>5} filings")

print("\n" + "=" * 80)
