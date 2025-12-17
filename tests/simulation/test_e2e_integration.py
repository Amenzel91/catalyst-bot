"""
End-to-end integration tests for the simulation environment.

These tests validate that all simulation components work together:
- SimulationController orchestration
- Clock time management
- MockFeedProvider -> feeds.py integration
- MockMarketDataFeed -> market.py integration
- Full simulation cycle execution
"""

import os
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from catalyst_bot.feeds import (
    fetch_pr_feeds,
    get_mock_feed_provider,
    set_mock_feed_provider,
)
from catalyst_bot.market import (
    get_last_price_snapshot,
    get_mock_market_data_feed,
    set_mock_market_data_feed,
)
from catalyst_bot.simulation import SimulationClock, init_clock
from catalyst_bot.simulation import reset as reset_clock
from catalyst_bot.simulation.mock_feeds import MockFeedProvider
from catalyst_bot.simulation.mock_market_data import MockMarketDataFeed
from catalyst_bot.time_utils import is_simulation as is_sim_mode
from catalyst_bot.time_utils import now as sim_now
from catalyst_bot.time_utils import sleep as sim_sleep


class TestSimulationClockIntegration:
    """Test that simulation clock integrates with time_utils."""

    def setup_method(self):
        """Set up simulation environment."""
        os.environ["SIMULATION_MODE"] = "1"
        self.start_time = datetime(2024, 11, 12, 14, 30, tzinfo=timezone.utc)
        init_clock(
            simulation_mode=True,
            start_time=self.start_time,
            speed_multiplier=0,  # Instant mode
        )

    def teardown_method(self):
        """Clean up."""
        reset_clock()
        os.environ.pop("SIMULATION_MODE", None)

    def test_time_utils_uses_simulation_clock(self):
        """Verify time_utils functions use simulation clock."""
        assert is_sim_mode() is True

        # now() should return simulation time
        current = sim_now()
        assert current.year == 2024
        assert current.month == 11
        assert current.day == 12
        assert current.hour == 14
        assert current.minute == 30

    def test_sleep_advances_simulation_time(self):
        """Verify sleep advances simulation time."""
        t1 = sim_now()
        sim_sleep(3600)  # 1 hour
        t2 = sim_now()

        elapsed = (t2 - t1).total_seconds()
        assert elapsed == 3600

    def test_multiple_sleeps_accumulate(self):
        """Verify multiple sleeps accumulate correctly."""
        t0 = sim_now()

        sim_sleep(1800)  # 30 min
        sim_sleep(1800)  # 30 min
        sim_sleep(1800)  # 30 min

        t1 = sim_now()
        elapsed = (t1 - t0).total_seconds()
        assert elapsed == 5400  # 90 minutes


