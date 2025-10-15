"""Tests for fundamental data scoring integration.

Tests cover:
- Float shares scoring logic
- Short interest scoring logic
- Integration with classification system
- Feature flag behavior
- Error handling and fallback
"""

from __future__ import annotations

import os
from unittest.mock import Mock, patch

import pytest

from catalyst_bot.fundamental_scoring import (
    calculate_fundamental_score,
    is_fundamental_scoring_enabled,
    score_float_shares,
    score_short_interest,
)


class TestFloatSharesScoring:
    """Test float shares scoring logic."""

    def test_very_low_float(self):
        """Very low float (<10M shares) should get highest boost."""
        score, reason = score_float_shares(5_000_000)
        assert score == 0.5
        assert reason == "very_low_float_<10M"

    def test_low_float(self):
        """Low float (10M-50M) should get medium boost."""
        score, reason = score_float_shares(30_000_000)
        assert score == 0.3
        assert reason == "low_float_10M-50M"

        # Test boundary
        score, reason = score_float_shares(49_999_999)
        assert score == 0.3

    def test_medium_float(self):
        """Medium float (50M-100M) should get small boost."""
        score, reason = score_float_shares(75_000_000)
        assert score == 0.1
        assert reason == "medium_float_50M-100M"

    def test_high_float(self):
        """High float (>100M) should get penalty."""
        score, reason = score_float_shares(150_000_000)
        assert score == -0.1
        assert reason == "high_float_>100M"

    def test_boundary_cases(self):
        """Test exact boundary values."""
        # Exactly 10M - should be low float
        score, reason = score_float_shares(10_000_000)
        assert score == 0.3
        assert reason == "low_float_10M-50M"

        # Exactly 50M - should be medium float
        score, reason = score_float_shares(50_000_000)
        assert score == 0.1
        assert reason == "medium_float_50M-100M"

        # Exactly 100M - should be high float
        score, reason = score_float_shares(100_000_000)
        assert score == -0.1
        assert reason == "high_float_>100M"


class TestShortInterestScoring:
    """Test short interest scoring logic."""

    def test_very_high_si(self):
        """Very high SI (>20%) should get highest boost."""
        score, reason = score_short_interest(25.0)
        assert score == 0.5
        assert reason == "very_high_si_>20%"

    def test_high_si(self):
        """High SI (15-20%) should get medium boost."""
        score, reason = score_short_interest(17.5)
        assert score == 0.3
        assert reason == "high_si_15-20%"

    def test_moderate_si(self):
        """Moderate SI (10-15%) should get small boost."""
        score, reason = score_short_interest(12.5)
        assert score == 0.15
        assert reason == "moderate_si_10-15%"

    def test_low_si(self):
        """Low SI (<10%) should be neutral."""
        score, reason = score_short_interest(5.0)
        assert score == 0.0
        assert reason == "low_si_<10%"

    def test_boundary_cases(self):
        """Test exact boundary values."""
        # Exactly 20% - should be very high
        score, reason = score_short_interest(20.0)
        assert score == 0.5
        assert reason == "very_high_si_>20%"

        # Exactly 15% - should be high
        score, reason = score_short_interest(15.0)
        assert score == 0.3
        assert reason == "high_si_15-20%"

        # Exactly 10% - should be moderate
        score, reason = score_short_interest(10.0)
        assert score == 0.15
        assert reason == "moderate_si_10-15%"


