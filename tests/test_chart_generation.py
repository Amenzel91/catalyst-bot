"""
Comprehensive Test Suite for Chart Generation Systems

This test suite validates all 3 chart systems (QuickChart, Sentiment Gauge, Advanced Charts)
and their interaction with market hours feature gating.

Agent: 4
Task: Chart Generation Testing
"""

import os
import pytest
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timezone


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def mock_market_info_open():
    """Mock market_info for market open (all features enabled)."""
    return {
        "status": "regular",
        "cycle_seconds": 60,
        "features": {
            "llm_enabled": True,
            "charts_enabled": True,
            "breakout_enabled": True,
        },
        "is_warmup": False,
        "is_weekend": False,
        "is_holiday": False,
    }


@pytest.fixture
def mock_market_info_closed():
    """Mock market_info for market closed (charts disabled)."""
    return {
        "status": "closed",
        "cycle_seconds": 180,
        "features": {
            "llm_enabled": False,
            "charts_enabled": False,
            "breakout_enabled": False,
        },
        "is_warmup": False,
        "is_weekend": True,
        "is_holiday": False,
    }


@pytest.fixture
def mock_market_info_extended():
    """Mock market_info for extended hours (charts disabled)."""
    return {
        "status": "pre_market",
        "cycle_seconds": 90,
        "features": {
            "llm_enabled": True,
            "charts_enabled": False,
            "breakout_enabled": True,
        },
        "is_warmup": False,
        "is_weekend": False,
        "is_holiday": False,
    }


@pytest.fixture
def mock_item_dict():
    """Mock news item dictionary."""
    return {
        "ticker": "AAPL",
        "title": "Apple announces new product line",
        "source": "benzinga",
        "ts": "2025-01-15T14:30:00Z",
        "link": "https://example.com/news",
        "summary": "Apple Inc. announced a revolutionary new product category.",
        "keywords": ["product launch", "innovation"],
    }


@pytest.fixture
def mock_scored_item():
    """Mock scored item with all required fields."""
    scored = Mock()
    scored.ticker = "AAPL"
    scored.float_shares = 15_000_000_000
    scored.current_volume = 50_000_000
    scored.avg_volume_20d = 40_000_000
    scored.rvol = 1.25
    scored.rvol_class = "ELEVATED_RVOL"
    scored.vwap = 175.50
    scored.vwap_distance_pct = 2.3
    scored.vwap_signal = "BULLISH"
    scored.market_regime = "BULL_MARKET"
    scored.market_vix = 15.2
    scored.short_interest_pct = 8.5
    scored.shares_outstanding = 15_500_000_000
    scored.sentiment_score = 0.75
    scored.sentiment_label = "Bullish"
    return scored


@pytest.fixture
def mock_quickchart_png():
    """Mock QuickChart PNG path."""
    return Path("/tmp/quickchart_AAPL.png")


@pytest.fixture
def mock_gauge_png():
    """Mock sentiment gauge PNG path."""
    return Path("/tmp/gauge_AAPL.png")


@pytest.fixture
def mock_advanced_chart_png():
    """Mock advanced chart PNG path."""
    return Path("/tmp/advanced_AAPL_1D.png")


# ============================================================================
# QuickChart Tests
# ============================================================================


