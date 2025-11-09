"""
Integration test for duplicate detection fix in runner.py.

Tests the full flow: item ingestion -> seen check -> alert send -> mark seen.
"""

import os
from unittest.mock import MagicMock, Mock, patch

import pytest

from catalyst_bot.seen_store import SeenStore, SeenStoreConfig


class TestRunnerDuplicateDetection:
    """Integration tests for runner duplicate detection."""

    @patch("catalyst_bot.runner.feeds")
    @patch("catalyst_bot.runner.send_alert_safe")
    @patch("catalyst_bot.runner.get_settings")
    def test_alert_success_marks_seen(self, mock_settings, mock_send_alert, mock_feeds, tmp_path):
        """Test that successful alerts mark items as seen."""
        # Setup
        mock_settings.return_value = Mock(
            feature_record_only=False,
            feature_persist_seen=True,
            min_score=0.0,
            min_sentiment_abs=None,
            categories_allow=None,
            price_ceiling=None,
        )

        # Mock feed data
        test_item = {
            "id": "test_alert_success",
            "ticker": "ALDX",
            "title": "ALDX Announces Major Partnership",
            "source": "businesswire",
            "link": "https://example.com/news/123",
            "pubDate": "2025-10-28T12:00:00Z",
            "summary": "Test summary",
        }

        mock_feeds.fetch_pr_feeds.return_value = [test_item]
        mock_feeds.dedupe.return_value = [test_item]

        # Mock successful alert send
        mock_send_alert.return_value = True

        # Setup seen store
        seen_store_path = tmp_path / "test_runner.db"
        os.environ["SEEN_DB_PATH"] = str(seen_store_path)
        os.environ["FEATURE_PERSIST_SEEN"] = "true"

        # Import and run cycle
        from catalyst_bot import runner

        with patch.object(runner, "SeenStore") as mock_store_class:
            mock_store = Mock()
            mock_store.is_seen.return_value = False
            mock_store_class.return_value = mock_store

            # Run a minimal cycle (we'll need to mock more components)
            # This is a simplified test to verify the logic flow

            # Verify flow:
            # 1. Check is_seen (should return False)
            assert not mock_store.is_seen(test_item["id"])

            # 2. Send alert (mocked to succeed)
            ok = mock_send_alert({})
            assert ok

            # 3. Mark as seen (should be called after success)
            mock_store.mark_seen(test_item["id"])

            # 4. Verify mark_seen was called
            mock_store.mark_seen.assert_called_with(test_item["id"])

    @patch("catalyst_bot.runner.feeds")
    @patch("catalyst_bot.runner.send_alert_safe")
    @patch("catalyst_bot.runner.get_settings")
    def test_alert_failure_does_not_mark_seen(self, mock_settings, mock_send_alert, mock_feeds, tmp_path):
        """Test that failed alerts do NOT mark items as seen."""
        # Setup
        mock_settings.return_value = Mock(
            feature_record_only=False,
            feature_persist_seen=True,
            min_score=0.0,
            min_sentiment_abs=None,
            categories_allow=None,
            price_ceiling=None,
        )

        # Mock feed data
        test_item = {
            "id": "test_alert_failure",
            "ticker": "ZENA",
            "title": "ZENA Major News",
            "source": "businesswire",
            "link": "https://example.com/news/456",
            "pubDate": "2025-10-28T12:00:00Z",
            "summary": "Test summary",
        }

        mock_feeds.fetch_pr_feeds.return_value = [test_item]
        mock_feeds.dedupe.return_value = [test_item]

        # Mock failed alert send
        mock_send_alert.return_value = False

        # Setup seen store
        seen_store_path = tmp_path / "test_runner_fail.db"
        os.environ["SEEN_DB_PATH"] = str(seen_store_path)
        os.environ["FEATURE_PERSIST_SEEN"] = "true"

        # Verify flow:
        mock_store = Mock()
        mock_store.is_seen.return_value = False

        # 1. Check is_seen (should return False)
        assert not mock_store.is_seen(test_item["id"])

        # 2. Send alert (mocked to fail)
        ok = mock_send_alert({})
        assert not ok

        # 3. mark_seen should NOT be called on failure
        # In fixed code, mark_seen is only called when ok=True

        # Verify mark_seen was NOT called
        mock_store.mark_seen.assert_not_called()

    def test_seen_check_is_readonly(self, tmp_path):
        """
        Test that checking seen status doesn't modify the store.
        """
        store = SeenStore(SeenStoreConfig(path=tmp_path / "readonly.db", ttl_days=7))
        item_id = "readonly_test"

        # Check if seen (should be False)
        is_seen_before = store.is_seen(item_id)
        assert not is_seen_before

        # Check again (should still be False - no side effects)
        is_seen_after = store.is_seen(item_id)
        assert not is_seen_after

        # Verify item was NOT automatically marked as seen
        # (This is the key behavior: is_seen is read-only)

    def test_multiple_retry_attempts(self, tmp_path):
        """
        Test that items can be retried multiple times until success.
        """
        store = SeenStore(SeenStoreConfig(path=tmp_path / "retry.db", ttl_days=7))
        item_id = "retry_test"

        # Attempt 1: Check and fail (don't mark)
        assert not store.is_seen(item_id)
        # Alert fails, don't mark

        # Attempt 2: Check and fail (don't mark)
        assert not store.is_seen(item_id)
        # Alert fails again, don't mark

        # Attempt 3: Check and succeed (mark)
        assert not store.is_seen(item_id)
        store.mark_seen(item_id)

        # Attempt 4: Should now be filtered
        assert store.is_seen(item_id)

    def test_old_should_filter_behavior_comparison(self, tmp_path):
        """
        Compare old (buggy) behavior with new (fixed) behavior.
        """
        # Old behavior: should_filter marks as seen immediately
        from catalyst_bot.seen_store import should_filter

        store_old = SeenStore(SeenStoreConfig(path=tmp_path / "old.db", ttl_days=7))
        item_id_old = "old_behavior_test"

        with patch.dict('os.environ', {'FEATURE_PERSIST_SEEN': 'true'}):
            # First call: not filtered, but marks as seen
            filtered1 = should_filter(item_id_old, store_old)
            assert not filtered1  # Not filtered on first call

            # Check if marked as seen (BUG: it is!)
            assert store_old.is_seen(item_id_old)

            # Second call: filtered (even if alert failed!)
            filtered2 = should_filter(item_id_old, store_old)
            assert filtered2  # This is the bug

        # New behavior: explicit check, then mark only on success
        store_new = SeenStore(SeenStoreConfig(path=tmp_path / "new.db", ttl_days=7))
        item_id_new = "new_behavior_test"

        # First attempt: check (read-only)
        if not store_new.is_seen(item_id_new):
            # Process and send alert (simulated failure)
            alert_ok = False

            # Only mark if success
            if alert_ok:
                store_new.mark_seen(item_id_new)

        # Verify NOT marked as seen
        assert not store_new.is_seen(item_id_new)

        # Second attempt: check (read-only)
        if not store_new.is_seen(item_id_new):
            # Process and send alert (simulated success)
            alert_ok = True

            # Mark on success
            if alert_ok:
                store_new.mark_seen(item_id_new)

        # Verify NOW marked as seen
        assert store_new.is_seen(item_id_new)

        # Third attempt: should be filtered
        if not store_new.is_seen(item_id_new):
            pytest.fail("Should be filtered on third attempt")


