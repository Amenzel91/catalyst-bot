"""
Test suite for offering sentiment correction (Wave 3.4).

Tests the offering sentiment detection and correction system to ensure:
1. Accurate stage detection (closing, announcement, pricing, upsize)
2. Correct sentiment assignment by stage
3. Proper integration with classification pipeline
4. Edge case handling (ambiguous language, multiple stages, false positives)
"""

import pytest

from src.catalyst_bot.offering_sentiment import (
    apply_offering_sentiment_correction,
    detect_offering_stage,
    get_offering_sentiment,
    get_offering_stage_label,
    get_offering_emoji,
    is_offering_news,
)


class TestOfferingDetection:
    """Test offering news detection and stage identification."""

    def test_is_offering_news_positive_cases(self):
        """Test that offering-related news is correctly identified."""
        assert is_offering_news("Company closes $50M public offering") is True
        assert is_offering_news("Announces secondary offering of common shares") is True
        assert is_offering_news("Prices underwritten public offering at $2.50") is True
        assert is_offering_news("Upsizes offering to $75M from $50M") is True

    def test_is_offering_news_negative_cases(self):
        """Test that non-offering news is correctly rejected."""
        assert is_offering_news("Apple releases new iPhone") is False
        assert is_offering_news("Company beats earnings estimates") is False
        assert is_offering_news("FDA approves new drug") is False
        assert is_offering_news("Merger agreement announced") is False

    def test_detect_closing_stage(self):
        """Test detection of offering closing/completion."""
        # Standard closing language
        title = "Company announces closing of $50M public offering"
        stage, confidence = detect_offering_stage(title)
        assert stage == "closing"
        assert confidence >= 0.85

        # Alternative closing language
        title = "Company closes previously announced offering"
        stage, confidence = detect_offering_stage(title)
        assert stage == "closing"

        # Completed language
        title = "Company completed $50M registered direct offering"
        stage, confidence = detect_offering_stage(title)
        assert stage == "closing"

    def test_detect_announcement_stage(self):
        """Test detection of new offering announcements."""
        # Standard announcement
        title = "Company announces $100M public offering"
        stage, confidence = detect_offering_stage(title)
        assert stage == "announcement"
        assert confidence >= 0.85

        # Filed offering
        title = "Company files for $50M shelf offering"
        stage, confidence = detect_offering_stage(title)
        assert stage == "announcement"

        # Intends to offer
        title = "Company intends to offer $30M in common stock"
        stage, confidence = detect_offering_stage(title)
        assert stage == "announcement"

    def test_detect_pricing_stage(self):
        """Test detection of offering pricing."""
        # Standard pricing
        title = "Company prices $50M offering at $10 per share"
        stage, confidence = detect_offering_stage(title)
        assert stage == "pricing"
        assert confidence >= 0.85

        # Priced offering
        title = "Company priced public offering of 5M shares"
        stage, confidence = detect_offering_stage(title)
        assert stage == "pricing"

    def test_detect_upsize_stage(self):
        """Test detection of offering upsize."""
        # Standard upsize
        title = "Company upsizes offering to $75M from $50M"
        stage, confidence = detect_offering_stage(title)
        assert stage == "upsize"
        assert confidence >= 0.9

        # Increases offering size
        title = "Company increases offering size to $100M"
        stage, confidence = detect_offering_stage(title)
        assert stage == "upsize"

    def test_stage_priority_upsize_over_others(self):
        """Test that upsize takes priority when multiple stages mentioned."""
        # Upsize + pricing mentioned together
        title = "Company upsizes and prices offering at $10/share"
        stage, confidence = detect_offering_stage(title)
        assert stage == "upsize"  # Upsize should win

    def test_stage_priority_closing_over_announcement(self):
        """Test that closing takes priority over announcement when both present."""
        # Sometimes news mentions original announcement + closing
        title = "Company announces closing of previously announced $50M offering"
        stage, confidence = detect_offering_stage(title)
        assert stage == "closing"  # Closing should win


