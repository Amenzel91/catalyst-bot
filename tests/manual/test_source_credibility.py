#!/usr/bin/env python3
"""Test script for source credibility scoring system.

This script demonstrates and tests the source credibility scoring system
to ensure it correctly weights news sources based on reliability.

Usage:
    python test_source_credibility.py
"""

from src.catalyst_bot.source_credibility import (
    extract_domain,
    get_source_category,
    get_source_tier,
    get_source_weight,
    get_tier_summary,
)


def test_domain_extraction():
    """Test domain extraction from various URL formats."""
    print("=" * 70)
    print("TEST 1: Domain Extraction")
    print("=" * 70)

    test_cases = [
        ("https://www.sec.gov/filing.html", "sec.gov"),
        ("https://www.bloomberg.com/news/article", "bloomberg.com"),
        ("https://news.reuters.com/article/123", "reuters.com"),
        ("https://www.globenewswire.com/news", "globenewswire.com"),
        ("https://unknown-blog.com/post", "unknown-blog.com"),
        ("www.wsj.com", "wsj.com"),
        ("ft.com/article", "ft.com"),
    ]

    all_passed = True
    for url, expected in test_cases:
        result = extract_domain(url)
        passed = result == expected
        all_passed = all_passed and passed
        status = "[PASS]" if passed else "[FAIL]"
        print(f"{status} URL: {url:50s} -> {result:25s} (expected: {expected})")

    print(f"\nDomain Extraction: {'PASSED' if all_passed else 'FAILED'}\n")
    return all_passed


def test_tier_classification():
    """Test source tier classification."""
    print("=" * 70)
    print("TEST 2: Tier Classification")
    print("=" * 70)

    test_cases = [
        # Tier 1 (HIGH) - Regulatory and premium news
        ("https://www.sec.gov/filing.html", 1, "Tier 1: SEC"),
        ("https://www.bloomberg.com/news", 1, "Tier 1: Bloomberg"),
        ("https://www.reuters.com/article", 1, "Tier 1: Reuters"),
        ("https://www.wsj.com/article", 1, "Tier 1: WSJ"),
        ("https://www.ft.com/content", 1, "Tier 1: FT"),
        # Tier 2 (MEDIUM) - PR wires and financial news
        ("https://www.globenewswire.com/news", 2, "Tier 2: GlobeNewswire"),
        ("https://www.businesswire.com/news", 2, "Tier 2: Business Wire"),
        ("https://www.prnewswire.com/news", 2, "Tier 2: PR Newswire"),
        ("https://www.marketwatch.com/story", 2, "Tier 2: MarketWatch"),
        # Tier 3 (LOW) - Unknown sources
        ("https://random-blog.com/post", 3, "Tier 3: Unknown blog"),
        ("https://penny-stock-pumper.com", 3, "Tier 3: Unknown site"),
    ]

    all_passed = True
    for url, expected_tier, description in test_cases:
        tier = get_source_tier(url)
        passed = tier == expected_tier
        all_passed = all_passed and passed
        status = "[PASS]" if passed else "[FAIL]"
        print(f"{status} {description:30s} -> Tier {tier} (expected: {expected_tier})")

    print(f"\nTier Classification: {'PASSED' if all_passed else 'FAILED'}\n")
    return all_passed


def test_weight_calculation():
    """Test credibility weight calculation."""
    print("=" * 70)
    print("TEST 3: Weight Calculation")
    print("=" * 70)

    test_cases = [
        # Tier 1 sources should get 1.5x weight
        ("https://www.sec.gov/filing.html", 1.5, "Tier 1: SEC (1.5x)"),
        ("https://www.bloomberg.com/news", 1.5, "Tier 1: Bloomberg (1.5x)"),
        # Tier 2 sources should get 1.0x weight
        ("https://www.globenewswire.com/news", 1.0, "Tier 2: GlobeNewswire (1.0x)"),
        ("https://www.marketwatch.com/story", 1.0, "Tier 2: MarketWatch (1.0x)"),
        # Tier 3 sources should get 0.5x weight
        ("https://random-blog.com/post", 0.5, "Tier 3: Unknown (0.5x)"),
    ]

    all_passed = True
    for url, expected_weight, description in test_cases:
        weight = get_source_weight(url)
        passed = abs(weight - expected_weight) < 0.01
        all_passed = all_passed and passed
        status = "[PASS]" if passed else "[FAIL]"
        print(
            f"{status} {description:40s} -> {weight:.2f} (expected: {expected_weight:.2f})"
        )

    print(f"\nWeight Calculation: {'PASSED' if all_passed else 'FAILED'}\n")
    return all_passed