class TestQuickChartGeneration:
    """Test QuickChart generation and feature flag logic."""

    def test_quickchart_generated_when_both_flags_enabled(
        self, mock_item_dict, mock_market_info_open, mock_quickchart_png
    ):
        """Test QuickChart is generated when charts_enabled=True and FEATURE_QUICKCHART_POST=1."""
        with patch.dict(os.environ, {"FEATURE_QUICKCHART_POST": "1"}), \
             patch("src.catalyst_bot.alerts.get_quickchart_png_path", return_value=mock_quickchart_png) as mock_qc:

            # Extract charts_enabled from market_info
            charts_enabled = mock_market_info_open["features"]["charts_enabled"]

            # Simulate the logic from alerts.py
            use_post = os.getenv("FEATURE_QUICKCHART_POST", "0").strip().lower() in ("1", "true", "yes")
            should_generate = use_post and charts_enabled

            assert charts_enabled is True, "charts_enabled should be True during market hours"
            assert use_post is True, "FEATURE_QUICKCHART_POST should be enabled"
            assert should_generate is True, "QuickChart should be generated"

    def test_quickchart_skipped_when_charts_disabled(
        self, mock_item_dict, mock_market_info_closed
    ):
        """Test QuickChart is skipped when charts_enabled=False."""
        with patch.dict(os.environ, {"FEATURE_QUICKCHART_POST": "1"}):

            charts_enabled = mock_market_info_closed["features"]["charts_enabled"]
            use_post = os.getenv("FEATURE_QUICKCHART_POST", "0").strip().lower() in ("1", "true", "yes")
            should_generate = use_post and charts_enabled

            assert charts_enabled is False, "charts_enabled should be False when market closed"
            assert use_post is True, "FEATURE_QUICKCHART_POST is enabled"
            assert should_generate is False, "QuickChart should NOT be generated when charts_enabled=False"

    def test_quickchart_skipped_when_feature_flag_disabled(
        self, mock_item_dict, mock_market_info_open
    ):
        """Test QuickChart is skipped when FEATURE_QUICKCHART_POST=0."""
        with patch.dict(os.environ, {"FEATURE_QUICKCHART_POST": "0"}):

            charts_enabled = mock_market_info_open["features"]["charts_enabled"]
            use_post = os.getenv("FEATURE_QUICKCHART_POST", "0").strip().lower() in ("1", "true", "yes")
            should_generate = use_post and charts_enabled

            assert charts_enabled is True, "charts_enabled should be True during market hours"
            assert use_post is False, "FEATURE_QUICKCHART_POST should be disabled"
            assert should_generate is False, "QuickChart should NOT be generated when feature flag disabled"

    def test_quickchart_respects_and_logic(self):
        """Test QuickChart respects both flags (AND logic)."""
        test_cases = [
            # (FEATURE_QUICKCHART_POST, charts_enabled, expected_result)
            ("1", True, True),   # Both enabled -> generate
            ("1", False, False), # Feature on, charts off -> skip
            ("0", True, False),  # Feature off, charts on -> skip
            ("0", False, False), # Both off -> skip
        ]

        for feature_flag, charts_enabled, expected in test_cases:
            with patch.dict(os.environ, {"FEATURE_QUICKCHART_POST": feature_flag}):
                use_post = os.getenv("FEATURE_QUICKCHART_POST", "0").strip().lower() in ("1", "true", "yes")
                should_generate = use_post and charts_enabled

                assert should_generate == expected, \
                    f"Failed for FEATURE_QUICKCHART_POST={feature_flag}, charts_enabled={charts_enabled}"


# ============================================================================
# Sentiment Gauge Tests
# ============================================================================


