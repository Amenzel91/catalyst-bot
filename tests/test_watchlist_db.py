"""
Tests for watchlist_db module (Phase 1)
"""

import os
import sqlite3
import tempfile
from pathlib import Path

import pytest

# Set test environment variable before importing
os.environ["WATCHLIST_PERFORMANCE_DB_PATH"] = str(
    Path(tempfile.gettempdir()) / "test_watchlist_performance.db"
)

from catalyst_bot import watchlist_db


@pytest.fixture
def test_db():
    """Create a temporary test database."""
    # Create test database
    watchlist_db.init_database()
    yield
    # Cleanup
    db_path = watchlist_db._get_db_path()
    if db_path.exists():
        os.remove(db_path)


def test_init_database():
    """Test database initialization."""
    watchlist_db.init_database()
    db_path = watchlist_db._get_db_path()

    assert db_path.exists(), "Database file should be created"

    # Check that tables exist
    conn = watchlist_db._get_connection()
    try:
        cursor = conn.cursor()

        # Check watchlist_tickers table
        cursor.execute("""
            SELECT name FROM sqlite_master
            WHERE type='table' AND name='watchlist_tickers'
        """)
        assert cursor.fetchone() is not None, "watchlist_tickers table should exist"

        # Check performance_snapshots table
        cursor.execute("""
            SELECT name FROM sqlite_master
            WHERE type='table' AND name='performance_snapshots'
        """)
        assert cursor.fetchone() is not None, "performance_snapshots table should exist"

        # Check schema_version table
        cursor.execute("""
            SELECT name FROM sqlite_master
            WHERE type='table' AND name='schema_version'
        """)
        assert cursor.fetchone() is not None, "schema_version table should exist"

    finally:
        conn.close()

    # Cleanup
    os.remove(db_path)


def test_add_ticker_basic(test_db):
    """Test adding a ticker with basic info."""
    success = watchlist_db.add_ticker(
        ticker="AAPL",
        state="HOT",
        trigger_reason="Test catalyst",
        trigger_price=150.50,
    )

    assert success, "add_ticker should succeed"

    # Verify ticker was added
    hot_tickers = watchlist_db.get_tickers_by_state("HOT")
    assert len(hot_tickers) == 1, "Should have 1 HOT ticker"
    assert hot_tickers[0]["ticker"] == "AAPL", "Ticker should be AAPL"
    assert hot_tickers[0]["state"] == "HOT", "State should be HOT"
    assert hot_tickers[0]["trigger_price"] == 150.50, "Price should match"


def test_add_ticker_full_context(test_db):
    """Test adding a ticker with full context."""
    success = watchlist_db.add_ticker(
        ticker="TSLA",
        state="HOT",
        trigger_reason="FDA approval catalyst",
        trigger_title="TSLA gets FDA approval",
        trigger_summary="Tesla receives FDA approval for new drug",
        catalyst_type="fda_approval",
        trigger_score=0.85,
        trigger_sentiment=0.7,
        trigger_price=250.00,
        trigger_volume=5000000,
        alert_id="alert_123",
        tags=["biotech", "fda"],
        metadata={"source": "pr_newswire"},
    )

    assert success, "add_ticker with full context should succeed"

    # Verify all fields
    hot_tickers = watchlist_db.get_tickers_by_state("HOT")
    ticker = hot_tickers[0]

    assert ticker["ticker"] == "TSLA"
    assert ticker["catalyst_type"] == "fda_approval"
    assert ticker["trigger_score"] == 0.85
    assert ticker["trigger_sentiment"] == 0.7
    assert ticker["trigger_price"] == 250.00
    assert ticker["trigger_volume"] == 5000000
    assert ticker["alert_id"] == "alert_123"


def test_record_snapshot(test_db):
    """Test recording performance snapshots."""
    # Add ticker first
    watchlist_db.add_ticker("AAPL", state="HOT", trigger_price=150.00)

    # Record snapshot
    success = watchlist_db.record_snapshot(
        ticker="AAPL",
        price=155.50,
        volume=2000000,
        rvol=1.5,
        vwap=155.00,
        price_change_pct=3.67,
    )

    assert success, "record_snapshot should succeed"

    # Verify snapshot was recorded
    snapshots = watchlist_db.get_snapshots("AAPL", limit=1)
    assert len(snapshots) == 1, "Should have 1 snapshot"

    snapshot = snapshots[0]
    assert snapshot["ticker"] == "AAPL"
    assert snapshot["price"] == 155.50
    assert snapshot["volume"] == 2000000
    assert snapshot["rvol"] == 1.5
    assert snapshot["vwap"] == 155.00
    assert snapshot["price_change_pct"] == 3.67


def test_get_tickers_by_state(test_db):
    """Test getting tickers by state."""
    # Add tickers in different states
    watchlist_db.add_ticker("AAPL", state="HOT")
    watchlist_db.add_ticker("TSLA", state="HOT")
    watchlist_db.add_ticker("MSFT", state="WARM")
    watchlist_db.add_ticker("GOOGL", state="COOL")

    # Test HOT
    hot = watchlist_db.get_tickers_by_state("HOT")
    assert len(hot) == 2, "Should have 2 HOT tickers"
    hot_tickers = [t["ticker"] for t in hot]
    assert "AAPL" in hot_tickers
    assert "TSLA" in hot_tickers

    # Test WARM
    warm = watchlist_db.get_tickers_by_state("WARM")
    assert len(warm) == 1, "Should have 1 WARM ticker"
    assert warm[0]["ticker"] == "MSFT"

    # Test COOL
    cool = watchlist_db.get_tickers_by_state("COOL")
    assert len(cool) == 1, "Should have 1 COOL ticker"
    assert cool[0]["ticker"] == "GOOGL"


