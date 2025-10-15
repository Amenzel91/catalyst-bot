#!/usr/bin/env python3
"""
Test script for MOA keyword discovery integration.

This script demonstrates how the keyword discovery pipeline works
and shows example output.
"""

import json
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from catalyst_bot.moa_analyzer import (
    run_moa_analysis,
    load_rejected_items,
    load_accepted_items,
    identify_missed_opportunities,
    discover_keywords_from_missed_opportunities,
)


def test_data_loading():
    """Test loading rejected and accepted items."""
    print("=" * 80)
    print("TEST 1: Data Loading")
    print("=" * 80)

    rejected = load_rejected_items(since_days=30)
    accepted = load_accepted_items(since_days=30)

    print(f"\nLoaded {len(rejected)} rejected items from last 30 days")
    print(f"Loaded {len(accepted)} accepted items from last 30 days")

    if rejected:
        sample = rejected[0]
        print(f"\nSample rejected item:")
        print(f"  Ticker: {sample.get('ticker')}")
        print(f"  Title: {sample.get('title', '')[:80]}...")
        print(f"  Timestamp: {sample.get('ts')}")

    if accepted:
        sample = accepted[0]
        print(f"\nSample accepted item:")
        print(f"  Ticker: {sample.get('ticker')}")
        print(f"  Title: {sample.get('title', '')[:80]}...")
        print(f"  Timestamp: {sample.get('ts')}")

    return rejected, accepted


def test_keyword_discovery(rejected_items):
    """Test keyword discovery pipeline."""
    print("\n" + "=" * 80)
    print("TEST 2: Keyword Discovery")
    print("=" * 80)

    # Identify missed opportunities
    print("\nIdentifying missed opportunities...")
    missed_opps = identify_missed_opportunities(rejected_items, threshold_pct=10.0)
    print(f"Found {len(missed_opps)} missed opportunities (rejected items that went up >10%)")

    if not missed_opps:
        print("No missed opportunities found - need historical data with price outcomes")
        return []

    # Show sample missed opportunity
    if missed_opps:
        sample = missed_opps[0]
        print(f"\nSample missed opportunity:")
        print(f"  Ticker: {sample.get('ticker')}")
        print(f"  Title: {sample.get('title', '')[:80]}...")
        price_outcomes = sample.get('price_outcomes', {})
        print(f"  Price outcomes: {price_outcomes}")

    # Discover keywords
    print("\nDiscovering keywords from missed opportunities...")
    discovered = discover_keywords_from_missed_opportunities(
        missed_opps=missed_opps,
        min_occurrences=5,
        min_lift=2.0,
    )

    print(f"Discovered {len(discovered)} new keyword candidates")

    if discovered:
        print("\nTop 10 discovered keywords by lift:")
        print(f"{'Keyword':<30} {'Lift':>6} {'Pos':>4} {'Neg':>4} {'Weight':>6}")
        print("-" * 80)

        # Sort by lift
        sorted_discovered = sorted(discovered, key=lambda x: x['lift'], reverse=True)
        for kw in sorted_discovered[:10]:
            print(f"{kw['keyword']:<30} {kw['lift']:>6.2f} "
                  f"{kw['positive_count']:>4} {kw['negative_count']:>4} "
                  f"{kw['recommended_weight']:>6.2f}")

    return discovered