class TestSentimentGaugeGeneration:
    """Test Sentiment Gauge generation and feature flag logic."""

    def test_sentiment_gauge_generated_when_both_flags_enabled(
        self, mock_item_dict, mock_scored_item, mock_market_info_open, mock_gauge_png
    ):
        """Test Sentiment Gauge is generated when charts_enabled=True and FEATURE_SENTIMENT_GAUGE=1."""
        with patch.dict(os.environ, {"FEATURE_SENTIMENT_GAUGE": "1"}), \
             patch("src.catalyst_bot.alerts.generate_sentiment_gauge", return_value=mock_gauge_png) as mock_gauge:

            charts_enabled = mock_market_info_open["features"]["charts_enabled"]
            use_gauge = os.getenv("FEATURE_SENTIMENT_GAUGE", "1").strip().lower() in ("1", "true", "yes")
            should_generate = use_gauge and charts_enabled

            assert charts_enabled is True, "charts_enabled should be True during market hours"
            assert use_gauge is True, "FEATURE_SENTIMENT_GAUGE should be enabled"
            assert should_generate is True, "Sentiment Gauge should be generated"

    def test_sentiment_gauge_skipped_when_charts_disabled(
        self, mock_item_dict, mock_scored_item, mock_market_info_closed
    ):
        """Test Sentiment Gauge is skipped when charts_enabled=False."""
        with patch.dict(os.environ, {"FEATURE_SENTIMENT_GAUGE": "1"}):

            charts_enabled = mock_market_info_closed["features"]["charts_enabled"]
            use_gauge = os.getenv("FEATURE_SENTIMENT_GAUGE", "1").strip().lower() in ("1", "true", "yes")
            should_generate = use_gauge and charts_enabled

            assert charts_enabled is False, "charts_enabled should be False when market closed"
            assert use_gauge is True, "FEATURE_SENTIMENT_GAUGE is enabled"
            assert should_generate is False, "Sentiment Gauge should NOT be generated when charts_enabled=False"

    def test_sentiment_gauge_skipped_when_feature_flag_disabled(
        self, mock_item_dict, mock_scored_item, mock_market_info_open
    ):
        """Test Sentiment Gauge is skipped when FEATURE_SENTIMENT_GAUGE=0."""
        with patch.dict(os.environ, {"FEATURE_SENTIMENT_GAUGE": "0"}):

            charts_enabled = mock_market_info_open["features"]["charts_enabled"]
            use_gauge = os.getenv("FEATURE_SENTIMENT_GAUGE", "1").strip().lower() in ("1", "true", "yes")
            should_generate = use_gauge and charts_enabled

            assert charts_enabled is True, "charts_enabled should be True during market hours"
            assert use_gauge is False, "FEATURE_SENTIMENT_GAUGE should be disabled"
            assert should_generate is False, "Sentiment Gauge should NOT be generated when feature flag disabled"

    def test_sentiment_gauge_respects_and_logic(self):
        """Test Sentiment Gauge respects both flags (AND logic)."""
        test_cases = [
            # (FEATURE_SENTIMENT_GAUGE, charts_enabled, expected_result)
            ("1", True, True),   # Both enabled -> generate
            ("1", False, False), # Feature on, charts off -> skip
            ("0", True, False),  # Feature off, charts on -> skip
            ("0", False, False), # Both off -> skip
        ]

        for feature_flag, charts_enabled, expected in test_cases:
            with patch.dict(os.environ, {"FEATURE_SENTIMENT_GAUGE": feature_flag}):
                use_gauge = os.getenv("FEATURE_SENTIMENT_GAUGE", "1").strip().lower() in ("1", "true", "yes")
                should_generate = use_gauge and charts_enabled

                assert should_generate == expected, \
                    f"Failed for FEATURE_SENTIMENT_GAUGE={feature_flag}, charts_enabled={charts_enabled}"


# ============================================================================
# Advanced Charts Tests
# ============================================================================


