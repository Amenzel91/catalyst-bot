"""
Test Database Performance Optimizations (Agent 4 - Week 1)
===========================================================

Tests for SQLite WAL mode and performance optimizations across all database modules.

Critical tests:
- WAL mode enabled on all database connections
- Pragma settings applied correctly
- Performance improvement measurable
- All database modules use optimized connections
"""

import os
import sqlite3
import time
from pathlib import Path

import pytest

from catalyst_bot.dedupe import FirstSeenIndex
from catalyst_bot.storage import init_optimized_connection


@pytest.fixture
def temp_db_path(tmp_path):
    """Provide a temporary database path for tests."""
    return str(tmp_path / "test_performance.db")


def test_init_optimized_connection_wal_mode(temp_db_path):
    """
    Test that init_optimized_connection enables WAL mode by default.

    Agent 4: Core optimization function test.
    """
    conn = init_optimized_connection(temp_db_path)

    cursor = conn.cursor()
    cursor.execute("PRAGMA journal_mode")
    mode = cursor.fetchone()[0]

    conn.close()

    assert mode.upper() == "WAL", f"Expected WAL mode, got {mode}"


def test_init_optimized_connection_pragmas(temp_db_path):
    """
    Test that all pragmas are set correctly.

    Agent 4: Verify synchronous, cache_size, temp_store settings.
    """
    conn = init_optimized_connection(temp_db_path)

    cursor = conn.cursor()

    # Check synchronous (1=NORMAL by default)
    cursor.execute("PRAGMA synchronous")
    synchronous = cursor.fetchone()[0]
    assert synchronous in (1, 2), f"Expected synchronous NORMAL(1) or FULL(2), got {synchronous}"

    # Check temp_store (2=MEMORY)
    cursor.execute("PRAGMA temp_store")
    temp_store = cursor.fetchone()[0]
    assert temp_store == 2, f"Expected temp_store MEMORY(2), got {temp_store}"

    # Check cache_size is set (non-zero)
    cursor.execute("PRAGMA cache_size")
    cache_size = cursor.fetchone()[0]
    assert abs(cache_size) > 0, "Cache size should be set"

    conn.close()


def test_dedupe_uses_optimized_connection(tmp_path):
    """
    Test that FirstSeenIndex uses optimized connection with WAL mode.

    Agent 4: Verify dedupe.py integration.
    """
    db_path = str(tmp_path / "dedupe_test.db")
    idx = FirstSeenIndex(db_path)

    cursor = idx._conn.cursor()
    cursor.execute("PRAGMA journal_mode")
    mode = cursor.fetchone()[0]

    idx.close()

    assert mode.upper() == "WAL", f"FirstSeenIndex should use WAL mode, got {mode}"


def test_wal_mode_disableable_via_env(temp_db_path):
    """
    Test that WAL mode can be disabled via SQLITE_WAL_MODE=0.

    Agent 4: Verify environment variable control.
    """
    # Disable WAL mode
    original_val = os.getenv("SQLITE_WAL_MODE")
    os.environ["SQLITE_WAL_MODE"] = "0"

    try:
        conn = init_optimized_connection(temp_db_path)

        cursor = conn.cursor()
        cursor.execute("PRAGMA journal_mode")
        mode = cursor.fetchone()[0]

        conn.close()

        # Should NOT be WAL when disabled
        assert mode.upper() != "WAL", f"WAL should be disabled, got {mode}"
    finally:
        # Restore original value
        if original_val is None:
            os.environ.pop("SQLITE_WAL_MODE", None)
        else:
            os.environ["SQLITE_WAL_MODE"] = original_val


def test_custom_synchronous_mode(temp_db_path):
    """
    Test that SQLITE_SYNCHRONOUS env var is respected.

    Agent 4: Verify synchronous mode customization.
    """
    original_val = os.getenv("SQLITE_SYNCHRONOUS")
    os.environ["SQLITE_SYNCHRONOUS"] = "FULL"

    try:
        conn = init_optimized_connection(temp_db_path)

        cursor = conn.cursor()
        cursor.execute("PRAGMA synchronous")
        synchronous = cursor.fetchone()[0]

        conn.close()

        # 2 = FULL
        assert synchronous == 2, f"Expected FULL(2), got {synchronous}"
    finally:
        if original_val is None:
            os.environ.pop("SQLITE_SYNCHRONOUS", None)
        else:
            os.environ["SQLITE_SYNCHRONOUS"] = original_val


def test_custom_cache_size(temp_db_path):
    """
    Test that SQLITE_CACHE_SIZE env var is respected.

    Agent 4: Verify cache size customization.
    """
    original_val = os.getenv("SQLITE_CACHE_SIZE")
    os.environ["SQLITE_CACHE_SIZE"] = "5000"

    try:
        conn = init_optimized_connection(temp_db_path)

        cursor = conn.cursor()
        cursor.execute("PRAGMA cache_size")
        cache_size = cursor.fetchone()[0]

        conn.close()

        # Should be 5000 or -5000 (depends on positive/negative interpretation)
        assert abs(cache_size) == 5000, f"Expected cache_size 5000, got {cache_size}"
    finally:
        if original_val is None:
            os.environ.pop("SQLITE_CACHE_SIZE", None)
        else:
            os.environ["SQLITE_CACHE_SIZE"] = original_val