class TestFeedsIntegrationE2E:
    """End-to-end tests for feeds.py simulation integration."""

    def setup_method(self):
        """Set up simulation environment with mock feeds."""
        os.environ["SIMULATION_MODE"] = "1"
        self.start_time = datetime(2024, 11, 12, 14, 30, tzinfo=timezone.utc)

        # Initialize global clock first
        init_clock(
            simulation_mode=True,
            start_time=self.start_time,
            speed_multiplier=0,
        )

        # Use the global clock so advancing it affects mock providers
        from catalyst_bot.simulation import clock_provider

        self.clock = clock_provider._clock

        # Create mock news and SEC data
        self.news_items = [
            {
                "id": "news_001",
                "title": "ACME Corp Announces Major Acquisition",
                "url": "https://example.com/news/001",
                "timestamp": self.start_time.isoformat(),
                "source": "pr_newswire",
                "ticker": "ACME",
                "summary": "ACME Corp to acquire competitor for $500M",
            },
            {
                "id": "news_002",
                "title": "Beta Inc Reports Strong Q3 Earnings",
                "url": "https://example.com/news/002",
                "timestamp": (self.start_time + timedelta(minutes=30)).isoformat(),
                "source": "businesswire",
                "ticker": "BETA",
                "summary": "Revenue up 25% YoY",
            },
        ]

        self.sec_filings = [
            {
                "accession_number": "0001234567-24-000001",
                "title": "Form 8-K Current Report",
                "url": "https://sec.gov/filing/001",
                "timestamp": (self.start_time + timedelta(minutes=15)).isoformat(),
                "ticker": "ACME",
                "form_type": "8-K",
                "company": "ACME Corporation",
            },
        ]

        self.feed_provider = MockFeedProvider(
            self.news_items,
            self.sec_filings,
            self.clock,
        )
        set_mock_feed_provider(self.feed_provider)

    def teardown_method(self):
        """Clean up."""
        set_mock_feed_provider(None)
        reset_clock()
        os.environ.pop("SIMULATION_MODE", None)

    @patch("catalyst_bot.feeds.is_sim_mode")
    def test_fetch_pr_feeds_returns_mock_data(self, mock_is_sim):
        """Verify fetch_pr_feeds returns mock data in simulation mode."""
        mock_is_sim.return_value = True

        items = fetch_pr_feeds()

        # Should have 1 news item at t=0 (first news is at start_time)
        assert len(items) >= 1
        assert any(
            item.get("title") == "ACME Corp Announces Major Acquisition"
            for item in items
        )

    @patch("catalyst_bot.feeds.is_sim_mode")
    def test_feeds_advance_with_time(self, mock_is_sim):
        """Verify new items appear as simulation time advances."""
        mock_is_sim.return_value = True

        # First fetch at t=0
        items1 = fetch_pr_feeds()
        len(items1)

        # Advance 20 minutes - SEC filing should now be available
        self.clock.sleep(20 * 60)

        items2 = fetch_pr_feeds()

        # Should have SEC filing now
        assert any(item.get("form_type") == "8-K" for item in items2)

    @patch("catalyst_bot.feeds.is_sim_mode")
    def test_items_not_duplicated(self, mock_is_sim):
        """Verify items aren't returned multiple times."""
        mock_is_sim.return_value = True

        items1 = fetch_pr_feeds()
        items2 = fetch_pr_feeds()

        # Second fetch should not return same items
        assert len(items2) == 0 or items2 != items1


class TestMarketIntegrationE2E:
    """End-to-end tests for market.py simulation integration."""

    def setup_method(self):
        """Set up simulation environment with mock market data."""
        os.environ["SIMULATION_MODE"] = "1"
        self.start_time = datetime(2024, 11, 12, 14, 30, tzinfo=timezone.utc)

        # Initialize global clock first
        init_clock(
            simulation_mode=True,
            start_time=self.start_time,
            speed_multiplier=0,
        )

        # Use the global clock so advancing it affects mock providers
        from catalyst_bot.simulation import clock_provider

        self.clock = clock_provider._clock

        # Create mock price data
        self.price_bars = {
            "ACME": [
                {
                    "timestamp": self.start_time.isoformat(),
                    "open": 5.00,
                    "high": 5.50,
                    "low": 4.90,
                    "close": 5.25,
                    "volume": 500000,
                },
                {
                    "timestamp": (self.start_time + timedelta(minutes=30)).isoformat(),
                    "open": 5.25,
                    "high": 6.00,
                    "low": 5.20,
                    "close": 5.80,
                    "volume": 750000,
                },
            ],
            "BETA": [
                {
                    "timestamp": self.start_time.isoformat(),
                    "open": 2.50,
                    "high": 2.75,
                    "low": 2.45,
                    "close": 2.60,
                    "volume": 200000,
                },
            ],
        }

        self.market_feed = MockMarketDataFeed(self.price_bars, self.clock)
        set_mock_market_data_feed(self.market_feed)

    def teardown_method(self):
        """Clean up."""
        set_mock_market_data_feed(None)
        reset_clock()
        os.environ.pop("SIMULATION_MODE", None)

    @patch("catalyst_bot.market.is_sim_mode")
    def test_get_price_returns_mock_data(self, mock_is_sim):
        """Verify get_last_price_snapshot returns mock prices."""
        mock_is_sim.return_value = True

        last, prev = get_last_price_snapshot("ACME")

        # Should return mock data
        assert last == 5.25  # close price
        assert prev == 5.00  # open price (first bar)

    @patch("catalyst_bot.market.is_sim_mode")
    def test_prices_advance_with_time(self, mock_is_sim):
        """Verify prices change as simulation time advances."""
        mock_is_sim.return_value = True

        # Price at t=0
        last1, _ = get_last_price_snapshot("ACME")
        assert last1 == 5.25

        # Advance 30 minutes
        self.clock.sleep(30 * 60)

        # Price at t+30min
        last2, prev2 = get_last_price_snapshot("ACME")
        assert last2 == 5.80  # new close
        assert prev2 == 5.25  # previous close

    @patch("catalyst_bot.market.is_sim_mode")
    def test_multiple_tickers(self, mock_is_sim):
        """Verify multiple tickers work correctly."""
        mock_is_sim.return_value = True

        acme_last, _ = get_last_price_snapshot("ACME")
        beta_last, _ = get_last_price_snapshot("BETA")

        assert acme_last == 5.25
        assert beta_last == 2.60

    @patch("catalyst_bot.market.is_sim_mode")
    def test_unknown_ticker_returns_none(self, mock_is_sim):
        """Verify unknown tickers return None, not real data."""
        mock_is_sim.return_value = True

        last, prev = get_last_price_snapshot("UNKNOWN_TICKER_XYZ")

        assert last is None
        assert prev is None


