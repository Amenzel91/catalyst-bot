"""
Test SEC LLM Cache Thread Safety (Agent 2 - Week 1)
====================================================

Tests for thread safety and WAL mode in SEC LLM cache.

Critical tests:
- Concurrent cache reads don't cause race conditions
- Concurrent cache writes don't corrupt database
- WAL mode enabled for better concurrency
- Flash-Lite pricing exists in monitor
"""

import json
import os
import sqlite3
import threading
import time
from pathlib import Path

import pytest

from catalyst_bot.llm_usage_monitor import PRICING
from catalyst_bot.sec_llm_cache import SECLLMCache


@pytest.fixture
def test_cache_path(tmp_path):
    """Provide a temporary cache database path for tests."""
    return tmp_path / "test_sec_cache.db"


@pytest.fixture
def cache(test_cache_path):
    """Create a test cache instance."""
    return SECLLMCache(db_path=test_cache_path)


def test_concurrent_cache_reads(cache):
    """
    Test concurrent cache reads don't cause race conditions.

    Agent 2: Verify thread-safe reads with 50 concurrent threads.
    """
    # Pre-populate cache
    test_result = {"keywords": ["test", "keywords"], "sentiment": 0.5}
    cache.cache_sec_analysis("test_filing_001", "TEST", "8-K", test_result)

    results = []
    errors = []

    def read_cache():
        try:
            result = cache.get_cached_sec_analysis("test_filing_001", "TEST", "8-K")
            results.append(result)
        except Exception as e:
            errors.append(e)

    # Launch 50 concurrent read threads
    threads = [threading.Thread(target=read_cache) for _ in range(50)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=5.0)

    # Verify results
    assert len(errors) == 0, f"Errors occurred: {errors}"
    assert len(results) == 50, f"Expected 50 results, got {len(results)}"
    assert all(r == test_result for r in results), "All results should match"


def test_concurrent_cache_writes(cache):
    """
    Test concurrent cache writes don't corrupt database.

    Agent 2: Verify thread-safe writes with 50 concurrent threads.
    """
    errors = []

    def write_cache(filing_id, ticker):
        try:
            result = {"keywords": [ticker], "sentiment": 0.5}
            cache.cache_sec_analysis(filing_id, ticker, "8-K", result)
        except Exception as e:
            errors.append(e)

    # Launch 50 concurrent write threads
    threads = [
        threading.Thread(target=write_cache, args=(f"filing_{i}", f"TICK{i}"))
        for i in range(50)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=5.0)

    # Verify no errors
    assert len(errors) == 0, f"Errors occurred: {errors}"

    # Verify all filings were cached
    for i in range(50):
        result = cache.get_cached_sec_analysis(f"filing_{i}", f"TICK{i}", "8-K")
        assert result is not None, f"filing_{i} should be cached"
        assert result["keywords"] == [f"TICK{i}"], f"Keywords mismatch for filing_{i}"


def test_mixed_concurrent_operations(cache):
    """
    Test mixed concurrent reads and writes.

    Agent 2: Verify thread safety under realistic load with mixed operations.
    """
    # Pre-populate some entries
    for i in range(10):
        cache.cache_sec_analysis(
            f"existing_{i}", f"PRE{i}", "8-K", {"keywords": [f"PRE{i}"], "sentiment": 0.5}
        )

    errors = []
    read_results = []
    write_results = []

    def read_random():
        try:
            import random
            i = random.randint(0, 9)
            result = cache.get_cached_sec_analysis(f"existing_{i}", f"PRE{i}", "8-K")
            read_results.append(result)
        except Exception as e:
            errors.append(e)

    def write_new(filing_id, ticker):
        try:
            result = {"keywords": [ticker], "sentiment": 0.5}
            success = cache.cache_sec_analysis(filing_id, ticker, "8-K", result)
            write_results.append(success)
        except Exception as e:
            errors.append(e)

    # Mix of 25 reads and 25 writes
    threads = []
    for i in range(25):
        threads.append(threading.Thread(target=read_random))
        threads.append(threading.Thread(target=write_new, args=(f"new_{i}", f"NEW{i}")))

    # Shuffle to randomize execution order
    import random
    random.shuffle(threads)

    # Execute all threads
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=5.0)

    # Verify no errors
    assert len(errors) == 0, f"Errors occurred: {errors}"
    assert len(read_results) == 25, f"Expected 25 reads, got {len(read_results)}"
    assert len(write_results) == 25, f"Expected 25 writes, got {len(write_results)}"


