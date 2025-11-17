"""
Quick Keyword Merge - Direct from Rejected Items to Outcomes
=============================================================

Directly copies keywords from rejected_items.jsonl to outcomes.jsonl
by matching (ticker, rejection_ts) pairs. Much faster than full classification.

Usage:
    python quick_merge_keywords.py
"""

import json
import shutil
from pathlib import Path
from datetime import datetime

def quick_merge():
    """Directly merge keywords from rejected_items into outcomes"""

    rejected_path = Path("data/rejected_items.jsonl")
    outcomes_path = Path("data/moa/outcomes.jsonl")

    print("Loading rejected items with keywords...")

    # Build lookup: (ticker, ts) -> keywords
    keyword_lookup = {}

    with open(rejected_path, 'r', encoding='utf-8') as f:
        for line in f:
            if not line.strip():
                continue
            try:
                item = json.loads(line)
                ticker = item.get('ticker')
                ts = item.get('ts')
                keywords = item.get('cls', {}).get('keywords', [])

                if ticker and ts:
                    keyword_lookup[(ticker, ts)] = keywords

            except:
                continue

    total_rejected = len(keyword_lookup)
    with_keywords = sum(1 for kw in keyword_lookup.values() if kw)

    print(f"   Total rejected items: {total_rejected}")
    print(f"   With keywords: {with_keywords} ({with_keywords/total_rejected*100:.1f}%)")

    # Backup outcomes
    backup_path = outcomes_path.parent / f"outcomes_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jsonl"
    shutil.copy2(outcomes_path, backup_path)
    print(f"\nBackup created: {backup_path}")

    # Update outcomes
    print(f"\nMerging keywords into outcomes...")

    outcomes = []
    matched = 0
    updated = 0
    no_match = 0

    with open(outcomes_path, 'r', encoding='utf-8') as f:
        for line in f:
            if not line.strip():
                continue

            outcome = json.loads(line)
            ticker = outcome.get('ticker')
            ts = outcome.get('rejection_ts')

            if (ticker, ts) in keyword_lookup:
                matched += 1
                keywords = keyword_lookup[(ticker, ts)]

                if keywords:  # Only update if keywords exist
                    if 'cls' not in outcome:
                        outcome['cls'] = {}
                    outcome['cls']['keywords'] = keywords
                    updated += 1

            else:
                no_match += 1

            outcomes.append(outcome)

    total_outcomes = len(outcomes)

    print(f"\nResults:")
    print(f"   Total outcomes: {total_outcomes}")
    print(f"   Matched with rejected items: {matched} ({matched/total_outcomes*100:.1f}%)")
    print(f"   Updated with keywords: {updated} ({updated/total_outcomes*100:.1f}%)")
    print(f"   No match found: {no_match} ({no_match/total_outcomes*100:.1f}%)")

    # Write back
    print(f"\nWriting updated outcomes...")
    with open(outcomes_path, 'w', encoding='utf-8') as f:
        for outcome in outcomes:
            f.write(json.dumps(outcome) + '\n')

    print(f"   Done!")

    # Show coverage improvement
    coverage = (updated / total_outcomes * 100) if total_outcomes > 0 else 0

    print(f"\nCoverage:")
    print(f"   Before: 0.0%")
    print(f"   After:  {coverage:.1f}%")
    print(f"   Improvement: +{coverage:.1f}%")

    if coverage < 50:
        print(f"\n[!] Coverage still low. This is because:")
        print(f"   - Only {with_keywords/total_rejected*100:.1f}% of rejected items had keywords")
        print(f"   - Need to run classification to extract keywords from the rest")
        print(f"\n   Next step: Run classification script for better results")

    return coverage

if __name__ == '__main__':
    coverage = quick_merge()

    if coverage > 5:  # If we got some keywords
        print(f"\nNext Step: Re-run MOA to see new keyword recommendations")
        print(f"   python -c \"from catalyst_bot.moa_historical_analyzer import run_historical_moa_analysis; run_historical_moa_analysis()\"")