class TestFundamentalScoreCalculation:
    """Test complete fundamental score calculation."""

    @patch.dict(os.environ, {"FEATURE_FUNDAMENTAL_SCORING": "0"})
    def test_feature_disabled(self):
        """When feature is disabled, should return 0 score."""
        score, metadata = calculate_fundamental_score("AAPL")
        assert score == 0.0
        assert metadata["enabled"] is False
        assert metadata["reason"] == "feature_disabled"

    @patch.dict(os.environ, {"FEATURE_FUNDAMENTAL_SCORING": "1"})
    @patch("catalyst_bot.fundamental_scoring.get_fundamentals")
    def test_both_factors_available(self, mock_get_fundamentals):
        """When both factors available, should combine scores."""
        # Low float (30M) + very high SI (25%) = 0.3 + 0.5 = 0.8
        mock_get_fundamentals.return_value = (30_000_000, 25.0)

        score, metadata = calculate_fundamental_score("GME")

        assert score == 0.8
        assert metadata["enabled"] is True
        assert metadata["ticker"] == "GME"
        assert metadata["float_shares"] == 30_000_000
        assert metadata["short_interest"] == 25.0
        assert metadata["float_score"] == 0.3
        assert metadata["si_score"] == 0.5
        assert metadata["float_reason"] == "low_float_10M-50M"
        assert metadata["si_reason"] == "very_high_si_>20%"

    @patch.dict(os.environ, {"FEATURE_FUNDAMENTAL_SCORING": "1"})
    @patch("catalyst_bot.fundamental_scoring.get_fundamentals")
    def test_only_float_available(self, mock_get_fundamentals):
        """When only float available, should score that factor."""
        mock_get_fundamentals.return_value = (5_000_000, None)

        score, metadata = calculate_fundamental_score("SPRT")

        assert score == 0.5  # Very low float
        assert metadata["float_score"] == 0.5
        assert metadata["si_score"] == 0.0
        assert metadata["float_reason"] == "very_low_float_<10M"
        assert metadata["si_reason"] == "data_unavailable"

    @patch.dict(os.environ, {"FEATURE_FUNDAMENTAL_SCORING": "1"})
    @patch("catalyst_bot.fundamental_scoring.get_fundamentals")
    def test_only_si_available(self, mock_get_fundamentals):
        """When only SI available, should score that factor."""
        mock_get_fundamentals.return_value = (None, 18.0)

        score, metadata = calculate_fundamental_score("AMC")

        assert score == 0.3  # High SI
        assert metadata["float_score"] == 0.0
        assert metadata["si_score"] == 0.3
        assert metadata["float_reason"] == "data_unavailable"
        assert metadata["si_reason"] == "high_si_15-20%"

    @patch.dict(os.environ, {"FEATURE_FUNDAMENTAL_SCORING": "1"})
    @patch("catalyst_bot.fundamental_scoring.get_fundamentals")
    def test_no_data_available(self, mock_get_fundamentals):
        """When no data available, should return neutral score."""
        mock_get_fundamentals.return_value = (None, None)

        score, metadata = calculate_fundamental_score("UNKN")

        assert score == 0.0
        assert metadata["reason"] == "no_data_available"

    @patch.dict(os.environ, {"FEATURE_FUNDAMENTAL_SCORING": "1"})
    def test_invalid_ticker(self):
        """Empty ticker should return neutral score."""
        score, metadata = calculate_fundamental_score("")
        assert score == 0.0
        assert metadata["reason"] == "invalid_ticker"

        score, metadata = calculate_fundamental_score(None)
        assert score == 0.0
        assert metadata["reason"] == "invalid_ticker"

    @patch.dict(os.environ, {"FEATURE_FUNDAMENTAL_SCORING": "1"})
    @patch("catalyst_bot.fundamental_scoring.get_fundamentals")
    def test_fetch_error_handling(self, mock_get_fundamentals):
        """Should handle fetch errors gracefully."""
        mock_get_fundamentals.side_effect = Exception("API error")

        score, metadata = calculate_fundamental_score("FAIL")

        assert score == 0.0
        assert metadata["reason"] == "fetch_error"
        assert "error" in metadata


class TestFeatureFlagCheck:
    """Test feature flag checking."""

    @patch.dict(os.environ, {"FEATURE_FUNDAMENTAL_SCORING": "1"})
    def test_enabled(self):
        """Should return True when flag is 1."""
        assert is_fundamental_scoring_enabled() is True

    @patch.dict(os.environ, {"FEATURE_FUNDAMENTAL_SCORING": "0"})
    def test_disabled(self):
        """Should return False when flag is 0."""
        assert is_fundamental_scoring_enabled() is False

    @patch.dict(os.environ, {}, clear=True)
    def test_default_disabled(self):
        """Should default to disabled when flag not set."""
        # Remove the key if it exists
        os.environ.pop("FEATURE_FUNDAMENTAL_SCORING", None)
        assert is_fundamental_scoring_enabled() is False


