"""Tests for ticker validation against official exchange lists."""

import logging
from unittest.mock import MagicMock, patch

import pytest

from catalyst_bot.ticker_validation import TickerValidator


class TestTickerValidator:
    """Test suite for TickerValidator class."""

    def test_valid_tickers_pass_validation(self):
        """Test that real tickers from major exchanges pass validation."""
        validator = TickerValidator()

        # Should always have tickers (either from library or fallback)
        assert validator.is_enabled, "Validator should have tickers loaded"

        # Test common tickers that should always be valid (in fallback list)
        valid_tickers = ["AAPL", "TSLA", "MSFT", "GOOGL", "AMZN", "META", "NVDA"]

        for ticker in valid_tickers:
            assert validator.is_valid(ticker), f"Expected {ticker} to be valid"
            assert validator.validate_and_log(
                ticker, "test_source"
            ), f"Expected {ticker} to pass validation"

    def test_invalid_tickers_fail_validation(self):
        """Test that fake/invalid tickers fail validation."""
        validator = TickerValidator()

        # Should always have tickers (either from library or fallback)
        assert validator.is_enabled, "Validator should have tickers loaded"

        # Test obviously invalid tickers
        invalid_tickers = ["FAKE", "XXXX", "ZZZ999", "NOTREAL", "ABC123"]

        for ticker in invalid_tickers:
            assert not validator.is_valid(ticker), f"Expected {ticker} to be invalid"
            assert not validator.validate_and_log(
                ticker, "test_source"
            ), f"Expected {ticker} to fail validation"

    def test_case_insensitive_validation(self):
        """Test that validation is case-insensitive."""
        validator = TickerValidator()

        # Should always have tickers (either from library or fallback)
        assert validator.is_enabled, "Validator should have tickers loaded"

        # Test various case combinations
        test_cases = [
            ("aapl", "AAPL"),
            ("AaPl", "AAPL"),
            ("tsla", "TSLA"),
            ("TsLa", "TSLA"),
        ]

        for lowercase_ticker, uppercase_ticker in test_cases:
            # Both should have the same validation result
            assert validator.is_valid(lowercase_ticker) == validator.is_valid(
                uppercase_ticker
            ), f"Case sensitivity mismatch for {lowercase_ticker}/{uppercase_ticker}"

    def test_empty_and_none_inputs(self):
        """Test that validator handles empty/None inputs gracefully."""
        validator = TickerValidator()

        # Empty string should return False
        assert not validator.validate_and_log("", "test_source")

        # None should return False
        assert not validator.validate_and_log(None, "test_source")  # type: ignore

        # Whitespace-only should also fail (after stripping)
        assert not validator.validate_and_log("   ", "test_source")

    def test_import_failure_graceful_handling(self):
        """Test that validator handles missing get-all-tickers library gracefully."""
        with patch("catalyst_bot.ticker_validation.logger") as mock_logger:
            # Mock the import to raise ImportError
            with patch.dict("sys.modules", {"get_all_tickers": None}):
                with patch(
                    "builtins.__import__",
                    side_effect=ImportError("get_all_tickers not found"),
                ):
                    validator = TickerValidator()

                    # Should log warning about using fallback
                    mock_logger.warning.assert_called()
                    warning_msg = mock_logger.warning.call_args[0][0]
                    assert (
                        "fallback" in warning_msg
                        or "get-all-tickers not installed" in warning_msg
                    )

                    # Validation should use fallback list (still enabled)
                    assert validator.is_enabled
                    assert validator.ticker_count > 0
                    # Valid tickers in fallback should pass
                    assert validator.is_valid("AAPL")
                    # Invalid tickers should fail
                    assert not validator.is_valid("FAKE")

    def test_load_failure_graceful_handling(self):
        """Test that validator handles get_tickers() failure gracefully."""
        # This test verifies graceful degradation when the library fails
        # We'll mock at the module import level
        import sys

        original_modules = sys.modules.copy()

        try:
            # Remove get_all_tickers from sys.modules if present
            if "get_all_tickers" in sys.modules:
                del sys.modules["get_all_tickers"]
            if "get_all_tickers.get_tickers" in sys.modules:
                del sys.modules["get_all_tickers.get_tickers"]

            # Create a mock module that raises an error
            mock_module = MagicMock()
            mock_module.get_tickers = MagicMock(
                side_effect=RuntimeError("Network error")
            )
            sys.modules["get_all_tickers.get_tickers"] = mock_module
            sys.modules["get_all_tickers"] = mock_module

            with patch("catalyst_bot.ticker_validation.logger") as mock_logger:
                validator = TickerValidator()

                # Should log warning about using fallback
                mock_logger.warning.assert_called()
                warning_msg = str(mock_logger.warning.call_args[0][0])
                assert (
                    "fallback" in warning_msg
                    or "Failed to load ticker list" in warning_msg
                )

                # Validation should use fallback list (still enabled)
                assert validator.is_enabled
                assert validator.ticker_count > 0
                # Valid tickers in fallback should pass
                assert validator.is_valid("AAPL")
                # Invalid tickers should fail
                assert not validator.is_valid("FAKE")
        finally:
            # Restore original modules
            sys.modules.clear()
            sys.modules.update(original_modules)

    def test_ticker_count_property(self):
        """Test that ticker_count property returns correct count."""
        validator = TickerValidator()

        # Should always have tickers (either from library or fallback)
        assert validator.is_enabled, "Validator should have tickers loaded"

        # Should have at least the fallback tickers (100+)
        assert validator.ticker_count >= 100, "Expected at least 100 tickers"

    def test_is_enabled_property(self):
        """Test that is_enabled property reflects validation state."""
        validator = TickerValidator()

        # is_enabled should match whether tickers were loaded
        if validator._valid_tickers:
            assert validator.is_enabled
            assert validator.ticker_count > 0
        else:
            assert not validator.is_enabled
            assert validator.ticker_count == 0

    def test_validate_and_log_debug_logging(self, caplog):
        """Test that validate_and_log logs rejections at DEBUG level."""
        validator = TickerValidator()

        # Should always have tickers (either from library or fallback)
        assert validator.is_enabled, "Validator should have tickers loaded"

        with caplog.at_level(logging.DEBUG):
            # Test invalid ticker
            result = validator.validate_and_log("INVALIDTICKER123", "test_feed")

            # Should fail validation
            assert not result

            # Should log rejection at DEBUG level
            debug_messages = [
                record.message
                for record in caplog.records
                if record.levelname == "DEBUG"
            ]
            assert any(
                "INVALIDTICKER123" in msg and "test_feed" in msg
                for msg in debug_messages
            )

    def test_successful_load_info_logging(self, caplog):
        """Test that successful ticker loading logs at INFO or WARNING level."""
        with caplog.at_level(logging.INFO):
            TickerValidator()

            # Should log successful load (INFO) or fallback warning (WARNING)
            all_messages = [record.message for record in caplog.records]
            assert any(
                "ticker" in msg.lower() for msg in all_messages
            ), "Expected ticker loading message"


