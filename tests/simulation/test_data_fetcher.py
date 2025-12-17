"""
Tests for HistoricalDataFetcher.
"""

import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import pytest

from catalyst_bot.simulation import HistoricalDataFetcher


class TestHistoricalDataFetcherBasics:
    """Basic functionality tests."""

    def test_initialization(self):
        """Test fetcher initializes correctly."""
        with tempfile.TemporaryDirectory() as tmpdir:
            fetcher = HistoricalDataFetcher(
                cache_dir=Path(tmpdir),
                price_source="cached",
                news_source="cached",
            )

            assert fetcher.cache_dir == Path(tmpdir)
            assert fetcher.price_source == "cached"
            assert fetcher.news_source == "cached"

    def test_cache_dir_creation(self):
        """Test cache directory is created if it doesn't exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_path = Path(tmpdir) / "new_cache"
            _fetcher = HistoricalDataFetcher(cache_dir=cache_path)  # noqa: F841

            assert cache_path.exists()

    def test_cache_key_generation(self):
        """Test cache key is consistent for same inputs."""
        with tempfile.TemporaryDirectory() as tmpdir:
            fetcher = HistoricalDataFetcher(cache_dir=Path(tmpdir))

            key1 = fetcher._cache_key("2024-11-12", ["AAPL", "TSLA"])
            key2 = fetcher._cache_key("2024-11-12", ["AAPL", "TSLA"])
            key3 = fetcher._cache_key(
                "2024-11-12", ["TSLA", "AAPL"]
            )  # Same tickers, different order

            assert key1 == key2
            assert key1 == key3  # Should be same because we sort tickers

    def test_cache_key_varies_by_date(self):
        """Test cache key varies by date."""
        with tempfile.TemporaryDirectory() as tmpdir:
            fetcher = HistoricalDataFetcher(cache_dir=Path(tmpdir))

            key1 = fetcher._cache_key("2024-11-12")
            key2 = fetcher._cache_key("2024-11-13")

            assert key1 != key2


class TestTickerExtraction:
    """Tests for ticker extraction from data."""

    def test_extract_tickers_from_news(self):
        """Test extracting tickers from news items."""
        with tempfile.TemporaryDirectory() as tmpdir:
            fetcher = HistoricalDataFetcher(cache_dir=Path(tmpdir))

            news_items = [
                {"related_tickers": ["AAPL", "MSFT"]},
                {"related_tickers": "TSLA,NVDA"},
                {"ticker": "AMD"},
                {"ticker": "N/A"},  # Should be ignored
            ]

            tickers = fetcher._extract_tickers_from_news(news_items)

            assert "AAPL" in tickers
            assert "MSFT" in tickers
            assert "TSLA" in tickers
            assert "NVDA" in tickers
            assert "AMD" in tickers
            assert "N/A" not in tickers

    def test_extract_tickers_from_sec(self):
        """Test extracting tickers from SEC filings."""
        with tempfile.TemporaryDirectory() as tmpdir:
            fetcher = HistoricalDataFetcher(cache_dir=Path(tmpdir))

            sec_filings = [
                {"ticker": "AAPL"},
                {"ticker": "TSLA"},
                {"ticker": "N/A"},
                {"ticker": ""},
            ]

            tickers = fetcher._extract_tickers_from_sec(sec_filings)

            assert "AAPL" in tickers
            assert "TSLA" in tickers
            assert "N/A" not in tickers


class TestCacheOperations:
    """Tests for caching functionality."""

    @pytest.mark.asyncio
    async def test_fetch_uses_cache(self):
        """Test that cached data is used on subsequent fetches."""
        with tempfile.TemporaryDirectory() as tmpdir:
            fetcher = HistoricalDataFetcher(
                cache_dir=Path(tmpdir),
                price_source="cached",
                news_source="cached",
            )

            date = datetime(2024, 11, 12, tzinfo=timezone.utc)

            # Create a fake cache file
            cache_key = fetcher._cache_key(date.strftime("%Y-%m-%d"), None)
            cache_file = Path(tmpdir) / f"{cache_key}.json"

            cached_data = {
                "date": "2024-11-12",
                "price_bars": {"AAPL": [{"close": 150.0}]},
                "news_items": [{"id": "test", "title": "Test News"}],
                "sec_filings": [],
                "metadata": {"cached": True},
            }

            with open(cache_file, "w") as f:
                json.dump(cached_data, f)

            # Fetch should use cache
            result = await fetcher.fetch_day(date, use_cache=True)

            assert result["metadata"].get("cached") is True
            assert "AAPL" in result["price_bars"]

    @pytest.mark.asyncio
    async def test_fetch_ignores_cache_when_disabled(self):
        """Test that cache is ignored when use_cache=False."""
        with tempfile.TemporaryDirectory() as tmpdir:
            fetcher = HistoricalDataFetcher(
                cache_dir=Path(tmpdir),
                price_source="cached",
                news_source="cached",
            )

            date = datetime(2024, 11, 12, tzinfo=timezone.utc)

            # Create a fake cache file
            cache_key = fetcher._cache_key(date.strftime("%Y-%m-%d"), None)
            cache_file = Path(tmpdir) / f"{cache_key}.json"

            cached_data = {"metadata": {"cached": True}}
            with open(cache_file, "w") as f:
                json.dump(cached_data, f)

            # Fetch with cache disabled - won't use cached data
            result = await fetcher.fetch_day(date, use_cache=False)

            # Result should be fresh (no cached flag)
            assert result["metadata"].get("cached") is not True

    def test_get_cached_dates(self):
        """Test getting list of cached dates."""
        with tempfile.TemporaryDirectory() as tmpdir:
            fetcher = HistoricalDataFetcher(cache_dir=Path(tmpdir))

            # Create some cache files
            (Path(tmpdir) / "2024-11-12_abc123.json").write_text("{}")
            (Path(tmpdir) / "2024-11-13_def456.json").write_text("{}")
            (Path(tmpdir) / "2024-11-14_ghi789.json").write_text("{}")

            dates = fetcher.get_cached_dates()

            assert "2024-11-12" in dates
            assert "2024-11-13" in dates
            assert "2024-11-14" in dates

    def test_clear_cache_all(self):
        """Test clearing all cache."""
        with tempfile.TemporaryDirectory() as tmpdir:
            fetcher = HistoricalDataFetcher(cache_dir=Path(tmpdir))

            # Create some cache files
            (Path(tmpdir) / "2024-11-12_abc.json").write_text("{}")
            (Path(tmpdir) / "2024-11-13_def.json").write_text("{}")

            deleted = fetcher.clear_cache()

            assert deleted == 2
            assert len(list(Path(tmpdir).glob("*.json"))) == 0

    def test_clear_cache_specific_date(self):
        """Test clearing cache for specific date."""
        with tempfile.TemporaryDirectory() as tmpdir:
            fetcher = HistoricalDataFetcher(cache_dir=Path(tmpdir))

            # Create some cache files
            (Path(tmpdir) / "2024-11-12_abc.json").write_text("{}")
            (Path(tmpdir) / "2024-11-13_def.json").write_text("{}")

            date = datetime(2024, 11, 12, tzinfo=timezone.utc)
            deleted = fetcher.clear_cache(date)

            assert deleted == 1
            assert (Path(tmpdir) / "2024-11-13_def.json").exists()


class TestCachedDataLoading:
    """Tests for loading cached data files."""

    def test_load_cached_news(self):
        """Test loading news from JSONL file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            fetcher = HistoricalDataFetcher(cache_dir=Path(tmpdir))

            # Create cached news file
            news_file = Path(tmpdir) / "news_2024-11-12.jsonl"
            with open(news_file, "w") as f:
                f.write(json.dumps({"id": "1", "title": "News 1"}) + "\n")
                f.write(json.dumps({"id": "2", "title": "News 2"}) + "\n")

            date = datetime(2024, 11, 12, tzinfo=timezone.utc)
            news = fetcher._load_cached_news(date)

            assert len(news) == 2
            assert news[0]["id"] == "1"
            assert news[1]["id"] == "2"

    def test_load_cached_bars(self):
        """Test loading price bars from JSON file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            fetcher = HistoricalDataFetcher(cache_dir=Path(tmpdir))

            # Create cached bars file
            bars_file = Path(tmpdir) / "prices_2024-11-12_AAPL.json"
            bars = [
                {"timestamp": "2024-11-12T14:30:00", "close": 150.0},
                {"timestamp": "2024-11-12T14:35:00", "close": 151.0},
            ]
            with open(bars_file, "w") as f:
                json.dump(bars, f)

            date = datetime(2024, 11, 12, tzinfo=timezone.utc)
            loaded = fetcher._load_cached_bars("AAPL", date)

            assert len(loaded) == 2
            assert loaded[0]["close"] == 150.0


class TestFetchDayStructure:
    """Tests for fetch_day return structure."""

    @pytest.mark.asyncio
    async def test_fetch_day_returns_expected_structure(self):
        """Test fetch_day returns all expected fields."""
        with tempfile.TemporaryDirectory() as tmpdir:
            fetcher = HistoricalDataFetcher(
                cache_dir=Path(tmpdir),
                price_source="cached",
                news_source="cached",
            )

            date = datetime(2024, 11, 12, tzinfo=timezone.utc)
            result = await fetcher.fetch_day(date)

            # Check all expected keys exist
            assert "date" in result
            assert "fetched_at" in result
            assert "price_bars" in result
            assert "news_items" in result
            assert "sec_filings" in result
            assert "metadata" in result

            # Check types
            assert isinstance(result["price_bars"], dict)
            assert isinstance(result["news_items"], list)
            assert isinstance(result["sec_filings"], list)
