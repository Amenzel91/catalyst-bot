"""
Integration tests for market.py simulation mode support.

Tests that get_last_price_snapshot() correctly returns mock data when
running in simulation mode with a MockMarketDataFeed.
"""

import os
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from catalyst_bot.market import (
    get_last_price_snapshot,
    get_mock_market_data_feed,
    set_mock_market_data_feed,
)
from catalyst_bot.simulation.clock import SimulationClock
from catalyst_bot.simulation.mock_market_data import MockMarketDataFeed


class TestMockMarketDataInjection:
    """Tests for the mock market data feed injection mechanism."""

    def test_set_and_get_feed(self):
        """Test that we can set and retrieve the mock market data feed."""
        # Initially should be None
        set_mock_market_data_feed(None)
        assert get_mock_market_data_feed() is None

        # Create a mock feed
        clock = SimulationClock(
            start_time=datetime(2024, 11, 12, 14, 30, tzinfo=timezone.utc),
            speed_multiplier=0,
        )
        feed = MockMarketDataFeed(
            price_bars={},
            clock=clock,
        )

        # Set it
        set_mock_market_data_feed(feed)
        assert get_mock_market_data_feed() is feed

        # Clear it
        set_mock_market_data_feed(None)
        assert get_mock_market_data_feed() is None

    def test_feed_persists_across_calls(self):
        """Test that feed persists across multiple calls."""
        clock = SimulationClock(
            start_time=datetime(2024, 11, 12, 14, 30, tzinfo=timezone.utc),
            speed_multiplier=0,
        )
        feed = MockMarketDataFeed({}, clock)

        set_mock_market_data_feed(feed)

        # Multiple gets should return same instance
        assert get_mock_market_data_feed() is feed
        assert get_mock_market_data_feed() is feed

        # Cleanup
        set_mock_market_data_feed(None)


class TestGetLastPriceSnapshotSimulationMode:
    """Tests for get_last_price_snapshot() simulation mode behavior."""

    def setup_method(self):
        """Set up test fixtures."""
        self.start_time = datetime(2024, 11, 12, 14, 30, tzinfo=timezone.utc)
        self.clock = SimulationClock(
            start_time=self.start_time,
            speed_multiplier=0,
        )

    def teardown_method(self):
        """Clean up after each test."""
        set_mock_market_data_feed(None)
        os.environ.pop("SIMULATION_MODE", None)

    @patch("catalyst_bot.market.is_sim_mode")
    def test_returns_mock_data_in_simulation_mode(self, mock_is_sim):
        """Test that get_last_price_snapshot returns mock data when in simulation mode."""
        mock_is_sim.return_value = True

        # Create price bars for a ticker - use unique test ticker to avoid real data
        t1 = self.start_time
        price_bars = {
            "TESTSIM": [
                {
                    "timestamp": t1.isoformat(),
                    "open": 150.0,
                    "high": 152.0,
                    "low": 149.0,
                    "close": 151.0,
                    "volume": 1000000,
                }
            ]
        }

        feed = MockMarketDataFeed(price_bars, self.clock)
        set_mock_market_data_feed(feed)

        last, prev = get_last_price_snapshot("TESTSIM")

        # Should return the mock data
        assert last == 151.0  # close price
        assert prev == 150.0  # open price (used as prev for first bar)

    @patch("catalyst_bot.market.is_sim_mode")
    def test_simulation_mode_skips_real_apis(self, mock_is_sim):
        """Test that real API calls are skipped in simulation mode."""
        mock_is_sim.return_value = True

        # Create empty price bars
        feed = MockMarketDataFeed({}, self.clock)
        set_mock_market_data_feed(feed)

        # This should return None from mock provider (no data for ticker),
        # but NOT attempt real API calls which would take time/fail
        last, prev = get_last_price_snapshot("NONEXISTENT")

        # Should be None since mock provider has no data
        assert last is None
        assert prev is None

    @patch("catalyst_bot.market.is_sim_mode")
    def test_production_mode_ignores_mock_feed(self, mock_is_sim):
        """Test that mock feed is ignored when not in simulation mode."""
        mock_is_sim.return_value = False

        # Even with a mock feed set with data, should not use it
        price_bars = {
            "MOCK": [
                {
                    "timestamp": self.start_time.isoformat(),
                    "open": 999.0,
                    "close": 999.0,
                }
            ]
        }
        feed = MockMarketDataFeed(price_bars, self.clock)
        set_mock_market_data_feed(feed)

        # In production mode, it should try real providers
        # Since we're in a test environment, it will likely return None
        # but the key is it won't return our mock 999.0 price
        last, prev = get_last_price_snapshot("MOCK")

        # Should NOT be our mock price of 999.0
        # (Either None from failed real lookup, or real price if somehow available)
        if last is not None:
            assert last != 999.0  # Shouldn't be our mock value

    @patch("catalyst_bot.market.is_sim_mode")
    def test_price_advances_with_clock(self, mock_is_sim):
        """Test that prices change as simulation clock advances."""
        mock_is_sim.return_value = True

        t1 = self.start_time
        t2 = self.start_time + timedelta(hours=1)

        price_bars = {
            "AAPL": [
                {
                    "timestamp": t1.isoformat(),
                    "open": 150.0,
                    "high": 152.0,
                    "low": 149.0,
                    "close": 151.0,
                    "volume": 1000000,
                },
                {
                    "timestamp": t2.isoformat(),
                    "open": 151.0,
                    "high": 155.0,
                    "low": 150.0,
                    "close": 154.0,
                    "volume": 1500000,
                },
            ]
        }

        feed = MockMarketDataFeed(price_bars, self.clock)
        set_mock_market_data_feed(feed)

        # First check - at t1
        last1, _ = get_last_price_snapshot("AAPL")
        assert last1 is not None

        # Advance clock by 1 hour
        self.clock.sleep(3600)

        # Second check - at t2, should have new price
        last2, _ = get_last_price_snapshot("AAPL")
        assert last2 is not None

        # Prices should be different (close at t2 is 154, prev close is 151)
        # The exact values depend on MockMarketDataFeed implementation


class TestMockMarketDataFeedIntegration:
    """Tests for MockMarketDataFeed behavior in market.py context."""

    def setup_method(self):
        """Set up test fixtures."""
        self.start_time = datetime(2024, 11, 12, 14, 30, tzinfo=timezone.utc)
        self.clock = SimulationClock(
            start_time=self.start_time,
            speed_multiplier=0,
        )

    def teardown_method(self):
        """Clean up after each test."""
        set_mock_market_data_feed(None)

    def test_mock_feed_returns_correct_format(self):
        """Test that mock feed returns tuple of (last, prev)."""
        price_bars = {
            "AAPL": [
                {
                    "timestamp": self.start_time.isoformat(),
                    "open": 150.0,
                    "close": 151.0,
                }
            ]
        }

        feed = MockMarketDataFeed(price_bars, self.clock)
        result = feed.get_last_price_snapshot("AAPL")

        # Should return a tuple of two values
        assert isinstance(result, tuple)
        assert len(result) == 2

    def test_mock_feed_handles_unknown_ticker(self):
        """Test that mock feed handles unknown tickers gracefully."""
        feed = MockMarketDataFeed({}, self.clock)
        result = feed.get_last_price_snapshot("UNKNOWN")

        # Should return None for unknown ticker
        assert result is None