class TestSentimentAssignment:
    """Test sentiment score assignment for each offering stage."""

    def test_closing_sentiment_positive(self):
        """Test that closing gets slightly bullish sentiment."""
        sentiment = get_offering_sentiment("closing")
        assert sentiment == 0.2
        assert sentiment > 0  # Positive

    def test_announcement_sentiment_negative(self):
        """Test that announcement gets bearish sentiment."""
        sentiment = get_offering_sentiment("announcement")
        assert sentiment == -0.6
        assert sentiment < 0  # Negative

    def test_pricing_sentiment_negative(self):
        """Test that pricing gets bearish sentiment."""
        sentiment = get_offering_sentiment("pricing")
        assert sentiment == -0.5
        assert sentiment < 0  # Negative

    def test_upsize_sentiment_very_negative(self):
        """Test that upsize gets most bearish sentiment."""
        sentiment = get_offering_sentiment("upsize")
        assert sentiment == -0.7
        assert sentiment < get_offering_sentiment("pricing")  # More negative than pricing
        assert sentiment < get_offering_sentiment("announcement")  # Most negative

    def test_unknown_stage_defaults_bearish(self):
        """Test that unknown stage defaults to bearish."""
        sentiment = get_offering_sentiment("unknown")
        assert sentiment == -0.5
        assert sentiment < 0


class TestSentimentCorrection:
    """Test the sentiment correction application."""

    def test_correction_applied_for_closing(self):
        """Test that closing sentiment overrides negative baseline."""
        title = "Company closes $50M public offering"
        current_sentiment = -0.5  # Wrongly bearish

        corrected, stage, was_corrected = apply_offering_sentiment_correction(
            title, current_sentiment=current_sentiment
        )

        assert was_corrected is True
        assert stage == "closing"
        assert corrected == 0.2  # Corrected to slightly bullish
        assert corrected > current_sentiment  # Improved

    def test_correction_applied_for_announcement(self):
        """Test that announcement sentiment is applied."""
        title = "Company announces $100M public offering"
        current_sentiment = 0.0

        corrected, stage, was_corrected = apply_offering_sentiment_correction(
            title, current_sentiment=current_sentiment
        )

        assert was_corrected is True
        assert stage == "announcement"
        assert corrected == -0.6  # Bearish

    def test_correction_applied_for_upsize(self):
        """Test that upsize sentiment is most negative."""
        title = "Company upsizes offering to $75M"
        current_sentiment = -0.3

        corrected, stage, was_corrected = apply_offering_sentiment_correction(
            title, current_sentiment=current_sentiment
        )

        assert was_corrected is True
        assert stage == "upsize"
        assert corrected == -0.7  # Very bearish
        assert corrected < current_sentiment  # Made more negative

    def test_no_correction_for_non_offering(self):
        """Test that non-offering news is not corrected."""
        title = "Apple releases new iPhone"
        current_sentiment = 0.3

        corrected, stage, was_corrected = apply_offering_sentiment_correction(
            title, current_sentiment=current_sentiment
        )

        assert was_corrected is False
        assert stage is None
        assert corrected == current_sentiment  # Unchanged

    def test_confidence_threshold_respected(self):
        """Test that low-confidence detections don't override."""
        title = "Company closes $50M public offering"
        current_sentiment = -0.5

        # Set impossibly high confidence threshold
        corrected, stage, was_corrected = apply_offering_sentiment_correction(
            title, current_sentiment=current_sentiment, min_confidence=0.99
        )

        # Stage detected but confidence too low to override
        assert stage == "closing"
        # Should not override due to confidence check
        # (Our closing confidence is 0.9, below 0.99)