class TestClassificationIntegration:
    """Test integration with classify() function."""

    @patch.dict(os.environ, {"FEATURE_FUNDAMENTAL_SCORING": "1"})
    @patch("catalyst_bot.fundamental_scoring.get_fundamentals")
    def test_classification_with_fundamental_boost(self, mock_get_fundamentals):
        """Classification should apply fundamental boost when available."""
        from catalyst_bot.classify import classify
        from catalyst_bot.models import NewsItem

        # Setup mock fundamental data
        mock_get_fundamentals.return_value = (8_000_000, 22.0)  # Very low float + very high SI

        # Create test news item with ticker
        item = NewsItem(
            title="FDA Approval for XYZ",
            link="https://example.com/news",
            source_host="example",
            ts="2024-01-01T12:00:00Z",
        )
        # Set ticker attribute
        item.ticker = "XYZ"

        # Classify the item
        scored = classify(item)

        # Should have fundamental metadata attached
        if hasattr(scored, "fundamental_score"):
            assert scored.fundamental_score == 1.0  # 0.5 + 0.5
            assert scored.fundamental_float_shares == 8_000_000
            assert scored.fundamental_short_interest == 22.0
            assert scored.fundamental_float_score == 0.5
            assert scored.fundamental_si_score == 0.5

        # Should have fundamental tags
        tags = getattr(scored, "tags", []) or scored.get("tags", [])
        assert any("fundamental_" in str(tag) for tag in tags)

    @patch.dict(os.environ, {"FEATURE_FUNDAMENTAL_SCORING": "0"})
    def test_classification_with_feature_disabled(self):
        """Classification should work normally when feature disabled."""
        from catalyst_bot.classify import classify
        from catalyst_bot.models import NewsItem

        item = NewsItem(
            title="Regular News Item",
            link="https://example.com/news",
            source_host="example",
            ts="2024-01-01T12:00:00Z",
        )
        item.ticker = "ABC"

        # Should not raise errors
        scored = classify(item)
        assert scored is not None

    @patch.dict(os.environ, {"FEATURE_FUNDAMENTAL_SCORING": "1"})
    def test_classification_without_ticker(self):
        """Classification should handle items without ticker."""
        from catalyst_bot.classify import classify
        from catalyst_bot.models import NewsItem

        item = NewsItem(
            title="News Without Ticker",
            link="https://example.com/news",
            source_host="example",
            ts="2024-01-01T12:00:00Z",
        )
        # No ticker set

        # Should not raise errors
        scored = classify(item)
        assert scored is not None

    @patch.dict(os.environ, {"FEATURE_FUNDAMENTAL_SCORING": "1"})
    @patch("catalyst_bot.fundamental_scoring.get_fundamentals")
    def test_classification_handles_fundamental_errors(self, mock_get_fundamentals):
        """Classification should handle fundamental scoring errors gracefully."""
        from catalyst_bot.classify import classify
        from catalyst_bot.models import NewsItem

        # Simulate error in fundamental data fetch
        mock_get_fundamentals.side_effect = Exception("Network error")

        item = NewsItem(
            title="Test News",
            link="https://example.com/news",
            source_host="example",
            ts="2024-01-01T12:00:00Z",
        )
        item.ticker = "TEST"

        # Should not crash, just skip fundamental scoring
        scored = classify(item)
        assert scored is not None


class TestRealWorldScenarios:
    """Test real-world catalyst scenarios."""

    @patch.dict(os.environ, {"FEATURE_FUNDAMENTAL_SCORING": "1"})
    @patch("catalyst_bot.fundamental_scoring.get_fundamentals")
    def test_low_float_squeeze_candidate(self, mock_get_fundamentals):
        """Low float + high SI = strong squeeze candidate."""
        # Real scenario: Small biotech with 15M float and 18% SI
        mock_get_fundamentals.return_value = (15_000_000, 18.0)

        score, metadata = calculate_fundamental_score("BIOTECH")

        # Should get moderate-high boost
        assert score == 0.6  # 0.3 (low float) + 0.3 (high SI)

    @patch.dict(os.environ, {"FEATURE_FUNDAMENTAL_SCORING": "1"})
    @patch("catalyst_bot.fundamental_scoring.get_fundamentals")
    def test_meme_stock_characteristics(self, mock_get_fundamentals):
        """Very low float + very high SI = maximum boost."""
        # Real scenario: GME-like stock with 8M float and 35% SI
        mock_get_fundamentals.return_value = (8_000_000, 35.0)

        score, metadata = calculate_fundamental_score("MEME")

        # Should get maximum boost
        assert score == 1.0  # 0.5 (very low float) + 0.5 (very high SI)

    @patch.dict(os.environ, {"FEATURE_FUNDAMENTAL_SCORING": "1"})
    @patch("catalyst_bot.fundamental_scoring.get_fundamentals")
    def test_large_cap_stock(self, mock_get_fundamentals):
        """Large cap with high float = penalty."""
        # Real scenario: Large cap with 500M float and 3% SI
        mock_get_fundamentals.return_value = (500_000_000, 3.0)

        score, metadata = calculate_fundamental_score("LARGECAP")

        # Should get penalty from high float, nothing from low SI
        assert score == -0.1  # -0.1 (high float) + 0.0 (low SI)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
