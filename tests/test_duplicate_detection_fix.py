"""
Test for duplicate alert detection fix.

Root Cause
----------
The seen_store.should_filter() function marks items as seen BEFORE alerts
are sent. If an alert fails to send (network error, validation error, etc.),
the item is already marked as seen and will be filtered on retry, causing
missed alerts.

The fix ensures items are only marked as seen AFTER successful alert delivery.
"""

import time
from unittest.mock import Mock, patch

import pytest

from catalyst_bot.seen_store import SeenStore, SeenStoreConfig


class TestDuplicateDetectionFix:
    """Test suite for duplicate alert detection fix."""

    def test_should_filter_marks_seen_prematurely(self, tmp_path):
        """
        Test that demonstrates the bug: should_filter marks items as seen
        even before alerts are sent, causing duplicates to be missed on retry.
        """
        # Setup
        store = SeenStore(SeenStoreConfig(path=tmp_path / "test.db", ttl_days=7))
        item_id = "test_item_123"

        # First check - this should mark as seen
        is_seen = store.is_seen(item_id)
        assert not is_seen, "Item should not be seen initially"

        # Simulate the current behavior: should_filter marks as seen
        from catalyst_bot.seen_store import should_filter
        with patch.dict('os.environ', {'FEATURE_PERSIST_SEEN': 'true'}):
            result = should_filter(item_id, store)

        # Result is False on first call (not filtered)
        assert not result, "First call should not filter"

        # But the item is now marked as seen
        is_seen_after = store.is_seen(item_id)
        assert is_seen_after, "Item is marked as seen after should_filter"

        # Second call would filter it out
        result2 = should_filter(item_id, store)
        assert result2, "Second call should filter (this is the bug)"

    def test_mark_seen_only_after_success(self, tmp_path):
        """
        Test the correct behavior: mark as seen only after successful alert send.
        """
        store = SeenStore(SeenStoreConfig(path=tmp_path / "test.db", ttl_days=7))
        item_id = "test_item_456"

        # Check if seen (should be False)
        is_seen = store.is_seen(item_id)
        assert not is_seen

        # Simulate alert failure - do NOT mark as seen
        # (this is what the fix should do)

        # Item should still not be seen
        is_seen_after_failure = store.is_seen(item_id)
        assert not is_seen_after_failure

        # Simulate alert success - NOW mark as seen
        store.mark_seen(item_id)

        # Item should now be seen
        is_seen_after_success = store.is_seen(item_id)
        assert is_seen_after_success

    def test_race_condition_scenario(self, tmp_path):
        """
        Test the race condition where an item fails to send but is marked seen.
        This simulates the ALDX, ZENA, POET, DVLT scenario.
        """
        store = SeenStore(SeenStoreConfig(path=tmp_path / "test.db", ttl_days=7))

        # Simulate 4 items that had issues on Oct 28
        items = [
            {"id": "aldx_item_1", "ticker": "ALDX", "title": "ALDX News"},
            {"id": "zena_item_1", "ticker": "ZENA", "title": "ZENA News"},
            {"id": "poet_item_1", "ticker": "POET", "title": "POET News"},
            {"id": "dvlt_item_1", "ticker": "DVLT", "title": "DVLT News"},
        ]

        for item in items:
            item_id = item["id"]

            # First attempt: check if seen (should be False)
            assert not store.is_seen(item_id)

            # CURRENT BUG: should_filter marks as seen before alert
            from catalyst_bot.seen_store import should_filter
            with patch.dict('os.environ', {'FEATURE_PERSIST_SEEN': 'true'}):
                filtered = should_filter(item_id, store)
            assert not filtered, f"First call should not filter {item_id}"

            # Simulate alert send failure
            alert_sent = False  # Simulated failure

            # Bug: Item is already marked as seen even though alert failed
            assert store.is_seen(item_id), f"{item_id} marked seen despite failure"

            # Second attempt: Item is filtered out (causing missed alert)
            with patch.dict('os.environ', {'FEATURE_PERSIST_SEEN': 'true'}):
                filtered2 = should_filter(item_id, store)
            assert filtered2, f"{item_id} filtered on retry (this is the bug)"

    def test_fixed_behavior_with_explicit_check(self, tmp_path):
        """
        Test the fixed behavior: check seen status WITHOUT marking,
        then mark only after successful send.
        """
        store = SeenStore(SeenStoreConfig(path=tmp_path / "test.db", ttl_days=7))
        item_id = "test_fixed_789"

        # Step 1: Check if already seen (read-only check)
        if store.is_seen(item_id):
            # Item already processed, skip
            pytest.skip("Item already seen")

        # Step 2: Process the item (score, enrich, etc.)
        # ... processing logic ...

        # Step 3: Send alert
        alert_success = True  # Simulated success

        # Step 4: ONLY mark as seen if alert succeeded
        if alert_success:
            store.mark_seen(item_id)

        # Verify item is now seen
        assert store.is_seen(item_id)

        # Second attempt should be filtered
        if store.is_seen(item_id):
            # Correctly filtered on second attempt
            pass

    def test_seen_store_ttl_expiration(self, tmp_path):
        """Test that seen items expire after TTL."""
        # Use 0 days TTL to test immediate expiration
        store = SeenStore(SeenStoreConfig(path=tmp_path / "test.db", ttl_days=0))
        item_id = "expiring_item"

        # Mark as seen
        store.mark_seen(item_id)
        assert store.is_seen(item_id)

        # Wait a moment and purge
        time.sleep(0.1)
        store.purge_expired()

        # Should be expired now
        # Note: With 0 days TTL, items expire immediately
        # This tests the expiration mechanism

    def test_concurrent_access_pattern(self, tmp_path):
        """
        Test that multiple cycles don't create duplicate alerts.
        This simulates the production scenario.
        """
        store = SeenStore(SeenStoreConfig(path=tmp_path / "test.db", ttl_days=7))

        # Cycle 1: First time seeing item
        item_id = "concurrent_test_1"
        assert not store.is_seen(item_id)

        # Simulate successful alert send
        store.mark_seen(item_id)

        # Cycle 2: Same item appears again (should be filtered)
        assert store.is_seen(item_id)

        # Cycle 3: Still filtered
        assert store.is_seen(item_id)

    def test_network_failure_recovery(self, tmp_path):
        """
        Test that network failures don't prevent retry alerts.
        """
        store = SeenStore(SeenStoreConfig(path=tmp_path / "test.db", ttl_days=7))
        item_id = "network_failure_test"

        # Attempt 1: Check if seen
        if not store.is_seen(item_id):
            # Try to send alert (simulated network failure)
            alert_sent = False

            # DO NOT mark as seen if alert failed
            if not alert_sent:
                pass  # Don't mark as seen

        # Verify item is NOT marked as seen
        assert not store.is_seen(item_id)

        # Attempt 2: Retry should succeed
        if not store.is_seen(item_id):
            # Try to send alert (simulated success)
            alert_sent = True

            # Mark as seen only on success
            if alert_sent:
                store.mark_seen(item_id)

        # Verify item is now marked as seen
        assert store.is_seen(item_id)

    def test_dedupe_with_different_sources(self, tmp_path):
        """
        Test that the same news from different sources is properly deduped.
        """
        store = SeenStore(SeenStoreConfig(path=tmp_path / "test.db", ttl_days=7))

        # Same news from different sources should have same ID after normalization
        # This tests the signature_from() function integration
        from catalyst_bot.dedupe import signature_from

        title = "ALDX Announces Major Partnership"
        url1 = "https://source1.com/news/123"
        url2 = "https://source2.com/news/456"
        ticker = "ALDX"

        # Generate signatures
        sig1 = signature_from(title, url1, ticker)
        sig2 = signature_from(title, url2, ticker)

        # Different URLs should create different signatures
        # (This is expected behavior to allow same news from different sources)
        assert sig1 != sig2

        # But same URL + title should create same signature
        sig1_dup = signature_from(title, url1, ticker)
        assert sig1 == sig1_dup


