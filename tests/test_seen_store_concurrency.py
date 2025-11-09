"""
Tests for SeenStore thread safety and concurrency.

Week 1 Critical Fixes: Verifies that threading locks prevent race conditions
and database corruption under concurrent access.
"""

import pytest
import threading
import time
from pathlib import Path
import tempfile
import shutil
from catalyst_bot.seen_store import SeenStore, SeenStoreConfig


@pytest.fixture
def temp_db_path():
    """Create a temporary directory for test databases."""
    temp_dir = tempfile.mkdtemp()
    db_path = Path(temp_dir) / "test_seen_store.db"
    yield db_path
    # Cleanup
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture
def seen_store(temp_db_path):
    """Create a SeenStore instance with a temporary database."""
    config = SeenStoreConfig(path=temp_db_path, ttl_days=7)
    store = SeenStore(config=config)
    yield store
    store.close()


def test_concurrent_is_seen_calls(seen_store):
    """Test 100 concurrent is_seen() calls don't cause race conditions."""
    # Pre-populate
    test_id = "concurrent_test_item"
    seen_store.mark_seen(test_id)

    results = []
    errors = []

    def check_seen():
        try:
            results.append(seen_store.is_seen(test_id))
        except Exception as e:
            errors.append(e)

    # Launch 100 concurrent threads
    threads = [threading.Thread(target=check_seen) for _ in range(100)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=5.0)

    assert len(errors) == 0, f"Errors occurred: {errors}"
    assert all(results), "All threads should see the item"
    assert len(results) == 100, "All threads should complete"


def test_concurrent_mark_seen_calls(seen_store):
    """Test 100 concurrent mark_seen() calls don't corrupt database."""
    errors = []

    def mark_item(item_id):
        try:
            seen_store.mark_seen(item_id)
        except Exception as e:
            errors.append(e)

    # Launch 100 concurrent threads with unique IDs
    threads = [threading.Thread(target=mark_item, args=(f"item_{i}",)) for i in range(100)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=5.0)

    assert len(errors) == 0, f"Errors occurred: {errors}"

    # Verify all items were marked
    for i in range(100):
        assert seen_store.is_seen(f"item_{i}"), f"item_{i} should be marked"


def test_wal_mode_enabled(seen_store):
    """Verify WAL mode is enabled on connection."""
    cursor = seen_store._conn.cursor()
    cursor.execute("PRAGMA journal_mode")
    mode = cursor.fetchone()[0]

    assert mode.upper() == "WAL", f"Expected WAL mode, got {mode}"


def test_context_manager(temp_db_path):
    """Test context manager properly closes connection."""
    config = SeenStoreConfig(path=temp_db_path, ttl_days=7)

    with SeenStore(config=config) as store:
        store.mark_seen("context_test")
        assert store.is_seen("context_test")

    # Connection should be closed
    assert store._conn is None


def test_cleanup_old_entries(seen_store):
    """Test cleanup removes old entries."""
    # Add old entry (31 days ago)
    old_time = int(time.time()) - (31 * 86400)
    seen_store.mark_seen("old_item", ts=old_time)

    # Add recent entry
    seen_store.mark_seen("recent_item")

    # Verify both exist
    assert seen_store.is_seen("old_item")
    assert seen_store.is_seen("recent_item")

    # Cleanup entries older than 30 days
    deleted = seen_store.cleanup_old_entries(days_old=30)

    assert deleted >= 1, "Should delete at least old_item"
    assert not seen_store.is_seen("old_item"), "Old item should be removed"
    assert seen_store.is_seen("recent_item"), "Recent item should remain"


def test_concurrent_mixed_operations(seen_store):
    """Test concurrent reads and writes don't cause corruption."""
    errors = []
    read_results = []

    def read_operation():
        try:
            for i in range(20):
                seen_store.is_seen(f"mixed_{i}")
        except Exception as e:
            errors.append(("read", e))

    def write_operation(start_idx):
        try:
            for i in range(start_idx, start_idx + 20):
                seen_store.mark_seen(f"mixed_{i}")
        except Exception as e:
            errors.append(("write", e))

    # Create 50 reader threads and 50 writer threads
    readers = [threading.Thread(target=read_operation) for _ in range(50)]
    writers = [threading.Thread(target=write_operation, args=(i * 20,)) for i in range(50)]

    # Interleave starting readers and writers
    all_threads = []
    for r, w in zip(readers, writers):
        all_threads.extend([r, w])

    for t in all_threads:
        t.start()
    for t in all_threads:
        t.join(timeout=10.0)

    assert len(errors) == 0, f"Errors occurred: {errors}"


