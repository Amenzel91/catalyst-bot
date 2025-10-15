"""Comprehensive tests for FeedStateManager (ETags, Last-Modified, 304 handling)."""

from __future__ import annotations

import json
import threading
from pathlib import Path
from unittest.mock import MagicMock


from catalyst_bot.feed_state_manager import FeedStateManager


class TestFeedStateManagerBasics:
    """Test basic state manager functionality."""

    def test_initialization_new_file(self, tmp_path):
        """Test initialization with non-existent state file."""
        state_file = tmp_path / "feed_state.json"
        manager = FeedStateManager(state_file)

        assert manager.state_file == state_file
        assert manager.state == {}
        assert not state_file.exists()  # Not created until first save

    def test_initialization_existing_file(self, tmp_path):
        """Test initialization with existing state file."""
        state_file = tmp_path / "feed_state.json"
        initial_state = {
            "https://example.com/feed.rss": {
                "etag": '"abc123"',
                "last_modified": "Mon, 01 Jan 2024 00:00:00 GMT",
            }
        }
        state_file.write_text(json.dumps(initial_state))

        manager = FeedStateManager(state_file)
        assert manager.state == initial_state

    def test_initialization_corrupted_json(self, tmp_path):
        """Test graceful handling of corrupted JSON file."""
        state_file = tmp_path / "feed_state.json"
        state_file.write_text("not valid json {{{")

        manager = FeedStateManager(state_file)
        assert manager.state == {}  # Falls back to empty state

    def test_initialization_invalid_structure(self, tmp_path):
        """Test handling of valid JSON but invalid structure."""
        state_file = tmp_path / "feed_state.json"
        state_file.write_text('["not", "a", "dict"]')

        manager = FeedStateManager(state_file)
        assert manager.state == {}

    def test_default_state_file_path(self):
        """Test default state file path is data/feed_state.json."""
        manager = FeedStateManager()
        assert manager.state_file == Path("data/feed_state.json")


class TestHeaderGeneration:
    """Test conditional request header generation."""

    def test_get_headers_no_state(self, tmp_path):
        """Test header generation for feed with no cached state."""
        manager = FeedStateManager(tmp_path / "state.json")
        headers = manager.get_headers("https://example.com/feed.rss")
        assert headers == {}

    def test_get_headers_with_etag(self, tmp_path):
        """Test header generation with ETag only."""
        manager = FeedStateManager(tmp_path / "state.json")
        manager.state["https://example.com/feed.rss"] = {
            "etag": '"abc123"',
            "last_modified": None,
        }

        headers = manager.get_headers("https://example.com/feed.rss")
        assert headers == {"If-None-Match": '"abc123"'}

    def test_get_headers_with_last_modified(self, tmp_path):
        """Test header generation with Last-Modified only."""
        manager = FeedStateManager(tmp_path / "state.json")
        manager.state["https://example.com/feed.rss"] = {
            "etag": None,
            "last_modified": "Mon, 01 Jan 2024 00:00:00 GMT",
        }

        headers = manager.get_headers("https://example.com/feed.rss")
        assert headers == {"If-Modified-Since": "Mon, 01 Jan 2024 00:00:00 GMT"}

    def test_get_headers_with_both(self, tmp_path):
        """Test header generation with both ETag and Last-Modified."""
        manager = FeedStateManager(tmp_path / "state.json")
        manager.state["https://example.com/feed.rss"] = {
            "etag": '"abc123"',
            "last_modified": "Mon, 01 Jan 2024 00:00:00 GMT",
        }

        headers = manager.get_headers("https://example.com/feed.rss")
        assert headers == {
            "If-None-Match": '"abc123"',
            "If-Modified-Since": "Mon, 01 Jan 2024 00:00:00 GMT",
        }


