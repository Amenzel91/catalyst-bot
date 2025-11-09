# tests/test_catalyst_badges.py
"""Tests for the Catalyst Badge System (Wave 2 - Agent 2.2).

This module tests the extraction and prioritization of catalyst badges
for Discord alerts.
"""

import pytest

from catalyst_bot.catalyst_badges import (
    BADGE_PRIORITY,
    CATALYST_BADGES,
    CATALYST_PATTERNS,
    extract_catalyst_badges,
)


class TestBadgeExtraction:
    """Test badge extraction from various inputs."""

    def test_earnings_badge_from_title(self):
        """Test earnings badge detection from title."""
        badges = extract_catalyst_badges(
            classification=None,
            title="AAPL beats Q4 earnings expectations",
        )
        assert "📊 EARNINGS" in badges

    def test_fda_badge_from_title(self):
        """Test FDA badge detection from title."""
        badges = extract_catalyst_badges(
            classification=None,
            title="FDA approves new therapy for rare disease",
        )
        assert "💊 FDA NEWS" in badges

    def test_merger_badge_from_title(self):
        """Test M&A badge detection from title."""
        badges = extract_catalyst_badges(
            classification=None,
            title="Company A acquires Company B for $2B",
        )
        assert "🤝 M&A" in badges

    def test_guidance_badge_from_title(self):
        """Test guidance badge detection from title."""
        badges = extract_catalyst_badges(
            classification=None,
            title="Company raises full-year guidance",
        )
        assert "📈 GUIDANCE" in badges

    def test_sec_filing_badge_from_title(self):
        """Test SEC filing badge detection from title."""
        badges = extract_catalyst_badges(
            classification=None,
            title="Company files 8-K form with SEC",
        )
        assert "📄 SEC FILING" in badges

    def test_offering_badge_from_title(self):
        """Test offering badge detection from title."""
        badges = extract_catalyst_badges(
            classification=None,
            title="Company prices $50M secondary offering",
        )
        assert "💰 OFFERING" in badges

    def test_analyst_badge_from_title(self):
        """Test analyst badge detection from title."""
        badges = extract_catalyst_badges(
            classification=None,
            title="Analyst upgrades stock to buy with $150 price target",
        )
        assert "🎯 ANALYST" in badges

    def test_contract_badge_from_title(self):
        """Test contract badge detection from title."""
        badges = extract_catalyst_badges(
            classification=None,
            title="Company wins $10M government contract",
        )
        assert "📝 CONTRACT" in badges

    def test_partnership_badge_from_title(self):
        """Test partnership badge detection from title."""
        badges = extract_catalyst_badges(
            classification=None,
            title="Company announces collaboration with major pharma",
        )
        assert "🤝 PARTNERSHIP" in badges

    def test_product_badge_from_title(self):
        """Test product badge detection from title."""
        badges = extract_catalyst_badges(
            classification=None,
            title="Company launches new flagship product",
        )
        assert "🚀 PRODUCT" in badges

    def test_clinical_badge_from_title(self):
        """Test clinical badge detection from title."""
        badges = extract_catalyst_badges(
            classification=None,
            title="Positive trial results show 85% efficacy",
        )
        assert "🧪 CLINICAL" in badges

    def test_regulatory_badge_from_title(self):
        """Test regulatory badge detection from title."""
        badges = extract_catalyst_badges(
            classification=None,
            title="Company receives patent approval",
        )
        assert "⚖️ REGULATORY" in badges


class TestBadgeFromClassification:
    """Test badge extraction from classification tags."""

    def test_earnings_from_tags(self):
        """Test earnings badge from classification tags."""
        classification = {"tags": ["earnings", "revenue"]}
        badges = extract_catalyst_badges(
            classification=classification,
            title="Company reports results",
        )
        assert "📊 EARNINGS" in badges

    def test_fda_from_tags(self):
        """Test FDA badge from classification tags."""
        classification = {"tags": ["fda", "approval"]}
        badges = extract_catalyst_badges(
            classification=classification,
            title="Regulatory update",
        )
        assert "💊 FDA NEWS" in badges

    def test_multiple_tags_mapping(self):
        """Test multiple tags map to correct catalyst types."""
        classification = {"tags": ["earnings", "guidance", "analyst"]}
        badges = extract_catalyst_badges(
            classification=classification,
            title="Company updates outlook",
        )
        assert "📊 EARNINGS" in badges
        assert "📈 GUIDANCE" in badges
        # Analyst might not appear due to max_badges=3 and priority

    def test_keyword_hits_field(self):
        """Test extraction from keyword_hits field."""
        classification = {"keyword_hits": ["merger", "acquisition"]}
        badges = extract_catalyst_badges(
            classification=classification,
            title="Deal announced",
        )
        assert "🤝 M&A" in badges

    def test_keywords_field_fallback(self):
        """Test extraction from keywords field as fallback."""
        classification = {"keywords": ["offering", "priced"]}
        badges = extract_catalyst_badges(
            classification=classification,
            title="Capital raise",
        )
        assert "💰 OFFERING" in badges


