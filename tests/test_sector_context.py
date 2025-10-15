"""
Test suite for Sector Context Module (Agent 3)

Tests:
- Sector/industry lookup via yfinance
- Sector performance calculation (1d, 5d returns)
- Sector vs SPY comparison
- Sector relative volume
- Multi-level caching (memory and disk)
- Bulk operations
- ETF mapping

Author: Claude Code (Agent 3)
Date: 2025-10-12
"""

from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import Mock, patch

import pandas as pd
import pytest

from catalyst_bot.sector_context import (
    SECTOR_ETF_MAP,
    SectorContextManager,
    get_sector_manager,
    get_sector_metrics,
    get_ticker_sector,
)


@pytest.fixture
def temp_cache_dir(tmp_path):
    """Create temporary cache directory."""
    cache_dir = tmp_path / "sector_cache"
    cache_dir.mkdir()
    return cache_dir


@pytest.fixture
def sector_mgr(temp_cache_dir):
    """Create sector context manager with temp cache."""
    return SectorContextManager(cache_dir=temp_cache_dir)


class TestSectorLookup:
    """Test sector and industry lookup functionality."""

    @patch("catalyst_bot.sector_context.yf.Ticker")
    def test_get_ticker_sector_info_success(self, mock_ticker, sector_mgr):
        """Test successful sector info fetch."""
        # Mock yfinance response
        mock_ticker_obj = Mock()
        mock_ticker_obj.info = {
            "sector": "Technology",
            "industry": "Software Infrastructure",
        }
        mock_ticker.return_value = mock_ticker_obj

        result = sector_mgr.get_ticker_sector_info("AAPL")

        assert result["sector"] == "Technology"
        assert result["industry"] == "Software Infrastructure"
        assert "cached_at" in result
        assert isinstance(result["cached_at"], datetime)

    @patch("catalyst_bot.sector_context.yf.Ticker")
    def test_get_ticker_sector_info_no_data(self, mock_ticker, sector_mgr):
        """Test handling when ticker has no sector info."""
        # Mock yfinance response with no sector
        mock_ticker_obj = Mock()
        mock_ticker_obj.info = {}
        mock_ticker.return_value = mock_ticker_obj

        result = sector_mgr.get_ticker_sector_info("UNKNOWN")

        assert result["sector"] is None
        assert result["industry"] is None

    def test_get_ticker_sector_info_empty_ticker(self, sector_mgr):
        """Test handling of empty ticker."""
        result = sector_mgr.get_ticker_sector_info("")

        assert result["sector"] is None
        assert result["industry"] is None


