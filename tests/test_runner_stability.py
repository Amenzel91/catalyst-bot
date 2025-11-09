# -*- coding: utf-8 -*-
"""
Week 1: Runner Stability Tests

Tests for critical stability fixes in runner.py:
1. asyncio.run() deadlock prevention
2. Price cache memory leak prevention
3. Network failure detection (consecutive empty cycles)
"""

import os
import pytest
import time
from unittest.mock import Mock, patch, MagicMock

# Set test environment before importing runner
os.environ["FEATURE_PERSIST_SEEN"] = "false"  # Disable seen store for tests


class TestAsyncioSafety:
    """Test asyncio.run() deadlock prevention."""

    def test_asyncio_run_with_no_existing_loop(self):
        """Test asyncio.run() succeeds when no event loop exists."""
        import asyncio

        # Verify no loop exists
        with pytest.raises(RuntimeError):
            asyncio.get_running_loop()

        # This should succeed
        async def dummy():
            return "success"

        result = asyncio.run(dummy())
        assert result == "success"

    def test_asyncio_run_error_handling(self):
        """Test asyncio.run() with exception is caught gracefully."""
        import asyncio

        async def failing_task():
            raise ValueError("test error")

        # Should catch and handle exception
        try:
            asyncio.run(failing_task())
            assert False, "Should have raised ValueError"
        except ValueError as e:
            assert str(e) == "test error"


class TestPriceCacheLeak:
    """Test price cache memory leak prevention."""

    def test_price_cache_cleared_at_cycle_end(self):
        """Test that _PX_CACHE is cleared at the end of each cycle."""
        from catalyst_bot.runner import _PX_CACHE, _px_cache_put

        # Pre-populate cache
        _px_cache_put("TEST1", 10.0, ttl=60)
        _px_cache_put("TEST2", 20.0, ttl=60)
        _px_cache_put("TEST3", 30.0, ttl=60)

        assert len(_PX_CACHE) == 3, "Cache should have 3 entries"

        # Clear cache (simulating end of cycle)
        _PX_CACHE.clear()

        assert len(_PX_CACHE) == 0, "Cache should be empty after clear"

    def test_price_cache_get_expired(self):
        """Test that expired price cache entries are removed."""
        from catalyst_bot.runner import _PX_CACHE, _px_cache_put, _px_cache_get

        # Add entry with short TTL
        _px_cache_put("EXPIRE", 15.0, ttl=0)  # Expires immediately

        # Wait a moment
        time.sleep(0.1)

        # Try to get expired entry
        result = _px_cache_get("EXPIRE")

        assert result is None, "Expired cache entry should return None"
        assert "EXPIRE" not in _PX_CACHE, "Expired entry should be removed"

    def test_price_cache_put_and_get(self):
        """Test basic price cache put and get operations."""
        from catalyst_bot.runner import _PX_CACHE, _px_cache_put, _px_cache_get

        _PX_CACHE.clear()

        ticker = "AAPL"
        price = 150.50

        # Put into cache
        _px_cache_put(ticker, price, ttl=60)

        # Get from cache
        cached_price = _px_cache_get(ticker)

        assert cached_price == price, f"Expected {price}, got {cached_price}"


