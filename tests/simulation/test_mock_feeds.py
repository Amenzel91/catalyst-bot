"""
Tests for MockFeedProvider.
"""

from datetime import datetime, timezone

from catalyst_bot.simulation import MockFeedProvider, SimulationClock


class TestMockFeedProviderBasics:
    """Basic functionality tests."""

    def test_initialization(self, sample_news, sample_sec, instant_clock):
        """Test feed provider initializes correctly."""
        feed = MockFeedProvider(
            news_items=sample_news,
            sec_filings=sample_sec,
            clock=instant_clock,
        )

        stats = feed.get_stats()
        assert stats["total_news"] == 7
        assert stats["total_sec"] == 4

    def test_has_more_items(self, sample_news, sample_sec, instant_clock):
        """Test checking for more items."""
        feed = MockFeedProvider(
            news_items=sample_news,
            sec_filings=sample_sec,
            clock=instant_clock,
        )

        assert feed.has_more_items() is True


class TestNewsDelivery:
    """Tests for news item delivery."""

    def test_get_new_items_at_start(self, sample_news, sample_sec):
        """Test getting news items at simulation start."""
        # Start before any news
        clock = SimulationClock(
            start_time=datetime(2024, 11, 12, 14, 30, 0, tzinfo=timezone.utc),
            speed_multiplier=0,
        )
        feed = MockFeedProvider(
            news_items=sample_news,
            sec_filings=sample_sec,
            clock=clock,
        )

        # At 14:30, no news yet (first is at 14:32)
        items = feed.get_new_items()
        assert len(items) == 0

    def test_news_arrives_with_time(self, sample_news, sample_sec):
        """Test news items arrive as time advances."""
        clock = SimulationClock(
            start_time=datetime(2024, 11, 12, 14, 30, 0, tzinfo=timezone.utc),
            speed_multiplier=0,
        )
        feed = MockFeedProvider(
            news_items=sample_news,
            sec_filings=sample_sec,
            clock=clock,
        )

        # Advance to 14:33 (after first news at 14:32)
        clock.sleep(180)  # 3 minutes
        items = feed.get_new_items()
        assert len(items) == 1
        assert items[0]["id"] == "news_001"

    def test_news_deduplication(self, sample_news, sample_sec):
        """Test news items are not returned twice."""
        clock = SimulationClock(
            start_time=datetime(2024, 11, 12, 14, 30, 0, tzinfo=timezone.utc),
            speed_multiplier=0,
        )
        feed = MockFeedProvider(
            news_items=sample_news,
            sec_filings=sample_sec,
            clock=clock,
        )

        # Advance and get items
        clock.sleep(180)
        first_batch = feed.get_new_items()
        assert len(first_batch) == 1

        # Get again - should be empty (item already delivered)
        second_batch = feed.get_new_items()
        assert len(second_batch) == 0

    def test_multiple_news_at_once(self, sample_news, sample_sec):
        """Test getting multiple news items that arrived."""
        clock = SimulationClock(
            start_time=datetime(2024, 11, 12, 14, 30, 0, tzinfo=timezone.utc),
            speed_multiplier=0,
        )
        feed = MockFeedProvider(
            news_items=sample_news,
            sec_filings=sample_sec,
            clock=clock,
        )

        # Advance to 14:40 (several news items should be available)
        clock.sleep(600)  # 10 minutes
        items = feed.get_new_items()

        # Should have news_001 (14:32), news_002 (14:35), news_003 (14:38)
        assert len(items) == 3


class TestSECDelivery:
    """Tests for SEC filing delivery."""

    def test_get_sec_filings(self, sample_news, sample_sec):
        """Test getting SEC filings."""
        clock = SimulationClock(
            start_time=datetime(2024, 11, 12, 14, 30, 0, tzinfo=timezone.utc),
            speed_multiplier=0,
        )
        feed = MockFeedProvider(
            news_items=sample_news,
            sec_filings=sample_sec,
            clock=clock,
        )

        # Advance to 14:35 (after first SEC filing at 14:33)
        clock.sleep(300)
        filings = feed.get_new_sec_filings()
        assert len(filings) == 1
        assert filings[0]["ticker"] == "ABCD"
        assert filings[0]["form_type"] == "8-K"

    def test_sec_deduplication(self, sample_news, sample_sec):
        """Test SEC filings are not returned twice."""
        clock = SimulationClock(
            start_time=datetime(2024, 11, 12, 14, 30, 0, tzinfo=timezone.utc),
            speed_multiplier=0,
        )
        feed = MockFeedProvider(
            news_items=sample_news,
            sec_filings=sample_sec,
            clock=clock,
        )

        # Advance and get filings
        clock.sleep(300)
        first_batch = feed.get_new_sec_filings()
        assert len(first_batch) == 1

        # Get again - should be empty
        second_batch = feed.get_new_sec_filings()
        assert len(second_batch) == 0


