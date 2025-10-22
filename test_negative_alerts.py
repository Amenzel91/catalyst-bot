#!/usr/bin/env python3
"""
Test script for negative alert detection.

Tests the negative catalyst alert system with realistic examples.
"""

import logging

# CRITICAL: Load .env file BEFORE importing any modules that use config
from dotenv import load_dotenv
load_dotenv()

# Configure logging to see DEBUG output
logging.basicConfig(
    level=logging.INFO,
    format='%(levelname)s - %(name)s - %(message)s'
)

from src.catalyst_bot.models import NewsItem
from src.catalyst_bot.classify import classify


def create_test_item(title, summary, ticker="TEST", source="test"):
    """Helper to create a NewsItem for testing."""
    from datetime import datetime, timezone

    return NewsItem(
        title=title,
        link="https://example.com/test",
        published="2025-01-01T00:00:00Z",
        ticker=ticker,
        source=source,
        summary=summary,
        ts_utc=datetime.now(timezone.utc),
    )


def test_offering_detection():
    """Test 1: Public offering detection (DFLI real example)."""
    print("=" * 70)
    print("TEST 1: Public Offering Detection (DFLI)")
    print("=" * 70)

    item = create_test_item(
        title="Dragonfly Energy Announces Proposed Public Offering of Common Stock and Pre-Funded Warrants",
        summary=(
            "RENO, Nev., Oct. 15, 2025 (GLOBE NEWSWIRE) -- Dragonfly Energy Holdings Corp. "
            "announced that it has commenced an underwritten public offering of shares of its "
            "common stock and, in lieu of common stock to investors who so choose, pre-funded "
            "warrants to purchase shares of its common stock."
        ),
        ticker="DFLI",
        source="globenewswire_public",
    )

    result = classify(item)

    print(f"\nTitle: {item.title[:80]}...")
    print(f"Score: {_get_score(result):.3f}")
    print(f"Sentiment: {_get_sentiment(result):.3f}")
    print(f"Keywords: {_get_keywords(result)}")
    print(f"Alert Type: {_get_attr(result, 'alert_type', 'N/A')}")
    print(f"Negative Keywords: {_get_attr(result, 'negative_keywords', [])}")

    # Verify negative alert detected
    is_negative = _get_attr(result, 'alert_type') == "NEGATIVE"
    has_neg_keywords = len(_get_attr(result, 'negative_keywords', [])) > 0
    score_is_negative = _get_score(result) < 0

    print("\nCHECKS:")
    print(f"  Alert Type = NEGATIVE: {'PASS' if is_negative else 'FAIL'}")
    print(f"  Has Negative Keywords: {'PASS' if has_neg_keywords else 'FAIL'}")
    print(f"  Score is Negative: {'PASS' if score_is_negative else 'FAIL'}")

    return is_negative and has_neg_keywords and score_is_negative


def test_dilution_detection():
    """Test 2: Dilutive offering detection."""
    print("\n" + "=" * 70)
    print("TEST 2: Dilutive Offering Detection")
    print("=" * 70)

    item = create_test_item(
        title="Company Announces $50M Dilutive Equity Financing",
        summary="The company will issue new shares representing significant dilution to existing shareholders.",
        ticker="TEST",
    )

    result = classify(item)

    print(f"\nTitle: {item.title}")
    print(f"Score: {_get_score(result):.3f}")
    print(f"Alert Type: {_get_attr(result, 'alert_type', 'N/A')}")
    print(f"Negative Keywords: {_get_attr(result, 'negative_keywords', [])}")

    is_negative = _get_attr(result, 'alert_type') == "NEGATIVE"
    print(f"\nNegative alert detected: {'YES' if is_negative else 'NO'}")

    return is_negative


def test_warrant_detection():
    """Test 3: Warrant exercise detection."""
    print("\n" + "=" * 70)
    print("TEST 3: Warrant Exercise Detection")
    print("=" * 70)

    item = create_test_item(
        title="Company Announces Warrant Exercise and Share Issuance",
        summary="Warrant holders exercised 5 million pre-funded warrants at $0.01 per share.",
        ticker="TEST",
    )

    result = classify(item)

    print(f"\nTitle: {item.title}")
    print(f"Score: {_get_score(result):.3f}")
    print(f"Alert Type: {_get_attr(result, 'alert_type', 'N/A')}")
    print(f"Negative Keywords: {_get_attr(result, 'negative_keywords', [])}")

    is_negative = _get_attr(result, 'alert_type') == "NEGATIVE"
    print(f"\nNegative alert detected: {'YES' if is_negative else 'NO'}")

    return is_negative