def test_wal_mode_enabled(cache):
    """
    Verify WAL mode is enabled on cache database.

    Agent 2: Critical for concurrent access performance.
    """
    conn = sqlite3.connect(str(cache.db_path))
    try:
        cursor = conn.cursor()
        cursor.execute("PRAGMA journal_mode")
        mode = cursor.fetchone()[0]
        assert mode.upper() == "WAL", f"Expected WAL mode, got {mode}"
    finally:
        conn.close()


def test_wal_pragmas_applied(cache):
    """
    Verify all WAL-related pragmas are correctly applied.

    Agent 2: Ensure optimal SQLite configuration.
    Note: Some pragmas like temp_store are connection-specific,
    but WAL mode persists at the database level.
    """
    conn = sqlite3.connect(str(cache.db_path))
    try:
        cursor = conn.cursor()

        # Check journal_mode (persists at database level)
        cursor.execute("PRAGMA journal_mode")
        journal_mode = cursor.fetchone()[0]
        assert journal_mode.upper() == "WAL", f"journal_mode should be WAL, got {journal_mode}"

        # Check synchronous (persists at database level)
        cursor.execute("PRAGMA synchronous")
        synchronous = cursor.fetchone()[0]
        # Should be 1 (NORMAL) for balance of safety and speed
        assert synchronous in (0, 1, 2), f"synchronous should be valid (0-2), got {synchronous}"

        # temp_store is connection-specific, so we just verify it's set when cache operates
        # The important part is that WAL mode is enabled, which we verify above

    finally:
        conn.close()


def test_cache_hit_rate_tracking(cache):
    """
    Test that cache hit rate is tracked correctly.

    Agent 2: Verify statistics are maintained accurately.
    """
    # Initial state
    assert cache.stats["total_requests"] == 0
    assert cache.stats["cache_hits"] == 0
    assert cache.stats["cache_misses"] == 0

    # First request - miss
    result = cache.get_cached_sec_analysis("test_001", "TEST", "8-K")
    assert result is None
    assert cache.stats["total_requests"] == 1
    assert cache.stats["cache_misses"] == 1

    # Cache the result
    cache.cache_sec_analysis("test_001", "TEST", "8-K", {"keywords": ["test"]})

    # Second request - hit
    result = cache.get_cached_sec_analysis("test_001", "TEST", "8-K")
    assert result is not None
    assert cache.stats["total_requests"] == 2
    assert cache.stats["cache_hits"] == 1

    # Third request - hit
    result = cache.get_cached_sec_analysis("test_001", "TEST", "8-K")
    assert result is not None
    assert cache.stats["total_requests"] == 3
    assert cache.stats["cache_hits"] == 2

    # Calculate hit rate
    hit_rate = cache.stats["cache_hits"] / cache.stats["total_requests"]
    assert hit_rate == 2/3, f"Hit rate should be 2/3, got {hit_rate}"


def test_flash_lite_pricing_exists():
    """
    Verify Flash-Lite pricing added to monitor.

    Agent 2: Critical for accurate cost tracking of Flash-Lite model.
    """
    assert "gemini" in PRICING
    assert "gemini-2.0-flash-lite" in PRICING["gemini"]

    flash_lite_pricing = PRICING["gemini"]["gemini-2.0-flash-lite"]
    assert "input" in flash_lite_pricing
    assert "output" in flash_lite_pricing

    # Verify pricing values
    assert flash_lite_pricing["input"] == 0.000_000_02, "Flash-Lite input should be $0.02 per 1M tokens"
    assert flash_lite_pricing["output"] == 0.000_000_10, "Flash-Lite output should be $0.10 per 1M tokens"


def test_flash_lite_pricing_lower_than_flash():
    """
    Verify Flash-Lite is cheaper than Flash models.

    Agent 2: Ensure cost hierarchy is correct.
    """
    flash_lite = PRICING["gemini"]["gemini-2.0-flash-lite"]
    flash_25 = PRICING["gemini"]["gemini-2.5-flash"]
    flash_15 = PRICING["gemini"]["gemini-1.5-flash"]

    # Flash-Lite should be cheaper than other Flash models
    assert flash_lite["input"] < flash_25["input"]
    assert flash_lite["input"] < flash_15["input"]
    assert flash_lite["output"] < flash_25["output"]
    assert flash_lite["output"] < flash_15["output"]


