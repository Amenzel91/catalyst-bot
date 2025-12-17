"""
Tests for MockMarketDataFeed.
"""

from datetime import datetime, timezone

from catalyst_bot.simulation import MockMarketDataFeed, SimulationClock


class TestMockMarketDataFeedBasics:
    """Basic functionality tests."""

    def test_initialization(self, sample_prices, instant_clock):
        """Test feed initializes correctly."""
        feed = MockMarketDataFeed(price_bars=sample_prices, clock=instant_clock)

        assert len(feed.get_available_tickers()) == 4
        assert "AAPL" in feed.get_available_tickers()
        assert "TSLA" in feed.get_available_tickers()

    def test_get_available_tickers(self, sample_prices, instant_clock):
        """Test getting list of available tickers."""
        feed = MockMarketDataFeed(price_bars=sample_prices, clock=instant_clock)

        tickers = feed.get_available_tickers()
        assert set(tickers) == {"AAPL", "TSLA", "NVDA", "ABCD"}

    def test_has_data_for_ticker(self, sample_prices, instant_clock):
        """Test checking ticker data availability."""
        feed = MockMarketDataFeed(price_bars=sample_prices, clock=instant_clock)

        assert feed.has_data_for_ticker("AAPL") is True
        assert feed.has_data_for_ticker("UNKNOWN") is False


class TestPriceLookup:
    """Tests for price lookup functionality."""

    def test_get_last_price_at_start(self, sample_prices, simulation_start_time):
        """Test getting price at simulation start."""
        # Start time is 14:45, first bar is 14:30
        clock = SimulationClock(
            start_time=simulation_start_time,
            speed_multiplier=0,
        )
        feed = MockMarketDataFeed(price_bars=sample_prices, clock=clock)

        # At 14:45, we should get the 14:45 bar
        price = feed.get_last_price("AAPL")
        assert price == 226.70  # Close of 14:45 bar

    def test_get_last_price_between_bars(self, sample_prices):
        """Test getting price between bar timestamps."""
        # Start at 14:37 (between 14:35 and 14:40 bars)
        clock = SimulationClock(
            start_time=datetime(2024, 11, 12, 14, 37, 0, tzinfo=timezone.utc),
            speed_multiplier=0,
        )
        feed = MockMarketDataFeed(price_bars=sample_prices, clock=clock)

        # Should return the 14:35 bar (most recent before current time)
        price = feed.get_last_price("AAPL")
        assert price == 226.00

    def test_get_last_price_before_data(self, sample_prices):
        """Test getting price before any data exists."""
        # Start before first bar
        clock = SimulationClock(
            start_time=datetime(2024, 11, 12, 14, 0, 0, tzinfo=timezone.utc),
            speed_multiplier=0,
        )
        feed = MockMarketDataFeed(price_bars=sample_prices, clock=clock)

        price = feed.get_last_price("AAPL")
        assert price is None

    def test_price_advances_with_time(self, sample_prices):
        """Test price changes as simulation time advances."""
        clock = SimulationClock(
            start_time=datetime(2024, 11, 12, 14, 30, 0, tzinfo=timezone.utc),
            speed_multiplier=0,
        )
        feed = MockMarketDataFeed(price_bars=sample_prices, clock=clock)

        # At 14:30
        price1 = feed.get_last_price("AAPL")
        assert price1 == 225.60  # 14:30 bar

        # Advance to 14:35
        clock.sleep(300)  # 5 minutes
        price2 = feed.get_last_price("AAPL")
        assert price2 == 226.00  # 14:35 bar

        # Advance to 14:40
        clock.sleep(300)
        price3 = feed.get_last_price("AAPL")
        assert price3 == 226.40  # 14:40 bar