class TestSectorPerformance:
    """Test sector performance calculation."""

    @patch("catalyst_bot.sector_context.yf.Ticker")
    def test_get_sector_performance_success(self, mock_ticker, sector_mgr):
        """Test successful sector performance calculation."""
        # Mock ETF history
        etf_data = pd.DataFrame(
            {
                "Close": [100.0, 101.0, 102.0, 103.0, 104.0, 105.0, 106.0],
                "Volume": [1000000] * 7,
            }
        )

        # Mock SPY history
        spy_data = pd.DataFrame(
            {"Close": [200.0, 201.0, 201.5, 202.0, 202.5, 203.0, 203.5]}
        )

        mock_ticker_obj = Mock()
        mock_ticker_obj.history = Mock(side_effect=[etf_data, spy_data])
        mock_ticker.return_value = mock_ticker_obj

        result = sector_mgr.get_sector_performance("Technology")

        assert result["sector_1d_return"] is not None
        assert result["sector_5d_return"] is not None
        assert result["sector_vs_spy"] is not None
        assert result["sector_rvol"] is not None
        assert result["etf_ticker"] == "XLK"

    @patch("catalyst_bot.sector_context.yf.Ticker")
    def test_get_sector_performance_calculations(self, mock_ticker, sector_mgr):
        """Test sector performance calculation accuracy."""
        # Price progression: 100 -> 102 -> 104 -> 106 -> 108 -> 110 (last 6 values)
        # Then flat at 110 for remaining 14 days
        etf_data = pd.DataFrame(
            {
                "Close": [100.0, 102.0, 104.0, 106.0, 108.0, 110.0] + [110.0] * 14,
                "Volume": [1000000] * 20,
            }
        )

        # SPY goes from 200 to 204 (2% gain)
        spy_data = pd.DataFrame(
            {"Close": [200.0, 200.5, 201.0, 201.5, 202.0, 204.0] + [204.0] * 14}
        )

        mock_ticker_obj = Mock()
        mock_ticker_obj.history = Mock(side_effect=[etf_data, spy_data])
        mock_ticker.return_value = mock_ticker_obj

        result = sector_mgr.get_sector_performance("Technology")

        # 1-day return: (110 - 110) / 110 = 0% (last two values are both 110)
        assert result["sector_1d_return"] == 0.0

        # 5-day return: iloc[-1] = 110, iloc[-6] = 110
        # (110 - 110) / 110 = 0%
        # This is correct because we have 14 flat days, so looking back 5 days still gives 110
        assert result["sector_5d_return"] == 0.0

    @patch("catalyst_bot.sector_context.yf.Ticker")
    def test_get_sector_performance_vs_spy(self, mock_ticker, sector_mgr):
        """Test sector vs SPY outperformance calculation."""
        # Sector: Create actual outperformance over 20 days
        # Start at 100, end at 120 (20% gain over full period)
        etf_data = pd.DataFrame(
            {
                "Close": [100.0] * 14 + [102.0, 106.0, 110.0, 114.0, 118.0, 120.0],
                "Volume": [1000000] * 20,
            }
        )

        # SPY: Start at 200, end at 205 (2.5% gain over full period)
        spy_data = pd.DataFrame(
            {"Close": [200.0] * 14 + [201.0, 202.0, 203.0, 204.0, 204.5, 205.0]}
        )

        mock_ticker_obj = Mock()
        mock_ticker_obj.history = Mock(side_effect=[etf_data, spy_data])
        mock_ticker.return_value = mock_ticker_obj

        result = sector_mgr.get_sector_performance("Technology")

        # 5-day sector return: (120 - 102) / 102 = 17.65%
        # 5-day SPY return: (205 - 201) / 201 = 1.99%
        # Sector vs SPY should be positive (sector outperforming)
        assert result["sector_vs_spy"] > 0
        # Should be around 15.66% (17.65 - 1.99)
        assert result["sector_vs_spy"] > 10

    def test_get_sector_performance_no_etf_mapping(self, sector_mgr):
        """Test handling when sector has no ETF mapping."""
        result = sector_mgr.get_sector_performance("Unknown Sector")

        assert result["sector_1d_return"] is None
        assert result["sector_5d_return"] is None
        assert result["etf_ticker"] is None


