"""Test suite for WAVE 3: Float Data Robustness.

Tests the enhanced float data module with multi-source fetching, caching,
validation, and graceful error handling.
"""

from __future__ import annotations

import json
import os
import tempfile
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from catalyst_bot.float_data import (
    DEFAULT_CACHE_TTL_HOURS,
    MAX_VALID_FLOAT,
    MIN_VALID_FLOAT,
    get_cache_path,
    get_float_data,
    is_cache_fresh,
    validate_float_value,
    _fetch_tiingo,
    _fetch_yfinance,
    _get_from_cache,
    _save_to_cache,
    classify_float,
    get_float_multiplier,
    scrape_finviz,
)


class TestFloatValidation:
    """Test float data validation logic."""

    def test_validate_valid_float(self):
        """Valid float values should pass validation."""
        assert validate_float_value(5_000_000) is True  # 5M shares
        assert validate_float_value(20_000_000) is True  # 20M shares
        assert validate_float_value(1_000_000_000) is True  # 1B shares

    def test_validate_boundary_values(self):
        """Boundary values should be validated correctly."""
        assert validate_float_value(MIN_VALID_FLOAT) is True  # Minimum valid
        assert validate_float_value(MIN_VALID_FLOAT - 1) is False  # Below minimum
        assert validate_float_value(MAX_VALID_FLOAT) is True  # Maximum valid
        assert validate_float_value(MAX_VALID_FLOAT + 1) is False  # Above maximum

    def test_validate_invalid_float(self):
        """Invalid float values should fail validation."""
        assert validate_float_value(None) is False  # Null
        assert validate_float_value(0) is False  # Zero
        assert validate_float_value(-1000) is False  # Negative
        assert validate_float_value(1) is False  # Too small (1 share)
        assert validate_float_value(999_999_999_999_999) is False  # Too large

    def test_validate_type_coercion(self):
        """Should handle different numeric types."""
        assert validate_float_value(5000000.0) is True  # Float
        assert validate_float_value(5000000) is True  # Int
        assert validate_float_value("invalid") is False  # String


class TestCacheFreshness:
    """Test cache freshness validation."""

    def test_fresh_cache(self):
        """Recently cached data should be considered fresh."""
        now = datetime.now(timezone.utc)
        cached_at = now.isoformat()
        assert is_cache_fresh(cached_at, max_age_hours=24) is True

    def test_expired_cache(self):
        """Old cached data should be considered stale."""
        old_time = datetime.now(timezone.utc) - timedelta(hours=25)
        cached_at = old_time.isoformat()
        assert is_cache_fresh(cached_at, max_age_hours=24) is False

    def test_cache_boundary(self):
        """Cache should expire exactly at TTL boundary."""
        # Cached exactly 24 hours ago (on the boundary)
        boundary_time = datetime.now(timezone.utc) - timedelta(hours=24, seconds=1)
        cached_at = boundary_time.isoformat()
        assert is_cache_fresh(cached_at, max_age_hours=24) is False

    def test_custom_ttl(self):
        """Should respect custom TTL values."""
        # Cached 2 hours ago
        two_hours_ago = datetime.now(timezone.utc) - timedelta(hours=2)
        cached_at = two_hours_ago.isoformat()

        # Should be fresh with 3-hour TTL
        assert is_cache_fresh(cached_at, max_age_hours=3) is True

        # Should be stale with 1-hour TTL
        assert is_cache_fresh(cached_at, max_age_hours=1) is False

    def test_invalid_timestamp(self):
        """Invalid timestamps should be considered stale."""
        assert is_cache_fresh("invalid-timestamp") is False
        assert is_cache_fresh("") is False
        assert is_cache_fresh(None) is False