class TestCombinedDelivery:
    """Tests for combined news and SEC delivery."""

    def test_get_all_new(self, sample_news, sample_sec):
        """Test getting all new items at once."""
        clock = SimulationClock(
            start_time=datetime(2024, 11, 12, 14, 30, 0, tzinfo=timezone.utc),
            speed_multiplier=0,
        )
        feed = MockFeedProvider(
            news_items=sample_news,
            sec_filings=sample_sec,
            clock=clock,
        )

        # Advance to 14:45
        clock.sleep(900)  # 15 minutes
        all_new = feed.get_all_new()

        assert "news" in all_new
        assert "sec" in all_new
        assert len(all_new["news"]) > 0
        assert len(all_new["sec"]) > 0


class TestPeekFunctions:
    """Tests for peek functionality."""

    def test_peek_next_item_time(self, sample_news, sample_sec):
        """Test peeking at next item time."""
        clock = SimulationClock(
            start_time=datetime(2024, 11, 12, 14, 30, 0, tzinfo=timezone.utc),
            speed_multiplier=0,
        )
        feed = MockFeedProvider(
            news_items=sample_news,
            sec_filings=sample_sec,
            clock=clock,
        )

        # Next item should be at 14:32 (news_001)
        next_time = feed.peek_next_item_time()
        assert next_time is not None
        assert next_time.minute == 32

    def test_peek_next_news_time(self, sample_news, sample_sec):
        """Test peeking at next news time."""
        clock = SimulationClock(
            start_time=datetime(2024, 11, 12, 14, 30, 0, tzinfo=timezone.utc),
            speed_multiplier=0,
        )
        feed = MockFeedProvider(
            news_items=sample_news,
            sec_filings=sample_sec,
            clock=clock,
        )

        next_news = feed.peek_next_news_time()
        assert next_news is not None
        assert next_news.minute == 32

    def test_peek_next_sec_time(self, sample_news, sample_sec):
        """Test peeking at next SEC filing time."""
        clock = SimulationClock(
            start_time=datetime(2024, 11, 12, 14, 30, 0, tzinfo=timezone.utc),
            speed_multiplier=0,
        )
        feed = MockFeedProvider(
            news_items=sample_news,
            sec_filings=sample_sec,
            clock=clock,
        )

        next_sec = feed.peek_next_sec_time()
        assert next_sec is not None
        assert next_sec.minute == 33


class TestReset:
    """Tests for reset functionality."""

    def test_reset(self, sample_news, sample_sec):
        """Test resetting the feed."""
        clock = SimulationClock(
            start_time=datetime(2024, 11, 12, 14, 30, 0, tzinfo=timezone.utc),
            speed_multiplier=0,
        )
        feed = MockFeedProvider(
            news_items=sample_news,
            sec_filings=sample_sec,
            clock=clock,
        )

        # Consume some items
        clock.sleep(600)
        feed.get_new_items()

        stats_before = feed.get_stats()
        assert stats_before["delivered_news"] > 0

        # Reset
        feed.reset()

        stats_after = feed.get_stats()
        assert stats_after["delivered_news"] == 0
        assert stats_after["remaining_news"] == stats_after["total_news"]


class TestTickerExtraction:
    """Tests for ticker extraction."""

    def test_get_tickers_in_news(self, sample_news, sample_sec, instant_clock):
        """Test extracting tickers from news."""
        feed = MockFeedProvider(
            news_items=sample_news,
            sec_filings=sample_sec,
            clock=instant_clock,
        )

        tickers = feed.get_tickers_in_news()
        assert "ABCD" in tickers
        assert "AAPL" in tickers
        assert "NVDA" in tickers

    def test_get_tickers_in_sec(self, sample_news, sample_sec, instant_clock):
        """Test extracting tickers from SEC filings."""
        feed = MockFeedProvider(
            news_items=sample_news,
            sec_filings=sample_sec,
            clock=instant_clock,
        )

        tickers = feed.get_tickers_in_sec()
        assert "ABCD" in tickers
        assert "AAPL" in tickers
        assert "NVDA" in tickers


class TestItemsInRange:
    """Tests for get_items_in_range."""

    def test_get_items_in_range(self, sample_news, sample_sec, instant_clock):
        """Test getting items within a time range."""
        feed = MockFeedProvider(
            news_items=sample_news,
            sec_filings=sample_sec,
            clock=instant_clock,
        )

        start = datetime(2024, 11, 12, 14, 35, 0, tzinfo=timezone.utc)
        end = datetime(2024, 11, 12, 14, 45, 0, tzinfo=timezone.utc)

        items = feed.get_items_in_range(start, end)

        assert "news" in items
        assert "sec" in items
        # This doesn't mark items as seen
        assert feed.get_stats()["delivered_news"] == 0