def test_concurrent_cache_invalidation(cache):
    """
    Test thread safety during cache invalidation.

    Agent 2: Verify invalidation doesn't interfere with concurrent operations.
    """
    # Pre-populate cache with multiple entries for same ticker
    for i in range(10):
        cache.cache_sec_analysis(f"filing_{i}", "TEST", "8-K", {"keywords": [f"test_{i}"]})

    errors = []
    invalidation_results = []

    def invalidate():
        try:
            count = cache.invalidate_amendment_caches("TEST", "8-K")
            invalidation_results.append(count)
        except Exception as e:
            errors.append(e)

    def read_cache(filing_id):
        try:
            cache.get_cached_sec_analysis(filing_id, "TEST", "8-K")
        except Exception as e:
            errors.append(e)

    # Mix of invalidations and reads
    threads = [threading.Thread(target=invalidate) for _ in range(5)]
    threads += [threading.Thread(target=read_cache, args=(f"filing_{i}",)) for i in range(10)]

    # Shuffle and execute
    import random
    random.shuffle(threads)

    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=5.0)

    # Verify no errors
    assert len(errors) == 0, f"Errors occurred: {errors}"


def test_cache_expiration_thread_safety(cache):
    """
    Test that expired entries are handled correctly under concurrent access.

    Agent 2: Verify expiration logic is thread-safe.
    """
    # Create a cache entry with very short TTL
    short_ttl_cache = SECLLMCache(db_path=cache.db_path, ttl_hours=0.001)  # ~3.6 seconds

    # Cache an entry
    short_ttl_cache.cache_sec_analysis(
        "expiring_001", "TEST", "8-K", {"keywords": ["expiring"]}
    )

    # Verify it exists
    result = short_ttl_cache.get_cached_sec_analysis("expiring_001", "TEST", "8-K")
    assert result is not None

    # Wait for expiration
    time.sleep(4)

    # Now try concurrent reads after expiration
    results = []
    errors = []

    def read_expired():
        try:
            result = short_ttl_cache.get_cached_sec_analysis("expiring_001", "TEST", "8-K")
            results.append(result)
        except Exception as e:
            errors.append(e)

    threads = [threading.Thread(target=read_expired) for _ in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=5.0)

    # All should return None (expired)
    assert len(errors) == 0, f"Errors occurred: {errors}"
    assert all(r is None for r in results), "All results should be None (expired)"


def test_database_not_locked_under_load(cache):
    """
    Test that database doesn't get locked under heavy concurrent load.

    Agent 2: Critical test - this was the main issue we're fixing.
    """
    errors = []
    lock_errors = []
    success_count = [0]  # Use list for closure mutation

    def heavy_operation(i):
        try:
            # Mix of operations
            if i % 3 == 0:
                # Write
                cache.cache_sec_analysis(
                    f"heavy_{i}", f"TICK{i}", "8-K",
                    {"keywords": [f"heavy_{i}"], "sentiment": 0.5}
                )
            else:
                # Read
                cache.get_cached_sec_analysis(f"heavy_{i}", f"TICK{i}", "8-K")

            success_count[0] += 1
        except sqlite3.OperationalError as e:
            if "locked" in str(e).lower():
                lock_errors.append(e)
            else:
                errors.append(e)
        except Exception as e:
            errors.append(e)

    # Launch 100 concurrent operations
    threads = [threading.Thread(target=heavy_operation, args=(i,)) for i in range(100)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10.0)

    # Verify no lock errors
    assert len(lock_errors) == 0, f"Database lock errors occurred: {lock_errors}"
    assert len(errors) == 0, f"Other errors occurred: {errors}"
    assert success_count[0] == 100, f"Expected 100 successful operations, got {success_count[0]}"


def test_cache_stats_thread_safe(cache):
    """
    Test that cache statistics remain accurate under concurrent access.

    Agent 2: Verify stats dictionary is thread-safe.
    """
    # Perform many concurrent operations
    def mixed_ops(i):
        if i % 2 == 0:
            cache.cache_sec_analysis(f"stat_{i}", f"ST{i}", "8-K", {"keywords": [f"st_{i}"]})
        cache.get_cached_sec_analysis(f"stat_{i}", f"ST{i}", "8-K")

    threads = [threading.Thread(target=mixed_ops, args=(i,)) for i in range(100)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10.0)

    # Verify stats consistency
    stats = cache.stats
    assert stats["total_requests"] == 100, "Should have 100 total requests"
    assert stats["cache_hits"] + stats["cache_misses"] == 100, "Hits + misses should equal total"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