def test_positive_news_not_flagged():
    """Test 4: Positive news should NOT be flagged as negative."""
    print("\n" + "=" * 70)
    print("TEST 4: Positive News (Should NOT be Negative)")
    print("=" * 70)

    item = create_test_item(
        title="Company Reports Record Earnings Beat, Raises Guidance",
        summary="Strong quarterly performance with revenue up 50% year over year.",
        ticker="TEST",
    )

    result = classify(item)

    print(f"\nTitle: {item.title}")
    print(f"Score: {_get_score(result):.3f}")
    print(f"Alert Type: {_get_attr(result, 'alert_type', 'N/A')}")

    is_negative = _get_attr(result, 'alert_type') == "NEGATIVE"
    print(f"\nCorrectly NOT flagged as negative: {'YES' if not is_negative else 'NO'}")

    return not is_negative


def test_distress_detection():
    """Test 5: Financial distress detection."""
    print("\n" + "=" * 70)
    print("TEST 5: Financial Distress Detection")
    print("=" * 70)

    item = create_test_item(
        title="Company Receives Going Concern Warning from Auditors",
        summary="Auditors raised substantial doubt about the company's ability to continue as a going concern.",
        ticker="TEST",
    )

    result = classify(item)

    print(f"\nTitle: {item.title}")
    print(f"Score: {_get_score(result):.3f}")
    print(f"Alert Type: {_get_attr(result, 'alert_type', 'N/A')}")
    print(f"Negative Keywords: {_get_attr(result, 'negative_keywords', [])}")

    is_negative = _get_attr(result, 'alert_type') == "NEGATIVE"
    print(f"\nNegative alert detected: {'YES' if is_negative else 'NO'}")

    return is_negative


# Helper functions to extract data from ScoredItem (dict or object)
def _get_score(scored):
    """Extract score from scored item."""
    if isinstance(scored, dict):
        return scored.get('score', 0.0)
    return getattr(scored, 'source_weight', 0.0)


def _get_sentiment(scored):
    """Extract sentiment from scored item."""
    if isinstance(scored, dict):
        return scored.get('sentiment', 0.0)
    return getattr(scored, 'sentiment', 0.0)


def _get_keywords(scored):
    """Extract keywords from scored item."""
    if isinstance(scored, dict):
        return scored.get('keywords', scored.get('tags', []))
    return getattr(scored, 'tags', [])


def _get_attr(scored, attr, default=None):
    """Get attribute from scored item (dict or object)."""
    if isinstance(scored, dict):
        return scored.get(attr, default)
    return getattr(scored, attr, default)


def main():
    """Run all tests."""
    print("\nNEGATIVE ALERT DETECTION TESTS")
    print("=" * 70)
    print("Testing negative catalyst detection system...")
    print()

    results = []

    # Run tests
    try:
        results.append(("Offering Detection (DFLI)", test_offering_detection()))
    except Exception as e:
        print(f"\nX EXCEPTION: {e}")
        results.append(("Offering Detection (DFLI)", False))

    try:
        results.append(("Dilution Detection", test_dilution_detection()))
    except Exception as e:
        print(f"\nX EXCEPTION: {e}")
        results.append(("Dilution Detection", False))

    try:
        results.append(("Warrant Detection", test_warrant_detection()))
    except Exception as e:
        print(f"\nX EXCEPTION: {e}")
        results.append(("Warrant Detection", False))

    try:
        results.append(("Positive News Check", test_positive_news_not_flagged()))
    except Exception as e:
        print(f"\nX EXCEPTION: {e}")
        results.append(("Positive News Check", False))

    try:
        results.append(("Distress Detection", test_distress_detection()))
    except Exception as e:
        print(f"\nX EXCEPTION: {e}")
        results.append(("Distress Detection", False))

    # Summary
    print("\n" + "=" * 70)
    print("TEST SUMMARY")
    print("=" * 70)

    passed = sum(1 for _, result in results if result)
    total = len(results)

    for test_name, result in results:
        status = "[PASS]" if result else "[FAIL]"
        print(f"{status}: {test_name}")

    print(f"\nTotal: {passed}/{total} tests passed")

    if passed == total:
        print("\nAll tests passed! Negative alerts are working correctly.")
        return 0
    else:
        print(f"\n{total - passed} test(s) failed")
        return 1


if __name__ == "__main__":
    exit(main())