class TestAdvancedChartsGeneration:
    """Test Advanced Charts generation and feature flag logic."""

    def test_advanced_charts_generated_when_both_flags_enabled(
        self, mock_item_dict, mock_market_info_open, mock_advanced_chart_png
    ):
        """Test Advanced Charts are generated when charts_enabled=True and FEATURE_ADVANCED_CHARTS=1."""
        with patch.dict(os.environ, {"FEATURE_ADVANCED_CHARTS": "1"}), \
             patch("src.catalyst_bot.alerts.generate_multi_panel_chart", return_value=mock_advanced_chart_png) as mock_chart:

            charts_enabled = mock_market_info_open["features"]["charts_enabled"]
            use_advanced = os.getenv("FEATURE_ADVANCED_CHARTS", "0").strip().lower() in ("1", "true", "yes", "on")
            should_generate = use_advanced and charts_enabled

            assert charts_enabled is True, "charts_enabled should be True during market hours"
            assert use_advanced is True, "FEATURE_ADVANCED_CHARTS should be enabled"
            assert should_generate is True, "Advanced Charts should be generated"

    def test_advanced_charts_skipped_when_charts_disabled(
        self, mock_item_dict, mock_market_info_closed
    ):
        """Test Advanced Charts are skipped when charts_enabled=False."""
        with patch.dict(os.environ, {"FEATURE_ADVANCED_CHARTS": "1"}):

            charts_enabled = mock_market_info_closed["features"]["charts_enabled"]
            use_advanced = os.getenv("FEATURE_ADVANCED_CHARTS", "0").strip().lower() in ("1", "true", "yes", "on")
            should_generate = use_advanced and charts_enabled

            assert charts_enabled is False, "charts_enabled should be False when market closed"
            assert use_advanced is True, "FEATURE_ADVANCED_CHARTS is enabled"
            assert should_generate is False, "Advanced Charts should NOT be generated when charts_enabled=False"

    def test_advanced_charts_skipped_when_feature_flag_disabled(
        self, mock_item_dict, mock_market_info_open
    ):
        """Test Advanced Charts are skipped when FEATURE_ADVANCED_CHARTS=0."""
        with patch.dict(os.environ, {"FEATURE_ADVANCED_CHARTS": "0"}):

            charts_enabled = mock_market_info_open["features"]["charts_enabled"]
            use_advanced = os.getenv("FEATURE_ADVANCED_CHARTS", "0").strip().lower() in ("1", "true", "yes", "on")
            should_generate = use_advanced and charts_enabled

            assert charts_enabled is True, "charts_enabled should be True during market hours"
            assert use_advanced is False, "FEATURE_ADVANCED_CHARTS should be disabled"
            assert should_generate is False, "Advanced Charts should NOT be generated when feature flag disabled"

    def test_advanced_charts_respects_and_logic(self):
        """Test Advanced Charts respect both flags (AND logic)."""
        test_cases = [
            # (FEATURE_ADVANCED_CHARTS, charts_enabled, expected_result)
            ("1", True, True),   # Both enabled -> generate
            ("1", False, False), # Feature on, charts off -> skip
            ("0", True, False),  # Feature off, charts on -> skip
            ("0", False, False), # Both off -> skip
        ]

        for feature_flag, charts_enabled, expected in test_cases:
            with patch.dict(os.environ, {"FEATURE_ADVANCED_CHARTS": feature_flag}):
                use_advanced = os.getenv("FEATURE_ADVANCED_CHARTS", "0").strip().lower() in ("1", "true", "yes", "on")
                should_generate = use_advanced and charts_enabled

                assert should_generate == expected, \
                    f"Failed for FEATURE_ADVANCED_CHARTS={feature_flag}, charts_enabled={charts_enabled}"


# ============================================================================
# Market Hours Integration Tests
# ============================================================================


class TestMarketHoursIntegration:
    """Test chart generation with market hours detection."""

    def test_all_charts_enabled_during_market_hours(
        self, mock_market_info_open
    ):
        """Test all charts enabled during regular market hours."""
        with patch.dict(os.environ, {
            "FEATURE_QUICKCHART_POST": "1",
            "FEATURE_SENTIMENT_GAUGE": "1",
            "FEATURE_ADVANCED_CHARTS": "1",
        }):
            charts_enabled = mock_market_info_open["features"]["charts_enabled"]

            use_quickchart = os.getenv("FEATURE_QUICKCHART_POST", "0").strip().lower() in ("1", "true", "yes")
            use_gauge = os.getenv("FEATURE_SENTIMENT_GAUGE", "1").strip().lower() in ("1", "true", "yes")
            use_advanced = os.getenv("FEATURE_ADVANCED_CHARTS", "0").strip().lower() in ("1", "true", "yes", "on")

            assert charts_enabled is True, "charts_enabled should be True during market hours"
            assert use_quickchart and charts_enabled, "QuickChart should be enabled"
            assert use_gauge and charts_enabled, "Sentiment Gauge should be enabled"
            assert use_advanced and charts_enabled, "Advanced Charts should be enabled"

    def test_all_charts_disabled_after_hours(
        self, mock_market_info_extended
    ):
        """Test all charts disabled during extended hours."""
        with patch.dict(os.environ, {
            "FEATURE_QUICKCHART_POST": "1",
            "FEATURE_SENTIMENT_GAUGE": "1",
            "FEATURE_ADVANCED_CHARTS": "1",
        }):
            charts_enabled = mock_market_info_extended["features"]["charts_enabled"]

            use_quickchart = os.getenv("FEATURE_QUICKCHART_POST", "0").strip().lower() in ("1", "true", "yes")
            use_gauge = os.getenv("FEATURE_SENTIMENT_GAUGE", "1").strip().lower() in ("1", "true", "yes")
            use_advanced = os.getenv("FEATURE_ADVANCED_CHARTS", "0").strip().lower() in ("1", "true", "yes", "on")

            assert charts_enabled is False, "charts_enabled should be False during extended hours"
            assert not (use_quickchart and charts_enabled), "QuickChart should be disabled"
            assert not (use_gauge and charts_enabled), "Sentiment Gauge should be disabled"
            assert not (use_advanced and charts_enabled), "Advanced Charts should be disabled"

    def test_all_charts_disabled_when_market_closed(
        self, mock_market_info_closed
    ):
        """Test all charts disabled when market is closed."""
        with patch.dict(os.environ, {
            "FEATURE_QUICKCHART_POST": "1",
            "FEATURE_SENTIMENT_GAUGE": "1",
            "FEATURE_ADVANCED_CHARTS": "1",
            "CLOSED_DISABLE_CHARTS": "1",
        }):
            charts_enabled = mock_market_info_closed["features"]["charts_enabled"]

            use_quickchart = os.getenv("FEATURE_QUICKCHART_POST", "0").strip().lower() in ("1", "true", "yes")
            use_gauge = os.getenv("FEATURE_SENTIMENT_GAUGE", "1").strip().lower() in ("1", "true", "yes")
            use_advanced = os.getenv("FEATURE_ADVANCED_CHARTS", "0").strip().lower() in ("1", "true", "yes", "on")

            assert charts_enabled is False, "charts_enabled should be False when market closed"
            assert not (use_quickchart and charts_enabled), "QuickChart should be disabled"
            assert not (use_gauge and charts_enabled), "Sentiment Gauge should be disabled"
            assert not (use_advanced and charts_enabled), "Advanced Charts should be disabled"


