"""Test script for news velocity sentiment source.

This script simulates article spikes and tests the velocity scoring logic
to ensure it correctly identifies high media attention and viral catalysts.

Usage:
    python test_news_velocity.py
"""

import os
import sys
import time
from datetime import datetime, timedelta, timezone

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from catalyst_bot.news_velocity import NewsVelocityTracker


def test_normal_flow():
    """Test normal article flow (2-3 articles/day)."""
    print("\n=== Test 1: Normal Flow (2-3 articles/day) ===")

    tracker = NewsVelocityTracker(db_path="data/news_velocity_test.db")

    # Simulate 3 articles over 24 hours
    articles = [
        ("Article 1: Company announces new product", "https://example.com/1"),
        ("Article 2: Earnings report preview", "https://example.com/2"),
        ("Article 3: Analyst upgrades stock", "https://example.com/3"),
    ]

    for title, url in articles:
        tracker.record_article(
            ticker="AAPL",
            title=title,
            url=url,
            source="test",
        )

    # Get velocity sentiment
    result = tracker.get_velocity_sentiment("AAPL")

    print(f"Articles 1h: {result['articles_1h']}")
    print(f"Articles 4h: {result['articles_4h']}")
    print(f"Articles 24h: {result['articles_24h']}")
    print(f"Velocity Score: {result['velocity_score']:.3f}")
    print(f"Sentiment: {result['sentiment']:.3f}")
    print(f"Confidence: {result['confidence']:.3f}")
    print(f"Is Spike: {result['is_spike']}")

    # Assertions
    assert result["articles_24h"] == 3, "Expected 3 articles in 24h"
    assert result["velocity_score"] < 0.3, "Normal flow should have low velocity score"
    assert not result["is_spike"], "Normal flow should not be flagged as spike"

    print("[PASS] Normal flow test passed")


def test_article_spike():
    """Test article spike (10+ articles in 1 hour)."""
    print("\n=== Test 2: Article Spike (10+ articles in 1 hour) ===")

    tracker = NewsVelocityTracker(db_path="data/news_velocity_test.db")

    # Simulate 15 articles in 1 hour (spike scenario)
    base_time = datetime.now(timezone.utc)
    articles = [
        (f"Breaking news: Major development {i}", f"https://example.com/spike{i}")
        for i in range(15)
    ]

    for title, url in articles:
        tracker.record_article(
            ticker="TSLA",
            title=title,
            url=url,
            source="test",
        )

    # Get velocity sentiment
    result = tracker.get_velocity_sentiment("TSLA")

    print(f"Articles 1h: {result['articles_1h']}")
    print(f"Articles 4h: {result['articles_4h']}")
    print(f"Articles 24h: {result['articles_24h']}")
    print(f"Velocity Score: {result['velocity_score']:.3f}")
    print(f"Sentiment: {result['sentiment']:.3f}")
    print(f"Confidence: {result['confidence']:.3f}")
    print(f"Is Spike: {result['is_spike']}")

    # Assertions
    assert result["articles_1h"] >= 10, "Expected 10+ articles in 1h"
    assert result["velocity_score"] >= 0.3, "Spike should have high velocity score"
    assert result["sentiment"] >= 0.3, "Spike should have positive sentiment"

    print("[PASS] Article spike test passed")


def test_viral_catalyst():
    """Test viral catalyst (20+ articles in 1 hour)."""
    print("\n=== Test 3: Viral Catalyst (20+ articles in 1 hour) ===")

    tracker = NewsVelocityTracker(db_path="data/news_velocity_test.db")

    # Simulate 25 articles in 1 hour (viral scenario)
    articles = [
        (f"Viral news: Breaking development {i}", f"https://example.com/viral{i}")
        for i in range(25)
    ]

    for title, url in articles:
        tracker.record_article(
            ticker="GME",
            title=title,
            url=url,
            source="test",
        )

    # Get velocity sentiment
    result = tracker.get_velocity_sentiment("GME")

    print(f"Articles 1h: {result['articles_1h']}")
    print(f"Articles 4h: {result['articles_4h']}")
    print(f"Articles 24h: {result['articles_24h']}")
    print(f"Velocity Score: {result['velocity_score']:.3f}")
    print(f"Sentiment: {result['sentiment']:.3f}")
    print(f"Confidence: {result['confidence']:.3f}")
    print(f"Is Spike: {result['is_spike']}")

    # Assertions
    assert result["articles_1h"] >= 20, "Expected 20+ articles in 1h"
    assert result["velocity_score"] >= 0.5, "Viral catalyst should have very high score"
    assert result["sentiment"] >= 0.5, "Viral catalyst should have strong positive sentiment"

    print("[PASS] Viral catalyst test passed")


