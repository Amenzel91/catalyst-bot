"""
One-Command Fix for Missing Keywords
======================================

Executes the complete fix for missing keywords in LOW_SCORE rejections:
1. Classifies rejected items missing keywords
2. Backfills outcomes with classification
3. Re-runs MOA analysis
4. Shows before/after comparison

Usage:
    python fix_missing_keywords.py
"""

import json
import subprocess
import sys
from pathlib import Path
from datetime import datetime

def print_section(title):
    """Print a section header"""
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}\n")

def check_keyword_coverage():
    """Check current keyword coverage in outcomes.jsonl"""
    outcomes_path = Path("data/moa/outcomes.jsonl")

    if not outcomes_path.exists():
        return 0, 0, 0.0

    total = 0
    with_keywords = 0

    with open(outcomes_path, 'r', encoding='utf-8') as f:
        for line in f:
            if not line.strip():
                continue
            try:
                outcome = json.loads(line)
                total += 1
                keywords = outcome.get('cls', {}).get('keywords', [])
                if keywords:
                    with_keywords += 1
            except:
                continue

    coverage = (with_keywords / total * 100) if total > 0 else 0
    return total, with_keywords, coverage

def get_moa_recommendations():
    """Get current MOA recommendation count"""
    report_path = Path("data/moa/analysis_report.json")

    if not report_path.exists():
        return 0

    try:
        with open(report_path, 'r', encoding='utf-8') as f:
            report = json.load(f)
            return len(report.get('recommendations', []))
    except:
        return 0

def main():
    print_section("MISSING KEYWORDS FIX - Complete Solution")

    print("This script will:")
    print("  1. Check current keyword coverage")
    print("  2. Classify rejected items missing keywords")
    print("  3. Backfill outcomes with classification")
    print("  4. Re-run MOA analysis")
    print("  5. Show improvement metrics")

    input("\nPress Enter to continue (or Ctrl+C to cancel)...")

    # Step 1: Check baseline
    print_section("Step 1: Checking Baseline")

    total_before, with_kw_before, coverage_before = check_keyword_coverage()
    recs_before = get_moa_recommendations()

    print(f"Current Status:")
    print(f"  Total outcomes: {total_before}")
    print(f"  With keywords: {with_kw_before} ({coverage_before:.1f}%)")
    print(f"  MOA recommendations: {recs_before}")

    # Step 2: Classify rejected items
    print_section("Step 2: Classifying Rejected Items")

    print("Running classification script...")
    result = subprocess.run(
        [sys.executable, "-m", "catalyst_bot.scripts.classify_rejected_items"],
        capture_output=False
    )

    if result.returncode != 0:
        print("⚠️  Classification script encountered errors, but continuing...")

    # Step 3: Backfill with classification
    print_section("Step 3: Backfilling Outcomes with Classification")

    print("Running enhanced backfill...")
    result = subprocess.run(
        [sys.executable, "backfill_with_classification.py"],
        capture_output=False
    )

    if result.returncode != 0:
        print("❌ Backfill failed. Aborting.")
        return

    # Step 4: Merge classified keywords
    print_section("Step 4: Merging Classified Keywords")

    classified_path = Path("data/rejected_items_classified.jsonl")
    if classified_path.exists():
        print("Running keyword merger...")
        result = subprocess.run(
            [sys.executable, "merge_classified_keywords.py", "--backup"],
            capture_output=False
        )

        if result.returncode != 0:
            print("⚠️  Keyword merger had issues, but continuing...")
    else:
        print("⚠️  No classified items file found, skipping merge")

    # Step 5: Re-run MOA
    print_section("Step 5: Re-running MOA Analysis")

    print("Analyzing outcomes with new keyword data...")
    result = subprocess.run(
        [sys.executable, "-c",
         "from catalyst_bot.moa_historical_analyzer import run_historical_moa_analysis; "
         "import json; "
         "r = run_historical_moa_analysis(); "
         "print(f'\\nStatus: {r.get(\"status\")}'); "
         "print(f'Recommendations: {len(r.get(\"recommendations\", []))}')"],
        capture_output=False
    )

    # Step 6: Show results
    print_section("Step 6: Results")

    total_after, with_kw_after, coverage_after = check_keyword_coverage()
    recs_after = get_moa_recommendations()

    print(f"📊 Keyword Coverage:")
    print(f"   Before: {with_kw_before}/{total_before} ({coverage_before:.1f}%)")
    print(f"   After:  {with_kw_after}/{total_after} ({coverage_after:.1f}%)")
    print(f"   Improvement: +{coverage_after - coverage_before:.1f}%")

    print(f"\n📈 MOA Recommendations:")
    print(f"   Before: {recs_before} keywords")
    print(f"   After:  {recs_after} keywords")
    print(f"   Improvement: +{recs_after - recs_before} keywords")

    if recs_after > recs_before:
        print(f"\n✨ Success! MOA can now learn from {recs_after - recs_before} more keywords")
        print(f"   Check data/moa/analysis_report.json for details")
    else:
        print(f"\n⚠️  No new recommendations found.")
        print(f"   This could mean:")
        print(f"   - Keywords didn't meet MIN_OCCURRENCES threshold")
        print(f"   - Classification didn't extract useful keywords")
        print(f"   - More data needed for statistical significance")

    print_section("Done!")

    print("Next steps:")
    print("  1. Review new recommendations in data/moa/analysis_report.json")
    print("  2. Check which keywords from LOW_SCORE items are profitable")
    print("  3. Consider adjusting MIN_OCCURRENCES if needed")

if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n❌ Cancelled by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