class TestCacheOperations:
    """Test cache read/write operations."""

    def test_cache_save_and_load(self):
        """Should save and load cache data correctly."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Mock cache path
            with patch("catalyst_bot.float_data.get_cache_path") as mock_path:
                cache_file = Path(tmpdir) / "float_cache.json"
                mock_path.return_value = cache_file

                # Save test data
                test_data = {
                    "ticker": "AAPL",
                    "float_shares": 15_500_000_000,
                    "cached_at": datetime.now(timezone.utc).isoformat(),
                    "source": "finviz",
                    "success": True,
                }
                _save_to_cache("AAPL", test_data)

                # Verify file was created
                assert cache_file.exists()

                # Load data back
                loaded_data = _get_from_cache("AAPL")
                assert loaded_data is not None
                assert loaded_data["ticker"] == "AAPL"
                assert loaded_data["float_shares"] == 15_500_000_000
                assert loaded_data["source"] == "finviz"

    def test_cache_miss(self):
        """Should return None for cache miss."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("catalyst_bot.float_data.get_cache_path") as mock_path:
                cache_file = Path(tmpdir) / "float_cache.json"
                mock_path.return_value = cache_file

                # Cache doesn't exist yet
                result = _get_from_cache("TSLA")
                assert result is None

    def test_cache_expired_data(self):
        """Should return None for expired cache data."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("catalyst_bot.float_data.get_cache_path") as mock_path:
                cache_file = Path(tmpdir) / "float_cache.json"
                mock_path.return_value = cache_file

                # Save old data
                old_time = datetime.now(timezone.utc) - timedelta(hours=30)
                test_data = {
                    "ticker": "TSLA",
                    "float_shares": 3_200_000_000,
                    "cached_at": old_time.isoformat(),
                    "source": "yfinance",
                    "success": True,
                }
                _save_to_cache("TSLA", test_data)

                # Mock settings to use 24-hour TTL
                with patch("catalyst_bot.float_data.get_settings") as mock_settings:
                    settings = Mock()
                    settings.float_cache_max_age_hours = 24
                    mock_settings.return_value = settings

                    # Should return None (expired)
                    result = _get_from_cache("TSLA")
                    assert result is None

    def test_cache_invalid_data_rejection(self):
        """Should reject cached data with invalid float values."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("catalyst_bot.float_data.get_cache_path") as mock_path:
                cache_file = Path(tmpdir) / "float_cache.json"
                mock_path.return_value = cache_file

                # Save data with invalid float
                test_data = {
                    "ticker": "INVALID",
                    "float_shares": 1,  # Too small to be valid
                    "cached_at": datetime.now(timezone.utc).isoformat(),
                    "source": "finviz",
                    "success": True,
                }
                _save_to_cache("INVALID", test_data)

                # Should return None (invalid data)
                result = _get_from_cache("INVALID")
                assert result is None


class TestMultiSourceFallback:
    """Test cascading fallback across multiple sources."""

    @patch("catalyst_bot.float_data.scrape_finviz")
    @patch("catalyst_bot.float_data._fetch_yfinance")
    @patch("catalyst_bot.float_data._fetch_tiingo")
    @patch("catalyst_bot.float_data._get_from_cache")
    @patch("catalyst_bot.float_data._save_to_cache")
    def test_finviz_primary_success(self, mock_save, mock_cache, mock_tiingo, mock_yf, mock_finviz):
        """Should use FinViz data when available."""
        # Cache miss
        mock_cache.return_value = None

        # FinViz succeeds
        mock_finviz.return_value = {
            "float_shares": 5_000_000,
            "source": "finviz",
            "success": True,
        }

        result = get_float_data("TEST")

        # Should use FinViz data
        assert result["source"] == "finviz"
        assert result["float_shares"] == 5_000_000

        # Should not try fallback sources
        mock_yf.assert_not_called()
        mock_tiingo.assert_not_called()

    @patch("catalyst_bot.float_data.scrape_finviz")
    @patch("catalyst_bot.float_data._fetch_yfinance")
    @patch("catalyst_bot.float_data._fetch_tiingo")
    @patch("catalyst_bot.float_data._get_from_cache")
    @patch("catalyst_bot.float_data._save_to_cache")
    def test_yfinance_fallback(self, mock_save, mock_cache, mock_tiingo, mock_yf, mock_finviz):
        """Should fallback to yfinance when FinViz fails."""
        # Cache miss
        mock_cache.return_value = None

        # FinViz fails
        mock_finviz.return_value = {
            "float_shares": None,
            "source": "finviz",
            "success": False,
            "error": "HTTP 403",
        }

        # yfinance succeeds
        mock_yf.return_value = {
            "float_shares": 6_000_000,
            "source": "yfinance",
            "success": True,
        }

        result = get_float_data("TEST")

        # Should use yfinance data
        assert result["source"] == "yfinance"
        assert result["float_shares"] == 6_000_000

        # Should not try Tiingo (yfinance succeeded)
        mock_tiingo.assert_not_called()

    @patch("catalyst_bot.float_data.scrape_finviz")
    @patch("catalyst_bot.float_data._fetch_yfinance")
    @patch("catalyst_bot.float_data._fetch_tiingo")
    @patch("catalyst_bot.float_data._get_from_cache")
    @patch("catalyst_bot.float_data._save_to_cache")
    def test_tiingo_fallback(self, mock_save, mock_cache, mock_tiingo, mock_yf, mock_finviz):
        """Should fallback to Tiingo when FinViz and yfinance fail."""
        # Cache miss
        mock_cache.return_value = None

        # FinViz fails
        mock_finviz.return_value = {
            "float_shares": None,
            "source": "finviz",
            "success": False,
        }

        # yfinance fails
        mock_yf.return_value = {
            "float_shares": None,
            "source": "yfinance",
            "success": False,
            "error": "yfinance not installed",
        }

        # Tiingo succeeds
        mock_tiingo.return_value = {
            "float_shares": 7_000_000,
            "source": "tiingo",
            "success": True,
        }

        result = get_float_data("TEST")

        # Should use Tiingo data
        assert result["source"] == "tiingo"
        assert result["float_shares"] == 7_000_000

    @patch("catalyst_bot.float_data.scrape_finviz")
    @patch("catalyst_bot.float_data._fetch_yfinance")
    @patch("catalyst_bot.float_data._fetch_tiingo")
    @patch("catalyst_bot.float_data._get_from_cache")
    @patch("catalyst_bot.float_data._save_to_cache")
    def test_all_sources_fail(self, mock_save, mock_cache, mock_tiingo, mock_yf, mock_finviz):
        """Should handle gracefully when all sources fail."""
        # Cache miss
        mock_cache.return_value = None

        # All sources fail
        mock_finviz.return_value = {
            "float_shares": None,
            "source": "finviz",
            "success": False,
        }
        mock_yf.return_value = {
            "float_shares": None,
            "source": "yfinance",
            "success": False,
        }
        mock_tiingo.return_value = {
            "float_shares": None,
            "source": "tiingo",
            "success": False,
        }

        result = get_float_data("TEST")

        # Should return UNKNOWN classification
        assert result["float_shares"] is None
        assert result["float_class"] == "UNKNOWN"
        assert result["multiplier"] == 1.0
        assert result["success"] is False

        # Should still save to cache (to avoid hammering sources)
        mock_save.assert_called_once()