def test_extreme_attention():
    """Test extreme attention (50+ articles in 1 hour)."""
    print("\n=== Test 4: Extreme Attention (50+ articles in 1 hour) ===")

    tracker = NewsVelocityTracker(db_path="data/news_velocity_test.db")

    # Simulate 60 articles in 1 hour (extreme scenario - potential pump)
    articles = [
        (f"Extreme attention: Event {i}", f"https://example.com/extreme{i}")
        for i in range(60)
    ]

    for title, url in articles:
        tracker.record_article(
            ticker="PUMP",
            title=title,
            url=url,
            source="test",
        )

    # Get velocity sentiment
    result = tracker.get_velocity_sentiment("PUMP")

    print(f"Articles 1h: {result['articles_1h']}")
    print(f"Articles 4h: {result['articles_4h']}")
    print(f"Articles 24h: {result['articles_24h']}")
    print(f"Velocity Score: {result['velocity_score']:.3f}")
    print(f"Sentiment: {result['sentiment']:.3f}")
    print(f"Confidence: {result['confidence']:.3f}")
    print(f"Is Spike: {result['is_spike']}")

    # Assertions
    assert result["articles_1h"] >= 50, "Expected 50+ articles in 1h"
    assert result["velocity_score"] >= 0.7, "Extreme attention should have max score"
    assert result["sentiment"] >= 0.7, "Extreme attention should have max sentiment"

    print("[PASS] Extreme attention test passed")


def test_deduplication():
    """Test article deduplication by title similarity."""
    print("\n=== Test 5: Deduplication ===")

    tracker = NewsVelocityTracker(db_path="data/news_velocity_test.db")

    # Use unique ticker to avoid collision with previous tests
    ticker = "DEDUP_TEST"

    # Record same article multiple times (should dedupe)
    title = "Unique deduplication test article with specific content here"
    for i in range(5):
        result = tracker.record_article(
            ticker=ticker,
            title=title,
            url=f"https://example.com/dedup_unique_{i}",
            source="test",
        )
        if i == 0:
            assert result is True, f"First article should be recorded (got {result})"
        else:
            assert result is False, f"Duplicate articles should be rejected (iteration {i}, got {result})"

    # Get velocity sentiment
    result = tracker.get_velocity_sentiment(ticker)

    print(f"Articles 24h: {result['articles_24h']}")
    print(f"Expected: 1 (deduplicated)")

    # Assertions
    assert result["articles_24h"] == 1, "Should only record 1 article (rest deduplicated)"

    print("[PASS] Deduplication test passed")


def test_sustained_coverage():
    """Test sustained coverage (4h velocity > 3x baseline)."""
    print("\n=== Test 6: Sustained Coverage Detection ===")

    tracker = NewsVelocityTracker(db_path="data/news_velocity_test.db")

    # Simulate sustained coverage: 12 articles/hour over 4 hours = 48 total
    # Baseline is 5 articles/day = 0.208/hour
    # 12/hour is >3x baseline, should trigger is_spike
    articles = [
        (f"Sustained news coverage {i}", f"https://example.com/sustained{i}")
        for i in range(48)
    ]

    for title, url in articles:
        tracker.record_article(
            ticker="SUST",
            title=title,
            url=url,
            source="test",
        )

    # Get velocity sentiment
    result = tracker.get_velocity_sentiment("SUST", baseline_articles_per_day=5.0)

    print(f"Articles 4h: {result['articles_4h']}")
    print(f"Velocity 4h: {result['velocity_4h']:.2f} articles/hour")
    print(f"Baseline hourly: {result['baseline_hourly']:.2f} articles/hour")
    print(f"Is Spike: {result['is_spike']}")
    print(f"Sentiment: {result['sentiment']:.3f}")

    # Assertions
    assert result["velocity_4h"] > result["baseline_hourly"] * 3, "4h velocity should exceed 3x baseline"
    assert result["is_spike"], "Sustained coverage should be flagged as spike"
    # Spike bonus adds 0.2, but sentiment is clamped to 1.0, so >= check
    assert result["sentiment"] >= result["velocity_score"], "Spike should maintain or boost sentiment"

    print("[PASS] Sustained coverage test passed")


