"""
Merge Classified Keywords into Outcomes
=========================================

Merges keywords from rejected_items_classified.jsonl back into outcomes.jsonl.
This enables MOA to analyze keywords from previously unclassified LOW_SCORE rejections.

Usage:
    python merge_classified_keywords.py [--dry-run] [--backup]

Options:
    --dry-run  Show what would be updated without modifying outcomes.jsonl
    --backup   Create backup of outcomes.jsonl before modifying (recommended)
"""

import json
import shutil
from datetime import datetime
from pathlib import Path
from collections import defaultdict

def merge_classified_keywords(dry_run=False, backup=True):
    """Merge keywords from rejected_items_classified.jsonl into outcomes.jsonl"""

    # Paths
    classified_path = Path("data/rejected_items_classified.jsonl")
    outcomes_path = Path("data/moa/outcomes.jsonl")

    if not classified_path.exists():
        print("❌ Error: data/rejected_items_classified.jsonl not found")
        print("   Run: python -m catalyst_bot.scripts.classify_rejected_items")
        return

    if not outcomes_path.exists():
        print("❌ Error: data/moa/outcomes.jsonl not found")
        return

    # Backup if requested
    if backup and not dry_run:
        backup_path = outcomes_path.parent / f"outcomes_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jsonl"
        shutil.copy2(outcomes_path, backup_path)
        print(f"✅ Backup created: {backup_path}")

    # 1. Load classified keywords keyed by (ticker, rejection_ts)
    print("📖 Loading classified keywords...")
    classified_keywords = {}

    with open(classified_path, 'r', encoding='utf-8') as f:
        for line in f:
            if not line.strip():
                continue
            try:
                item = json.loads(line)
                key = (item.get('ticker'), item.get('ts'))
                keywords = item.get('cls', {}).get('keywords', [])
                if keywords:
                    classified_keywords[key] = keywords
            except:
                continue

    print(f"   Loaded {len(classified_keywords)} items with keywords")

    # 2. Update outcomes
    print("🔄 Processing outcomes...")
    outcomes = []
    updated_count = 0
    no_match_count = 0
    already_has_keywords = 0

    with open(outcomes_path, 'r', encoding='utf-8') as f:
        for line in f:
            if not line.strip():
                continue

            outcome = json.loads(line)
            key = (outcome.get('ticker'), outcome.get('rejection_ts'))

            # Check if outcome already has keywords
            existing_kw = outcome.get('cls', {}).get('keywords', [])

            if existing_kw:
                already_has_keywords += 1
            elif key in classified_keywords:
                # Merge keywords
                if 'cls' not in outcome:
                    outcome['cls'] = {}
                outcome['cls']['keywords'] = classified_keywords[key]
                updated_count += 1
            else:
                no_match_count += 1

            outcomes.append(outcome)

    # 3. Report
    total = len(outcomes)
    print(f"\n📊 Results:")
    print(f"   Total outcomes: {total}")
    print(f"   ✅ Already had keywords: {already_has_keywords} ({already_has_keywords/total*100:.1f}%)")
    print(f"   ✨ Updated with keywords: {updated_count} ({updated_count/total*100:.1f}%)")
    print(f"   ⚠️  No match in classified: {no_match_count} ({no_match_count/total*100:.1f}%)")

    coverage_before = already_has_keywords / total * 100
    coverage_after = (already_has_keywords + updated_count) / total * 100
    improvement = coverage_after - coverage_before

    print(f"\n📈 Coverage:")
    print(f"   Before: {coverage_before:.1f}%")
    print(f"   After:  {coverage_after:.1f}%")
    print(f"   Improvement: +{improvement:.1f}%")

    # 4. Write back (unless dry-run)
    if dry_run:
        print(f"\n🔍 DRY RUN - No changes made")
        print(f"   Run without --dry-run to apply changes")
    else:
        print(f"\n💾 Writing updated outcomes...")
        with open(outcomes_path, 'w', encoding='utf-8') as f:
            for outcome in outcomes:
                f.write(json.dumps(outcome) + '\n')
        print(f"   ✅ Done!")

        # Show next steps
        print(f"\n🎯 Next Steps:")
        print(f"   1. Re-run MOA analysis:")
        print(f"      python -c \"from catalyst_bot.moa_historical_analyzer import run_historical_moa_analysis; run_historical_moa_analysis()\"")
        print(f"   2. Check new keyword recommendations in data/moa/analysis_report.json")

if __name__ == '__main__':
    import sys

    dry_run = '--dry-run' in sys.argv
    backup = '--backup' in sys.argv or '--no-backup' not in sys.argv  # Default True

    merge_classified_keywords(dry_run=dry_run, backup=backup)