def test_full_pipeline():
    """Test the complete MOA analysis pipeline."""
    print("\n" + "=" * 80)
    print("TEST 3: Full MOA Analysis Pipeline")
    print("=" * 80)

    print("\nRunning complete MOA analysis...")
    result = run_moa_analysis(since_days=30)

    print(f"\nAnalysis Result:")
    print(f"  Status: {result.get('status')}")
    print(f"  Total rejected: {result.get('total_rejected', 0)}")
    print(f"  Missed opportunities: {result.get('missed_opportunities', 0)}")
    print(f"  Recommendations: {result.get('recommendations_count', 0)}")

    if result.get('status') == 'success':
        # Load recommendations file
        recommendations_path = Path("data/moa/recommendations.json")
        if recommendations_path.exists():
            with open(recommendations_path) as f:
                data = json.load(f)

            print(f"\nRecommendations Summary:")
            print(f"  Discovered keywords: {data.get('discovered_keywords_count', 0)}")
            print(f"  Analysis period: {data.get('analysis_period')}")

            # Categorize recommendations
            recommendations = data.get('recommendations', [])

            by_type = {}
            for rec in recommendations:
                rec_type = rec.get('type', 'unknown')
                if rec_type not in by_type:
                    by_type[rec_type] = []
                by_type[rec_type].append(rec)

            print(f"\n  Recommendations by type:")
            for rec_type, recs in sorted(by_type.items()):
                print(f"    {rec_type}: {len(recs)}")

            # Show sample recommendations
            print(f"\nSample Recommendations:")
            print(f"{'Type':<25} {'Keyword':<25} {'Current':>8} {'Recommended':>11} {'Confidence':>10}")
            print("-" * 80)

            for rec in recommendations[:10]:
                rec_type = rec.get('type', 'unknown')
                keyword = rec.get('keyword', '')[:24]
                current = rec.get('current_weight')
                recommended = rec.get('recommended_weight', 0)
                confidence = rec.get('confidence', 0)

                current_str = f"{current:.2f}" if current is not None else "NEW"

                print(f"{rec_type:<25} {keyword:<25} {current_str:>8} "
                      f"{recommended:>11.2f} {confidence:>10.2f}")

            # Show discovered keywords specifically
            discovered_recs = [r for r in recommendations if 'discovered' in r.get('type', '')]
            if discovered_recs:
                print(f"\nDiscovered Keywords Detail:")
                print(f"{'Keyword':<30} {'Lift':>6} {'Pos':>4} {'Neg':>4} {'Weight':>6}")
                print("-" * 80)

                for rec in discovered_recs[:10]:
                    keyword = rec.get('keyword', '')
                    evidence = rec.get('evidence', {})
                    lift = evidence.get('lift', 0)
                    pos_count = evidence.get('positive_count', 0)
                    neg_count = evidence.get('negative_count', 0)
                    weight = rec.get('recommended_weight', 0)

                    print(f"{keyword:<30} {lift:>6.2f} {pos_count:>4} {neg_count:>4} {weight:>6.2f}")

    return result


def main():
    """Run all tests."""
    print("\n" + "=" * 80)
    print("MOA KEYWORD DISCOVERY INTEGRATION TEST")
    print("=" * 80)

    try:
        # Test 1: Data loading
        rejected, accepted = test_data_loading()

        if not rejected:
            print("\nWARNING: No rejected items found.")
            print("Please ensure data/rejected_items.jsonl has data from the last 30 days.")
            return

        if not accepted:
            print("\nWARNING: No accepted items found.")
            print("Keyword discovery requires data/accepted_items.jsonl for negative examples.")
            print("The system will still work but won't discover new keywords.")

        # Test 2: Keyword discovery
        if rejected:
            discovered = test_keyword_discovery(rejected)

        # Test 3: Full pipeline
        result = test_full_pipeline()

        print("\n" + "=" * 80)
        print("TEST COMPLETE")
        print("=" * 80)

        if result.get('status') == 'success':
            print("\n✓ All tests passed!")
            print(f"\nRecommendations saved to: data/moa/recommendations.json")
            print(f"Analysis state saved to: data/moa/analysis_state.json")
        else:
            print(f"\n✗ Analysis failed: {result.get('message')}")

    except ImportError as e:
        print(f"\n✗ Import error: {e}")
        print("\nMake sure keyword_miner.py exists in src/catalyst_bot/")
    except Exception as e:
        print(f"\n✗ Test failed with error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