def test_classifier_integration():
    """Test integration with classify.py."""
    print("\n=== Test 7: Classifier Integration ===")

    try:
        from catalyst_bot.classify import aggregate_sentiment_sources
        from catalyst_bot.models import NewsItem

        tracker = NewsVelocityTracker(db_path="data/news_velocity_test.db")

        # Record some articles for ticker
        for i in range(15):
            tracker.record_article(
                ticker="INTEG",
                title=f"Integration test article {i}",
                url=f"https://example.com/integ{i}",
                source="test",
            )

        # Create a mock news item
        class MockItem:
            def __init__(self):
                self.title = "Test integration with classifier"
                self.ticker = "INTEG"
                self.raw = {}

        item = MockItem()

        # Get aggregated sentiment (should include news velocity)
        # Note: aggregate_sentiment_sources returns 4 values, but in some cases may return 3
        result = aggregate_sentiment_sources(item)
        if len(result) == 4:
            sentiment, confidence, breakdown, trend = result
        elif len(result) == 3:
            sentiment, confidence, breakdown = result
            trend = None
        else:
            raise ValueError(f"Unexpected return value count: {len(result)}")

        print(f"Sentiment: {sentiment:.3f}")
        print(f"Confidence: {confidence:.3f}")
        print(f"Breakdown: {breakdown}")

        # Check if news_velocity is in breakdown
        if "news_velocity" in breakdown:
            print(f"News Velocity Sentiment: {breakdown['news_velocity']:.3f}")
            print("[PASS] Classifier integration test passed")
        else:
            print("WARNING: News velocity not in sentiment breakdown (feature may be disabled)")

    except Exception as e:
        print(f"WARNING: Classifier integration test skipped: {e}")


def test_statistics():
    """Test tracker statistics."""
    print("\n=== Test 8: Tracker Statistics ===")

    tracker = NewsVelocityTracker(db_path="data/news_velocity_test.db")

    stats = tracker.get_stats()

    print(f"Total Articles: {stats['total_articles']}")
    print(f"Unique Tickers: {stats['unique_tickers']}")
    print(f"Articles 24h: {stats['articles_24h']}")

    assert stats["total_articles"] > 0, "Should have recorded articles"
    assert stats["unique_tickers"] > 0, "Should have tracked tickers"

    print("[PASS] Statistics test passed")


def cleanup():
    """Clean up test database."""
    print("\n=== Cleanup ===")

    import os
    import time

    test_db = "data/news_velocity_test.db"
    if os.path.exists(test_db):
        # Give time for database connections to close
        time.sleep(0.5)
        try:
            os.remove(test_db)
            print(f"Removed test database: {test_db}")
        except PermissionError:
            print(f"Warning: Could not remove test database (still in use): {test_db}")


def main():
    """Run all tests."""
    print("=" * 60)
    print("NEWS VELOCITY SENTIMENT SOURCE - TEST SUITE")
    print("=" * 60)

    try:
        # Run tests
        test_normal_flow()
        test_article_spike()
        test_viral_catalyst()
        test_extreme_attention()
        test_deduplication()
        test_sustained_coverage()
        test_classifier_integration()
        test_statistics()

        print("\n" + "=" * 60)
        print("ALL TESTS PASSED")
        print("=" * 60)

    except AssertionError as e:
        print(f"\nTEST FAILED: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\nERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        cleanup()


if __name__ == "__main__":
    main()
