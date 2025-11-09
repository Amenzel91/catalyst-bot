"""Test offering classification fix for PSEC/POET scenarios.

This test suite validates that the offering sentiment correction system
properly handles:
1. Debt/notes offerings (PSEC) - should be neutral/positive (no dilution)
2. Equity offering closings (POET) - should be slightly positive (completion)
3. Regular equity offerings - should remain negative (dilutive)

Bug context:
- User reported PSEC debt offering had green border (classified as positive) ✓
- User questioned if it should be negative
- Actually: debt offerings don't dilute equity, so neutral/positive is CORRECT
- User reported POET offering had no pump despite closing
- Issue: ALL offerings were being marked as negative alerts (red border)
- Fix: Detect offering stage and debt vs equity to assign proper sentiment
"""

import pytest

from src.catalyst_bot.offering_sentiment import (
    apply_offering_sentiment_correction,
    detect_offering_stage,
    is_debt_offering,
    is_offering_news,
)


class TestPSECScenario:
    """Test PSEC debt offering scenario (should be neutral/positive)."""

    def test_psec_is_debt_offering(self):
        """PSEC: Verify it's detected as debt offering."""
        title = (
            "Prospect Capital Corporation Announces Pricing of "
            "$167 Million 5.5% Oversubscribed Institutional Unsecured Notes Offering"
        )

        # Should be recognized as offering news
        assert is_offering_news(title) is True

        # Should be recognized as DEBT offering (non-dilutive)
        assert is_debt_offering(title) is True

    def test_psec_sentiment_correction(self):
        """PSEC: Verify sentiment is corrected to neutral/positive."""
        title = (
            "Prospect Capital Corporation Announces Pricing of "
            "$167 Million 5.5% Oversubscribed Institutional Unsecured Notes Offering"
        )

        # Simulate negative sentiment from keyword matching
        current_sentiment = -0.6  # Would be negative due to "offering" keyword

        # Apply correction
        corrected_sentiment, stage, was_corrected = apply_offering_sentiment_correction(
            title=title,
            text="",
            current_sentiment=current_sentiment,
            min_confidence=0.7,
        )

        # Should be corrected
        assert was_corrected is True
        assert stage == "debt"  # Detected as debt offering
        assert corrected_sentiment == 0.3  # Neutral to slightly positive

    def test_psec_not_negative_alert(self):
        """PSEC: Verify it's NOT marked as negative alert."""
        # This test verifies the classify.py integration
        # When stage is "debt", offering_negative should be removed from negative_keywords
        title = (
            "Prospect Capital Corporation Announces Pricing of "
            "$167 Million 5.5% Oversubscribed Institutional Unsecured Notes Offering"
        )

        # Detect stage
        corrected_sentiment, stage, was_corrected = apply_offering_sentiment_correction(
            title=title, current_sentiment=-0.6
        )

        # Should be debt offering, not negative alert
        assert stage == "debt"
        assert corrected_sentiment > 0  # Positive sentiment


class TestPOETScenario:
    """Test POET equity offering closing scenario (should be slightly positive)."""

    def test_poet_is_equity_offering_closing(self):
        """POET: Verify it's detected as offering closing."""
        title = (
            "POET Technologies Announces Closing of US$150 Million "
            "Oversubscribed Registered Direct Offering"
        )

        # Should be recognized as offering news
        assert is_offering_news(title) is True

        # Should NOT be debt offering (it's equity)
        assert is_debt_offering(title) is False

        # Should detect "closing" stage
        stage, confidence = detect_offering_stage(title)
        assert stage == "closing"
        assert confidence >= 0.85

    def test_poet_sentiment_correction(self):
        """POET: Verify sentiment is corrected to slightly positive."""
        title = (
            "POET Technologies Announces Closing of US$150 Million "
            "Oversubscribed Registered Direct Offering"
        )

        # Simulate negative sentiment from keyword matching
        current_sentiment = -0.6  # Would be negative due to "offering" keyword

        # Apply correction
        corrected_sentiment, stage, was_corrected = apply_offering_sentiment_correction(
            title=title,
            text="",
            current_sentiment=current_sentiment,
            min_confidence=0.7,
        )

        # Should be corrected
        assert was_corrected is True
        assert stage == "closing"  # Detected as closing stage
        assert corrected_sentiment == 0.2  # Slightly positive (completion)

    def test_poet_not_negative_alert(self):
        """POET: Verify it's NOT marked as negative alert."""
        # When stage is "closing", offering_negative should be removed from negative_keywords
        title = (
            "POET Technologies Announces Closing of US$150 Million "
            "Oversubscribed Registered Direct Offering"
        )

        # Detect stage
        corrected_sentiment, stage, was_corrected = apply_offering_sentiment_correction(
            title=title, current_sentiment=-0.6
        )

        # Should be closing stage, slightly positive
        assert stage == "closing"
        assert corrected_sentiment > 0  # Positive sentiment (completion)