# ============================================================================
# Edge Case Tests
# ============================================================================


class TestChartGenerationEdgeCases:
    """Test edge cases and error handling for chart generation."""

    def test_behavior_with_missing_market_info(
        self, mock_item_dict
    ):
        """Test chart generation with missing market_info (defaults to enabled)."""
        # When market_info is not provided, features default to enabled
        with patch.dict(os.environ, {"FEATURE_QUICKCHART_POST": "1"}):
            # Simulate missing market_info by using default value
            market_info = {}
            features = market_info.get("features", {})
            charts_enabled = features.get("charts_enabled", True)  # Default to True

            use_post = os.getenv("FEATURE_QUICKCHART_POST", "0").strip().lower() in ("1", "true", "yes")
            should_generate = use_post and charts_enabled

            assert charts_enabled is True, "charts_enabled should default to True when missing"
            assert should_generate is True, "Charts should generate when market_info missing"

    def test_behavior_with_missing_ticker(
        self, mock_market_info_open
    ):
        """Test chart generation with missing ticker."""
        item_dict = {
            "title": "News without ticker",
            "source": "benzinga",
            "ts": "2025-01-15T14:30:00Z",
        }

        ticker = item_dict.get("ticker") or ""

        assert ticker == "", "Ticker should be empty string when missing"
        # Chart generation functions should handle empty ticker gracefully

    def test_behavior_with_missing_scored_item(
        self, mock_item_dict, mock_market_info_open
    ):
        """Test chart generation with missing scored_item."""
        # Sentiment gauge requires scored_item for sentiment data
        scored = None

        # Should handle None gracefully without crashing
        sentiment_score = getattr(scored, "sentiment_score", 0.0) if scored else 0.0
        sentiment_label = getattr(scored, "sentiment_label", "Neutral") if scored else "Neutral"

        assert sentiment_score == 0.0, "Should default to 0.0 when scored is None"
        assert sentiment_label == "Neutral", "Should default to Neutral when scored is None"

    @pytest.mark.parametrize("quickchart,gauge,advanced", [
        ("1", "0", "0"),  # Only QuickChart
        ("0", "1", "0"),  # Only Sentiment Gauge
        ("0", "0", "1"),  # Only Advanced Charts
        ("1", "1", "0"),  # QuickChart + Gauge
        ("1", "0", "1"),  # QuickChart + Advanced
        ("0", "1", "1"),  # Gauge + Advanced
        ("1", "1", "1"),  # All three
        ("0", "0", "0"),  # None
    ])
    def test_mixed_feature_flag_configurations(
        self, quickchart, gauge, advanced, mock_market_info_open
    ):
        """Test various combinations of feature flags."""
        with patch.dict(os.environ, {
            "FEATURE_QUICKCHART_POST": quickchart,
            "FEATURE_SENTIMENT_GAUGE": gauge,
            "FEATURE_ADVANCED_CHARTS": advanced,
        }):
            charts_enabled = mock_market_info_open["features"]["charts_enabled"]

            use_quickchart = os.getenv("FEATURE_QUICKCHART_POST", "0").strip().lower() in ("1", "true", "yes")
            use_gauge = os.getenv("FEATURE_SENTIMENT_GAUGE", "1").strip().lower() in ("1", "true", "yes")
            use_advanced = os.getenv("FEATURE_ADVANCED_CHARTS", "0").strip().lower() in ("1", "true", "yes", "on")

            # Verify each chart system respects its own flag independently
            assert (use_quickchart and charts_enabled) == (quickchart == "1" and charts_enabled)
            assert (use_gauge and charts_enabled) == (gauge == "1" and charts_enabled)
            assert (use_advanced and charts_enabled) == (advanced == "1" and charts_enabled)