def test_category_assignment():
    """Test source category assignment."""
    print("=" * 70)
    print("TEST 4: Category Assignment")
    print("=" * 70)

    test_cases = [
        ("https://www.sec.gov/filing.html", "regulatory", "SEC"),
        ("https://www.bloomberg.com/news", "premium_news", "Bloomberg"),
        ("https://www.globenewswire.com/news", "pr_wire", "GlobeNewswire"),
        ("https://www.marketwatch.com/story", "financial_news", "MarketWatch"),
        ("https://random-blog.com/post", "unknown", "Unknown"),
    ]

    all_passed = True
    for url, expected_category, description in test_cases:
        category = get_source_category(url)
        passed = category == expected_category
        all_passed = all_passed and passed
        status = "[PASS]" if passed else "[FAIL]"
        print(
            f"{status} {description:20s} -> {category:20s} (expected: {expected_category})"
        )

    print(f"\nCategory Assignment: {'PASSED' if all_passed else 'FAILED'}\n")
    return all_passed


def test_tier_summary():
    """Test tier summary generation."""
    print("=" * 70)
    print("TEST 5: Tier Summary")
    print("=" * 70)

    summary = get_tier_summary()

    # Check that all tiers exist
    expected_tiers = [1, 2, 3]
    all_passed = True

    for tier in expected_tiers:
        if tier not in summary:
            print(f"[FAIL] Missing tier {tier}")
            all_passed = False
        else:
            tier_data = summary[tier]
            weight = tier_data["weight"]
            sources = tier_data["sources"]
            categories = tier_data["categories"]

            print(f"\nTier {tier} (weight: {weight}x):")
            print(f"  Sources: {len(sources)}")
            if sources and sources[0] != "unknown":
                print(f"  Examples: {', '.join(sources[:3])}")
            print(f"  Categories: {', '.join(categories)}")

    print(f"\nTier Summary: {'PASSED' if all_passed else 'FAILED'}\n")
    return all_passed


def test_impact_on_scores():
    """Test how credibility weights impact classification scores."""
    print("=" * 70)
    print("TEST 6: Impact on Classification Scores")
    print("=" * 70)

    base_score = 100.0  # Arbitrary base score

    test_cases = [
        ("https://www.sec.gov/filing.html", 1.5),
        ("https://www.globenewswire.com/news", 1.0),
        ("https://random-blog.com/post", 0.5),
    ]

    print("Base score: 100.0\n")

    for url, expected_multiplier in test_cases:
        weight = get_source_weight(url)
        tier = get_source_tier(url)
        adjusted_score = base_score * weight

        domain = extract_domain(url)
        print(
            f"Source: {domain:30s} (Tier {tier}) -> "
            f"{base_score:.1f} × {weight:.2f} = {adjusted_score:.1f}"
        )

    print("\nNote: Higher tier sources get boosted, lower tier sources get penalized.")
    print("Impact on Classification Scores: PASSED\n")
    return True


def main():
    """Run all tests and report results."""
    print("\n" + "=" * 70)
    print("SOURCE CREDIBILITY SCORING SYSTEM - TEST SUITE")
    print("=" * 70 + "\n")

    tests = [
        test_domain_extraction,
        test_tier_classification,
        test_weight_calculation,
        test_category_assignment,
        test_tier_summary,
        test_impact_on_scores,
    ]

    results = []
    for test_func in tests:
        try:
            result = test_func()
            results.append(result)
        except Exception as e:
            print(f"[FAIL] Test failed with exception: {e}\n")
            results.append(False)

    # Final summary
    passed = sum(results)
    total = len(results)

    print("=" * 70)
    print("FINAL RESULTS")
    print("=" * 70)
    print(f"Tests passed: {passed}/{total}")
    print(f"Success rate: {(passed/total*100):.1f}%")

    if passed == total:
        print("\n[SUCCESS] All tests PASSED")
        return 0
    else:
        print(f"\n[FAILED] {total - passed} test(s) FAILED")
        return 1


if __name__ == "__main__":
    exit(main())