class TestFloatClassification:
    """Test float size classification."""

    def test_micro_float(self):
        """Floats <5M should be classified as MICRO_FLOAT."""
        assert classify_float(1_000_000) == "MICRO_FLOAT"
        assert classify_float(4_999_999) == "MICRO_FLOAT"
        assert get_float_multiplier(1_000_000) == 1.3

    def test_low_float(self):
        """Floats 5M-20M should be classified as LOW_FLOAT."""
        assert classify_float(5_000_000) == "LOW_FLOAT"
        assert classify_float(19_999_999) == "LOW_FLOAT"
        assert get_float_multiplier(10_000_000) == 1.2

    def test_medium_float(self):
        """Floats 20M-50M should be classified as MEDIUM_FLOAT."""
        assert classify_float(20_000_000) == "MEDIUM_FLOAT"
        assert classify_float(49_999_999) == "MEDIUM_FLOAT"
        assert get_float_multiplier(30_000_000) == 1.0

    def test_high_float(self):
        """Floats >50M should be classified as HIGH_FLOAT."""
        assert classify_float(50_000_000) == "HIGH_FLOAT"
        assert classify_float(1_000_000_000) == "HIGH_FLOAT"
        assert get_float_multiplier(100_000_000) == 0.9

    def test_unknown_float(self):
        """None/invalid floats should be classified as UNKNOWN."""
        assert classify_float(None) == "UNKNOWN"
        assert classify_float(0) == "UNKNOWN"
        assert classify_float(-1000) == "UNKNOWN"
        assert get_float_multiplier(None) == 1.0


class TestConcurrency:
    """Test thread-safety of cache operations."""

    @patch("catalyst_bot.float_data.get_cache_path")
    def test_concurrent_cache_access(self, mock_path):
        """Multiple concurrent cache operations should not corrupt data."""
        import threading

        with tempfile.TemporaryDirectory() as tmpdir:
            cache_file = Path(tmpdir) / "float_cache.json"
            mock_path.return_value = cache_file

            def write_ticker(ticker_num):
                """Write ticker data to cache."""
                data = {
                    "ticker": f"TEST{ticker_num}",
                    "float_shares": ticker_num * 1_000_000,
                    "cached_at": datetime.now(timezone.utc).isoformat(),
                    "source": "test",
                    "success": True,
                }
                _save_to_cache(f"TEST{ticker_num}", data)

            # Create 10 threads writing concurrently
            threads = []
            for i in range(10):
                t = threading.Thread(target=write_ticker, args=(i,))
                threads.append(t)
                t.start()

            # Wait for all threads to complete
            for t in threads:
                t.join()

            # Verify all data was written
            with open(cache_file, "r") as f:
                cache = json.load(f)
                assert len(cache) == 10
                for i in range(10):
                    assert f"TEST{i}" in cache


class TestErrorHandling:
    """Test graceful error handling."""

    @patch("catalyst_bot.float_data._get_from_cache")
    def test_cache_read_error_graceful(self, mock_cache):
        """Should handle cache read errors gracefully."""
        # Cache throws exception
        mock_cache.side_effect = Exception("Disk error")

        # Should not crash - will try to fetch from sources
        with patch("catalyst_bot.float_data.scrape_finviz") as mock_finviz:
            mock_finviz.return_value = {
                "float_shares": 5_000_000,
                "source": "finviz",
                "success": True,
            }

            with patch("catalyst_bot.float_data._save_to_cache"):
                result = get_float_data("TEST")
                assert result["float_shares"] == 5_000_000

    def test_invalid_json_cache(self):
        """Should handle corrupted cache file gracefully."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("catalyst_bot.float_data.get_cache_path") as mock_path:
                cache_file = Path(tmpdir) / "float_cache.json"
                mock_path.return_value = cache_file

                # Write invalid JSON
                cache_file.write_text("{ invalid json }")

                # Should not crash
                result = _get_from_cache("TEST")
                assert result is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