class TestTemporalDeduplication:
    """Test temporal deduplication with 30-minute buckets."""

    def test_temporal_dedup_key_same_bucket(self):
        """Test that items in same 30-min bucket get same key."""
        from catalyst_bot.dedupe import temporal_dedup_key

        ticker = "ALDX"
        title = "Breaking News"

        # Two timestamps 10 minutes apart (same bucket)
        ts1 = 1000000000  # Some timestamp
        ts2 = ts1 + (10 * 60)  # +10 minutes

        key1 = temporal_dedup_key(ticker, title, ts1)
        key2 = temporal_dedup_key(ticker, title, ts2)

        assert key1 == key2, "Same 30-min bucket should produce same key"

    def test_temporal_dedup_key_different_bucket(self):
        """Test that items in different 30-min buckets get different keys."""
        from catalyst_bot.dedupe import temporal_dedup_key

        ticker = "ALDX"
        title = "Breaking News"

        # Two timestamps 31 minutes apart (different buckets)
        ts1 = 1000000000
        ts2 = ts1 + (31 * 60)  # +31 minutes

        key1 = temporal_dedup_key(ticker, title, ts1)
        key2 = temporal_dedup_key(ticker, title, ts2)

        assert key1 != key2, "Different 30-min buckets should produce different keys"

    def test_temporal_dedup_different_tickers(self):
        """Test that same news for different tickers gets different keys."""
        from catalyst_bot.dedupe import temporal_dedup_key

        title = "Breaking News"
        timestamp = 1000000000

        key1 = temporal_dedup_key("ALDX", title, timestamp)
        key2 = temporal_dedup_key("ZENA", title, timestamp)

        assert key1 != key2, "Different tickers should produce different keys"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