class TestFullSimulationCycle:
    """Test a complete simulation cycle with all components."""

    def setup_method(self):
        """Set up complete simulation environment."""
        os.environ["SIMULATION_MODE"] = "1"
        self.start_time = datetime(2024, 11, 12, 14, 30, tzinfo=timezone.utc)

    def teardown_method(self):
        """Clean up."""
        set_mock_feed_provider(None)
        set_mock_market_data_feed(None)
        reset_clock()
        os.environ.pop("SIMULATION_MODE", None)

    @patch("catalyst_bot.feeds.is_sim_mode")
    @patch("catalyst_bot.market.is_sim_mode")
    def test_simulated_trading_day_scenario(self, mock_market_sim, mock_feeds_sim):
        """Simulate a realistic trading scenario."""
        mock_market_sim.return_value = True
        mock_feeds_sim.return_value = True

        # Initialize global clock first
        init_clock(
            simulation_mode=True,
            start_time=self.start_time,
            speed_multiplier=0,
        )

        # Get the shared clock from clock_provider
        from catalyst_bot.simulation import clock_provider

        clock = clock_provider._clock

        # Set up mock data
        news_items = [
            {
                "id": "catalyst_news",
                "title": "SmallCap Inc Receives FDA Approval",
                "url": "https://example.com/fda",
                "timestamp": self.start_time.isoformat(),
                "ticker": "SMCP",
                "source": "pr_newswire",
            },
        ]

        price_bars = {
            "SMCP": [
                {
                    "timestamp": self.start_time.isoformat(),
                    "open": 3.00,
                    "high": 3.50,
                    "low": 2.90,
                    "close": 3.25,
                    "volume": 100000,
                },
                {
                    "timestamp": (self.start_time + timedelta(hours=1)).isoformat(),
                    "open": 3.25,
                    "high": 4.50,
                    "low": 3.20,
                    "close": 4.25,
                    "volume": 500000,
                },
            ],
        }

        feed_provider = MockFeedProvider(news_items, [], clock)
        market_feed = MockMarketDataFeed(price_bars, clock)

        set_mock_feed_provider(feed_provider)
        set_mock_market_data_feed(market_feed)

        # === SIMULATE A TRADING CYCLE ===

        # 1. Check initial time
        current_time = sim_now()
        assert current_time == self.start_time

        # 2. Fetch feeds - should get FDA news
        items = fetch_pr_feeds()
        assert len(items) == 1
        assert items[0]["ticker"] == "SMCP"

        # 3. Get price for the ticker
        last, prev = get_last_price_snapshot("SMCP")
        assert last == 3.25
        assert prev == 3.00

        # 4. Advance time by 1 hour
        sim_sleep(3600)

        # 5. Verify time advanced
        new_time = sim_now()
        assert (new_time - self.start_time).total_seconds() == 3600

        # 6. Get updated price
        last2, prev2 = get_last_price_snapshot("SMCP")
        assert last2 == 4.25  # Price went up after FDA news!
        assert prev2 == 3.25

        # 7. Calculate simulated gain
        gain_pct = ((last2 - last) / last) * 100
        assert gain_pct > 30  # ~30.7% gain

    @patch("catalyst_bot.feeds.is_sim_mode")
    @patch("catalyst_bot.market.is_sim_mode")
    def test_multi_cycle_simulation(self, mock_market_sim, mock_feeds_sim):
        """Test multiple feed cycles in simulation."""
        mock_market_sim.return_value = True
        mock_feeds_sim.return_value = True

        # Initialize global clock first
        init_clock(
            simulation_mode=True,
            start_time=self.start_time,
            speed_multiplier=0,
        )

        # Get the shared clock from clock_provider
        from catalyst_bot.simulation import clock_provider

        clock = clock_provider._clock

        # News items at different times
        t1 = self.start_time
        t2 = self.start_time + timedelta(minutes=5)
        t3 = self.start_time + timedelta(minutes=10)

        news_items = [
            {"id": "n1", "title": "News 1", "timestamp": t1.isoformat(), "ticker": "A"},
            {"id": "n2", "title": "News 2", "timestamp": t2.isoformat(), "ticker": "B"},
            {"id": "n3", "title": "News 3", "timestamp": t3.isoformat(), "ticker": "C"},
        ]

        feed_provider = MockFeedProvider(news_items, [], clock)
        set_mock_feed_provider(feed_provider)

        # Cycle 1: t=0
        items1 = fetch_pr_feeds()
        assert len(items1) == 1
        assert items1[0]["ticker"] == "A"

        # Cycle 2: t=5min - use sim_sleep to advance global clock
        sim_sleep(5 * 60)
        items2 = fetch_pr_feeds()
        assert len(items2) == 1
        assert items2[0]["ticker"] == "B"

        # Cycle 3: t=10min
        sim_sleep(5 * 60)
        items3 = fetch_pr_feeds()
        assert len(items3) == 1
        assert items3[0]["ticker"] == "C"

        # Cycle 4: No more news
        sim_sleep(5 * 60)
        items4 = fetch_pr_feeds()
        assert len(items4) == 0