class TestPriceSnapshot:
    """Tests for get_last_price_snapshot."""

    def test_snapshot_returns_tuple(self, sample_prices):
        """Test snapshot returns (last, prev_close) tuple."""
        clock = SimulationClock(
            start_time=datetime(2024, 11, 12, 14, 35, 0, tzinfo=timezone.utc),
            speed_multiplier=0,
        )
        feed = MockMarketDataFeed(price_bars=sample_prices, clock=clock)

        snapshot = feed.get_last_price_snapshot("AAPL")
        assert snapshot is not None
        last, prev = snapshot
        assert last == 226.00  # 14:35 close
        assert prev == 225.60  # 14:30 close (previous bar)

    def test_snapshot_first_bar_uses_open(self, sample_prices):
        """Test first bar uses open price as prev_close."""
        clock = SimulationClock(
            start_time=datetime(2024, 11, 12, 14, 30, 0, tzinfo=timezone.utc),
            speed_multiplier=0,
        )
        feed = MockMarketDataFeed(price_bars=sample_prices, clock=clock)

        snapshot = feed.get_last_price_snapshot("AAPL")
        assert snapshot is not None
        last, prev = snapshot
        assert last == 225.60  # close
        assert prev == 225.50  # open (no previous bar)


class TestBatchPrices:
    """Tests for batch_get_prices."""

    def test_batch_get_prices(self, sample_prices, simulation_start_time):
        """Test batch fetching prices."""
        clock = SimulationClock(
            start_time=simulation_start_time,
            speed_multiplier=0,
        )
        feed = MockMarketDataFeed(price_bars=sample_prices, clock=clock)

        results = feed.batch_get_prices(["AAPL", "TSLA", "NVDA"])

        assert len(results) == 3
        assert "AAPL" in results
        assert "TSLA" in results
        assert "NVDA" in results

        # Each result should be (price, change_pct)
        for ticker, (price, change_pct) in results.items():
            assert isinstance(price, float)
            assert isinstance(change_pct, float)

    def test_batch_includes_change_percent(self, sample_prices):
        """Test batch results include change percentage."""
        clock = SimulationClock(
            start_time=datetime(2024, 11, 12, 14, 35, 0, tzinfo=timezone.utc),
            speed_multiplier=0,
        )
        feed = MockMarketDataFeed(price_bars=sample_prices, clock=clock)

        results = feed.batch_get_prices(["AAPL"])
        price, change_pct = results["AAPL"]

        # 226.00 vs 225.60 = ~0.177% gain
        assert price == 226.00
        assert 0.1 < change_pct < 0.3


class TestOHLCV:
    """Tests for get_ohlcv."""

    def test_get_ohlcv(self, sample_prices, simulation_start_time):
        """Test getting OHLCV bar."""
        clock = SimulationClock(
            start_time=simulation_start_time,
            speed_multiplier=0,
        )
        feed = MockMarketDataFeed(price_bars=sample_prices, clock=clock)

        bar = feed.get_ohlcv("AAPL")
        assert bar is not None
        assert "open" in bar
        assert "high" in bar
        assert "low" in bar
        assert "close" in bar
        assert "volume" in bar


class TestStats:
    """Tests for get_stats and utilities."""

    def test_get_stats(self, sample_prices, instant_clock):
        """Test getting feed statistics."""
        feed = MockMarketDataFeed(price_bars=sample_prices, clock=instant_clock)

        stats = feed.get_stats()
        assert stats["tickers"] == 4
        assert stats["total_bars"] == 20  # 5 bars * 4 tickers
        assert isinstance(stats["ticker_list"], list)

    def test_get_price_range(self, sample_prices, instant_clock):
        """Test getting price range for ticker."""
        feed = MockMarketDataFeed(price_bars=sample_prices, clock=instant_clock)

        price_range = feed.get_price_range("AAPL")
        assert price_range is not None
        earliest, latest = price_range
        assert earliest < latest

    def test_clear_cache(self, sample_prices, simulation_start_time):
        """Test clearing price cache."""
        clock = SimulationClock(
            start_time=simulation_start_time,
            speed_multiplier=0,
        )
        feed = MockMarketDataFeed(price_bars=sample_prices, clock=clock)

        # Get a price (populates cache)
        feed.get_last_price("AAPL")
        assert len(feed._latest_prices) > 0

        # Clear cache
        feed.clear_cache()
        assert len(feed._latest_prices) == 0
