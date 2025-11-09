"""
Integration tests for critical alert system patches (Waves 1-3).

Tests verify:
- Wave 1: Environment configuration changes
- Wave 2: Retrospective filter integration
- Wave 3: SEC filing alert improvements

Run with:
    pytest tests/test_critical_patches.py -v
"""

import os
import pytest
from unittest.mock import Mock, patch


# ============================================================================
# Wave 1: Environment Configuration Tests
# ============================================================================

class TestWave1EnvironmentConfiguration:
    """Verify Wave 1 configuration changes."""

    def test_rvol_disabled(self):
        """Verify FEATURE_RVOL is disabled."""
        from catalyst_bot.config import Settings
        settings = Settings()
        assert settings.FEATURE_RVOL == 0, "FEATURE_RVOL should be 0 (disabled)"

    def test_rvol_min_avg_volume_reduced(self):
        """Verify RVOL_MIN_AVG_VOLUME reduced from 100k to 50k."""
        from catalyst_bot.config import Settings
        settings = Settings()
        assert settings.RVOL_MIN_AVG_VOLUME == 50000, \
            "RVOL_MIN_AVG_VOLUME should be 50000"

    def test_momentum_indicators_disabled(self):
        """Verify FEATURE_MOMENTUM_INDICATORS is disabled."""
        from catalyst_bot.config import Settings
        settings = Settings()
        assert settings.FEATURE_MOMENTUM_INDICATORS == 0, \
            "FEATURE_MOMENTUM_INDICATORS should be 0 (disabled)"

    def test_volume_price_divergence_disabled(self):
        """Verify FEATURE_VOLUME_PRICE_DIVERGENCE is disabled."""
        from catalyst_bot.config import Settings
        settings = Settings()
        assert settings.FEATURE_VOLUME_PRICE_DIVERGENCE == 0, \
            "FEATURE_VOLUME_PRICE_DIVERGENCE should be 0 (disabled)"

    def test_premarket_sentiment_disabled(self):
        """Verify FEATURE_PREMARKET_SENTIMENT is disabled."""
        from catalyst_bot.config import Settings
        settings = Settings()
        assert settings.FEATURE_PREMARKET_SENTIMENT == 0, \
            "FEATURE_PREMARKET_SENTIMENT should be 0 (disabled)"

    def test_aftermarket_sentiment_disabled(self):
        """Verify FEATURE_AFTERMARKET_SENTIMENT is disabled."""
        from catalyst_bot.config import Settings
        settings = Settings()
        assert settings.FEATURE_AFTERMARKET_SENTIMENT == 0, \
            "FEATURE_AFTERMARKET_SENTIMENT should be 0 (disabled)"

    def test_market_open_cycle_reduced(self):
        """Verify MARKET_OPEN_CYCLE_SEC reduced from 60s to 20s."""
        from catalyst_bot.config import Settings
        settings = Settings()
        assert settings.MARKET_OPEN_CYCLE_SEC == 20, \
            "MARKET_OPEN_CYCLE_SEC should be 20 seconds"

    def test_extended_hours_cycle_reduced(self):
        """Verify EXTENDED_HOURS_CYCLE_SEC reduced from 90s to 30s."""
        from catalyst_bot.config import Settings
        settings = Settings()
        assert settings.EXTENDED_HOURS_CYCLE_SEC == 30, \
            "EXTENDED_HOURS_CYCLE_SEC should be 30 seconds"

    def test_max_article_age_increased(self):
        """Verify MAX_ARTICLE_AGE_MINUTES increased from 30 to 60."""
        from catalyst_bot.config import Settings
        settings = Settings()
        assert settings.MAX_ARTICLE_AGE_MINUTES == 60, \
            "MAX_ARTICLE_AGE_MINUTES should be 60 minutes"

    def test_latency_improvement_calculation(self):
        """Verify expected latency improvement from cycle time changes."""
        from catalyst_bot.config import Settings
        settings = Settings()

        # Old: 60s cycle, New: 20s cycle
        old_cycle = 60
        new_cycle = settings.MARKET_OPEN_CYCLE_SEC

        # Improvement percentage
        improvement_pct = ((old_cycle - new_cycle) / old_cycle) * 100

        assert improvement_pct >= 60, \
            f"Expected >=60% latency improvement, got {improvement_pct:.1f}%"


# ============================================================================
# Wave 2: Retrospective Filter Tests
# ============================================================================