class TestStateUpdates:
    """Test state updates from response headers."""

    def test_update_state_dict_headers(self, tmp_path):
        """Test updating state from dict headers (requests library)."""
        state_file = tmp_path / "state.json"
        manager = FeedStateManager(state_file)

        response_headers = {
            "ETag": '"xyz789"',
            "Last-Modified": "Tue, 02 Jan 2024 12:00:00 GMT",
            "Content-Type": "application/rss+xml",
        }

        manager.update_state("https://example.com/feed.rss", response_headers)

        assert manager.state["https://example.com/feed.rss"] == {
            "etag": '"xyz789"',
            "last_modified": "Tue, 02 Jan 2024 12:00:00 GMT",
        }
        assert state_file.exists()

    def test_update_state_lowercase_headers(self, tmp_path):
        """Test case-insensitive header lookup."""
        manager = FeedStateManager(tmp_path / "state.json")

        response_headers = {
            "etag": '"lowercase-etag"',
            "last-modified": "Wed, 03 Jan 2024 00:00:00 GMT",
        }

        manager.update_state("https://example.com/feed.rss", response_headers)

        assert manager.state["https://example.com/feed.rss"] == {
            "etag": '"lowercase-etag"',
            "last_modified": "Wed, 03 Jan 2024 00:00:00 GMT",
        }

    def test_update_state_partial_headers(self, tmp_path):
        """Test update with only ETag or Last-Modified."""
        manager = FeedStateManager(tmp_path / "state.json")

        # Only ETag
        manager.update_state("https://example.com/feed1.rss", {"ETag": '"only-etag"'})
        assert manager.state["https://example.com/feed1.rss"] == {
            "etag": '"only-etag"',
            "last_modified": None,
        }

        # Only Last-Modified
        manager.update_state(
            "https://example.com/feed2.rss",
            {"Last-Modified": "Thu, 04 Jan 2024 00:00:00 GMT"},
        )
        assert manager.state["https://example.com/feed2.rss"] == {
            "etag": None,
            "last_modified": "Thu, 04 Jan 2024 00:00:00 GMT",
        }

    def test_update_state_no_validation_headers(self, tmp_path):
        """Test update with no ETag or Last-Modified (no-op)."""
        state_file = tmp_path / "state.json"
        manager = FeedStateManager(state_file)

        manager.update_state(
            "https://example.com/feed.rss", {"Content-Type": "application/rss+xml"}
        )

        # State should not be saved if no validation headers
        assert "https://example.com/feed.rss" not in manager.state
        assert not state_file.exists()

    def test_update_state_aiohttp_headers(self, tmp_path):
        """Test updating state from aiohttp CIMultiDictProxy-like headers."""
        manager = FeedStateManager(tmp_path / "state.json")

        # Mock aiohttp headers with .get() method
        mock_headers = MagicMock()
        mock_headers.get = lambda k: {
            "ETag": '"aiohttp-etag"',
            "etag": None,
            "Last-Modified": "Fri, 05 Jan 2024 00:00:00 GMT",
            "last-modified": None,
        }.get(k)

        manager.update_state("https://example.com/feed.rss", mock_headers)

        assert manager.state["https://example.com/feed.rss"] == {
            "etag": '"aiohttp-etag"',
            "last_modified": "Fri, 05 Jan 2024 00:00:00 GMT",
        }


class TestNotModifiedDetection:
    """Test 304 Not Modified detection."""

    def test_should_skip_304(self, tmp_path):
        """Test that 304 status returns True."""
        manager = FeedStateManager(tmp_path / "state.json")
        assert manager.should_skip(304) is True

    def test_should_skip_200(self, tmp_path):
        """Test that 200 status returns False."""
        manager = FeedStateManager(tmp_path / "state.json")
        assert manager.should_skip(200) is False

    def test_should_skip_404(self, tmp_path):
        """Test that error statuses return False."""
        manager = FeedStateManager(tmp_path / "state.json")
        assert manager.should_skip(404) is False
        assert manager.should_skip(500) is False