def test_get_tickers_needing_check(test_db):
    """Test getting tickers that need checking."""
    import time

    # Add ticker with check interval of 1 second (for testing)
    watchlist_db.add_ticker(
        "AAPL",
        state="HOT",
        check_interval_seconds=1,
    )

    # Wait 2 seconds so ticker needs check
    time.sleep(2)

    # Get tickers needing check
    needing_check = watchlist_db.get_tickers_needing_check()
    assert len(needing_check) == 1, "Should have 1 ticker needing check"
    assert needing_check[0]["ticker"] == "AAPL"


def test_update_next_check_time(test_db):
    """Test updating next check time."""
    # Add ticker
    watchlist_db.add_ticker("AAPL", state="HOT")

    # Update next check time
    success = watchlist_db.update_next_check_time("AAPL", interval_seconds=3600)
    assert success, "update_next_check_time should succeed"

    # Verify it's not needing check immediately
    needing_check = watchlist_db.get_tickers_needing_check()
    assert len(needing_check) == 0, "Should have no tickers needing check"


def test_get_state_counts(test_db):
    """Test getting state counts."""
    # Add tickers in different states
    watchlist_db.add_ticker("AAPL", state="HOT")
    watchlist_db.add_ticker("TSLA", state="HOT")
    watchlist_db.add_ticker("MSFT", state="WARM")
    watchlist_db.add_ticker("GOOGL", state="COOL")
    watchlist_db.add_ticker("NVDA", state="COOL")

    # Get counts
    counts = watchlist_db.get_state_counts()
    assert counts["HOT"] == 2, "Should have 2 HOT tickers"
    assert counts["WARM"] == 1, "Should have 1 WARM ticker"
    assert counts["COOL"] == 2, "Should have 2 COOL tickers"


def test_remove_ticker_soft_delete(test_db):
    """Test soft deleting a ticker."""
    # Add ticker
    watchlist_db.add_ticker("AAPL", state="HOT")

    # Soft delete
    success = watchlist_db.remove_ticker("AAPL", soft_delete=True)
    assert success, "remove_ticker should succeed"

    # Verify ticker is not in active list
    hot = watchlist_db.get_tickers_by_state("HOT")
    assert len(hot) == 0, "Should have no HOT tickers"

    # Verify ticker still exists with removed_at set
    hot_removed = watchlist_db.get_tickers_by_state("HOT", include_removed=True)
    assert len(hot_removed) == 1, "Should have 1 removed ticker"
    assert hot_removed[0]["removed_at"] is not None, "removed_at should be set"


def test_remove_ticker_hard_delete(test_db):
    """Test hard deleting a ticker."""
    # Add ticker with snapshot
    watchlist_db.add_ticker("AAPL", state="HOT", trigger_price=150.00)
    watchlist_db.record_snapshot("AAPL", price=155.00)

    # Verify snapshot exists
    snapshots = watchlist_db.get_snapshots("AAPL")
    assert len(snapshots) == 1, "Should have 1 snapshot"

    # Hard delete
    success = watchlist_db.remove_ticker("AAPL", soft_delete=False)
    assert success, "remove_ticker should succeed"

    # Verify ticker is completely removed
    hot = watchlist_db.get_tickers_by_state("HOT", include_removed=True)
    assert len(hot) == 0, "Should have no tickers"

    # Verify snapshots are cascade deleted
    snapshots = watchlist_db.get_snapshots("AAPL")
    assert len(snapshots) == 0, "Snapshots should be cascade deleted"


def test_multiple_snapshots(test_db):
    """Test recording multiple snapshots for a ticker."""
    import time

    # Add ticker
    watchlist_db.add_ticker("AAPL", state="HOT", trigger_price=150.00)

    # Record multiple snapshots
    for i in range(5):
        watchlist_db.record_snapshot(
            ticker="AAPL",
            price=150.00 + i,
            volume=1000000 * (i + 1),
        )
        time.sleep(0.1)  # Small delay to ensure different timestamps

    # Get all snapshots
    snapshots = watchlist_db.get_snapshots("AAPL")
    assert len(snapshots) == 5, "Should have 5 snapshots"

    # Verify snapshots are ordered by time DESC (newest first)
    prices = [s["price"] for s in snapshots]
    assert prices == [154.00, 153.00, 152.00, 151.00, 150.00], \
        "Snapshots should be ordered newest first"

    # Test limit
    limited = watchlist_db.get_snapshots("AAPL", limit=2)
    assert len(limited) == 2, "Should have 2 snapshots with limit"
    assert limited[0]["price"] == 154.00, "Should get newest snapshot first"


def test_ticker_uppercase_normalization(test_db):
    """Test that ticker symbols are normalized to uppercase."""
    # Add ticker with lowercase
    watchlist_db.add_ticker("aapl", state="HOT")

    # Verify it's stored as uppercase
    hot = watchlist_db.get_tickers_by_state("HOT")
    assert len(hot) == 1
    assert hot[0]["ticker"] == "AAPL", "Ticker should be uppercase"

    # Verify snapshot with lowercase ticker works
    watchlist_db.record_snapshot("aapl", price=150.00)
    snapshots = watchlist_db.get_snapshots("AAPL")
    assert len(snapshots) == 1


def test_invalid_state(test_db):
    """Test that invalid states are rejected."""
    # Try to add ticker with invalid state
    success = watchlist_db.add_ticker("AAPL", state="INVALID")
    assert not success, "Should reject invalid state"

    # Verify ticker was not added
    all_hot = watchlist_db.get_tickers_by_state("HOT")
    assert len(all_hot) == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