class TestWave2RetrospectiveFilter:
    """Verify Wave 2 retrospective filter implementation."""

    def test_function_exists(self):
        """Verify _is_retrospective_article function exists."""
        from catalyst_bot.feeds import _is_retrospective_article
        assert callable(_is_retrospective_article), \
            "_is_retrospective_article should be a callable function"

    # Category 1: Past-tense movements
    def test_why_articles_with_ticker_prefix(self):
        """Test 'why' articles with [TICKER] prefix are blocked."""
        from catalyst_bot.feeds import _is_retrospective_article

        # Real-world failures from 11/5/2025
        assert _is_retrospective_article(
            "[MX] Why Magnachip (MX) Stock Is Trading Lower Today",
            ""
        ) == True, "Should block: Why [ticker] stock is trading lower"

        assert _is_retrospective_article(
            "[CLOV] Why Clover Health (CLOV) Stock Is Falling Today",
            ""
        ) == True, "Should block: Why [ticker] stock is falling"

    def test_why_stock_dropped_percentage(self):
        """Test 'why stock dropped X%' articles are blocked."""
        from catalyst_bot.feeds import _is_retrospective_article

        assert _is_retrospective_article(
            "Why SoundHound Stock Dropped 14.6%",
            ""
        ) == True, "Should block: Why stock dropped X%"

        assert _is_retrospective_article(
            "Why BYND shares fell 23% after earnings",
            ""
        ) == True, "Should block: Why shares fell X%"

    def test_heres_why_articles(self):
        """Test 'here's why' articles are blocked."""
        from catalyst_bot.feeds import _is_retrospective_article

        assert _is_retrospective_article(
            "Here's why investors aren't happy",
            ""
        ) == True, "Should block: Here's why..."

    def test_percentage_moves_in_headlines(self):
        """Test price percentage moves are blocked."""
        from catalyst_bot.feeds import _is_retrospective_article

        assert _is_retrospective_article(
            "Stock Surged 23% After Earnings",
            ""
        ) == True, "Should block: Stock surged X%"

        assert _is_retrospective_article(
            "Shares plunge 15% on guidance cut",
            ""
        ) == True, "Should block: Shares plunge X%"

    def test_stock_slides_despite(self):
        """Test 'stock slides despite' articles are blocked."""
        from catalyst_bot.feeds import _is_retrospective_article

        assert _is_retrospective_article(
            "Stock Slides Despite Earnings Beat",
            ""
        ) == True, "Should block: Stock slides despite"

    # Category 2: Earnings reports
    def test_earnings_reports(self):
        """Test earnings report summaries are blocked."""
        from catalyst_bot.feeds import _is_retrospective_article

        assert _is_retrospective_article(
            "Reports Q4 Loss, Lags Revenue Estimates",
            ""
        ) == True, "Should block: Reports Q4 loss"

        assert _is_retrospective_article(
            "Company Reports Q3 Earnings Miss",
            ""
        ) == True, "Should block: Reports Q3 earnings miss"

    def test_beats_misses_estimates(self):
        """Test beats/misses estimates articles are blocked."""
        from catalyst_bot.feeds import _is_retrospective_article

        assert _is_retrospective_article(
            "Beats Revenue Estimates by $5M",
            ""
        ) == True, "Should block: Beats revenue estimates"

        assert _is_retrospective_article(
            "Misses earnings estimates for Q2",
            ""
        ) == True, "Should block: Misses earnings estimates"

    # Category 3: Earnings snapshots
    def test_earnings_snapshots(self):
        """Test earnings snapshot articles are blocked."""
        from catalyst_bot.feeds import _is_retrospective_article

        assert _is_retrospective_article(
            "Earnings Snapshot: BYND stock",
            ""
        ) == True, "Should block: Earnings snapshot"

    # Category 4: Speculative pre-earnings
    def test_what_to_expect_articles(self):
        """Test 'what to expect' articles are blocked."""
        from catalyst_bot.feeds import _is_retrospective_article

        assert _is_retrospective_article(
            "What to expect from earnings call tomorrow",
            ""
        ) == True, "Should block: What to expect"

    # Valid catalysts should NOT be blocked
    def test_valid_catalysts_allowed_acquisitions(self):
        """Test acquisition announcements are NOT blocked."""
        from catalyst_bot.feeds import _is_retrospective_article

        assert _is_retrospective_article(
            "Company Announces $50M Acquisition",
            ""
        ) == False, "Should allow: Acquisition announcement"

    def test_valid_catalysts_allowed_fda(self):
        """Test FDA approvals are NOT blocked."""
        from catalyst_bot.feeds import _is_retrospective_article

        assert _is_retrospective_article(
            "FDA Approves New Drug for Diabetes",
            ""
        ) == False, "Should allow: FDA approval"

    def test_valid_catalysts_allowed_insider_buying(self):
        """Test insider buying is NOT blocked."""
        from catalyst_bot.feeds import _is_retrospective_article

        assert _is_retrospective_article(
            "Insider Buys $2M in Shares",
            ""
        ) == False, "Should allow: Insider buying"

    def test_valid_catalysts_allowed_future_earnings(self):
        """Test future earnings announcements are NOT blocked."""
        from catalyst_bot.feeds import _is_retrospective_article

        assert _is_retrospective_article(
            "Company to Report Earnings After Market Close",
            ""
        ) == False, "Should allow: Future earnings (not retrospective)"

    def test_valid_catalysts_allowed_partnerships(self):
        """Test partnership deals are NOT blocked."""
        from catalyst_bot.feeds import _is_retrospective_article

        assert _is_retrospective_article(
            "Partnership Deal with Major Tech Firm",
            ""
        ) == False, "Should allow: Partnership announcement"

    def test_valid_catalysts_allowed_product_launches(self):
        """Test product launches are NOT blocked."""
        from catalyst_bot.feeds import _is_retrospective_article

        assert _is_retrospective_article(
            "New Product Launch Announced for Q3",
            ""
        ) == False, "Should allow: Product launch"

    def test_pattern_coverage(self):
        """Verify pattern count matches expected (20 patterns)."""
        from catalyst_bot.feeds import _is_retrospective_article
        import inspect

        # Get source code
        source = inspect.getsource(_is_retrospective_article)

        # Count patterns (lines starting with r" in the patterns list)
        pattern_count = source.count('r"\\b')  # Most patterns use \b word boundary

        assert pattern_count >= 15, \
            f"Expected >=15 patterns, found {pattern_count}"