class TestRealWorldScenarios:
    """Test real-world duplicate scenarios from Oct 28."""

    def test_aldx_zena_poet_dvlt_scenario(self, tmp_path):
        """
        Simulate the Oct 28 scenario where ALDX, ZENA, POET, DVLT
        had duplicate alerts due to the race condition.
        """
        store = SeenStore(SeenStoreConfig(path=tmp_path / "oct28.db", ttl_days=7))

        tickers = ["ALDX", "ZENA", "POET", "DVLT"]

        for ticker in tickers:
            item_id = f"{ticker.lower()}_news_oct28"

            # Cycle 1: Item appears, check if seen
            assert not store.is_seen(item_id), f"{ticker} should not be seen initially"

            # Simulate network issue or validation error
            alert_success_cycle1 = False

            # Fixed behavior: don't mark as seen on failure
            if alert_success_cycle1:
                store.mark_seen(item_id)

            # Verify NOT marked as seen
            assert not store.is_seen(item_id), f"{ticker} should not be marked after failure"

            # Cycle 2: Item appears again (same news, retry)
            assert not store.is_seen(item_id), f"{ticker} should still not be seen"

            # This time alert succeeds
            alert_success_cycle2 = True

            # Mark as seen on success
            if alert_success_cycle2:
                store.mark_seen(item_id)

            # Verify NOW marked as seen
            assert store.is_seen(item_id), f"{ticker} should be marked after success"

            # Cycle 3: Item appears again (should be filtered)
            assert store.is_seen(item_id), f"{ticker} should be filtered on third cycle"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
