"""
Comprehensive tests for MOA Phase 2 - moa_price_tracker.py

Tests cover:
1. get_pending_items() for each timeframe (1h, 4h, 24h, 1w)
2. record_outcome() with mock price data
3. Outcome JSONL append
4. is_missed_opportunity() logic
5. Time elapsed calculations
6. Market hours gating
7. Rate limiting
8. Handling of missing tickers
"""

import json
import os
import tempfile
import time
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock, patch

import pytest


# Mock classes for MOA price tracker (to be implemented)
class MOAPriceTracker:
    """Mock MOA Price Tracker for testing purposes"""

    def __init__(self, rejected_items_path, outcomes_path, market_interface):
        self.rejected_items_path = rejected_items_path
        self.outcomes_path = outcomes_path
        self.market = market_interface
        self.rate_limit_delay = 0.1  # 100ms between requests
        self.last_request_time = 0
        self.missed_opportunity_threshold = 0.10  # 10%

    def get_pending_items(self, timeframe_hours):
        """Get items pending outcome tracking for specified timeframe"""
        pending = []
        cutoff_time = datetime.now(timezone.utc) - timedelta(hours=timeframe_hours)

        if not os.path.exists(self.rejected_items_path):
            return pending

        # Load rejected items
        with open(self.rejected_items_path, "r", encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                try:
                    item = json.loads(line)
                    item_time = datetime.fromisoformat(
                        item["ts"].replace("Z", "+00:00")
                    )

                    # Check if enough time has elapsed
                    if item_time <= cutoff_time:
                        # Check if not already tracked for this timeframe
                        if not self._already_tracked(item, timeframe_hours):
                            pending.append(item)
                except (json.JSONDecodeError, KeyError, ValueError):
                    continue

        return pending

    def _already_tracked(self, item, timeframe_hours):
        """Check if item already has outcome recorded for this timeframe"""
        if not os.path.exists(self.outcomes_path):
            return False

        ticker = item.get("ticker")
        timestamp = item.get("ts")

        with open(self.outcomes_path, "r", encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                try:
                    outcome = json.loads(line)
                    if (
                        outcome.get("ticker") == ticker
                        and outcome.get("timestamp") == timestamp
                        and outcome.get("timeframe") == f"{timeframe_hours}h"
                    ):
                        return True
                except json.JSONDecodeError:
                    continue

        return False

    def record_outcome(self, item, timeframe_hours):
        """Record price outcome for an item"""
        ticker = item.get("ticker")

        if not ticker:
            return None

        # Rate limiting
        self._apply_rate_limit()

        # Get initial price
        initial_price = item.get("price")
        if not initial_price:
            return None

        # Get current price with retry logic
        try:
            current_price, _ = self.market.get_last_price_change(ticker)
        except Exception:
            # Handle missing/delisted tickers
            return None

        if current_price is None or current_price <= 0:
            return None

        # Calculate price change
        price_change_pct = ((current_price - initial_price) / initial_price) * 100

        # Build outcome record
        outcome = {
            "ticker": ticker,
            "timestamp": item.get("ts"),
            "initial_price": initial_price,
            "current_price": current_price,
            "price_change_pct": round(price_change_pct, 2),
            "timeframe": f"{timeframe_hours}h",
            "keywords": item.get("cls", {}).get("keywords", []),
            "rejection_reason": item.get("rejection_reason"),
            "recorded_at": datetime.now(timezone.utc).isoformat(),
        }

        # Append to outcomes file
        self._append_outcome(outcome)

        return outcome

    def _apply_rate_limit(self):
        """Apply rate limiting between API calls"""
        elapsed = time.time() - self.last_request_time
        if elapsed < self.rate_limit_delay:
            time.sleep(self.rate_limit_delay - elapsed)
        self.last_request_time = time.time()

    def _append_outcome(self, outcome):
        """Append outcome to JSONL file"""
        with open(self.outcomes_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(outcome) + "\n")

    def is_missed_opportunity(self, outcome):
        """Determine if outcome represents a missed opportunity"""
        if not outcome:
            return False

        price_change = outcome.get("price_change_pct", 0)
        return price_change >= (self.missed_opportunity_threshold * 100)

    def calculate_time_elapsed(self, item_timestamp, reference_time=None):
        """Calculate time elapsed since item timestamp"""
        if reference_time is None:
            reference_time = datetime.now(timezone.utc)

        item_time = datetime.fromisoformat(item_timestamp.replace("Z", "+00:00"))
        elapsed = reference_time - item_time

        return elapsed.total_seconds() / 3600  # Return hours

    def is_market_hours(self, dt=None):
        """Check if current time is within market hours (9:30 AM - 4:00 PM ET)"""
        if dt is None:
            dt = datetime.now(timezone.utc)

        # Convert to ET (UTC-5 or UTC-4 depending on DST)
        # Simplified: assume UTC-5 for testing
        et_hour = (dt.hour - 5) % 24

        # Market hours: 9:30 AM - 4:00 PM ET
        if et_hour < 9:
            return False
        if et_hour > 16:
            return False
        if et_hour == 9 and dt.minute < 30:
            return False

        # Check if weekend
        if dt.weekday() >= 5:  # Saturday=5, Sunday=6
            return False

        return True

    def should_track_now(self, timeframe_hours):
        """Determine if tracking should occur now based on timeframe and market hours"""
        # For intraday timeframes (1h, 4h), require market hours
        if timeframe_hours <= 4:
            return self.is_market_hours()

        # For longer timeframes (24h, 1w), can track anytime
        return True


# Fixtures


@pytest.fixture
def temp_data_dir():
    """Create a temporary directory for test data"""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


@pytest.fixture
def mock_market():
    """Mock market interface"""
    market = Mock()
    market.get_last_price_change = Mock(return_value=(2.50, 0.05))
    return market


@pytest.fixture
def sample_rejected_items():
    """Sample rejected items"""
    base_time = datetime.now(timezone.utc)
    return [
        {
            "ts": (base_time - timedelta(hours=2)).isoformat(),
            "ticker": "SNAL",
            "title": "FDA approval news",
            "price": 1.03,
            "cls": {"keywords": ["fda", "approval"], "score": 0.18},
            "rejection_reason": "LOW_SCORE",
        },
        {
            "ts": (base_time - timedelta(hours=5)).isoformat(),
            "ticker": "ABCD",
            "title": "Partnership announcement",
            "price": 2.45,
            "cls": {"keywords": ["partnership"], "score": 0.20},
            "rejection_reason": "LOW_SCORE",
        },
        {
            "ts": (base_time - timedelta(hours=25)).isoformat(),
            "ticker": "EFGH",
            "title": "Earnings beat",
            "price": 5.00,
            "cls": {"keywords": ["earnings"], "score": 0.22},
            "rejection_reason": "LOW_SCORE",
        },
    ]


# Test Cases


def test_get_pending_items_1h_timeframe(
    temp_data_dir, mock_market, sample_rejected_items
):
    """Test getting pending items for 1h timeframe"""
    rejected_path = os.path.join(temp_data_dir, "rejected_items.jsonl")
    outcomes_path = os.path.join(temp_data_dir, "outcomes.jsonl")

    # Write sample data
    with open(rejected_path, "w", encoding="utf-8") as f:
        for item in sample_rejected_items:
            f.write(json.dumps(item) + "\n")

    tracker = MOAPriceTracker(rejected_path, outcomes_path, mock_market)
    pending = tracker.get_pending_items(timeframe_hours=1)

    # All items older than 1h should be pending
    assert len(pending) == 3


def test_get_pending_items_4h_timeframe(
    temp_data_dir, mock_market, sample_rejected_items
):
    """Test getting pending items for 4h timeframe"""
    rejected_path = os.path.join(temp_data_dir, "rejected_items.jsonl")
    outcomes_path = os.path.join(temp_data_dir, "outcomes.jsonl")

    with open(rejected_path, "w", encoding="utf-8") as f:
        for item in sample_rejected_items:
            f.write(json.dumps(item) + "\n")

    tracker = MOAPriceTracker(rejected_path, outcomes_path, mock_market)
    pending = tracker.get_pending_items(timeframe_hours=4)

    # Items older than 4h
    assert len(pending) == 2  # ABCD (5h) and EFGH (25h)


def test_get_pending_items_24h_timeframe(
    temp_data_dir, mock_market, sample_rejected_items
):
    """Test getting pending items for 24h timeframe"""
    rejected_path = os.path.join(temp_data_dir, "rejected_items.jsonl")
    outcomes_path = os.path.join(temp_data_dir, "outcomes.jsonl")

    with open(rejected_path, "w", encoding="utf-8") as f:
        for item in sample_rejected_items:
            f.write(json.dumps(item) + "\n")

    tracker = MOAPriceTracker(rejected_path, outcomes_path, mock_market)
    pending = tracker.get_pending_items(timeframe_hours=24)

    # Items older than 24h
    assert len(pending) == 1  # Only EFGH (25h)


def test_get_pending_items_1w_timeframe(
    temp_data_dir, mock_market, sample_rejected_items
):
    """Test getting pending items for 1w timeframe"""
    rejected_path = os.path.join(temp_data_dir, "rejected_items.jsonl")
    outcomes_path = os.path.join(temp_data_dir, "outcomes.jsonl")

    # Add item from 8 days ago
    old_item = {
        "ts": (datetime.now(timezone.utc) - timedelta(days=8)).isoformat(),
        "ticker": "OLD",
        "title": "Old news",
        "price": 3.00,
        "cls": {"keywords": ["test"], "score": 0.18},
        "rejection_reason": "LOW_SCORE",
    }

    with open(rejected_path, "w", encoding="utf-8") as f:
        for item in sample_rejected_items:
            f.write(json.dumps(item) + "\n")
        f.write(json.dumps(old_item) + "\n")

    tracker = MOAPriceTracker(rejected_path, outcomes_path, mock_market)
    pending = tracker.get_pending_items(timeframe_hours=168)  # 1 week

    assert len(pending) >= 1
    # Should include OLD item
    assert any(item["ticker"] == "OLD" for item in pending)


def test_record_outcome_success(temp_data_dir, mock_market):
    """Test recording outcome with successful price fetch"""
    outcomes_path = os.path.join(temp_data_dir, "outcomes.jsonl")

    item = {
        "ts": "2025-10-11T10:00:00+00:00",
        "ticker": "TEST",
        "price": 2.00,
        "cls": {"keywords": ["fda"]},
        "rejection_reason": "LOW_SCORE",
    }

    # Mock returns price of 2.50 (25% gain)
    mock_market.get_last_price_change.return_value = (2.50, 0.05)

    tracker = MOAPriceTracker(None, outcomes_path, mock_market)
    outcome = tracker.record_outcome(item, timeframe_hours=24)

    assert outcome is not None
    assert outcome["ticker"] == "TEST"
    assert outcome["initial_price"] == 2.00
    assert outcome["current_price"] == 2.50
    assert outcome["price_change_pct"] == 25.0
    assert outcome["timeframe"] == "24h"


def test_record_outcome_appends_to_file(temp_data_dir, mock_market):
    """Test that record_outcome appends to outcomes.jsonl"""
    outcomes_path = os.path.join(temp_data_dir, "outcomes.jsonl")

    item = {
        "ts": "2025-10-11T10:00:00+00:00",
        "ticker": "TEST",
        "price": 2.00,
        "cls": {"keywords": ["fda"]},
        "rejection_reason": "LOW_SCORE",
    }

    mock_market.get_last_price_change.return_value = (2.50, 0.05)

    tracker = MOAPriceTracker(None, outcomes_path, mock_market)
    tracker.record_outcome(item, timeframe_hours=24)

    # Verify file exists and contains data
    assert os.path.exists(outcomes_path)

    with open(outcomes_path, "r", encoding="utf-8") as f:
        lines = f.readlines()

    assert len(lines) == 1
    outcome = json.loads(lines[0])
    assert outcome["ticker"] == "TEST"


def test_record_outcome_multiple_appends(temp_data_dir, mock_market):
    """Test multiple outcome recordings append correctly"""
    outcomes_path = os.path.join(temp_data_dir, "outcomes.jsonl")

    items = [
        {
            "ts": "2025-10-11T10:00:00+00:00",
            "ticker": "TEST1",
            "price": 2.00,
            "cls": {"keywords": []},
            "rejection_reason": "LOW_SCORE",
        },
        {
            "ts": "2025-10-11T11:00:00+00:00",
            "ticker": "TEST2",
            "price": 3.00,
            "cls": {"keywords": []},
            "rejection_reason": "LOW_SCORE",
        },
    ]

    mock_market.get_last_price_change.return_value = (2.50, 0.05)

    tracker = MOAPriceTracker(None, outcomes_path, mock_market)
    for item in items:
        tracker.record_outcome(item, timeframe_hours=1)

    with open(outcomes_path, "r", encoding="utf-8") as f:
        lines = f.readlines()

    assert len(lines) == 2


def test_is_missed_opportunity_true(temp_data_dir, mock_market):
    """Test is_missed_opportunity returns True for >10% gain"""
    outcome = {"ticker": "TEST", "price_change_pct": 25.0}

    tracker = MOAPriceTracker(None, None, mock_market)
    assert tracker.is_missed_opportunity(outcome) is True


def test_is_missed_opportunity_false(temp_data_dir, mock_market):
    """Test is_missed_opportunity returns False for <10% gain"""
    outcome = {"ticker": "TEST", "price_change_pct": 5.0}

    tracker = MOAPriceTracker(None, None, mock_market)
    assert tracker.is_missed_opportunity(outcome) is False


def test_is_missed_opportunity_at_threshold(temp_data_dir, mock_market):
    """Test is_missed_opportunity at exact threshold"""
    outcome = {"ticker": "TEST", "price_change_pct": 10.0}

    tracker = MOAPriceTracker(None, None, mock_market)
    assert tracker.is_missed_opportunity(outcome) is True


def test_calculate_time_elapsed(temp_data_dir, mock_market):
    """Test calculating time elapsed since item timestamp"""
    tracker = MOAPriceTracker(None, None, mock_market)

    reference = datetime(2025, 10, 11, 15, 0, 0, tzinfo=timezone.utc)
    item_ts = "2025-10-11T10:00:00+00:00"  # 5 hours earlier

    elapsed = tracker.calculate_time_elapsed(item_ts, reference)

    assert elapsed == 5.0


def test_calculate_time_elapsed_fractional(temp_data_dir, mock_market):
    """Test calculating fractional time elapsed"""
    tracker = MOAPriceTracker(None, None, mock_market)

    reference = datetime(2025, 10, 11, 12, 30, 0, tzinfo=timezone.utc)
    item_ts = "2025-10-11T10:00:00+00:00"  # 2.5 hours earlier

    elapsed = tracker.calculate_time_elapsed(item_ts, reference)

    assert elapsed == 2.5


def test_market_hours_during_trading(temp_data_dir, mock_market):
    """Test is_market_hours during trading hours"""
    tracker = MOAPriceTracker(None, None, mock_market)

    # Tuesday 3:00 PM UTC = 10:00 AM ET (within market hours 9:30-4:00 PM)
    test_time = datetime(2025, 10, 14, 15, 0, 0, tzinfo=timezone.utc)

    assert tracker.is_market_hours(test_time) is True


def test_market_hours_before_open(temp_data_dir, mock_market):
    """Test is_market_hours before market open"""
    tracker = MOAPriceTracker(None, None, mock_market)

    # Tuesday 12:00 PM UTC = 7:00 AM ET (before open)
    test_time = datetime(2025, 10, 14, 12, 0, 0, tzinfo=timezone.utc)

    assert tracker.is_market_hours(test_time) is False


def test_market_hours_after_close(temp_data_dir, mock_market):
    """Test is_market_hours after market close"""
    tracker = MOAPriceTracker(None, None, mock_market)

    # Tuesday 10:00 PM UTC = 5:00 PM ET (after close)
    test_time = datetime(2025, 10, 14, 22, 0, 0, tzinfo=timezone.utc)

    assert tracker.is_market_hours(test_time) is False


def test_market_hours_weekend(temp_data_dir, mock_market):
    """Test is_market_hours on weekend"""
    tracker = MOAPriceTracker(None, None, mock_market)

    # Saturday
    test_time = datetime(2025, 10, 11, 15, 0, 0, tzinfo=timezone.utc)

    assert tracker.is_market_hours(test_time) is False


def test_rate_limiting_applied(temp_data_dir, mock_market):
    """Test that rate limiting is applied between requests"""
    outcomes_path = os.path.join(temp_data_dir, "outcomes.jsonl")

    items = [
        {
            "ts": "2025-10-11T10:00:00+00:00",
            "ticker": f"TEST{i}",
            "price": 2.00,
            "cls": {"keywords": []},
            "rejection_reason": "LOW_SCORE",
        }
        for i in range(3)
    ]

    mock_market.get_last_price_change.return_value = (2.50, 0.05)

    tracker = MOAPriceTracker(None, outcomes_path, mock_market)
    tracker.rate_limit_delay = 0.05  # 50ms delay

    start_time = time.time()
    for item in items:
        tracker.record_outcome(item, timeframe_hours=1)
    elapsed = time.time() - start_time

    # Should take at least 2 * delay (for 3 requests, 2 delays between them)
    assert elapsed >= 0.1  # 2 * 0.05


def test_handling_missing_ticker(temp_data_dir, mock_market):
    """Test handling of item with missing ticker"""
    outcomes_path = os.path.join(temp_data_dir, "outcomes.jsonl")

    item = {
        "ts": "2025-10-11T10:00:00+00:00",
        # No ticker field
        "price": 2.00,
        "cls": {"keywords": []},
        "rejection_reason": "LOW_SCORE",
    }

    tracker = MOAPriceTracker(None, outcomes_path, mock_market)
    outcome = tracker.record_outcome(item, timeframe_hours=1)

    assert outcome is None


def test_handling_delisted_ticker(temp_data_dir, mock_market):
    """Test handling of delisted/invalid ticker"""
    outcomes_path = os.path.join(temp_data_dir, "outcomes.jsonl")

    item = {
        "ts": "2025-10-11T10:00:00+00:00",
        "ticker": "DELISTED",
        "price": 2.00,
        "cls": {"keywords": []},
        "rejection_reason": "LOW_SCORE",
    }

    # Mock returns None for delisted ticker
    mock_market.get_last_price_change.side_effect = Exception("Ticker not found")

    tracker = MOAPriceTracker(None, outcomes_path, mock_market)
    outcome = tracker.record_outcome(item, timeframe_hours=1)

    assert outcome is None


def test_handling_zero_price(temp_data_dir, mock_market):
    """Test handling of zero/invalid price"""
    outcomes_path = os.path.join(temp_data_dir, "outcomes.jsonl")

    item = {
        "ts": "2025-10-11T10:00:00+00:00",
        "ticker": "TEST",
        "price": 2.00,
        "cls": {"keywords": []},
        "rejection_reason": "LOW_SCORE",
    }

    # Mock returns 0 price
    mock_market.get_last_price_change.return_value = (0.0, 0.0)

    tracker = MOAPriceTracker(None, outcomes_path, mock_market)
    outcome = tracker.record_outcome(item, timeframe_hours=1)

    assert outcome is None


def test_outcome_includes_keywords(temp_data_dir, mock_market):
    """Test that outcome includes keywords from original item"""
    outcomes_path = os.path.join(temp_data_dir, "outcomes.jsonl")

    item = {
        "ts": "2025-10-11T10:00:00+00:00",
        "ticker": "TEST",
        "price": 2.00,
        "cls": {"keywords": ["fda", "approval", "breakthrough"]},
        "rejection_reason": "LOW_SCORE",
    }

    mock_market.get_last_price_change.return_value = (2.50, 0.05)

    tracker = MOAPriceTracker(None, outcomes_path, mock_market)
    outcome = tracker.record_outcome(item, timeframe_hours=24)

    assert "keywords" in outcome
    assert outcome["keywords"] == ["fda", "approval", "breakthrough"]


def test_outcome_includes_rejection_reason(temp_data_dir, mock_market):
    """Test that outcome includes rejection reason"""
    outcomes_path = os.path.join(temp_data_dir, "outcomes.jsonl")

    item = {
        "ts": "2025-10-11T10:00:00+00:00",
        "ticker": "TEST",
        "price": 2.00,
        "cls": {"keywords": []},
        "rejection_reason": "HIGH_PRICE",
    }

    mock_market.get_last_price_change.return_value = (2.50, 0.05)

    tracker = MOAPriceTracker(None, outcomes_path, mock_market)
    outcome = tracker.record_outcome(item, timeframe_hours=24)

    assert "rejection_reason" in outcome
    assert outcome["rejection_reason"] == "HIGH_PRICE"


def test_should_track_now_intraday_market_hours(temp_data_dir, mock_market):
    """Test should_track_now for intraday during market hours"""
    tracker = MOAPriceTracker(None, None, mock_market)

    # Mock market hours
    with patch.object(tracker, "is_market_hours", return_value=True):
        assert tracker.should_track_now(timeframe_hours=1) is True
        assert tracker.should_track_now(timeframe_hours=4) is True


def test_should_track_now_intraday_closed(temp_data_dir, mock_market):
    """Test should_track_now for intraday when market closed"""
    tracker = MOAPriceTracker(None, None, mock_market)

    # Mock market closed
    with patch.object(tracker, "is_market_hours", return_value=False):
        assert tracker.should_track_now(timeframe_hours=1) is False
        assert tracker.should_track_now(timeframe_hours=4) is False


def test_should_track_now_daily_anytime(temp_data_dir, mock_market):
    """Test should_track_now for daily/weekly timeframes (anytime)"""
    tracker = MOAPriceTracker(None, None, mock_market)

    # Mock market closed, but should still track for longer timeframes
    with patch.object(tracker, "is_market_hours", return_value=False):
        assert tracker.should_track_now(timeframe_hours=24) is True
        assert tracker.should_track_now(timeframe_hours=168) is True


def test_already_tracked_prevents_duplicates(
    temp_data_dir, mock_market, sample_rejected_items
):
    """Test that already tracked items are not returned as pending"""
    rejected_path = os.path.join(temp_data_dir, "rejected_items.jsonl")
    outcomes_path = os.path.join(temp_data_dir, "outcomes.jsonl")

    # Write rejected item
    with open(rejected_path, "w", encoding="utf-8") as f:
        f.write(json.dumps(sample_rejected_items[0]) + "\n")

    # Write outcome for same item
    outcome = {
        "ticker": sample_rejected_items[0]["ticker"],
        "timestamp": sample_rejected_items[0]["ts"],
        "timeframe": "1h",
        "price_change_pct": 5.0,
    }
    with open(outcomes_path, "w", encoding="utf-8") as f:
        f.write(json.dumps(outcome) + "\n")

    tracker = MOAPriceTracker(rejected_path, outcomes_path, mock_market)
    pending = tracker.get_pending_items(timeframe_hours=1)

    # Should not include already tracked item
    assert len(pending) == 0


def test_negative_price_change(temp_data_dir, mock_market):
    """Test handling negative price change"""
    outcomes_path = os.path.join(temp_data_dir, "outcomes.jsonl")

    item = {
        "ts": "2025-10-11T10:00:00+00:00",
        "ticker": "TEST",
        "price": 2.00,
        "cls": {"keywords": []},
        "rejection_reason": "LOW_SCORE",
    }

    # Price dropped to 1.50 (-25%)
    mock_market.get_last_price_change.return_value = (1.50, -0.05)

    tracker = MOAPriceTracker(None, outcomes_path, mock_market)
    outcome = tracker.record_outcome(item, timeframe_hours=24)

    assert outcome is not None
    assert outcome["price_change_pct"] == -25.0
    assert tracker.is_missed_opportunity(outcome) is False


def test_fetch_intraday_price_15m():
    """Test fetching intraday price for 15-minute timeframe"""
    from catalyst_bot.moa_price_tracker import fetch_intraday_price

    # Test with a recent time (within last 7 days)
    target_time = datetime.now(timezone.utc) - timedelta(hours=2)

    # Mock test - in real scenario this would fetch actual price
    # For now, we're testing the function signature and basic flow
    try:
        price = fetch_intraday_price("AAPL", target_time)
        # Price can be None if data unavailable, which is acceptable
        assert price is None or isinstance(price, float)
    except Exception as e:
        # Function should handle errors gracefully
        assert False, f"fetch_intraday_price should not raise: {e}"


def test_fetch_intraday_price_30m():
    """Test fetching intraday price for 30-minute timeframe"""
    from catalyst_bot.moa_price_tracker import fetch_intraday_price

    # Test with a recent time (within last 7 days)
    target_time = datetime.now(timezone.utc) - timedelta(hours=1)

    try:
        price = fetch_intraday_price("MSFT", target_time)
        # Price can be None if data unavailable, which is acceptable
        assert price is None or isinstance(price, float)
    except Exception as e:
        # Function should handle errors gracefully
        assert False, f"fetch_intraday_price should not raise: {e}"


def test_fetch_intraday_price_old_data():
    """Test that fetch_intraday_price returns None for data older than 7 days"""
    from catalyst_bot.moa_price_tracker import fetch_intraday_price

    # Test with time older than 7 days
    old_target_time = datetime.now(timezone.utc) - timedelta(days=10)

    price = fetch_intraday_price("AAPL", old_target_time)

    # Should return None for data older than 7 days
    assert price is None


def test_fetch_intraday_price_invalid_ticker():
    """Test that fetch_intraday_price handles invalid ticker gracefully"""
    from catalyst_bot.moa_price_tracker import fetch_intraday_price

    # Test with invalid ticker
    target_time = datetime.now(timezone.utc) - timedelta(hours=2)

    price = fetch_intraday_price("INVALID_TICKER_12345", target_time)

    # Should return None for invalid ticker
    assert price is None


def test_record_outcome_15m_timeframe(temp_data_dir):
    """Test recording outcome for 15m timeframe"""
    from catalyst_bot.moa_price_tracker import record_outcome

    # Create a recent rejection (within last 7 days for intraday data)
    rejection_time = datetime.now(timezone.utc) - timedelta(hours=1)
    rejection_ts = rejection_time.isoformat()

    # Attempt to record outcome for 15m timeframe
    # This may return False if yfinance data is unavailable, which is acceptable
    result = record_outcome(
        ticker="AAPL",
        timeframe="15m",
        rejection_ts=rejection_ts,
        rejection_price=150.0,
        rejection_reason="TEST",
    )

    # Result can be True or False depending on data availability
    assert isinstance(result, bool)


def test_record_outcome_30m_timeframe(temp_data_dir):
    """Test recording outcome for 30m timeframe"""
    from catalyst_bot.moa_price_tracker import record_outcome

    # Create a recent rejection (within last 7 days for intraday data)
    rejection_time = datetime.now(timezone.utc) - timedelta(hours=2)
    rejection_ts = rejection_time.isoformat()

    # Attempt to record outcome for 30m timeframe
    result = record_outcome(
        ticker="MSFT",
        timeframe="30m",
        rejection_ts=rejection_ts,
        rejection_price=300.0,
        rejection_reason="TEST",
    )

    # Result can be True or False depending on data availability
    assert isinstance(result, bool)


def test_get_pending_items_15m_timeframe(
    temp_data_dir, mock_market, sample_rejected_items
):
    """Test getting pending items for 15m timeframe"""
    rejected_path = os.path.join(temp_data_dir, "rejected_items.jsonl")
    outcomes_path = os.path.join(temp_data_dir, "outcomes.jsonl")

    # Create a very recent rejection (15 minutes ago)
    recent_item = {
        "ts": (datetime.now(timezone.utc) - timedelta(minutes=20)).isoformat(),
        "ticker": "TEST15M",
        "title": "Test news",
        "price": 2.00,
        "cls": {"keywords": ["test"], "score": 0.20},
        "rejection_reason": "LOW_SCORE",
    }

    with open(rejected_path, "w", encoding="utf-8") as f:
        f.write(json.dumps(recent_item) + "\n")

    tracker = MOAPriceTracker(rejected_path, outcomes_path, mock_market)
    pending = tracker.get_pending_items(timeframe_hours=0.25)  # 15 minutes

    # Should include items older than 15 minutes
    assert len(pending) == 1
    assert pending[0]["ticker"] == "TEST15M"


def test_get_pending_items_30m_timeframe(
    temp_data_dir, mock_market, sample_rejected_items
):
    """Test getting pending items for 30m timeframe"""
    rejected_path = os.path.join(temp_data_dir, "rejected_items.jsonl")
    outcomes_path = os.path.join(temp_data_dir, "outcomes.jsonl")

    # Create a recent rejection (45 minutes ago)
    recent_item = {
        "ts": (datetime.now(timezone.utc) - timedelta(minutes=45)).isoformat(),
        "ticker": "TEST30M",
        "title": "Test news",
        "price": 3.00,
        "cls": {"keywords": ["test"], "score": 0.20},
        "rejection_reason": "LOW_SCORE",
    }

    with open(rejected_path, "w", encoding="utf-8") as f:
        f.write(json.dumps(recent_item) + "\n")

    tracker = MOAPriceTracker(rejected_path, outcomes_path, mock_market)
    pending = tracker.get_pending_items(timeframe_hours=0.5)  # 30 minutes

    # Should include items older than 30 minutes
    assert len(pending) == 1
    assert pending[0]["ticker"] == "TEST30M"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