# ============================================================================
# Wave 3: SEC Filing Alert Tests
# ============================================================================

class TestWave3SECFilingAlerts:
    """Verify Wave 3 SEC filing alert improvements."""

    def test_dilution_calculation_function_exists(self):
        """Verify dilution calculation function exists."""
        from catalyst_bot.sec_filing_alerts import _calculate_dilution_percentage
        assert callable(_calculate_dilution_percentage), \
            "_calculate_dilution_percentage should be callable"

    def test_dilution_calculation_logic(self):
        """Test dilution percentage calculation logic."""
        from catalyst_bot.sec_filing_alerts import _calculate_dilution_percentage

        # Mock market data to return 10M shares outstanding
        with patch('catalyst_bot.sec_filing_alerts.get_market_data') as mock_market:
            mock_data = Mock()
            mock_data.shares_outstanding = 10_000_000
            mock_market.return_value = mock_data

            # 1.5M new shares / 10M outstanding = 15% dilution
            dilution = _calculate_dilution_percentage(1_500_000, "TEST")
            assert dilution == 15.0, f"Expected 15% dilution, got {dilution}%"

    def test_format_filing_items_exists(self):
        """Verify filing items formatting function exists."""
        from catalyst_bot.sec_filing_alerts import _format_filing_items
        assert callable(_format_filing_items), \
            "_format_filing_items should be callable"

    def test_format_filing_items_bulleted_output(self):
        """Test filing items use bulleted format."""
        from catalyst_bot.sec_filing_alerts import _format_filing_items

        # Mock filing section
        mock_filing = Mock()
        mock_filing.item_title = "Completion of Acquisition"
        mock_filing.item_code = "2.01"
        mock_filing.deal_size_usd = 2_900_000

        result = _format_filing_items(mock_filing)

        # Verify bullet format
        assert "•" in result, "Should use bullet points"
        assert "Item 2.01" in result, "Should include item code"
        assert "└" in result or "Deal Size" in result, \
            "Should include sub-item details"

    def test_format_filing_items_dilution_display(self):
        """Test dilution is displayed in Item 3.02."""
        from catalyst_bot.sec_filing_alerts import _format_filing_items

        # Mock filing section for Item 3.02
        mock_filing = Mock()
        mock_filing.item_title = "Unregistered Sales of Equity Securities"
        mock_filing.item_code = "3.02"
        mock_filing.share_count = 1_500_000
        mock_filing.ticker = "TEST"

        # Mock market data for dilution calculation
        with patch('catalyst_bot.sec_filing_alerts._calculate_dilution_percentage') as mock_dilution:
            mock_dilution.return_value = 18.2

            result = _format_filing_items(mock_filing)

            # Verify dilution is displayed
            assert "dilution" in result.lower(), "Should display dilution percentage"
            assert "1,500,000" in result, "Should format share count with commas"

    def test_create_sec_filing_embed_has_filing_items_field(self):
        """Verify embed includes '📋 Filing Items' field."""
        from catalyst_bot.sec_filing_alerts import create_sec_filing_embed

        # Mock filing section
        mock_filing = Mock()
        mock_filing.ticker = "TEST"
        mock_filing.filing_type = "8-K"
        mock_filing.item_code = "2.01"
        mock_filing.item_title = "Completion of Acquisition"
        mock_filing.catalyst_type = "acquisition"
        mock_filing.filing_url = "https://sec.gov/test"
        mock_filing.deal_size_usd = 2_900_000

        # Mock sentiment
        mock_sentiment = Mock()
        mock_sentiment.score = 0.5
        mock_sentiment.weighted_score = 0.5
        mock_sentiment.justification = "Positive acquisition"

        # Create embed
        embed = create_sec_filing_embed(
            filing_section=mock_filing,
            sentiment_output=mock_sentiment,
            llm_summary="Test summary",
        )

        # Verify filing items field exists
        field_names = [f["name"] for f in embed.get("fields", [])]
        assert "📋 Filing Items" in field_names, \
            "Embed should include '📋 Filing Items' field"

    def test_no_metadata_clutter_in_embed(self):
        """Verify AccNo, Size, Filed date are NOT in embed."""
        from catalyst_bot.sec_filing_alerts import create_sec_filing_embed

        # Mock filing section
        mock_filing = Mock()
        mock_filing.ticker = "TEST"
        mock_filing.filing_type = "10-Q"
        mock_filing.item_code = None
        mock_filing.item_title = "Quarterly Report"
        mock_filing.catalyst_type = None
        mock_filing.filing_url = "https://sec.gov/test"
        mock_filing.accession_number = "0001234567-12-123456"  # Should NOT appear
        mock_filing.size_bytes = 1234567  # Should NOT appear

        # Mock sentiment
        mock_sentiment = Mock()
        mock_sentiment.score = 0.0
        mock_sentiment.weighted_score = 0.0
        mock_sentiment.justification = ""

        # Create embed
        embed = create_sec_filing_embed(
            filing_section=mock_filing,
            sentiment_output=mock_sentiment,
            llm_summary="Test",
        )

        # Convert embed to string for easier checking
        import json
        embed_str = json.dumps(embed).lower()

        # Verify metadata NOT present
        assert "accno" not in embed_str, "Should NOT include AccNo"
        assert "accession" not in embed_str, "Should NOT include accession number"
        assert "size" not in embed_str or "deal size" in embed_str, \
            "Should NOT include file size (but deal size is ok)"