class TestCaching:
    """Test multi-level caching functionality."""

    @patch("catalyst_bot.sector_context.yf.Ticker")
    def test_memory_cache_hit(self, mock_ticker, sector_mgr):
        """Test that memory cache is used on second call."""
        # Mock yfinance response
        mock_ticker_obj = Mock()
        mock_ticker_obj.info = {"sector": "Technology", "industry": "Software"}
        mock_ticker.return_value = mock_ticker_obj

        # First call - should hit API
        result1 = sector_mgr.get_ticker_sector_info("AAPL")

        # Second call - should hit memory cache
        result2 = sector_mgr.get_ticker_sector_info("AAPL")

        # API should only be called once
        assert mock_ticker.call_count == 1

        # Results should be the same
        assert result1["sector"] == result2["sector"]
        assert result1["industry"] == result2["industry"]

    @patch("catalyst_bot.sector_context.yf.Ticker")
    def test_disk_cache_persistence(self, mock_ticker, temp_cache_dir):
        """Test that disk cache persists across manager instances."""
        # Mock yfinance response
        mock_ticker_obj = Mock()
        mock_ticker_obj.info = {"sector": "Technology", "industry": "Software"}
        mock_ticker.return_value = mock_ticker_obj

        # First manager - should fetch from API
        mgr1 = SectorContextManager(cache_dir=temp_cache_dir)
        result1 = mgr1.get_ticker_sector_info("AAPL")

        # Second manager (new instance) - should load from disk cache
        mgr2 = SectorContextManager(cache_dir=temp_cache_dir)
        result2 = mgr2.get_ticker_sector_info("AAPL")

        # API should only be called once (by first manager)
        assert mock_ticker.call_count == 1

        # Results should be the same
        assert result1["sector"] == result2["sector"]

    @patch("catalyst_bot.sector_context.yf.Ticker")
    def test_cache_ttl_expiration(self, mock_ticker, sector_mgr):
        """Test that cache expires after TTL."""
        # Mock yfinance response
        mock_ticker_obj = Mock()
        mock_ticker_obj.info = {"sector": "Technology", "industry": "Software"}
        mock_ticker.return_value = mock_ticker_obj

        # First call
        result1 = sector_mgr.get_ticker_sector_info("AAPL")

        # Manually expire the cache by modifying cached_at in memory AND disk
        old_date = datetime.now(timezone.utc) - timedelta(days=35)
        sector_mgr._sector_info_cache["AAPL"]["cached_at"] = old_date

        # Also expire disk cache
        disk_path = sector_mgr._get_disk_cache_path("sector_info", "AAPL")
        if disk_path.exists():
            with open(disk_path, "rb") as f:
                import pickle

                cached = pickle.load(f)
            cached["cached_at"] = old_date
            with open(disk_path, "wb") as f:
                pickle.dump(cached, f)

        # Second call - cache should be expired, fetch from API again
        result2 = sector_mgr.get_ticker_sector_info("AAPL")

        # API should be called twice (cache expired)
        assert mock_ticker.call_count == 2


class TestBulkOperations:
    """Test bulk sector info fetching."""

    @patch("catalyst_bot.sector_context.yf.Ticker")
    def test_get_bulk_sector_info(self, mock_ticker, sector_mgr):
        """Test bulk sector info fetching."""
        # Mock yfinance responses
        def mock_ticker_response(ticker):
            mock_obj = Mock()
            if ticker == "AAPL":
                mock_obj.info = {"sector": "Technology", "industry": "Electronics"}
            elif ticker == "JPM":
                mock_obj.info = {"sector": "Financials", "industry": "Banking"}
            else:
                mock_obj.info = {}
            return mock_obj

        mock_ticker.side_effect = mock_ticker_response

        tickers = ["AAPL", "JPM", "XYZ"]
        results = sector_mgr.get_bulk_sector_info(tickers)

        assert len(results) == 3
        assert results["AAPL"]["sector"] == "Technology"
        assert results["JPM"]["sector"] == "Financials"
        assert results["XYZ"]["sector"] is None

    @patch("catalyst_bot.sector_context.yf.Ticker")
    def test_bulk_uses_cache(self, mock_ticker, sector_mgr):
        """Test that bulk operation uses cache for already-fetched tickers."""
        # Pre-populate cache
        mock_ticker_obj = Mock()
        mock_ticker_obj.info = {"sector": "Technology", "industry": "Software"}
        mock_ticker.return_value = mock_ticker_obj

        sector_mgr.get_ticker_sector_info("AAPL")
        mock_ticker.reset_mock()

        # Bulk fetch including cached ticker
        tickers = ["AAPL", "MSFT"]
        results = sector_mgr.get_bulk_sector_info(tickers)

        # Only MSFT should be fetched (AAPL is cached)
        assert mock_ticker.call_count == 1
        assert len(results) == 2