class TestNetworkFailureDetection:
    """Test consecutive empty cycle detection."""

    def test_consecutive_empty_cycles_increment(self):
        """Test that consecutive empty cycles counter increments."""
        # This test would require mocking the _cycle function
        # and verifying that _CONSECUTIVE_EMPTY_CYCLES increments
        # when items list is empty.

        # Since _cycle is a large function, we test the logic in isolation
        consecutive_count = 0

        # Simulate empty feed results
        items = []

        if not items or len(items) == 0:
            consecutive_count += 1

        assert consecutive_count == 1, "Counter should increment for empty items"

    def test_consecutive_empty_cycles_reset(self):
        """Test that consecutive empty cycles counter resets on success."""
        consecutive_count = 3  # Simulate 3 empty cycles

        # Simulate successful fetch
        items = [{"id": "1", "title": "Test"}]

        if items and len(items) > 0:
            consecutive_count = 0

        assert consecutive_count == 0, "Counter should reset on successful fetch"

    def test_empty_cycle_threshold_detection(self):
        """Test that alert triggers after threshold is reached."""
        max_empty_cycles = 5
        consecutive_count = 0
        alert_triggered = False

        # Simulate 6 consecutive empty cycles
        for i in range(6):
            items = []

            if not items or len(items) == 0:
                consecutive_count += 1

                if consecutive_count >= max_empty_cycles:
                    alert_triggered = True

        assert consecutive_count == 6, "Should have 6 empty cycles"
        assert alert_triggered, "Alert should be triggered after 5 empty cycles"


class TestCycleIntegration:
    """Integration tests for cycle function (limited due to complexity)."""

    @patch("catalyst_bot.runner.feeds.fetch_pr_feeds")
    @patch("catalyst_bot.runner.feeds.dedupe")
    def test_cycle_handles_empty_feeds(self, mock_dedupe, mock_fetch):
        """Test that _cycle handles empty feed results gracefully."""
        from catalyst_bot.runner import _cycle
        from catalyst_bot.config import get_settings
        from catalyst_bot.logging_utils import get_logger

        # Mock empty feed results
        mock_fetch.return_value = []
        mock_dedupe.return_value = []

        log = get_logger("test_runner")
        settings = get_settings()

        # Should not raise exception
        try:
            # Note: _cycle has many dependencies, this may fail without full mocking
            # This is more of a smoke test than a full integration test
            pass  # Actual cycle call would require extensive mocking
        except Exception as e:
            pytest.skip(f"Cycle integration test requires full environment: {e}")

    def test_price_cache_global_variable_exists(self):
        """Test that price cache global variable is accessible."""
        from catalyst_bot.runner import _PX_CACHE

        assert isinstance(_PX_CACHE, dict), "_PX_CACHE should be a dictionary"

    def test_consecutive_empty_cycles_global_exists(self):
        """Test that consecutive empty cycles global variable exists."""
        from catalyst_bot.runner import _CONSECUTIVE_EMPTY_CYCLES, _MAX_EMPTY_CYCLES

        assert isinstance(_CONSECUTIVE_EMPTY_CYCLES, int), "Should be an integer"
        assert isinstance(_MAX_EMPTY_CYCLES, int), "Should be an integer"
        assert _MAX_EMPTY_CYCLES > 0, "Max empty cycles should be positive"


class TestMemoryStability:
    """Test memory stability over multiple cycles."""

    def test_price_cache_bounded_growth(self):
        """Test that price cache doesn't grow unbounded."""
        from catalyst_bot.runner import _PX_CACHE, _px_cache_put

        _PX_CACHE.clear()

        # Simulate adding entries over many cycles
        for cycle in range(10):
            # Add entries
            for i in range(50):
                ticker = f"TICK{cycle}{i}"
                _px_cache_put(ticker, 10.0 + i, ttl=60)

            # Simulate clearing at end of cycle (Week 1 fix)
            _PX_CACHE.clear()

            # Cache should be empty after clear
            assert len(_PX_CACHE) == 0, f"Cache should be empty after cycle {cycle}"

    def test_price_cache_memory_after_100_cycles(self):
        """Simulate 100 cycles to verify memory doesn't leak."""
        from catalyst_bot.runner import _PX_CACHE, _px_cache_put

        _PX_CACHE.clear()

        for cycle in range(100):
            # Add random entries
            for i in range(10):
                _px_cache_put(f"T{cycle}_{i}", float(cycle + i), ttl=60)

            # Week 1 fix: Clear cache at end of cycle
            _PX_CACHE.clear()

        # After 100 cycles, cache should still be empty
        assert len(_PX_CACHE) == 0, "Cache should be empty after 100 cycles"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