# ============================================================================
# Integration Tests (All Waves)
# ============================================================================

class TestIntegration:
    """Integration tests across all three waves."""

    def test_end_to_end_alert_pipeline_stability(self):
        """Verify alert pipeline doesn't break with all patches."""
        # This is a smoke test - just verify imports work
        try:
            from catalyst_bot import feeds
            from catalyst_bot import sec_filing_alerts
            from catalyst_bot.config import Settings

            # Verify key functions exist
            assert hasattr(feeds, '_is_retrospective_article')
            assert hasattr(sec_filing_alerts, '_calculate_dilution_percentage')
            assert hasattr(sec_filing_alerts, '_format_filing_items')

            settings = Settings()
            assert settings.MARKET_OPEN_CYCLE_SEC == 20

        except Exception as e:
            pytest.fail(f"Pipeline integration broken: {e}")

    def test_configuration_values_consistent(self):
        """Verify all Wave 1 configuration values are consistent."""
        from catalyst_bot.config import Settings
        settings = Settings()

        # All critical features should be disabled
        assert settings.FEATURE_RVOL == 0
        assert settings.FEATURE_MOMENTUM_INDICATORS == 0
        assert settings.FEATURE_VOLUME_PRICE_DIVERGENCE == 0
        assert settings.FEATURE_PREMARKET_SENTIMENT == 0
        assert settings.FEATURE_AFTERMARKET_SENTIMENT == 0

        # Scan cycles should be fast
        assert settings.MARKET_OPEN_CYCLE_SEC == 20
        assert settings.EXTENDED_HOURS_CYCLE_SEC == 30

        # Article age should be extended
        assert settings.MAX_ARTICLE_AGE_MINUTES == 60


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