class TestPriorityOrdering:
    """Test badge priority ordering."""

    def test_fda_highest_priority(self):
        """Test FDA badge has highest priority."""
        # Title contains both earnings and FDA keywords
        badges = extract_catalyst_badges(
            classification=None,
            title="FDA approval boosts Q4 earnings outlook",
        )
        # FDA should be first
        assert badges[0] == "💊 FDA NEWS"

    def test_earnings_over_analyst(self):
        """Test earnings has priority over analyst."""
        badges = extract_catalyst_badges(
            classification=None,
            title="Analyst raises target after strong Q3 earnings beat",
        )
        # Should have both, but earnings first
        assert "📊 EARNINGS" in badges
        assert "🎯 ANALYST" in badges
        # Earnings should appear before analyst
        earnings_idx = badges.index("📊 EARNINGS")
        analyst_idx = badges.index("🎯 ANALYST")
        assert earnings_idx < analyst_idx

    def test_max_badges_respected(self):
        """Test max_badges limit is respected."""
        # Title with 5+ catalyst types
        badges = extract_catalyst_badges(
            classification=None,
            title="FDA approves drug, company beats earnings, raises guidance, announces partnership, files 8-K",
            max_badges=3,
        )
        assert len(badges) <= 3

    def test_priority_order_matches_spec(self):
        """Test that BADGE_PRIORITY order matches specification."""
        # From spec: FDA > Earnings > M&A > Offerings > ...
        assert BADGE_PRIORITY[0] == "fda"
        assert BADGE_PRIORITY[1] == "earnings"
        assert BADGE_PRIORITY[2] == "merger"
        assert BADGE_PRIORITY[3] == "offering"


class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_empty_title(self):
        """Test handling of empty title."""
        badges = extract_catalyst_badges(
            classification=None,
            title="",
        )
        # Should return generic news badge
        assert badges == ["📰 NEWS"]

    def test_none_classification(self):
        """Test handling of None classification."""
        badges = extract_catalyst_badges(
            classification=None,
            title="Some generic news",
        )
        # Should return generic news badge if no patterns match
        assert badges == ["📰 NEWS"]

    def test_empty_classification(self):
        """Test handling of empty classification dict."""
        badges = extract_catalyst_badges(
            classification={},
            title="Generic update",
        )
        assert badges == ["📰 NEWS"]

    def test_no_matches(self):
        """Test when no catalyst patterns match."""
        badges = extract_catalyst_badges(
            classification={"tags": ["unknown", "other"]},
            title="Random company update",
        )
        assert badges == ["📰 NEWS"]

    def test_case_insensitivity(self):
        """Test pattern matching is case-insensitive."""
        badges_upper = extract_catalyst_badges(
            classification=None,
            title="FDA APPROVAL",
        )
        badges_lower = extract_catalyst_badges(
            classification=None,
            title="fda approval",
        )
        badges_mixed = extract_catalyst_badges(
            classification=None,
            title="Fda ApPrOvAl",
        )
        assert badges_upper == badges_lower == badges_mixed

    def test_text_parameter_usage(self):
        """Test that text parameter is included in pattern matching."""
        badges = extract_catalyst_badges(
            classification=None,
            title="Company update",
            text="The FDA has granted approval for the new therapy",
        )
        assert "💊 FDA NEWS" in badges

    def test_sec_filing_source_detection(self):
        """Test SEC filing detection from source field."""
        classification = {"source": "sec_8k"}
        badges = extract_catalyst_badges(
            classification=classification,
            title="Regulatory filing",
        )
        assert "📄 SEC FILING" in badges