def test_connection_pragmas(seen_store):
    """Verify all optimized pragmas are set correctly."""
    cursor = seen_store._conn.cursor()

    # Check journal_mode
    cursor.execute("PRAGMA journal_mode")
    journal_mode = cursor.fetchone()[0]
    assert journal_mode.upper() == "WAL"

    # Check synchronous
    cursor.execute("PRAGMA synchronous")
    synchronous = cursor.fetchone()[0]
    # 1 = NORMAL, which is what we set
    assert synchronous in (1, 2), f"Expected synchronous to be NORMAL(1) or FULL(2), got {synchronous}"

    # Check temp_store
    cursor.execute("PRAGMA temp_store")
    temp_store = cursor.fetchone()[0]
    # 2 = MEMORY
    assert temp_store == 2, f"Expected temp_store to be MEMORY(2), got {temp_store}"


def test_error_handling_on_mark_seen(seen_store):
    """Test that errors in mark_seen are raised properly."""
    # Close the connection to force an error
    seen_store._conn.close()
    seen_store._conn = None

    # This should raise an exception because connection is None
    with pytest.raises(Exception):
        seen_store.mark_seen("error_test")


def test_is_seen_returns_false_on_error(temp_db_path):
    """Test that is_seen returns False on database errors (safe default)."""
    config = SeenStoreConfig(path=temp_db_path, ttl_days=7)
    store = SeenStore(config=config)

    # Close connection to force errors
    store._conn.close()
    store._conn = None

    # Should return False (not seen) on error - safer behavior
    result = store.is_seen("test_item")
    assert result is False, "is_seen should return False on error"


def test_multiple_stores_same_database(temp_db_path):
    """Test that multiple SeenStore instances can safely access same database with WAL mode."""
    config = SeenStoreConfig(path=temp_db_path, ttl_days=7)

    # Create two stores pointing to same database
    store1 = SeenStore(config=config)
    store2 = SeenStore(config=config)

    try:
        # Write with store1
        store1.mark_seen("multi_store_test")

        # Read with store2
        assert store2.is_seen("multi_store_test"), "Store2 should see item written by Store1"

        # Write with store2
        store2.mark_seen("another_item")

        # Read with store1
        assert store1.is_seen("another_item"), "Store1 should see item written by Store2"

    finally:
        store1.close()
        store2.close()


def test_cleanup_returns_zero_on_error(seen_store):
    """Test that cleanup_old_entries returns 0 on error."""
    # Close connection to force error
    seen_store._conn.close()
    seen_store._conn = None

    deleted = seen_store.cleanup_old_entries(days_old=30)
    assert deleted == 0, "cleanup_old_entries should return 0 on error"


def test_high_concurrency_stress_test(seen_store):
    """Stress test with 200 concurrent operations (100 reads, 100 writes)."""
    errors = []

    def reader():
        try:
            for i in range(50):
                seen_store.is_seen(f"stress_{i}")
        except Exception as e:
            errors.append(("reader", e))

    def writer():
        try:
            for i in range(50):
                seen_store.mark_seen(f"stress_{i}")
        except Exception as e:
            errors.append(("writer", e))

    # Create 100 reader threads and 100 writer threads
    readers = [threading.Thread(target=reader) for _ in range(100)]
    writers = [threading.Thread(target=writer) for _ in range(100)]

    all_threads = readers + writers

    # Start all threads
    for t in all_threads:
        t.start()

    # Wait for all to complete
    for t in all_threads:
        t.join(timeout=15.0)

    assert len(errors) == 0, f"Errors occurred during stress test: {errors[:5]}..."  # Show first 5 errors

    # Verify data integrity - all items should be marked
    for i in range(50):
        assert seen_store.is_seen(f"stress_{i}"), f"stress_{i} should be marked"