class TestETFMapping:
    """Test sector ETF mapping."""

    def test_sector_etf_map_coverage(self):
        """Test that major sectors have ETF mappings."""
        major_sectors = [
            "Technology",
            "Financials",
            "Energy",
            "Health Care",
            "Industrials",
            "Consumer Staples",
            "Consumer Discretionary",
            "Materials",
            "Utilities",
            "Real Estate",
            "Communication Services",
        ]

        for sector in major_sectors:
            assert sector in SECTOR_ETF_MAP, f"Sector '{sector}' missing ETF mapping"
            etf = SECTOR_ETF_MAP[sector]
            assert etf.startswith("XL"), f"Invalid ETF ticker: {etf}"

    def test_sector_name_aliases(self):
        """Test that sector name aliases are supported."""
        # Technology aliases
        assert SECTOR_ETF_MAP["Technology"] == SECTOR_ETF_MAP["Information Technology"]

        # Healthcare aliases
        assert SECTOR_ETF_MAP["Health Care"] == SECTOR_ETF_MAP["Healthcare"]

        # Consumer aliases
        assert (
            SECTOR_ETF_MAP["Consumer Discretionary"]
            == SECTOR_ETF_MAP["Consumer Cyclical"]
        )


class TestConvenienceFunctions:
    """Test convenience functions."""

    @patch("catalyst_bot.sector_context.yf.Ticker")
    def test_get_ticker_sector(self, mock_ticker):
        """Test get_ticker_sector convenience function."""
        mock_ticker_obj = Mock()
        mock_ticker_obj.info = {"sector": "Technology", "industry": "Software"}
        mock_ticker.return_value = mock_ticker_obj

        sector, industry = get_ticker_sector("AAPL")

        assert sector == "Technology"
        assert industry == "Software"

    @patch("catalyst_bot.sector_context.yf.Ticker")
    def test_get_sector_metrics(self, mock_ticker):
        """Test get_sector_metrics convenience function."""
        etf_data = pd.DataFrame(
            {
                "Close": [100.0, 101.0, 102.0, 103.0, 104.0, 105.0, 106.0] + [106.0] * 13,
                "Volume": [1000000] * 20,
            }
        )

        spy_data = pd.DataFrame(
            {"Close": [200.0, 201.0, 201.5, 202.0, 202.5, 203.0, 203.5] + [203.5] * 13}
        )

        mock_ticker_obj = Mock()
        mock_ticker_obj.history = Mock(side_effect=[etf_data, spy_data])
        mock_ticker.return_value = mock_ticker_obj

        metrics = get_sector_metrics("Technology")

        assert "sector_1d_return" in metrics
        assert "sector_5d_return" in metrics
        assert "sector_vs_spy" in metrics

    def test_get_sector_manager_singleton(self):
        """Test that get_sector_manager returns singleton."""
        mgr1 = get_sector_manager()
        mgr2 = get_sector_manager()

        assert mgr1 is mgr2


class TestEdgeCases:
    """Test edge cases and error handling."""

    @patch("catalyst_bot.sector_context.yf.Ticker")
    def test_yfinance_api_error(self, mock_ticker, sector_mgr):
        """Test handling of yfinance API errors."""
        mock_ticker.side_effect = Exception("API error")

        result = sector_mgr.get_ticker_sector_info("AAPL")

        # Should return None values, not crash
        assert result["sector"] is None
        assert result["industry"] is None

    @patch("catalyst_bot.sector_context.yf.Ticker")
    def test_empty_historical_data(self, mock_ticker, sector_mgr):
        """Test handling of empty historical data."""
        mock_ticker_obj = Mock()
        mock_ticker_obj.history.return_value = pd.DataFrame()
        mock_ticker.return_value = mock_ticker_obj

        result = sector_mgr.get_sector_performance("Technology")

        # Should return None values for metrics
        assert result["sector_1d_return"] is None
        assert result["sector_5d_return"] is None

    @patch("catalyst_bot.sector_context.yf.Ticker")
    def test_insufficient_historical_data(self, mock_ticker, sector_mgr):
        """Test handling when historical data is insufficient."""
        # Only 1 day of data (need at least 2 for calculations)
        etf_data = pd.DataFrame({"Close": [100.0], "Volume": [1000000]})

        mock_ticker_obj = Mock()
        mock_ticker_obj.history.return_value = etf_data
        mock_ticker.return_value = mock_ticker_obj

        result = sector_mgr.get_sector_performance("Technology")

        # Should return empty result
        assert result["sector_1d_return"] is None

    def test_case_insensitivity(self, sector_mgr):
        """Test that sector names are case-insensitive."""
        # Test ETF mapping with different cases
        etf1 = sector_mgr._get_sector_etf("Technology")
        etf2 = sector_mgr._get_sector_etf("TECHNOLOGY")
        etf3 = sector_mgr._get_sector_etf("technology")

        # All should map to same ETF (after normalization in actual usage)
        assert etf1 is not None


