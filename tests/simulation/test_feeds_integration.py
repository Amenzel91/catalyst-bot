"""
Integration tests for feeds.py simulation mode support.

Tests that fetch_pr_feeds() correctly returns mock data when
running in simulation mode with a MockFeedProvider.
"""

import os
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from catalyst_bot.feeds import (
    _get_simulation_items,
    fetch_pr_feeds,
    get_mock_feed_provider,
    set_mock_feed_provider,
)
from catalyst_bot.simulation.clock import SimulationClock
from catalyst_bot.simulation.mock_feeds import MockFeedProvider


class TestMockProviderInjection:
    """Tests for the mock feed provider injection mechanism."""

    def test_set_and_get_provider(self):
        """Test that we can set and retrieve the mock provider."""
        # Initially should be None
        set_mock_feed_provider(None)
        assert get_mock_feed_provider() is None

        # Create a mock provider
        clock = SimulationClock(
            start_time=datetime(2024, 11, 12, 14, 30, tzinfo=timezone.utc),
            speed_multiplier=0,
        )
        provider = MockFeedProvider(
            news_items=[],
            sec_filings=[],
            clock=clock,
        )

        # Set it
        set_mock_feed_provider(provider)
        assert get_mock_feed_provider() is provider

        # Clear it
        set_mock_feed_provider(None)
        assert get_mock_feed_provider() is None

    def test_provider_persists_across_calls(self):
        """Test that provider persists across multiple calls."""
        clock = SimulationClock(
            start_time=datetime(2024, 11, 12, 14, 30, tzinfo=timezone.utc),
            speed_multiplier=0,
        )
        provider = MockFeedProvider([], [], clock)

        set_mock_feed_provider(provider)

        # Multiple gets should return same instance
        assert get_mock_feed_provider() is provider
        assert get_mock_feed_provider() is provider

        # Cleanup
        set_mock_feed_provider(None)


class TestGetSimulationItems:
    """Tests for _get_simulation_items() conversion function."""

    def setup_method(self):
        """Set up test fixtures."""
        self.start_time = datetime(2024, 11, 12, 14, 30, tzinfo=timezone.utc)
        self.clock = SimulationClock(
            start_time=self.start_time,
            speed_multiplier=0,
        )

    def teardown_method(self):
        """Clean up after each test."""
        set_mock_feed_provider(None)

    def test_returns_empty_without_provider(self):
        """Test returns empty list when no provider is set."""
        set_mock_feed_provider(None)
        assert _get_simulation_items() == []

    def test_converts_news_items(self):
        """Test that news items are converted to standard format."""
        news_items = [
            {
                "id": "news1",
                "title": "Test News Article",
                "url": "https://example.com/news1",
                "timestamp": self.start_time.isoformat(),
                "source": "test_source",
                "ticker": "AAPL",
                "summary": "Test summary",
            }
        ]

        provider = MockFeedProvider(news_items, [], self.clock)
        set_mock_feed_provider(provider)

        items = _get_simulation_items()

        assert len(items) == 1
        assert items[0]["id"] == "news1"
        assert items[0]["title"] == "Test News Article"
        assert items[0]["link"] == "https://example.com/news1"
        assert items[0]["source"] == "test_source"
        assert items[0]["ticker"] == "AAPL"
        assert items[0]["summary"] == "Test summary"

    def test_converts_sec_filings(self):
        """Test that SEC filings are converted to standard format."""
        sec_filings = [
            {
                "accession_number": "0001234567-24-000001",
                "title": "8-K Filing",
                "url": "https://sec.gov/filing1",
                "timestamp": self.start_time.isoformat(),
                "ticker": "TSLA",
                "form_type": "8-K",
                "company": "Tesla Inc",
            }
        ]

        provider = MockFeedProvider([], sec_filings, self.clock)
        set_mock_feed_provider(provider)

        items = _get_simulation_items()

        assert len(items) == 1
        assert items[0]["id"] == "0001234567-24-000001"
        assert items[0]["source"] == "sec_rss"
        assert items[0]["ticker"] == "TSLA"
        assert items[0]["form_type"] == "8-K"
        assert "TSLA" in items[0]["tickers"]

    def test_combines_news_and_sec(self):
        """Test that both news and SEC items are returned together."""
        news_items = [
            {
                "id": "news1",
                "title": "News Article",
                "timestamp": self.start_time.isoformat(),
            }
        ]
        sec_filings = [
            {
                "accession_number": "acc1",
                "title": "8-K Filing",
                "timestamp": self.start_time.isoformat(),
                "ticker": "AAPL",
            }
        ]

        provider = MockFeedProvider(news_items, sec_filings, self.clock)
        set_mock_feed_provider(provider)

        items = _get_simulation_items()

        assert len(items) == 2
        sources = {item.get("source") for item in items}
        assert "sec_rss" in sources


