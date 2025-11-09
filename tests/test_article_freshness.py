"""
Unit tests for article freshness checking.

Tests the is_article_fresh() function to ensure stale articles are properly rejected.
"""
import pytest
from datetime import datetime, timedelta, timezone
from catalyst_bot.runner import is_article_fresh


def test_fresh_article():
    """Test that recent article passes freshness check."""
    now = datetime.now(timezone.utc)
    published_5_min_ago = now - timedelta(minutes=5)

    is_fresh, age_min = is_article_fresh(published_5_min_ago, max_age_minutes=30)

    assert is_fresh is True
    assert age_min == 5


def test_stale_article():
    """Test that old article fails freshness check."""
    now = datetime.now(timezone.utc)
    published_60_min_ago = now - timedelta(minutes=60)

    is_fresh, age_min = is_article_fresh(published_60_min_ago, max_age_minutes=30)

    assert is_fresh is False
    assert age_min == 60


def test_edge_case_exactly_at_threshold():
    """Test article exactly at threshold is considered fresh."""
    now = datetime.now(timezone.utc)
    published_30_min_ago = now - timedelta(minutes=30)

    is_fresh, age_min = is_article_fresh(published_30_min_ago, max_age_minutes=30)

    assert is_fresh is True
    assert age_min == 30


def test_edge_case_one_second_over_threshold():
    """Test article one second over threshold is considered stale."""
    now = datetime.now(timezone.utc)
    published_30_min_1_sec_ago = now - timedelta(minutes=30, seconds=1)

    is_fresh, age_min = is_article_fresh(published_30_min_1_sec_ago, max_age_minutes=30)

    assert is_fresh is False
    # age_min should be 30 (truncated from 30.016...)
    assert age_min == 30


def test_sec_filing_exception():
    """Test that SEC filings have longer freshness window."""
    now = datetime.now(timezone.utc)
    published_120_min_ago = now - timedelta(minutes=120)

    # Regular article: should be stale
    is_fresh_regular, _ = is_article_fresh(
        published_120_min_ago,
        max_age_minutes=30,
        is_sec_filing=False,
    )
    assert is_fresh_regular is False

    # SEC filing: should be fresh
    is_fresh_sec, age_min = is_article_fresh(
        published_120_min_ago,
        max_sec_age_minutes=240,
        is_sec_filing=True,
    )
    assert is_fresh_sec is True
    assert age_min == 120


def test_missing_publish_time():
    """Test that missing publish time allows through (fail-open)."""
    is_fresh, age_min = is_article_fresh(None, max_age_minutes=30)

    assert is_fresh is True  # Allow through when publish time unknown
    assert age_min is None


def test_timezone_naive_datetime():
    """Test that timezone-naive datetimes are handled correctly."""
    now = datetime.now(timezone.utc)
    # Create timezone-naive datetime
    published_10_min_ago = datetime.now() - timedelta(minutes=10)
    # Remove timezone info to make it naive
    published_10_min_ago = published_10_min_ago.replace(tzinfo=None)

    is_fresh, age_min = is_article_fresh(published_10_min_ago, max_age_minutes=30)

    # Should handle gracefully and convert to UTC
    assert is_fresh is True
    # Age should be approximately 10 minutes (allowing for minor clock drift)
    assert 9 <= age_min <= 11


def test_future_published_date():
    """Test handling of article with future publish date (edge case)."""
    now = datetime.now(timezone.utc)
    published_in_future = now + timedelta(minutes=5)

    is_fresh, age_min = is_article_fresh(published_in_future, max_age_minutes=30)

    # Negative age means future - should be considered "fresh" (age <= threshold)
    # The function calculates age = now - published, so future dates give negative age
    # Since -5 <= 30, it's considered fresh
    assert is_fresh is True
    assert age_min == -5  # Negative age


def test_very_old_article():
    """Test very old article (days old) is rejected."""
    now = datetime.now(timezone.utc)
    published_2_days_ago = now - timedelta(days=2)

    is_fresh, age_min = is_article_fresh(published_2_days_ago, max_age_minutes=30)

    assert is_fresh is False
    assert age_min == 2880  # 2 days * 24 hours * 60 minutes


def test_sec_filing_old_but_within_window():
    """Test SEC filing that is old for regular news but fresh for SEC."""
    now = datetime.now(timezone.utc)
    published_3_hours_ago = now - timedelta(hours=3)

    # Regular article: stale
    is_fresh_regular, _ = is_article_fresh(
        published_3_hours_ago,
        max_age_minutes=30,
        is_sec_filing=False,
    )
    assert is_fresh_regular is False

    # SEC filing: fresh (within 4-hour window)
    is_fresh_sec, age_min = is_article_fresh(
        published_3_hours_ago,
        max_sec_age_minutes=240,
        is_sec_filing=True,
    )
    assert is_fresh_sec is True
    assert age_min == 180  # 3 hours = 180 minutes


def test_sec_filing_beyond_window():
    """Test SEC filing beyond 4-hour window is rejected."""
    now = datetime.now(timezone.utc)
    published_5_hours_ago = now - timedelta(hours=5)

    is_fresh, age_min = is_article_fresh(
        published_5_hours_ago,
        max_sec_age_minutes=240,
        is_sec_filing=True,
    )

    assert is_fresh is False
    assert age_min == 300  # 5 hours = 300 minutes