class TestMultipleBadges:
    """Test scenarios with multiple badges."""

    def test_two_badges(self):
        """Test extraction of two distinct badges."""
        badges = extract_catalyst_badges(
            classification=None,
            title="Company beats earnings and raises guidance",
            max_badges=3,
        )
        assert len(badges) == 2
        assert "📊 EARNINGS" in badges
        assert "📈 GUIDANCE" in badges

    def test_three_badges(self):
        """Test extraction of three badges (max default)."""
        badges = extract_catalyst_badges(
            classification=None,
            title="FDA approves drug, earnings beat, analyst upgrade",
            max_badges=3,
        )
        assert len(badges) == 3

    def test_custom_max_badges(self):
        """Test custom max_badges parameter."""
        badges = extract_catalyst_badges(
            classification=None,
            title="FDA approves drug, earnings beat, merger announced",
            max_badges=2,
        )
        assert len(badges) == 2
        # Should prioritize FDA and earnings over merger
        assert "💊 FDA NEWS" in badges
        assert "📊 EARNINGS" in badges


class TestRealWorldScenarios:
    """Test with real-world classification data patterns."""

    def test_earnings_beat_scenario(self):
        """Test typical earnings beat alert."""
        classification = {
            "tags": ["earnings", "revenue"],
            "sentiment": 0.75,
        }
        badges = extract_catalyst_badges(
            classification=classification,
            title="TSLA reports record Q3 earnings, beats on revenue",
        )
        assert "📊 EARNINGS" in badges

    def test_fda_approval_scenario(self):
        """Test typical FDA approval alert."""
        classification = {
            "tags": ["fda", "regulatory"],
            "sentiment": 0.85,
        }
        badges = extract_catalyst_badges(
            classification=classification,
            title="FDA grants accelerated approval for cancer therapy",
        )
        assert "💊 FDA NEWS" in badges
        # May also have regulatory badge depending on priority
        if len(badges) > 1:
            assert "⚖️ REGULATORY" in badges

    def test_merger_announcement_scenario(self):
        """Test typical M&A announcement."""
        classification = {
            "tags": ["merger", "acquisition"],
            "sentiment": 0.65,
        }
        badges = extract_catalyst_badges(
            classification=classification,
            title="Tech giant acquires AI startup for $500M",
        )
        assert "🤝 M&A" in badges

    def test_dilution_offering_scenario(self):
        """Test typical offering/dilution alert."""
        classification = {
            "tags": ["offering", "dilution"],
            "sentiment": -0.40,
        }
        badges = extract_catalyst_badges(
            classification=classification,
            title="Biotech prices $100M secondary offering",
        )
        assert "💰 OFFERING" in badges

    def test_analyst_upgrade_scenario(self):
        """Test typical analyst upgrade."""
        classification = {
            "tags": ["analyst", "rating"],
            "sentiment": 0.55,
        }
        badges = extract_catalyst_badges(
            classification=classification,
            title="JPMorgan upgrades to Overweight, raises PT to $200",
        )
        assert "🎯 ANALYST" in badges


class TestBadgeConfiguration:
    """Test badge configuration constants."""

    def test_all_badge_types_defined(self):
        """Test all badge types from spec are defined."""
        required_types = [
            "earnings",
            "fda",
            "merger",
            "guidance",
            "sec_filing",
            "offering",
            "analyst",
            "contract",
            "partnership",
            "product",
            "clinical",
            "regulatory",
        ]
        for badge_type in required_types:
            assert badge_type in CATALYST_BADGES
            assert badge_type in CATALYST_PATTERNS

    def test_badge_format(self):
        """Test badge strings follow [EMOJI TEXT] format."""
        for badge_type, badge_text in CATALYST_BADGES.items():
            # Should contain emoji and text
            assert len(badge_text) > 1
            # Should be uppercase for consistency
            words = badge_text.split()[1:]  # Skip emoji
            assert all(word.isupper() or word in ["&", "/"] for word in words)

    def test_pattern_coverage(self):
        """Test all patterns are non-empty lists."""
        for catalyst_type, patterns in CATALYST_PATTERNS.items():
            assert isinstance(patterns, list)
            assert len(patterns) > 0
            # All patterns should be lowercase
            assert all(p.islower() for p in patterns)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
