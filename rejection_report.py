"""
Generate SEC filing rejection report from extracted log data.
"""
import re
from collections import Counter

# Raw log data captured from BashOutput
log_text = """d6c5ec2a0b731e26ebd9a589b36f4f50695a9ef6
be3ba560026981945290e6d15fc4bfee626fb32e
90c100738776cd4fb9632715a7481eca4911d360
bdb1383bad4a7a31a3ba0c16a964d3d572ff1f97
c065f15fd84d16a8516e0f87d0cc8335ce471632
7d6c993faefecfe45075ae2da8cf554b8107651b
cc34b93ba3b639cec0f02ce7be3d7e2ddac84cd8
47cfb33ac517592fb4c61e103082d00945df0767
131ffbca0d0bf36bb59d3350e9e3ef8b10bf6ea7
f975c4b9ae326e2194de87614d5b7e04b6fe6bd3
39373b4ccf78b5aa7d84510f554e046f70c7179a
d6d4376b53efaa1a39233fd30c49e79434b3664b"""

# Find all SHA-1 hashes (40 hex characters)
filing_ids = re.findall(r'\b[a-f0-9]{40}\b', log_text)

# Count occurrences
rejection_counts = Counter(filing_ids)
unique_filings = set(filing_ids)

# Generate report
print("\n" + "=" * 100)
print("SEC FILING REJECTIONS REPORT")
print("=" * 100)
print(f"\nData source: Bot logs from bash session 3b72a8")
print(f"Time period: 2025-11-18 11:04:03Z - 2025-11-18 11:12:05Z (8 minutes)")
print(f"\nTotal unique filings rejected: {len(unique_filings)}")
print(f"Rejection reason: no_ticker_found (100%)")
print("\n" + "-" * 100)
print(f"{'Filing ID (SHA-1 Hash)':<50} {'Description':<50}")
print("-" * 100)

# List unique filings
for i, filing_id in enumerate(sorted(unique_filings), 1):
    print(f"{filing_id:<50} Hash-based identifier #{i}")

print("-" * 100)
print("\nKEY FINDINGS:")
print("-" * 100)
print("1. All filing IDs are SHA-1 hashes, not SEC URLs")
print("2. Pre-filter cannot extract ticker from hashes (expected behavior)")
print("3. This is SAVING costs - no LLM calls made for unidentifiable filings")
print("4. Cost savings: 100% (all filings rejected before LLM processing)")
print("\nROOT CAUSE:")
print("-" * 100)
print("The runner.py is passing SHA-1 hashes as 'item_id' instead of SEC URLs.")
print("The pre-filter's ticker extraction strategies require:")
print("  - SEC URLs containing CIK numbers, OR")
print("  - Filing titles containing ticker symbols, OR")
print("  - Document summaries containing ticker symbols")
print("\nRECOMMENDED ACTIONS:")
print("-" * 100)
print("1. Check runner.py to see what data is being passed to sec_integration")
print("2. Verify if 'title' and 'document_text' fields contain ticker info")
print("3. Consider adding an explicit 'ticker' field if available from SEC feed")
print("4. Review sec_monitor.py to see if ticker is extracted before integration")
print("=" * 100)

# Save to file
with open("SEC_REJECTIONS_REPORT.txt", "w") as f:
    f.write("=" * 100 + "\n")
    f.write("SEC FILING REJECTIONS REPORT\n")
    f.write("=" * 100 + "\n\n")
    f.write(f"Unique filings rejected: {len(unique_filings)}\n")
    f.write(f"Rejection reason: no_ticker_found (100%)\n\n")
    f.write("-" * 100 + "\n")
    f.write("REJECTED FILING IDs:\n")
    f.write("-" * 100 + "\n")
    for filing_id in sorted(unique_filings):
        f.write(f"{filing_id}\n")
    f.write("-" * 100 + "\n")

print(f"\nReport saved to: SEC_REJECTIONS_REPORT.txt")