class TestNegativeOfferingScenarios:
    """Test scenarios that SHOULD remain negative (dilutive offerings)."""

    def test_announcement_remains_negative(self):
        """New offering announcements should be negative."""
        title = "Company announces $100M public offering"

        corrected_sentiment, stage, was_corrected = apply_offering_sentiment_correction(
            title=title, current_sentiment=0.0
        )

        assert was_corrected is True
        assert stage == "announcement"
        assert corrected_sentiment == -0.6  # Bearish

    def test_pricing_remains_negative(self):
        """Offering pricing should be negative."""
        title = "Company prices $50M offering at $10 per share"

        corrected_sentiment, stage, was_corrected = apply_offering_sentiment_correction(
            title=title, current_sentiment=0.0
        )

        assert was_corrected is True
        assert stage == "pricing"
        assert corrected_sentiment == -0.5  # Bearish

    def test_upsize_remains_negative(self):
        """Offering upsize should be very negative."""
        title = "Company upsizes offering to $75M from $50M"

        corrected_sentiment, stage, was_corrected = apply_offering_sentiment_correction(
            title=title, current_sentiment=0.0
        )

        assert was_corrected is True
        assert stage == "upsize"
        assert corrected_sentiment == -0.7  # Very bearish


class TestDebtOfferingVariations:
    """Test various debt offering formats to ensure broad coverage."""

    def test_senior_notes(self):
        """Test senior notes offering detection."""
        title = "Company prices $200M senior notes offering"
        assert is_debt_offering(title) is True

        corrected, stage, corrected_flag = apply_offering_sentiment_correction(
            title=title, current_sentiment=-0.5
        )
        assert stage == "debt"
        assert corrected > 0

    def test_convertible_notes(self):
        """Test convertible notes offering detection."""
        title = "Company announces $150M convertible notes offering"
        assert is_debt_offering(title) is True

        corrected, stage, corrected_flag = apply_offering_sentiment_correction(
            title=title, current_sentiment=-0.5
        )
        assert stage == "debt"
        assert corrected > 0

    def test_bond_offering(self):
        """Test bond offering detection."""
        title = "Company completes $300M bond offering"
        assert is_debt_offering(title) is True

        corrected, stage, corrected_flag = apply_offering_sentiment_correction(
            title=title, current_sentiment=-0.5
        )
        assert stage == "debt"
        assert corrected > 0


class TestBorderColorLogic:
    """Test that border colors match sentiment properly.

    From alerts.py line 1728-1731:
    - is_negative_alert = True → color = 0xFF0000 (red)
    - is_negative_alert = False → color based on price movement or indicators

    The fix ensures:
    - Debt offerings → NOT negative alert → green/blue border (based on price)
    - Offering closings → NOT negative alert → green/blue border (based on price)
    - Dilutive offerings → NEGATIVE alert → red border
    """

    def test_debt_offering_not_negative_alert(self):
        """Debt offerings should not trigger negative alert (red border)."""
        title = "PSEC prices $167M unsecured notes offering"

        corrected, stage, corrected_flag = apply_offering_sentiment_correction(
            title=title, current_sentiment=-0.6
        )

        # Stage is "debt", so in classify.py it will remove "offering_negative"
        # from negative_keywords, preventing alert_type="NEGATIVE"
        assert stage == "debt"
        assert corrected > 0  # Positive sentiment → green border

    def test_closing_not_negative_alert(self):
        """Offering closings should not trigger negative alert (red border)."""
        title = "POET closes $150M registered direct offering"

        corrected, stage, corrected_flag = apply_offering_sentiment_correction(
            title=title, current_sentiment=-0.6
        )

        # Stage is "closing", so in classify.py it will remove "offering_negative"
        # from negative_keywords, preventing alert_type="NEGATIVE"
        assert stage == "closing"
        assert corrected > 0  # Positive sentiment → green border

    def test_dilutive_offering_is_negative_alert(self):
        """Dilutive offerings should trigger negative alert (red border)."""
        title = "Company announces $100M public offering"

        corrected, stage, corrected_flag = apply_offering_sentiment_correction(
            title=title, current_sentiment=0.0
        )

        # Stage is "announcement", negative_keywords will still contain "offering_negative"
        # so alert_type="NEGATIVE" and red border
        assert stage == "announcement"
        assert corrected < 0  # Negative sentiment → red border


class TestOversubscribedOfferings:
    """Test oversubscribed offerings (demand signal).

    Oversubscribed offerings indicate strong demand, which can be a positive signal.
    Combined with debt or closing, these should be clearly positive.
    """

    def test_psec_oversubscribed_debt(self):
        """PSEC oversubscribed debt offering - strong positive signal."""
        title = (
            "Prospect Capital Corporation Announces Pricing of "
            "$167 Million 5.5% Oversubscribed Institutional Unsecured Notes Offering"
        )

        # Contains "oversubscribed" + "notes" = strong positive
        assert is_debt_offering(title) is True

        corrected, stage, _ = apply_offering_sentiment_correction(
            title=title, current_sentiment=-0.6
        )

        assert stage == "debt"
        assert corrected > 0  # Positive sentiment

    def test_poet_oversubscribed_closing(self):
        """POET oversubscribed closing - moderately positive signal."""
        title = (
            "POET Technologies Announces Closing of US$150 Million "
            "Oversubscribed Registered Direct Offering"
        )

        # Contains "oversubscribed" + "closing" = moderately positive
        stage, confidence = detect_offering_stage(title)
        assert stage == "closing"

        corrected, stage, _ = apply_offering_sentiment_correction(
            title=title, current_sentiment=-0.6
        )

        assert stage == "closing"
        assert corrected > 0  # Positive sentiment (completion)


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