class TestSimulationIsolation:
    """Test that simulation mode doesn't leak into production."""

    def test_production_mode_by_default(self):
        """Verify production mode is default when env var not set."""
        os.environ.pop("SIMULATION_MODE", None)
        reset_clock()

        # Clear any mock providers
        set_mock_feed_provider(None)
        set_mock_market_data_feed(None)

        assert is_sim_mode() is False

    def test_cleanup_clears_all_mocks(self):
        """Verify cleanup properly clears all mock providers."""
        # Set up mocks
        os.environ["SIMULATION_MODE"] = "1"
        clock = SimulationClock(
            start_time=datetime(2024, 1, 1, tzinfo=timezone.utc),
            speed_multiplier=0,
        )

        feed_provider = MockFeedProvider([], [], clock)
        market_feed = MockMarketDataFeed({}, clock)

        set_mock_feed_provider(feed_provider)
        set_mock_market_data_feed(market_feed)

        assert get_mock_feed_provider() is not None
        assert get_mock_market_data_feed() is not None

        # Clean up
        set_mock_feed_provider(None)
        set_mock_market_data_feed(None)
        reset_clock()
        os.environ.pop("SIMULATION_MODE", None)

        # Verify all cleared
        assert get_mock_feed_provider() is None
        assert get_mock_market_data_feed() is None