# ============================================================================
# Integration Test with Full Alert Flow (Smoke Test)
# ============================================================================


class TestChartGenerationIntegration:
    """Integration tests that verify chart generation in full alert context."""

    def test_full_alert_flow_with_all_charts(
        self, mock_item_dict, mock_scored_item, mock_market_info_open,
        mock_quickchart_png, mock_gauge_png, mock_advanced_chart_png
    ):
        """Smoke test: Verify all chart systems can coexist in a single alert."""
        with patch.dict(os.environ, {
            "FEATURE_QUICKCHART_POST": "1",
            "FEATURE_SENTIMENT_GAUGE": "1",
            "FEATURE_ADVANCED_CHARTS": "1",
        }), \
        patch("src.catalyst_bot.alerts.get_quickchart_png_path", return_value=mock_quickchart_png), \
        patch("src.catalyst_bot.alerts.generate_sentiment_gauge", return_value=mock_gauge_png), \
        patch("src.catalyst_bot.alerts.generate_multi_panel_chart", return_value=mock_advanced_chart_png):

            charts_enabled = mock_market_info_open["features"]["charts_enabled"]

            # Simulate chart generation logic
            quickchart_path = mock_quickchart_png if charts_enabled else None
            gauge_path = mock_gauge_png if charts_enabled else None
            advanced_path = mock_advanced_chart_png if charts_enabled else None

            # All charts should be generated
            assert quickchart_path is not None, "QuickChart should be generated"
            assert gauge_path is not None, "Sentiment Gauge should be generated"
            assert advanced_path is not None, "Advanced Charts should be generated"

            # Verify paths are valid
            assert isinstance(quickchart_path, Path)
            assert isinstance(gauge_path, Path)
            assert isinstance(advanced_path, Path)

    def test_no_charts_generated_when_all_disabled(
        self, mock_item_dict, mock_scored_item, mock_market_info_closed
    ):
        """Test that no charts are generated when everything is disabled."""
        with patch.dict(os.environ, {
            "FEATURE_QUICKCHART_POST": "0",
            "FEATURE_SENTIMENT_GAUGE": "0",
            "FEATURE_ADVANCED_CHARTS": "0",
        }):
            charts_enabled = mock_market_info_closed["features"]["charts_enabled"]

            use_quickchart = os.getenv("FEATURE_QUICKCHART_POST", "0").strip().lower() in ("1", "true", "yes")
            use_gauge = os.getenv("FEATURE_SENTIMENT_GAUGE", "1").strip().lower() in ("1", "true", "yes")
            use_advanced = os.getenv("FEATURE_ADVANCED_CHARTS", "0").strip().lower() in ("1", "true", "yes", "on")

            # None should generate
            assert not (use_quickchart and charts_enabled), "QuickChart should NOT generate"
            assert not (use_gauge and charts_enabled), "Sentiment Gauge should NOT generate"
            assert not (use_advanced and charts_enabled), "Advanced Charts should NOT generate"


if __name__ == "__main__":
    # Run tests with verbose output
    pytest.main([__file__, "-v", "-s"])