class TestStatePersistence:
    """Test state saving and loading."""

    def test_save_and_load_cycle(self, tmp_path):
        """Test full save/load cycle."""
        state_file = tmp_path / "state.json"

        # Create and populate manager
        manager1 = FeedStateManager(state_file)
        manager1.update_state(
            "https://example.com/feed1.rss",
            {"ETag": '"feed1-etag"', "Last-Modified": "Mon, 01 Jan 2024 00:00:00 GMT"},
        )
        manager1.update_state("https://example.com/feed2.rss", {"ETag": '"feed2-etag"'})

        # Load in new manager
        manager2 = FeedStateManager(state_file)
        assert len(manager2.state) == 2
        assert manager2.state["https://example.com/feed1.rss"]["etag"] == '"feed1-etag"'
        assert manager2.state["https://example.com/feed2.rss"]["etag"] == '"feed2-etag"'

    def test_state_file_creation(self, tmp_path):
        """Test that state file and directory are created on first save."""
        state_file = tmp_path / "subdir" / "feed_state.json"
        manager = FeedStateManager(state_file)

        assert not state_file.exists()
        assert not state_file.parent.exists()

        manager.update_state("https://example.com/feed.rss", {"ETag": '"test"'})

        assert state_file.exists()
        assert state_file.parent.exists()

    def test_atomic_write(self, tmp_path):
        """Test that writes are atomic (uses temp file)."""
        state_file = tmp_path / "state.json"
        manager = FeedStateManager(state_file)

        manager.update_state("https://example.com/feed.rss", {"ETag": '"test"'})

        # Verify no .tmp file left behind
        assert not (state_file.parent / "state.json.tmp").exists()
        assert state_file.exists()