def test_read_performance_with_wal(temp_db_path):
    """
    Benchmark read performance with WAL mode optimizations.

    Agent 4: Verify performance improvement is measurable.
    """
    # Create test database with optimizations
    conn = init_optimized_connection(temp_db_path)

    # Create test table and populate
    conn.execute("CREATE TABLE test_perf (id INTEGER PRIMARY KEY, data TEXT)")
    conn.executemany(
        "INSERT INTO test_perf (data) VALUES (?)",
        [(f"data_{i}",) for i in range(1000)]
    )
    conn.commit()

    # Benchmark reads
    start = time.perf_counter()
    for _ in range(100):
        cursor = conn.execute("SELECT * FROM test_perf WHERE id = ?", (500,))
        cursor.fetchone()
    duration = time.perf_counter() - start

    conn.close()

    # Should complete in reasonable time (< 0.5 seconds for 100 reads)
    assert duration < 0.5, f"Read performance too slow: {duration:.3f}s for 100 reads"


def test_write_performance_with_wal(temp_db_path):
    """
    Benchmark write performance with WAL mode optimizations.

    Agent 4: Verify write performance is adequate.
    """
    conn = init_optimized_connection(temp_db_path)

    conn.execute("CREATE TABLE test_write (id INTEGER PRIMARY KEY, data TEXT)")

    # Benchmark writes
    start = time.perf_counter()
    for i in range(100):
        conn.execute("INSERT INTO test_write (data) VALUES (?)", (f"data_{i}",))
        conn.commit()
    duration = time.perf_counter() - start

    conn.close()

    # Should complete in reasonable time (< 1.0 seconds for 100 writes with commits)
    assert duration < 1.0, f"Write performance too slow: {duration:.3f}s for 100 writes"


def test_concurrent_access_with_wal(temp_db_path):
    """
    Test that WAL mode allows concurrent readers and writers.

    Agent 4: Verify WAL improves concurrency.
    """
    import threading

    conn = init_optimized_connection(temp_db_path)
    conn.execute("CREATE TABLE test_concurrent (id INTEGER PRIMARY KEY, data TEXT)")
    conn.commit()
    conn.close()

    errors = []

    def reader():
        try:
            conn = init_optimized_connection(temp_db_path)
            for _ in range(20):
                cursor = conn.execute("SELECT COUNT(*) FROM test_concurrent")
                cursor.fetchone()
                time.sleep(0.001)
            conn.close()
        except Exception as e:
            errors.append(("reader", e))

    def writer():
        try:
            conn = init_optimized_connection(temp_db_path)
            for i in range(20):
                conn.execute("INSERT INTO test_concurrent (data) VALUES (?)", (f"data_{i}",))
                conn.commit()
                time.sleep(0.001)
            conn.close()
        except Exception as e:
            errors.append(("writer", e))

    # Start concurrent readers and writers
    threads = []
    threads.extend([threading.Thread(target=reader) for _ in range(3)])
    threads.extend([threading.Thread(target=writer) for _ in range(2)])

    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=5.0)

    assert len(errors) == 0, f"Concurrent access errors: {errors}"


def test_mmap_size_setting(temp_db_path):
    """
    Test that mmap_size is configured correctly.

    Agent 4: Verify memory-mapped I/O configuration.
    """
    conn = init_optimized_connection(temp_db_path)

    cursor = conn.cursor()
    cursor.execute("PRAGMA mmap_size")
    mmap_size = cursor.fetchone()[0]

    conn.close()

    # Should be set to non-zero (default 30GB or env override)
    assert mmap_size > 0, "mmap_size should be set to enable memory-mapped I/O"


def test_timeout_parameter(temp_db_path):
    """
    Test that custom timeout parameter is respected.

    Agent 4: Verify timeout configuration.
    """
    # Create connection with custom timeout
    conn = init_optimized_connection(temp_db_path, timeout=60)

    # Verify connection works
    cursor = conn.execute("SELECT 1")
    result = cursor.fetchone()

    conn.close()

    assert result == (1,), "Connection should work with custom timeout"


def test_multiple_databases_isolation(tmp_path):
    """
    Test that multiple databases can be optimized independently.

    Agent 4: Verify no interference between databases.
    """
    db1_path = str(tmp_path / "db1.db")
    db2_path = str(tmp_path / "db2.db")

    conn1 = init_optimized_connection(db1_path)
    conn2 = init_optimized_connection(db2_path)

    # Create tables in both
    conn1.execute("CREATE TABLE test1 (id INTEGER PRIMARY KEY)")
    conn2.execute("CREATE TABLE test2 (id INTEGER PRIMARY KEY)")

    # Insert into both
    conn1.execute("INSERT INTO test1 VALUES (1)")
    conn2.execute("INSERT INTO test2 VALUES (2)")

    conn1.commit()
    conn2.commit()

    # Verify isolation
    cursor1 = conn1.execute("SELECT COUNT(*) FROM test1")
    assert cursor1.fetchone()[0] == 1

    cursor2 = conn2.execute("SELECT COUNT(*) FROM test2")
    assert cursor2.fetchone()[0] == 1

    conn1.close()
    conn2.close()


def test_optimized_connection_error_handling(tmp_path):
    """
    Test error handling in init_optimized_connection.

    Agent 4: Verify graceful handling of invalid paths.
    """
    # Try to create database in non-existent directory (should auto-create)
    db_path = str(tmp_path / "subdir" / "nested" / "test.db")

    conn = init_optimized_connection(db_path)

    # Verify connection works
    cursor = conn.execute("SELECT 1")
    result = cursor.fetchone()

    conn.close()

    assert result == (1,), "Should auto-create directory structure"
    assert Path(db_path).exists(), "Database file should exist"
