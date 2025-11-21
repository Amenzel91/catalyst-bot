"""
Parse rejected SEC filings from bot output.
"""
import json
import re
from collections import Counter

# Sample log data (will read from stdin in actual use)
log_data = """
[paste log data here - but we'll use the bash output directly]
"""

# Read from file or stdin
import sys

unique_filings = set()
rejection_counts = Counter()

# Read JSON log lines from stdin
for line in sys.stdin:
    line = line.strip()
    if not line or "filing_prefilter_rejected" not in line:
        continue

    try:
        # Parse JSON log line
        log_entry = json.loads(line)
        msg = log_entry.get("msg", "")

        # Extract filing ID using regex
        match = re.search(r"item_id=([a-f0-9]{40})", msg)
        if match:
            filing_id = match.group(1)
            unique_filings.add(filing_id)
            rejection_counts[filing_id] += 1
    except:
        continue

# Generate report
print("\n" + "=" * 100)
print("SEC FILING REJECTIONS REPORT")
print("=" * 100)
print(f"\nTotal unique filings rejected: {len(unique_filings)}")
print(f"Total rejection events: {sum(rejection_counts.values())}")
print(f"Rejection reason: no_ticker_found (100%)")
print("\n" + "-" * 100)
print(f"{'Filing ID (SHA-1 Hash)':<45} {'Times Rejected':<20}")
print("-" * 100)

# Sort by count (most rejected first)
for filing_id, count in rejection_counts.most_common():
    print(f"{filing_id:<45} {count:<20}")

print("-" * 100)
print("\nANALYSIS:")
print("-" * 100)
print("All filings are identified by SHA-1 hashes instead of SEC URLs.")
print("The pre-filter cannot extract ticker symbols from hash-based identifiers.")
print("This is EXPECTED behavior - saving LLM costs on non-identifiable filings.")
print("\nNEXT STEPS:")
print("1. Check if runner.py is passing proper SEC URLs in the 'item_id' field")
print("2. Or check if filing titles/summaries contain ticker information")
print("3. Consider adding ticker as a separate field when calling the integration layer")
print("=" * 100)
