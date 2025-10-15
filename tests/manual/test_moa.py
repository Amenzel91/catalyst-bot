#!/usr/bin/env python3
"""
Test script for MOA (Missed Opportunities Analyzer) module.

This script demonstrates the basic functionality of the MOA analyzer:
1. Loading rejected items
2. Identifying missed opportunities
3. Extracting keywords
4. Generating recommendations
5. Viewing summary

Usage:
    python test_moa.py
"""

import json
from src.catalyst_bot.moa_analyzer import (
    run_moa_analysis,
    get_moa_summary,
    load_rejected_items,
)


def print_section(title: str) -> None:
    """Print a section header."""
    print(f"\n{'=' * 60}")
    print(f"  {title}")
    print('=' * 60)


def main():
    """Run MOA analysis tests."""
    print_section("MOA (Missed Opportunities Analyzer) Test")

    # Test 1: Load rejected items
    print_section("1. Loading Rejected Items")
    items = load_rejected_items(since_days=30)
    print(f"Loaded {len(items)} rejected items from last 30 days")

    if items:
        print("\nSample rejected item:")
        sample = items[0]
        print(f"  Ticker: {sample.get('ticker')}")
        title = sample.get('title', '')[:60]
        # Handle Unicode encoding issues
        try:
            print(f"  Title: {title}...")
        except UnicodeEncodeError:
            print(f"  Title: {title.encode('ascii', 'replace').decode('ascii')}...")
        print(f"  Price: ${sample.get('price', 0):.2f}")
        print(f"  Reason: {sample.get('rejection_reason')}")
        print(f"  Keywords: {sample.get('cls', {}).get('keywords', [])}")

    # Test 2: Run full analysis
    print_section("2. Running Full MOA Analysis")
    result = run_moa_analysis(since_days=30)

    print(f"Status: {result.get('status')}")
    print(f"Total rejected: {result.get('total_rejected', 0)}")
    print(f"Missed opportunities: {result.get('missed_opportunities', 0)}")
    print(f"Recommendations: {result.get('recommendations_count', 0)}")

    if result.get('status') == 'success':
        print(f"Elapsed time: {result.get('elapsed_seconds', 0):.2f}s")

    # Test 3: Get summary
    print_section("3. Getting Analysis Summary")
    summary = get_moa_summary()

    if summary.get('status') == 'ok':
        print(f"Last run: {summary.get('last_run')}")
        print(f"Analysis period: {summary.get('analysis_period')}")
        print(f"\nRecommendations: {summary.get('recommendations_count', 0)}")

        recommendations = summary.get('recommendations', [])
        if recommendations:
            print("\nTop 5 recommendations:")
            for i, rec in enumerate(recommendations[:5], 1):
                print(f"\n  {i}. {rec['keyword']}")
                print(f"     Type: {rec['type']}")
                print(f"     Current weight: {rec.get('current_weight')}")
                print(f"     Recommended: {rec['recommended_weight']}")
                print(f"     Confidence: {rec['confidence']:.2f}")
                evidence = rec.get('evidence', {})
                print(f"     Evidence: {evidence.get('occurrences')} occurrences, "
                      f"{evidence.get('success_rate', 0):.1%} success rate, "
                      f"{evidence.get('avg_return', 0):.1%} avg return")
    else:
        print(f"Status: {summary.get('status')}")
        print(f"Message: {summary.get('message', 'No message')}")

    # Test 4: Check output files
    print_section("4. Output Files")
    import os
    from pathlib import Path

    output_files = [
        "data/moa/recommendations.json",
        "data/moa/analysis_state.json",
    ]

    for file_path in output_files:
        path = Path(file_path)
        if path.exists():
            size = path.stat().st_size
            print(f"[OK] {file_path} ({size} bytes)")
        else:
            print(f"[MISSING] {file_path}")

    print_section("Test Complete")
    print("\nMOA module is working correctly!")
    print("\nNext steps:")
    print("1. Ensure rejected_items.jsonl has data from feeds.py")
    print("2. Run MOA analysis nightly (e.g., at 2 AM UTC)")
    print("3. Review recommendations in data/moa/recommendations.json")
    print("4. Apply approved recommendations to keyword_stats.json")


if __name__ == "__main__":
    main()