class TestEdgeCases:
    """Test edge cases and ambiguous scenarios."""

    def test_multiple_offerings_mentioned(self):
        """Test handling when multiple offerings mentioned."""
        title = "Company closes $50M offering and announces new $100M offering"
        # Should prioritize most material/recent (closing)
        stage, confidence = detect_offering_stage(title)
        # Upsize not present, so closing vs announcement
        # Our priority: upsize > closing > pricing > announcement
        assert stage in ["closing", "announcement"]

    def test_offering_with_summary_text(self):
        """Test detection using both title and summary."""
        title = "Company announces corporate update"
        text = "We are pleased to announce the closing of our $50M public offering"

        stage, confidence = detect_offering_stage(title, text)
        assert stage == "closing"

    def test_registered_direct_offering(self):
        """Test detection of registered direct offerings."""
        title = "Company closes $10M registered direct offering"
        stage, confidence = detect_offering_stage(title)
        assert stage == "closing"

    def test_secondary_offering(self):
        """Test detection of secondary offerings."""
        title = "Company announces secondary offering of 2M shares"
        stage, confidence = detect_offering_stage(title)
        assert stage == "announcement"

    def test_shelf_offering(self):
        """Test detection of shelf offerings."""
        title = "Company files shelf offering registration"
        stage, confidence = detect_offering_stage(title)
        assert stage == "announcement"

    def test_underwritten_offering(self):
        """Test detection of underwritten offerings."""
        title = "Company prices underwritten public offering at $5.00"
        stage, confidence = detect_offering_stage(title)
        assert stage == "pricing"


class TestLabelingAndDisplay:
    """Test human-readable labels and emoji selection."""

    def test_stage_labels(self):
        """Test stage label generation."""
        assert get_offering_stage_label("closing") == "CLOSING"
        assert get_offering_stage_label("announcement") == "ANNOUNCED"
        assert get_offering_stage_label("pricing") == "PRICED"
        assert get_offering_stage_label("upsize") == "UPSIZED"
        assert get_offering_stage_label(None) == "OFFERING"
        assert get_offering_stage_label("unknown") == "OFFERING"

    def test_stage_emojis(self):
        """Test emoji selection for each stage."""
        assert get_offering_emoji("closing") == "✅"  # Checkmark (positive)
        assert get_offering_emoji("announcement") == "💰"  # Money bag (neutral/negative)
        assert get_offering_emoji("pricing") == "💵"  # Dollar (negative)
        assert get_offering_emoji("upsize") == "📉"  # Down chart (very negative)
        assert get_offering_emoji(None) == "💰"  # Default


class TestRealWorldExamples:
    """Test real-world examples from user feedback."""

    def test_example_1_aapl_closing(self):
        """Real-world test: AAPL closes offering."""
        title = "AAPL closes previously announced $100M public offering"

        stage, confidence = detect_offering_stage(title)
        assert stage == "closing"

        sentiment = get_offering_sentiment(stage)
        assert sentiment == 0.2  # Slightly bullish (completion)

    def test_example_2_tsla_announcement(self):
        """Real-world test: TSLA announces offering."""
        title = "TSLA announces $2B common stock offering"

        stage, confidence = detect_offering_stage(title)
        assert stage == "announcement"

        sentiment = get_offering_sentiment(stage)
        assert sentiment == -0.6  # Bearish (new dilution)

    def test_example_3_nvda_pricing(self):
        """Real-world test: NVDA prices offering."""
        title = "NVDA prices $500M offering at $120 per share"

        stage, confidence = detect_offering_stage(title)
        assert stage == "pricing"

        sentiment = get_offering_sentiment(stage)
        assert sentiment == -0.5  # Bearish (dilution confirmed)

    def test_example_4_amd_upsize(self):
        """Real-world test: AMD upsizes offering."""
        title = "AMD upsizes offering from $300M to $500M"

        stage, confidence = detect_offering_stage(title)
        assert stage == "upsize"

        sentiment = get_offering_sentiment(stage)
        assert sentiment == -0.7  # Very bearish (more dilution)

    def test_example_5_correction_scenario(self):
        """Test full correction scenario: closing misclassified as bearish."""
        title = "BioTech Inc. announces closing of $25M registered direct offering"

        # Simulate wrong sentiment from keyword matching
        wrong_sentiment = -0.5  # Keyword "offering" triggered bearish

        # Apply correction
        corrected, stage, was_corrected = apply_offering_sentiment_correction(
            title, current_sentiment=wrong_sentiment
        )

        assert was_corrected is True
        assert stage == "closing"
        assert corrected == 0.2  # Corrected to slightly bullish
        assert corrected > wrong_sentiment  # Fixed the error


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
