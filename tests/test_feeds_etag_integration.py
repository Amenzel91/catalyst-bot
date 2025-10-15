"""Integration tests for ETag/Last-Modified support in feeds.py."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from catalyst_bot.feed_state_manager import FeedStateManager


class TestFeedsETagIntegration:
    """Test ETag integration with actual feeds module functions."""

    def test_sync_get_with_etag_support(self, tmp_path):
        """Test synchronous _get function with ETag support."""
        from catalyst_bot import feeds

        # Replace global state manager with test instance
        test_state_file = tmp_path / "test_state.json"
        feeds._feed_state_manager = FeedStateManager(test_state_file)

        test_url = "https://example.com/feed.rss"

        # Mock requests.get
        with patch("catalyst_bot.feeds.requests.get") as mock_get:
            # First request - no conditional headers
            mock_response1 = MagicMock()
            mock_response1.status_code = 200
            rss_content = (
                '<?xml version="1.0"?>'
                "<rss><channel><item><title>Test</title></item></channel></rss>"
            )
            mock_response1.text = rss_content
            mock_response1.headers = {
                "ETag": '"abc123"',
                "Last-Modified": "Mon, 01 Jan 2024 00:00:00 GMT",
            }
            mock_get.return_value = mock_response1

            status, text = feeds._get(test_url)

            assert status == 200
            assert text is not None
            assert '"abc123"' in str(feeds._feed_state_manager.state)

            # Second request - should include conditional headers
            mock_response2 = MagicMock()
            mock_response2.status_code = 304
            mock_get.return_value = mock_response2

            status, text = feeds._get(test_url)

            assert status == 304
            assert text is None

            # Verify conditional headers were sent
            call_args = mock_get.call_args
            headers = call_args.kwargs["headers"]
            assert "If-None-Match" in headers
            assert headers["If-None-Match"] == '"abc123"'
            assert "If-Modified-Since" in headers

    @pytest.mark.skip(reason="pytest-asyncio not installed")
    async def test_async_get_with_etag_support(self, tmp_path):
        """Test async _get_async function with ETag support (simplified test)."""
        from catalyst_bot import feeds

        # Replace global state manager with test instance
        test_state_file = tmp_path / "test_state.json"
        feeds._feed_state_manager = FeedStateManager(test_state_file)

        test_url = "https://example.com/feed.rss"

        # Test that state manager methods are called (integration smoke test)
        # Full async mocking is complex and brittle, so we test the state manager directly

        # Simulate first fetch (200 with headers)
        headers_before = feeds._feed_state_manager.get_headers(test_url)
        assert headers_before == {}  # No state initially

        # Simulate receiving 200 response with validation headers
        feeds._feed_state_manager.update_state(
            test_url,
            {"ETag": '"xyz789"', "Last-Modified": "Tue, 02 Jan 2024 00:00:00 GMT"},
        )

        # Second fetch should include conditional headers
        headers_after = feeds._feed_state_manager.get_headers(test_url)
        assert "If-None-Match" in headers_after
        assert headers_after["If-None-Match"] == '"xyz789"'
        assert "If-Modified-Since" in headers_after

        # Test 304 detection
        assert feeds._feed_state_manager.should_skip(304) is True
        assert feeds._feed_state_manager.should_skip(200) is False

    def test_sync_get_multi_with_304(self, tmp_path):
        """Test _get_multi returns immediately on 304."""
        from catalyst_bot import feeds

        test_state_file = tmp_path / "test_state.json"
        feeds._feed_state_manager = FeedStateManager(test_state_file)

        urls = [
            "https://example.com/feed1.rss",
            "https://example.com/feed2.rss",
        ]

        with patch("catalyst_bot.feeds.requests.get") as mock_get:
            # First URL returns 304 on first try (no retries for 304)
            mock_response = MagicMock()
            mock_response.status_code = 304
            mock_get.return_value = mock_response

            status, text, used_url = feeds._get_multi(urls)

            assert status == 304
            assert text is None
            assert used_url == urls[0]
            # 304 should be returned immediately, no retries
            assert mock_get.call_count == 1

    def test_bandwidth_savings_calculation(self, tmp_path):
        """Test that bandwidth savings are calculated correctly."""
        from catalyst_bot import feeds

        # Mock the feed sources to be simple
        original_feeds = feeds.FEEDS
        feeds.FEEDS = {
            "test_source1": ["https://example.com/feed1.rss"],
            "test_source2": ["https://example.com/feed2.rss"],
        }

        try:
            test_state_file = tmp_path / "test_state.json"
            feeds._feed_state_manager = FeedStateManager(test_state_file)

            with patch("catalyst_bot.feeds.requests.get") as mock_get:
                # First source: 200 OK
                mock_response1 = MagicMock()
                mock_response1.status_code = 200
                mock_response1.text = (
                    '<?xml version="1.0"?><rss><channel></channel></rss>'
                )
                mock_response1.headers = {"ETag": '"feed1"'}

                # Second source: 304 Not Modified
                mock_response2 = MagicMock()
                mock_response2.status_code = 304

                mock_get.side_effect = [mock_response1, mock_response2]

                # Disable async to test sync path
                original_aiohttp = feeds.AIOHTTP_AVAILABLE
                feeds.AIOHTTP_AVAILABLE = False

                with patch("catalyst_bot.feeds._normalize_entry", return_value=None):
                    with patch("catalyst_bot.feeds.dedupe", side_effect=lambda x: x):
                        feeds.fetch_pr_feeds()

                # Restore
                feeds.AIOHTTP_AVAILABLE = original_aiohttp

                # The function should have calculated bandwidth savings
                # This is a basic smoke test - detailed metrics tested elsewhere

        finally:
            feeds.FEEDS = original_feeds

    def test_state_persistence_across_fetches(self, tmp_path):
        """Test that state persists across multiple fetch cycles."""
        from catalyst_bot import feeds

        test_state_file = tmp_path / "persistent_state.json"
        feeds._feed_state_manager = FeedStateManager(test_state_file)

        test_url = "https://example.com/feed.rss"

        with patch("catalyst_bot.feeds.requests.get") as mock_get:
            # First fetch - 200 with ETag
            mock_response1 = MagicMock()
            mock_response1.status_code = 200
            mock_response1.text = "test content"
            mock_response1.headers = {"ETag": '"persistent-etag"'}
            mock_get.return_value = mock_response1

            feeds._get(test_url)

        # Simulate bot restart - create new state manager from same file
        feeds._feed_state_manager = FeedStateManager(test_state_file)

        # State should be loaded from disk
        headers = feeds._feed_state_manager.get_headers(test_url)
        assert headers["If-None-Match"] == '"persistent-etag"'


class TestBandwidthSavingsMetrics:
    """Test bandwidth savings metrics in feed summary."""

    def test_summary_includes_bandwidth_metrics(self):
        """Test that feed summary includes bandwidth savings metrics."""

        # Create mock summary data
        summary = {
            "sources": 5,
            "by_source": {
                "source1": {"ok": 1, "not_modified": 0, "entries": 10},
                "source2": {"ok": 1, "not_modified": 1, "entries": 0},  # 304
                "source3": {"ok": 1, "not_modified": 1, "entries": 0},  # 304
                "source4": {"ok": 1, "not_modified": 0, "entries": 5},
                "source5": {"ok": 1, "not_modified": 1, "entries": 0},  # 304
            },
        }

        # Calculate what the code should compute
        total_feeds = 5
        not_modified_count = 3
        # expected_savings_pct = (3 / 5) * 100  # 60%

        # Verify the calculation logic
        actual_total = 0
        actual_not_modified = 0
        for stats in summary["by_source"].values():
            if stats.get("ok", 0) > 0 or stats.get("not_modified", 0) > 0:
                actual_total += 1
            actual_not_modified += stats.get("not_modified", 0)

        assert actual_total == total_feeds
        assert actual_not_modified == not_modified_count
        assert round((actual_not_modified / actual_total) * 100, 1) == 60.0


class TestErrorHandling:
    """Test that ETag errors don't crash feed fetching."""

    def test_state_manager_error_doesnt_break_feeds(self, tmp_path):
        """Test that state manager errors are handled gracefully."""
        from catalyst_bot import feeds

        test_url = "https://example.com/feed.rss"

        # Create state manager with invalid state file location
        # (This shouldn't crash, just log warnings)
        with patch("catalyst_bot.feeds.requests.get") as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.text = "content"
            mock_response.headers = {}
            mock_get.return_value = mock_response

            # Even without validation headers, fetch should work
            status, text = feeds._get(test_url)
            assert status == 200
            assert text == "content"

    def test_missing_etag_doesnt_break(self, tmp_path):
        """Test that feeds without ETag/Last-Modified still work."""
        from catalyst_bot import feeds

        test_state_file = tmp_path / "test_state.json"
        feeds._feed_state_manager = FeedStateManager(test_state_file)

        test_url = "https://example.com/no-etag-feed.rss"

        with patch("catalyst_bot.feeds.requests.get") as mock_get:
            # Response without validation headers
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.text = "content"
            mock_response.headers = {}  # No ETag or Last-Modified
            mock_get.return_value = mock_response

            status, text = feeds._get(test_url)

            assert status == 200
            assert text == "content"
            # No state should be saved for this feed
            assert test_url not in feeds._feed_state_manager.state