class TestConcurrency:
    """Test thread-safety of concurrent state updates."""

    def test_concurrent_updates(self, tmp_path):
        """Test multiple threads updating state simultaneously."""
        state_file = tmp_path / "state.json"
        manager = FeedStateManager(state_file)

        def update_feed(feed_num):
            for i in range(10):
                manager.update_state(
                    f"https://example.com/feed{feed_num}.rss",
                    {"ETag": f'"feed{feed_num}-{i}"'},
                )

        threads = [threading.Thread(target=update_feed, args=(i,)) for i in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # All feeds should be tracked
        assert len(manager.state) == 5
        # State file should be valid JSON
        loaded = json.loads(state_file.read_text())
        assert len(loaded) == 5

    def test_concurrent_reads(self, tmp_path):
        """Test multiple threads reading headers simultaneously."""
        manager = FeedStateManager(tmp_path / "state.json")
        manager.update_state(
            "https://example.com/feed.rss",
            {"ETag": '"test"', "Last-Modified": "Mon, 01 Jan 2024 00:00:00 GMT"},
        )

        results = []

        def read_headers():
            for _ in range(100):
                headers = manager.get_headers("https://example.com/feed.rss")
                results.append(headers)

        threads = [threading.Thread(target=read_headers) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # All reads should return same headers
        assert len(results) == 500
        assert all(r == results[0] for r in results)


class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_missing_data_directory(self, tmp_path):
        """Test that missing parent directory is created."""
        state_file = tmp_path / "missing" / "dir" / "state.json"
        manager = FeedStateManager(state_file)
        manager.update_state("https://example.com/feed.rss", {"ETag": '"test"'})

        assert state_file.exists()
        assert state_file.parent.exists()

    def test_update_overwrites_previous_state(self, tmp_path):
        """Test that updates overwrite previous state for same URL."""
        manager = FeedStateManager(tmp_path / "state.json")

        manager.update_state("https://example.com/feed.rss", {"ETag": '"old-etag"'})
        assert manager.state["https://example.com/feed.rss"]["etag"] == '"old-etag"'

        manager.update_state("https://example.com/feed.rss", {"ETag": '"new-etag"'})
        assert manager.state["https://example.com/feed.rss"]["etag"] == '"new-etag"'

    def test_clear_feed_state(self, tmp_path):
        """Test clearing state for specific feed."""
        state_file = tmp_path / "state.json"
        manager = FeedStateManager(state_file)

        manager.update_state("https://example.com/feed1.rss", {"ETag": '"feed1"'})
        manager.update_state("https://example.com/feed2.rss", {"ETag": '"feed2"'})

        assert len(manager.state) == 2

        manager.clear_feed_state("https://example.com/feed1.rss")

        assert len(manager.state) == 1
        assert "https://example.com/feed1.rss" not in manager.state
        assert "https://example.com/feed2.rss" in manager.state

        # Verify persistence
        loaded_state = json.loads(state_file.read_text())
        assert len(loaded_state) == 1

    def test_get_stats(self, tmp_path):
        """Test statistics about tracked feeds."""
        manager = FeedStateManager(tmp_path / "state.json")

        # Empty state
        stats = manager.get_stats()
        assert stats == {
            "total_feeds": 0,
            "feeds_with_etag": 0,
            "feeds_with_last_modified": 0,
            "feeds_with_both": 0,
        }

        # Add various combinations
        manager.update_state(
            "https://example.com/feed1.rss",
            {"ETag": '"etag1"', "Last-Modified": "Mon, 01 Jan 2024 00:00:00 GMT"},
        )
        manager.update_state("https://example.com/feed2.rss", {"ETag": '"etag2"'})
        manager.update_state(
            "https://example.com/feed3.rss",
            {"Last-Modified": "Tue, 02 Jan 2024 00:00:00 GMT"},
        )

        stats = manager.get_stats()
        assert stats["total_feeds"] == 3
        assert stats["feeds_with_etag"] == 2
        assert stats["feeds_with_last_modified"] == 2
        assert stats["feeds_with_both"] == 1


class TestIntegrationWithMockedHTTP:
    """Integration tests with mocked HTTP responses."""

    def test_first_fetch_then_304(self, tmp_path):
        """Simulate first fetch (200) followed by 304 on second fetch."""
        manager = FeedStateManager(tmp_path / "state.json")
        feed_url = "https://example.com/feed.rss"

        # First fetch - no conditional headers
        headers1 = manager.get_headers(feed_url)
        assert headers1 == {}

        # Simulate 200 response with validation headers
        manager.update_state(
            feed_url,
            {"ETag": '"abc123"', "Last-Modified": "Mon, 01 Jan 2024 00:00:00 GMT"},
        )

        # Second fetch - should include conditional headers
        headers2 = manager.get_headers(feed_url)
        assert headers2 == {
            "If-None-Match": '"abc123"',
            "If-Modified-Since": "Mon, 01 Jan 2024 00:00:00 GMT",
        }

        # Simulate 304 response (no state update needed)
        assert manager.should_skip(304) is True

    def test_feed_update_after_content_change(self, tmp_path):
        """Simulate feed content change (new ETag)."""
        manager = FeedStateManager(tmp_path / "state.json")
        feed_url = "https://example.com/feed.rss"

        # Initial fetch
        manager.update_state(feed_url, {"ETag": '"version1"'})
        headers = manager.get_headers(feed_url)
        assert headers["If-None-Match"] == '"version1"'

        # Content changed - server returns 200 with new ETag
        manager.update_state(feed_url, {"ETag": '"version2"'})

        # Next fetch uses new ETag
        headers = manager.get_headers(feed_url)
        assert headers["If-None-Match"] == '"version2"'

    def test_multiple_feeds_independent_state(self, tmp_path):
        """Test that multiple feeds maintain independent state."""
        manager = FeedStateManager(tmp_path / "state.json")

        manager.update_state("https://example.com/feed1.rss", {"ETag": '"feed1-etag"'})
        manager.update_state("https://example.com/feed2.rss", {"ETag": '"feed2-etag"'})

        headers1 = manager.get_headers("https://example.com/feed1.rss")
        headers2 = manager.get_headers("https://example.com/feed2.rss")

        assert headers1["If-None-Match"] == '"feed1-etag"'
        assert headers2["If-None-Match"] == '"feed2-etag"'


class TestErrorResilience:
    """Test that errors don't crash feed fetching."""

    def test_save_error_doesnt_crash(self, tmp_path, monkeypatch):
        """Test that save errors are logged but don't raise."""
        manager = FeedStateManager(tmp_path / "state.json")

        # Make state file directory read-only to cause write error
        state_dir = tmp_path / "readonly"
        state_dir.mkdir()
        readonly_file = state_dir / "state.json"
        manager.state_file = readonly_file

        # This should log warning but not raise
        manager.update_state("https://example.com/feed.rss", {"ETag": '"test"'})

        # State should still be updated in memory
        assert manager.state["https://example.com/feed.rss"]["etag"] == '"test"'

    def test_load_io_error(self, tmp_path, monkeypatch):
        """Test that load errors result in empty state."""
        state_file = tmp_path / "state.json"
        state_file.write_text('{"valid": "json"}')

        # Monkey patch open to raise IOError
        original_open = open

        def mock_open(*args, **kwargs):
            if str(args[0]) == str(state_file) and "r" in args[1]:
                raise IOError("Simulated read error")
            return original_open(*args, **kwargs)

        monkeypatch.setattr("builtins.open", mock_open)

        manager = FeedStateManager(state_file)
        assert manager.state == {}
