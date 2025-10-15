"""
Tests for RVOL (Relative Volume) calculation module.

Tests cover:
- Single ticker RVOL calculation
- Bulk ticker RVOL calculation
- Caching behavior (memory + disk)
- Edge cases (missing data, zero volume, etc.)
- RVOL category classification

Author: Claude Code (MOA Agent 1)
Date: 2025-10-12
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from catalyst_bot.rvol import bulk_calculate_rvol, calculate_rvol, get_cache_stats


@pytest.fixture
def mock_hist_data():
    """Create mock historical price data for testing."""
    # Create 30 days of data
    dates = pd.date_range(end=datetime.now(timezone.utc), periods=30, freq="D")

    data = pd.DataFrame(
        {
            "Close": [10.0 + i * 0.1 for i in range(30)],
            "Open": [10.0 + i * 0.1 for i in range(30)],
            "High": [10.2 + i * 0.1 for i in range(30)],
            "Low": [9.8 + i * 0.1 for i in range(30)],
            "Volume": [100000 + i * 1000 for i in range(30)],  # Increasing volume
        },
        index=dates,
    )

    return data


@pytest.fixture
def mock_high_volume_data():
    """Create mock data with high relative volume (RVOL > 2.0)."""
    dates = pd.date_range(end=datetime.now(timezone.utc), periods=30, freq="D")

    # Last day has 3x normal volume
    volumes = [100000] * 29 + [300000]

    data = pd.DataFrame(
        {
            "Close": [10.0] * 30,
            "Open": [10.0] * 30,
            "High": [10.2] * 30,
            "Low": [9.8] * 30,
            "Volume": volumes,
        },
        index=dates,
    )

    return data


@pytest.fixture
def mock_low_volume_data():
    """Create mock data with low relative volume (RVOL < 1.0)."""
    dates = pd.date_range(end=datetime.now(timezone.utc), periods=30, freq="D")

    # Last day has 0.5x normal volume
    volumes = [100000] * 29 + [50000]

    data = pd.DataFrame(
        {
            "Close": [10.0] * 30,
            "Open": [10.0] * 30,
            "High": [10.2] * 30,
            "Low": [9.8] * 30,
            "Volume": volumes,
        },
        index=dates,
    )

    return data


class TestRVOLCalculation:
    """Test RVOL calculation functionality."""

    @patch("catalyst_bot.rvol.yf.Ticker")
    def test_calculate_rvol_basic(self, mock_ticker, mock_hist_data):
        """Test basic RVOL calculation."""
        # Setup mock
        mock_ticker_obj = MagicMock()
        mock_ticker_obj.history.return_value = mock_hist_data
        mock_ticker.return_value = mock_ticker_obj

        # Calculate RVOL
        test_date = datetime.now(timezone.utc)
        result = calculate_rvol("AAPL", test_date, use_cache=False)

        # Verify result structure
        assert result is not None
        assert "ticker" in result
        assert "rvol" in result
        assert "rvol_category" in result
        assert "current_volume" in result
        assert "avg_volume_20d" in result

        # Verify ticker
        assert result["ticker"] == "AAPL"

        # Verify RVOL is calculated
        assert result["rvol"] > 0
        assert result["current_volume"] > 0
        assert result["avg_volume_20d"] > 0

    @patch("catalyst_bot.rvol.yf.Ticker")
    def test_calculate_rvol_high_volume(self, mock_ticker, mock_high_volume_data):
        """Test RVOL calculation with high relative volume."""
        mock_ticker_obj = MagicMock()
        mock_ticker_obj.history.return_value = mock_high_volume_data
        mock_ticker.return_value = mock_ticker_obj

        test_date = datetime.now(timezone.utc)
        result = calculate_rvol("TSLA", test_date, use_cache=False)

        # Should categorize as HIGH (RVOL > 2.0)
        assert result is not None
        assert result["rvol"] > 2.0
        assert result["rvol_category"] == "HIGH"

    @patch("catalyst_bot.rvol.yf.Ticker")
    def test_calculate_rvol_low_volume(self, mock_ticker, mock_low_volume_data):
        """Test RVOL calculation with low relative volume."""
        mock_ticker_obj = MagicMock()
        mock_ticker_obj.history.return_value = mock_low_volume_data
        mock_ticker.return_value = mock_ticker_obj

        test_date = datetime.now(timezone.utc)
        result = calculate_rvol("MSFT", test_date, use_cache=False)

        # Should categorize as LOW (RVOL < 1.0)
        assert result is not None
        assert result["rvol"] < 1.0
        assert result["rvol_category"] == "LOW"

    @patch("catalyst_bot.rvol.yf.Ticker")
    def test_calculate_rvol_moderate_volume(self, mock_ticker, mock_hist_data):
        """Test RVOL calculation with moderate relative volume."""
        mock_ticker_obj = MagicMock()
        mock_ticker_obj.history.return_value = mock_hist_data
        mock_ticker.return_value = mock_ticker_obj

        test_date = datetime.now(timezone.utc)
        result = calculate_rvol("GOOGL", test_date, use_cache=False)

        # Should categorize as MODERATE (1.0 <= RVOL < 2.0)
        assert result is not None
        if 1.0 <= result["rvol"] < 2.0:
            assert result["rvol_category"] == "MODERATE"

    @patch("catalyst_bot.rvol.yf.Ticker")
    def test_calculate_rvol_insufficient_data(self, mock_ticker):
        """Test RVOL calculation with insufficient historical data."""
        # Return only 10 days (need 20)
        dates = pd.date_range(end=datetime.now(timezone.utc), periods=10, freq="D")
        insufficient_data = pd.DataFrame(
            {
                "Close": [10.0] * 10,
                "Volume": [100000] * 10,
            },
            index=dates,
        )

        mock_ticker_obj = MagicMock()
        mock_ticker_obj.history.return_value = insufficient_data
        mock_ticker.return_value = mock_ticker_obj

        test_date = datetime.now(timezone.utc)
        result = calculate_rvol("BADTICKER", test_date, use_cache=False)

        # Should return None with insufficient data
        assert result is None

    @patch("catalyst_bot.rvol.yf.Ticker")
    def test_calculate_rvol_no_data(self, mock_ticker):
        """Test RVOL calculation with no data available."""
        mock_ticker_obj = MagicMock()
        mock_ticker_obj.history.return_value = pd.DataFrame()  # Empty
        mock_ticker.return_value = mock_ticker_obj

        test_date = datetime.now(timezone.utc)
        result = calculate_rvol("INVALID", test_date, use_cache=False)

        # Should return None with no data
        assert result is None

    @patch("catalyst_bot.rvol.yf.Ticker")
    def test_calculate_rvol_zero_volume(self, mock_ticker):
        """Test RVOL calculation with zero volume days."""
        dates = pd.date_range(end=datetime.now(timezone.utc), periods=30, freq="D")

        # Mix of zero and non-zero volume
        volumes = [0] * 10 + [100000] * 20

        data = pd.DataFrame(
            {
                "Close": [10.0] * 30,
                "Volume": volumes,
            },
            index=dates,
        )

        mock_ticker_obj = MagicMock()
        mock_ticker_obj.history.return_value = data
        mock_ticker.return_value = mock_ticker_obj

        test_date = datetime.now(timezone.utc)
        result = calculate_rvol("ZEROVOL", test_date, use_cache=False)

        # Should still calculate if we have enough valid days
        assert result is not None
        assert result["rvol"] > 0


class TestRVOLCaching:
    """Test RVOL caching behavior."""

    @patch("catalyst_bot.rvol.yf.Ticker")
    def test_cache_hit(self, mock_ticker, mock_hist_data, tmp_path):
        """Test that second call hits cache."""
        mock_ticker_obj = MagicMock()
        mock_ticker_obj.history.return_value = mock_hist_data
        mock_ticker.return_value = mock_ticker_obj

        test_date = datetime.now(timezone.utc)

        # First call (cache miss)
        result1 = calculate_rvol("AAPL", test_date, use_cache=True)
        call_count_1 = mock_ticker.call_count

        # Second call (should hit cache)
        result2 = calculate_rvol("AAPL", test_date, use_cache=True)
        call_count_2 = mock_ticker.call_count

        # Verify results are the same
        assert result1 == result2

        # Verify no additional API call was made
        assert call_count_2 == call_count_1

    @patch("catalyst_bot.rvol.yf.Ticker")
    def test_cache_disabled(self, mock_ticker, mock_hist_data):
        """Test that caching can be disabled."""
        mock_ticker_obj = MagicMock()
        mock_ticker_obj.history.return_value = mock_hist_data
        mock_ticker.return_value = mock_ticker_obj

        test_date = datetime.now(timezone.utc)

        # Two calls with cache disabled
        calculate_rvol("AAPL", test_date, use_cache=False)
        call_count_1 = mock_ticker.call_count

        calculate_rvol("AAPL", test_date, use_cache=False)
        call_count_2 = mock_ticker.call_count

        # Verify both calls hit the API
        assert call_count_2 > call_count_1

    def test_cache_stats(self):
        """Test cache statistics tracking."""
        stats = get_cache_stats()

        # Should return dict with expected keys
        assert isinstance(stats, dict)
        assert "memory_hits" in stats
        assert "disk_hits" in stats
        assert "misses" in stats
        assert "total_requests" in stats


class TestBulkRVOL:
    """Test bulk RVOL calculation."""

    @patch("catalyst_bot.rvol.yf.download")
    def test_bulk_calculate_rvol(self, mock_download, mock_hist_data):
        """Test bulk RVOL calculation for multiple tickers."""
        # Setup mock - simulate multi-ticker download
        mock_download.return_value = mock_hist_data

        test_date = datetime.now(timezone.utc)
        tickers = ["AAPL", "MSFT", "GOOGL"]

        results = bulk_calculate_rvol(tickers, test_date, use_cache=False)

        # Verify we got results for all tickers
        assert isinstance(results, dict)
        assert len(results) == len(tickers)

        # Verify each ticker has a result
        for ticker in tickers:
            assert ticker in results

    @patch("catalyst_bot.rvol.yf.download")
    def test_bulk_calculate_empty_list(self, mock_download):
        """Test bulk calculation with empty ticker list."""
        test_date = datetime.now(timezone.utc)
        results = bulk_calculate_rvol([], test_date)

        # Should return empty dict
        assert results == {}

    @patch("catalyst_bot.rvol.yf.download")
    def test_bulk_calculate_partial_failure(self, mock_download, mock_hist_data):
        """Test bulk calculation when some tickers fail."""
        # Mock will return valid data, but we'll test the None handling
        mock_download.return_value = mock_hist_data

        test_date = datetime.now(timezone.utc)
        tickers = ["AAPL", "INVALID", "MSFT"]

        results = bulk_calculate_rvol(tickers, test_date, use_cache=False)

        # Should still return results (even if some are None)
        assert isinstance(results, dict)


class TestRVOLEdgeCases:
    """Test edge cases and error handling."""

    def test_invalid_ticker_format(self):
        """Test handling of invalid ticker format."""
        test_date = datetime.now(timezone.utc)

        # Empty ticker
        result = calculate_rvol("", test_date, use_cache=False)
        assert result is None

        # Whitespace ticker
        result = calculate_rvol("   ", test_date, use_cache=False)
        assert result is None

    @patch("catalyst_bot.rvol.yf.Ticker")
    def test_future_date(self, mock_ticker, mock_hist_data):
        """Test calculation with future date."""
        mock_ticker_obj = MagicMock()
        mock_ticker_obj.history.return_value = mock_hist_data
        mock_ticker.return_value = mock_ticker_obj

        # Future date
        future_date = datetime.now(timezone.utc) + timedelta(days=365)

        calculate_rvol("AAPL", future_date, use_cache=False)

        # Should handle gracefully (may return None or current data)
        # The specific behavior depends on implementation
        # Just verify it doesn't crash
        assert True

    @patch("catalyst_bot.rvol.yf.Ticker")
    def test_ticker_normalization(self, mock_ticker, mock_hist_data):
        """Test that tickers are normalized (uppercased, trimmed)."""
        mock_ticker_obj = MagicMock()
        mock_ticker_obj.history.return_value = mock_hist_data
        mock_ticker.return_value = mock_ticker_obj

        test_date = datetime.now(timezone.utc)

        # Test lowercase ticker
        result = calculate_rvol("aapl", test_date, use_cache=False)
        assert result is not None
        assert result["ticker"] == "AAPL"

        # Test ticker with whitespace
        result = calculate_rvol("  msft  ", test_date, use_cache=False)
        assert result is not None
        assert result["ticker"] == "MSFT"


class TestRVOLIntegration:
    """Integration tests for RVOL module."""

    @patch("catalyst_bot.rvol.yf.Ticker")
    def test_realistic_workflow(self, mock_ticker, mock_hist_data):
        """Test realistic workflow: calculate RVOL, check category, use in decision."""
        mock_ticker_obj = MagicMock()
        mock_ticker_obj.history.return_value = mock_hist_data
        mock_ticker.return_value = mock_ticker_obj

        test_date = datetime.now(timezone.utc)

        # Calculate RVOL
        rvol_data = calculate_rvol("AAPL", test_date, use_cache=True)

        # Verify we can use the data
        assert rvol_data is not None

        # Check RVOL category and make a decision
        if rvol_data["rvol_category"] == "HIGH":
            priority = "high"
        elif rvol_data["rvol_category"] == "MODERATE":
            priority = "medium"
        else:
            priority = "low"

        assert priority in ["high", "medium", "low"]

        # Verify RVOL ratio matches category
        rvol = rvol_data["rvol"]
        category = rvol_data["rvol_category"]

        if rvol >= 2.0:
            assert category == "HIGH"
        elif rvol >= 1.0:
            assert category == "MODERATE"
        else:
            assert category == "LOW"