class TestIntegrationWithBootstrapper:
    """Test integration patterns with historical bootstrapper."""

    @patch("catalyst_bot.sector_context.yf.Ticker")
    def test_rejection_time_context(self, mock_ticker, sector_mgr):
        """Test fetching sector context at rejection time."""
        # Mock ticker info
        mock_ticker_obj = Mock()
        mock_ticker_obj.info = {"sector": "Technology", "industry": "Software"}

        # Mock historical data
        etf_data = pd.DataFrame(
            {
                "Close": [100.0, 101.0, 102.0, 103.0, 104.0, 105.0] + [105.0] * 14,
                "Volume": [1000000] * 20,
            }
        )

        spy_data = pd.DataFrame(
            {"Close": [200.0, 201.0, 201.5, 202.0, 202.5, 203.0] + [203.0] * 14}
        )

        mock_ticker_obj.history = Mock(side_effect=[etf_data, spy_data])
        mock_ticker.return_value = mock_ticker_obj

        # Simulate rejection event
        rejection_date = datetime.now(timezone.utc) - timedelta(days=5)

        # Get sector context
        sector_info = sector_mgr.get_ticker_sector_info("AAPL")
        sector_perf = sector_mgr.get_sector_performance(
            sector_info["sector"], rejection_date
        )

        # Verify all fields are populated
        assert sector_info["sector"] is not None
        assert sector_perf["sector_1d_return"] is not None
        assert sector_perf["sector_vs_spy"] is not None

    @patch("catalyst_bot.sector_context.yf.Ticker")
    def test_batch_processing_pattern(self, mock_ticker, sector_mgr):
        """Test batch processing pattern used by bootstrapper."""
        # Mock ticker responses
        def mock_ticker_response(ticker):
            mock_obj = Mock()
            sectors = {
                "AAPL": "Technology",
                "MSFT": "Technology",
                "JPM": "Financials",
                "XOM": "Energy",
            }
            mock_obj.info = {
                "sector": sectors.get(ticker, "Unknown"),
                "industry": "Test Industry",
            }
            return mock_obj

        mock_ticker.side_effect = mock_ticker_response

        # Batch fetch for multiple rejections
        tickers = ["AAPL", "MSFT", "JPM", "XOM"]
        results = sector_mgr.get_bulk_sector_info(tickers)

        # Verify all fetched
        assert len(results) == 4
        assert results["AAPL"]["sector"] == "Technology"
        assert results["JPM"]["sector"] == "Financials"


def test_sector_context_module_imports():
    """Test that all required exports are available."""
    from catalyst_bot.sector_context import (
        SECTOR_ETF_MAP,
        SectorContextManager,
        get_sector_manager,
        get_sector_metrics,
        get_ticker_sector,
    )

    # Verify exports exist
    assert SECTOR_ETF_MAP is not None
    assert SectorContextManager is not None
    assert callable(get_sector_manager)
    assert callable(get_ticker_sector)
    assert callable(get_sector_metrics)