class TestTickerValidationIntegration:
    """Test integration with feeds.py normalization."""

    def test_feeds_integration_valid_ticker(self):
        """Test that valid tickers pass through feeds normalization."""
        from types import SimpleNamespace

        from catalyst_bot.feeds import _TICKER_VALIDATOR, _normalize_entry

        # Should always have tickers (either from library or fallback)
        assert _TICKER_VALIDATOR.is_enabled, "Validator should have tickers loaded"

        # Create mock feed entry with valid ticker
        entry = SimpleNamespace(
            title="Apple Inc. (AAPL) Reports Record Earnings",
            link="https://example.com/news/1",
            published="2024-01-15T10:00:00Z",
            id="test-id-1",
            ticker="AAPL",
        )

        result = _normalize_entry("test_source", entry)

        # Should preserve valid ticker
        assert result is not None
        assert result["ticker"] == "AAPL"
        assert result["ticker_source"] == "title"

    def test_feeds_integration_invalid_ticker(self):
        """Test that invalid tickers are rejected by feeds normalization."""
        from types import SimpleNamespace

        from catalyst_bot.feeds import _TICKER_VALIDATOR, _normalize_entry

        # Should always have tickers (either from library or fallback)
        assert _TICKER_VALIDATOR.is_enabled, "Validator should have tickers loaded"

        # Create mock feed entry with invalid ticker
        entry = SimpleNamespace(
            title="FakeCompany (FAKE) Announces News",
            link="https://example.com/news/2",
            published="2024-01-15T10:00:00Z",
            id="test-id-2",
            ticker="FAKE",
        )

        result = _normalize_entry("test_source", entry)

        # Should reject invalid ticker
        assert result is not None
        assert result["ticker"] is None
        assert result["ticker_source"] is None

    def test_feeds_integration_no_ticker(self):
        """Test that entries without tickers are handled correctly."""
        from types import SimpleNamespace

        from catalyst_bot.feeds import _normalize_entry

        # Create mock feed entry with no ticker
        entry = SimpleNamespace(
            title="General Market News Without Ticker",
            link="https://example.com/news/3",
            published="2024-01-15T10:00:00Z",
            id="test-id-3",
        )

        result = _normalize_entry("test_source", entry)

        # Should handle gracefully (no crash)
        assert result is not None
        assert result["ticker"] is None

    def test_feeds_integration_case_insensitive(self):
        """Test that feeds integration handles case-insensitive validation."""
        from types import SimpleNamespace

        from catalyst_bot.feeds import _TICKER_VALIDATOR, _normalize_entry

        # Should always have tickers (either from library or fallback)
        assert _TICKER_VALIDATOR.is_enabled, "Validator should have tickers loaded"

        # Create mock feed entry with lowercase ticker
        entry = SimpleNamespace(
            title="Tesla Inc. (tsla) Stock Update",
            link="https://example.com/news/4",
            published="2024-01-15T10:00:00Z",
            id="test-id-4",
            ticker="tsla",
        )

        result = _normalize_entry("test_source", entry)

        # Should validate and preserve lowercase ticker
        assert result is not None
        # The ticker is stored as extracted (lowercase in this case)
        assert result["ticker"] == "tsla"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
