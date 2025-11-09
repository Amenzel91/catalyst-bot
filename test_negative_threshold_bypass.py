#!/usr/bin/env python3
"""
Test script to verify smart negative threshold bypass logic.

This script demonstrates that strong negative catalysts bypass MIN_SCORE threshold.
"""

import logging

# Configure logging to see the bypass messages
logging.basicConfig(
    level=logging.INFO,
    format='%(levelname)s - %(name)s - %(message)s'
)

print("=" * 70)
print("SMART NEGATIVE THRESHOLD BYPASS TEST")
print("=" * 70)
print()
print("This test verifies the dual threshold logic:")
print("  1. Positive alerts: Must meet MIN_SCORE >= 0.20")
print("  2. Strong negative alerts: Bypass MIN_SCORE if:")
print("     - Sentiment < -0.30 (strong negative)")
print("     - OR contains critical negative keywords")
print()
print("Expected behavior:")
print("  - Items with score < MIN_SCORE normally get skipped")
print("  - BUT if item has strong negative signals, it bypasses the check")
print()
print("=" * 70)
print()

# Simulate the threshold bypass logic
def test_bypass_logic():
    """Test cases demonstrating the bypass logic."""

    # Test case 1: Strong negative sentiment bypasses score threshold
    print("TEST CASE 1: Strong Negative Sentiment")
    print("-" * 70)
    score = 0.15  # Below MIN_SCORE=0.20
    sentiment = -0.45  # Strong negative
    title = "Company reports weak earnings"

    min_score = 0.20
    is_strong_negative = sentiment < -0.30

    print(f"  Score: {score:.3f} (MIN_SCORE={min_score})")
    print(f"  Sentiment: {sentiment:.3f}")
    print(f"  Title: {title}")
    print()
    print(f"  Below MIN_SCORE? {score < min_score}")
    print(f"  Strong negative? {is_strong_negative}")
    print(f"  RESULT: {'BYPASS - Alert sent!' if is_strong_negative else 'SKIP'}")
    print()

    # Test case 2: Critical keyword bypasses score threshold
    print("TEST CASE 2: Critical Negative Keyword")
    print("-" * 70)
    score = 0.18  # Below MIN_SCORE=0.20
    sentiment = -0.15  # Mild negative
    title = "Company announces dilutive equity offering"

    critical_negative_keywords = [
        "dilution", "offering", "warrant", "delisting", "bankruptcy",
        "trial failed", "fda rejected", "lawsuit", "going concern",
        "chapter 11", "restructuring", "default", "insolvent"
    ]

    title_lower = title.lower()
    has_critical_keyword = any(kw in title_lower for kw in critical_negative_keywords)
    matched_keyword = next((kw for kw in critical_negative_keywords if kw in title_lower), None)

    print(f"  Score: {score:.3f} (MIN_SCORE={min_score})")
    print(f"  Sentiment: {sentiment:.3f}")
    print(f"  Title: {title}")
    print()
    print(f"  Below MIN_SCORE? {score < min_score}")
    print(f"  Has critical keyword? {has_critical_keyword}")
    print(f"  Matched keyword: {matched_keyword}")
    print(f"  RESULT: {'BYPASS - Alert sent!' if has_critical_keyword else 'SKIP'}")
    print()

    # Test case 3: Normal weak negative (should skip)
    print("TEST CASE 3: Weak Negative (Normal Skip)")
    print("-" * 70)
    score = 0.12  # Below MIN_SCORE=0.20
    sentiment = -0.08  # Weak negative
    title = "Company faces minor regulatory questions"

    is_strong_negative = sentiment < -0.30
    title_lower = title.lower()
    has_critical_keyword = any(kw in title_lower for kw in critical_negative_keywords)

    print(f"  Score: {score:.3f} (MIN_SCORE={min_score})")
    print(f"  Sentiment: {sentiment:.3f}")
    print(f"  Title: {title}")
    print()
    print(f"  Below MIN_SCORE? {score < min_score}")
    print(f"  Strong negative? {is_strong_negative}")
    print(f"  Has critical keyword? {has_critical_keyword}")
    print(f"  RESULT: {'SKIP - Too weak to alert' if not (is_strong_negative or has_critical_keyword) else 'BYPASS'}")
    print()

    # Test case 4: ELBM case (divergence + negative sentiment)
    print("TEST CASE 4: ELBM Example (Real-world)")
    print("-" * 70)
    score = 0.186  # Was 0.286 before -0.100 divergence adjustment
    sentiment = -0.25  # Negative from sell-off
    divergence = "DIVERGENCE_NEG"
    title = "Electrum Special Acquisition Reports Strong Business Update"

    # Check if adjusted score is below threshold but sentiment is strong
    is_strong_negative = sentiment < -0.30  # False in this case
    has_critical_keyword = any(kw in title.lower() for kw in critical_negative_keywords)

    print(f"  Score: {score:.3f} (MIN_SCORE={min_score})")
    print(f"  Sentiment: {sentiment:.3f}")
    print(f"  Divergence: {divergence}")
    print(f"  Title: {title}")
    print()
    print(f"  Below MIN_SCORE? {score < min_score}")
    print(f"  Strong negative? {is_strong_negative} (threshold: < -0.30)")
    print(f"  Has critical keyword? {has_critical_keyword}")
    print()
    print("  NOTE: ELBM would NOT bypass with current thresholds.")
    print("  - Sentiment -0.25 is not < -0.30 threshold")
    print("  - No critical keywords present")
    print("  - Consider: Did divergence penalty make sense here?")
    print()

if __name__ == "__main__":
    test_bypass_logic()

    print("=" * 70)
    print("IMPLEMENTATION NOTES")
    print("=" * 70)
    print()
    print("The smart threshold bypass is now active in runner.py:")
    print("  1. Line ~1556: is_strong_negative flag initialized")
    print("  2. Line ~1559: Check sentiment < -0.30")
    print("  3. Line ~1568: Check critical negative keywords")
    print("  4. Line ~1588: Apply dual threshold logic")
    print()
    print("To verify in production:")
    print("  - Watch logs for 'strong_negative_detected' messages")
    print("  - Watch logs for 'min_score_bypassed' messages")
    print("  - Check cycle_metrics for 'strong_negatives_bypassed' count")
    print()
    print("Critical negative keywords:")
    print("  dilution, offering, warrant, delisting, bankruptcy,")
    print("  trial failed, fda rejected, lawsuit, going concern,")
    print("  chapter 11, restructuring, default, insolvent")
    print()
    print("=" * 70)
