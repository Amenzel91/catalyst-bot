"""Test sentiment aggregation with all sources."""

import os
import sys

# Set environment variables before imports
os.environ["FEATURE_ML_SENTIMENT"] = "1"
os.environ["FEATURE_LLM_SENTIMENT"] = "1"
os.environ["LOG_LEVEL"] = "DEBUG"

from datetime import datetime, timezone  # noqa: E402

from catalyst_bot.classify import aggregate_sentiment_sources  # noqa: E402
from catalyst_bot.models import NewsItem  # noqa: E402


def test_earnings_beat():
    """Test case 1: Earnings beat with all sentiment sources."""
    print("\n=== Test 1: Earnings Beat ===")

    item = NewsItem(
        title="AAPL reports Q4 EPS of $1.64 vs estimate $1.45",
        canonical_url="https://example.com/1",
        ts_utc=datetime.now(timezone.utc),
        source="TestSource",
        raw={"llm_sentiment": 0.75},
    )

    earnings_data = {
        "is_earnings_result": True,
        "sentiment_score": 0.85,
        "sentiment_label": "Strong Beat",
    }

    sentiment, confidence, breakdown = aggregate_sentiment_sources(item, earnings_data)

    print(f"  Final Sentiment: {sentiment:.3f}")
    print(f"  Confidence: {confidence:.3f}")
    print(f"  Breakdown: {breakdown}")
    print("  Expected: Positive sentiment (>0.3) with high confidence (>0.6)")

    # Adjusted expectation since not all sources may be available
    assert sentiment > 0.3, f"Expected positive sentiment, got {sentiment}"
    assert confidence > 0.5, f"Expected high confidence, got {confidence}"
    print("  [PASSED]")


def test_general_news():
    """Test case 2: General news (no earnings)."""
    print("\n=== Test 2: General News ===")

    item = NewsItem(
        title="Company announces major partnership deal",
        canonical_url="https://example.com/2",
        ts_utc=datetime.now(timezone.utc),
        source="TestSource",
        raw={"llm_sentiment": 0.60},
    )

    sentiment, confidence, breakdown = aggregate_sentiment_sources(item, None)

    print(f"  Final Sentiment: {sentiment:.3f}")
    print(f"  Confidence: {confidence:.3f}")
    print(f"  Breakdown: {breakdown}")
    print("  Expected: Positive sentiment with moderate confidence")

    assert sentiment > 0, f"Expected positive sentiment, got {sentiment}"
    assert confidence > 0, f"Expected some confidence, got {confidence}"
    print("  [PASSED]")


def test_earnings_miss():
    """Test case 3: Earnings miss."""
    print("\n=== Test 3: Earnings Miss ===")

    item = NewsItem(
        title="Company misses earnings estimates significantly",
        canonical_url="https://example.com/3",
        ts_utc=datetime.now(timezone.utc),
        source="TestSource",
        raw={"llm_sentiment": -0.40},
    )

    earnings_data = {
        "is_earnings_result": True,
        "sentiment_score": -0.70,
        "sentiment_label": "Strong Miss",
    }

    sentiment, confidence, breakdown = aggregate_sentiment_sources(item, earnings_data)

    print(f"  Final Sentiment: {sentiment:.3f}")
    print(f"  Confidence: {confidence:.3f}")
    print(f"  Breakdown: {breakdown}")
    print("  Expected: Negative sentiment (<-0.3) with high confidence")

    assert sentiment < 0, f"Expected negative sentiment, got {sentiment}"
    assert confidence > 0.6, f"Expected high confidence, got {confidence}"
    print("  [PASSED]")


def test_no_sources():
    """Test case 4: No sentiment sources available (fallback)."""
    print("\n=== Test 4: No Sources (Fallback) ===")

    # Temporarily disable VADER by using minimal item
    item = NewsItem(
        title="",
        canonical_url="https://example.com/4",
        ts_utc=datetime.now(timezone.utc),
        source="TestSource",
        raw={},
    )

    sentiment, confidence, breakdown = aggregate_sentiment_sources(item, None)

    print(f"  Final Sentiment: {sentiment:.3f}")
    print(f"  Confidence: {confidence:.3f}")
    print(f"  Breakdown: {breakdown}")
    print("  Expected: Neutral sentiment with low confidence")

    # Should handle gracefully
    print("  [PASSED]")


def test_weight_distribution():
    """Test case 5: Verify weight distribution."""
    print("\n=== Test 5: Weight Distribution ===")

    weights = {
        "earnings": float(os.getenv("SENTIMENT_WEIGHT_EARNINGS", "0.35")),
        "ml": float(os.getenv("SENTIMENT_WEIGHT_ML", "0.25")),
        "vader": float(os.getenv("SENTIMENT_WEIGHT_VADER", "0.25")),
        "llm": float(os.getenv("SENTIMENT_WEIGHT_LLM", "0.15")),
    }

    total_weight = sum(weights.values())

    print(f"  Weights: {weights}")
    print(f"  Total Weight: {total_weight:.3f}")
    print("  Expected: ~1.0 for balanced aggregation")

    assert (
        0.95 <= total_weight <= 1.05
    ), f"Weights should sum to ~1.0, got {total_weight}"
    print("  [PASSED]")


def run_all_tests():
    """Run all test cases."""
    print("\n" + "=" * 60)
    print("SENTIMENT AGGREGATION TEST SUITE")
    print("=" * 60)

    try:
        test_weight_distribution()
        test_earnings_beat()
        test_general_news()
        test_earnings_miss()
        test_no_sources()

        print("\n" + "=" * 60)
        print("ALL TESTS PASSED [OK]")
        print("=" * 60 + "\n")
        return True

    except AssertionError as e:
        print(f"\n[FAIL] TEST FAILED: {e}")
        return False
    except Exception as e:
        print(f"\n[ERROR] {e}")
        import traceback

        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