class TestFetchPrFeedsSimulationMode:
    """Tests for fetch_pr_feeds() simulation mode behavior."""

    def setup_method(self):
        """Set up test fixtures."""
        self.start_time = datetime(2024, 11, 12, 14, 30, tzinfo=timezone.utc)
        self.clock = SimulationClock(
            start_time=self.start_time,
            speed_multiplier=0,
        )

    def teardown_method(self):
        """Clean up after each test."""
        set_mock_feed_provider(None)
        os.environ.pop("SIMULATION_MODE", None)

    @patch("catalyst_bot.feeds.is_sim_mode")
    def test_returns_mock_data_in_simulation_mode(self, mock_is_sim):
        """Test that fetch_pr_feeds returns mock data when in simulation mode."""
        mock_is_sim.return_value = True

        news_items = [
            {
                "id": "sim_news_1",
                "title": "Simulated News",
                "url": "https://example.com/sim",
                "timestamp": self.start_time.isoformat(),
                "ticker": "TEST",
            }
        ]

        provider = MockFeedProvider(news_items, [], self.clock)
        set_mock_feed_provider(provider)

        items = fetch_pr_feeds()

        assert len(items) == 1
        assert items[0]["id"] == "sim_news_1"
        assert items[0]["title"] == "Simulated News"
        assert items[0]["ticker"] == "TEST"

    @patch("catalyst_bot.feeds.is_sim_mode")
    def test_simulation_mode_skips_real_apis(self, mock_is_sim):
        """Test that real API calls are skipped in simulation mode."""
        mock_is_sim.return_value = True

        provider = MockFeedProvider([], [], self.clock)
        set_mock_feed_provider(provider)

        # This should return empty list from mock provider,
        # NOT attempt to call real APIs
        items = fetch_pr_feeds()

        # Should be empty since mock provider has no items
        assert items == []

    @patch("catalyst_bot.feeds.is_sim_mode")
    def test_production_mode_ignores_mock_provider(self, mock_is_sim):
        """Test that mock provider is ignored when not in simulation mode."""
        mock_is_sim.return_value = False

        # Even with a mock provider set, should not use it
        provider = MockFeedProvider(
            [{"id": "mock", "title": "Mock", "timestamp": self.start_time.isoformat()}],
            [],
            self.clock,
        )
        set_mock_feed_provider(provider)

        # In production mode with PYTEST_CURRENT_TEST set,
        # it should skip external calls but not return mock data
        # Just verify the function runs without error
        # (actual API calls are skipped due to test environment)
        with patch.dict(os.environ, {"PYTEST_CURRENT_TEST": "test"}):
            items = fetch_pr_feeds()
            # Should NOT contain our mock item since is_sim_mode is False
            mock_ids = [i["id"] for i in items if i.get("id") == "mock"]
            assert len(mock_ids) == 0

    @patch("catalyst_bot.feeds.is_sim_mode")
    def test_multiple_items_delivered_over_time(self, mock_is_sim):
        """Test that items are delivered based on simulation clock time."""
        mock_is_sim.return_value = True

        t1 = self.start_time
        t2 = self.start_time + timedelta(hours=1)
        t3 = self.start_time + timedelta(hours=2)

        news_items = [
            {"id": "n1", "title": "News 1", "timestamp": t1.isoformat()},
            {"id": "n2", "title": "News 2", "timestamp": t2.isoformat()},
            {"id": "n3", "title": "News 3", "timestamp": t3.isoformat()},
        ]

        provider = MockFeedProvider(news_items, [], self.clock)
        set_mock_feed_provider(provider)

        # First call - only news at t1 should be available
        items1 = fetch_pr_feeds()
        assert len(items1) == 1
        assert items1[0]["id"] == "n1"

        # Advance clock by 1 hour
        self.clock.sleep(3600)

        # Second call - news at t2 should now be available
        items2 = fetch_pr_feeds()
        assert len(items2) == 1
        assert items2[0]["id"] == "n2"

        # Advance clock by another hour
        self.clock.sleep(3600)

        # Third call - news at t3 should now be available
        items3 = fetch_pr_feeds()
        assert len(items3) == 1
        assert items3[0]["id"] == "n3"


class TestSimulationItemDeduplication:
    """Tests for deduplication of simulation items."""

    def setup_method(self):
        """Set up test fixtures."""
        self.start_time = datetime(2024, 11, 12, 14, 30, tzinfo=timezone.utc)
        self.clock = SimulationClock(
            start_time=self.start_time,
            speed_multiplier=0,
        )

    def teardown_method(self):
        """Clean up after each test."""
        set_mock_feed_provider(None)

    @patch("catalyst_bot.feeds.is_sim_mode")
    def test_items_not_duplicated_on_repeated_calls(self, mock_is_sim):
        """Test that the same items aren't returned multiple times."""
        mock_is_sim.return_value = True

        news_items = [
            {
                "id": "unique_news",
                "title": "Unique News",
                "timestamp": self.start_time.isoformat(),
            }
        ]

        provider = MockFeedProvider(news_items, [], self.clock)
        set_mock_feed_provider(provider)

        # First call - should return the item
        items1 = fetch_pr_feeds()
        assert len(items1) == 1

        # Second call - item already delivered, should be empty
        items2 = fetch_pr_feeds()
        assert len(items2) == 0
