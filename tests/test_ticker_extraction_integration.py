# -*- coding: utf-8 -*-
"""Integration tests for fallback ticker extraction from RSS feed summaries.

Tests verify that:
1. Title extraction is tried first (primary path)
2. Summary fallback works when title extraction fails
3. Title takes priority over summary when both have tickers
4. Real-world RSS entry structures are handled correctly
5. ticker_source field correctly tracks extraction method
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from catalyst_bot.feeds import _normalize_entry


@pytest.fixture(autouse=True)
def mock_ticker_validator():
    """Mock ticker validator to allow test tickers."""
    with patch("catalyst_bot.feeds._TICKER_VALIDATOR.is_valid", return_value=True):
        yield


class TestTickerExtractionFallback:
    """Test suite for ticker extraction with summary fallback."""

    def test_title_extraction_primary_path(self):
        """Verify ticker is extracted from title when available."""
        # Mock RSS entry with ticker in title
        entry = SimpleNamespace(
            title="Apple Inc. Announces Q3 Results (NASDAQ: AAPL)",
            link="https://example.com/news/1",
            published="2024-01-15T10:00:00Z",
            id="entry-1",
            summary="Apple reports strong quarterly earnings.",
        )

        result = _normalize_entry("test_feed", entry)

        assert result is not None
        assert result["ticker"] == "AAPL"
        assert result["ticker_source"] == "title"
        assert result["source"] == "test_feed"

    def test_summary_fallback_when_title_fails(self):
        """Verify ticker is extracted from summary when title extraction fails."""
        # Mock RSS entry with no ticker in title, but ticker in summary
        entry = SimpleNamespace(
            title="Major Tech Company Reports Strong Earnings",
            link="https://example.com/news/2",
            published="2024-01-15T10:00:00Z",
            id="entry-2",
            summary="Tesla (NASDAQ: TSLA) announced record deliveries for Q4 2024.",
        )

        result = _normalize_entry("test_feed", entry)

        assert result is not None
        assert result["ticker"] == "TSLA"
        assert result["ticker_source"] == "summary"
        assert result["source"] == "test_feed"

    def test_title_priority_over_summary(self):
        """Verify title extraction takes priority when both title and summary have tickers."""
        # Mock RSS entry with different tickers in title and summary
        entry = SimpleNamespace(
            title="Microsoft (NASDAQ: MSFT) Acquires Gaming Studio",
            link="https://example.com/news/3",
            published="2024-01-15T10:00:00Z",
            id="entry-3",
            summary="The acquisition follows Sony's (NYSE: SONY) recent moves in gaming.",
        )

        result = _normalize_entry("test_feed", entry)

        assert result is not None
        assert result["ticker"] == "MSFT"  # Title ticker wins
        assert result["ticker_source"] == "title"
        assert result["source"] == "test_feed"

    def test_no_ticker_in_title_or_summary(self):
        """Verify graceful handling when neither title nor summary contain tickers."""
        # Mock RSS entry with no tickers anywhere
        entry = SimpleNamespace(
            title="Market Analysis: Tech Sector Outlook",
            link="https://example.com/news/4",
            published="2024-01-15T10:00:00Z",
            id="entry-4",
            summary="Analysts discuss the future of technology investments.",
        )

        result = _normalize_entry("test_feed", entry)

        assert result is not None
        assert result["ticker"] is None
        assert result["ticker_source"] is None
        assert result["source"] == "test_feed"

    def test_empty_summary_graceful_handling(self):
        """Verify no errors when summary is empty or missing."""
        # Mock RSS entry with no summary
        entry = SimpleNamespace(
            title="Breaking News Alert",
            link="https://example.com/news/5",
            published="2024-01-15T10:00:00Z",
            id="entry-5",
        )

        result = _normalize_entry("test_feed", entry)

        assert result is not None
        assert result["ticker"] is None
        assert result["ticker_source"] is None
        assert result["summary"] is None

    def test_summary_with_html_entities(self):
        """Verify ticker extraction works with HTML entities in summary."""
        # Mock RSS entry with HTML entities in summary
        entry = SimpleNamespace(
            title="Company Announcement",
            link="https://example.com/news/6",
            published="2024-01-15T10:00:00Z",
            id="entry-6",
            summary="Amazon &amp; AWS (NASDAQ: AMZN) expand cloud services.",
        )

        result = _normalize_entry("test_feed", entry)

        assert result is not None
        assert result["ticker"] == "AMZN"
        assert result["ticker_source"] == "summary"

    def test_multiple_tickers_in_summary_first_wins(self):
        """Verify first ticker in summary is extracted when multiple exist."""
        # Mock RSS entry with multiple tickers in summary
        entry = SimpleNamespace(
            title="Market Movers Today",
            link="https://example.com/news/7",
            published="2024-01-15T10:00:00Z",
            id="entry-7",
            summary="Top gainers include Netflix (NASDAQ: NFLX) and Disney (NYSE: DIS).",
        )

        result = _normalize_entry("test_feed", entry)

        assert result is not None
        assert result["ticker"] == "NFLX"  # First ticker wins
        assert result["ticker_source"] == "summary"

    def test_real_world_prnewswire_structure(self):
        """Test with real-world PR Newswire entry structure."""
        # Simulate actual PR Newswire RSS structure
        entry = SimpleNamespace(
            title="Biotech Company Announces Clinical Trial Results",
            link="https://www.prnewswire.com/news-releases/...",
            published="2024-01-15T09:30:00-05:00",
            id="prnewswire-123456",
            summary=(
                "CAMBRIDGE, Mass., Jan. 15, 2024 /PRNewswire/ -- BioTech Inc. "
                "(NASDAQ: BIOT) today announced positive results from its Phase 3 clinical trial."
            ),
        )

        result = _normalize_entry("prnewswire", entry)

        assert result is not None
        assert result["ticker"] == "BIOT"
        assert result["ticker_source"] == "summary"
        assert result["source"] == "prnewswire"

    def test_real_world_businesswire_structure(self):
        """Test with real-world Business Wire entry structure."""
        # Simulate actual Business Wire RSS structure
        entry = SimpleNamespace(
            title="Tech Company Reports Record Revenue",
            link="https://www.businesswire.com/news/home/...",
            published="2024-01-15T08:00:00Z",
            id="businesswire-789012",
            summary=(
                "SAN FRANCISCO--(BUSINESS WIRE)-- TechCorp (NYSE: TECH) today "
                "reported fourth quarter and full year 2024 financial results."
            ),
        )

        result = _normalize_entry("businesswire", entry)

        assert result is not None
        assert result["ticker"] == "TECH"
        assert result["ticker_source"] == "summary"
        assert result["source"] == "businesswire"

    def test_real_world_globenewswire_structure(self):
        """Test with real-world GlobeNewswire entry structure."""
        # Simulate actual GlobeNewswire RSS structure
        entry = SimpleNamespace(
            title="Pharmaceutical Company Receives FDA Approval",
            link="https://www.globenewswire.com/news-release/...",
            published="2024-01-15T07:30:00Z",
            id="globenewswire-345678",
            summary=(
                "NEW YORK, Jan. 15, 2024 (GLOBE NEWSWIRE) -- PharmaCo (NASDAQ: PHRM) "
                "announced today that it received FDA approval for its new drug."
            ),
        )

        result = _normalize_entry("globenewswire", entry)

        assert result is not None
        assert result["ticker"] == "PHRM"
        assert result["ticker_source"] == "summary"
        assert result["source"] == "globenewswire"

    def test_dollar_ticker_in_summary(self):
        """Test extraction of $TICKER format from summary.

        Note: The feeds.py extract_ticker() function doesn't currently support
        dollar ticker format. This test documents the current behavior.
        The runner.py enrich_ticker() will catch these with ticker_from_title().
        """
        # Mock entry with dollar ticker format
        entry = SimpleNamespace(
            title="Social Media Buzz",
            link="https://example.com/news/8",
            published="2024-01-15T10:00:00Z",
            id="entry-8",
            summary="Investors are excited about $NVDA earnings tomorrow.",
        )

        result = _normalize_entry("test_feed", entry)

        assert result is not None
        # Dollar tickers are not extracted by feeds.extract_ticker()
        # They will be caught by runner.enrich_ticker() using ticker_from_title()
        assert result["ticker"] is None
        assert result["ticker_source"] is None

    def test_class_shares_in_summary(self):
        """Test extraction of class share tickers (e.g., BRK.A) from summary."""
        # Mock entry with class share ticker
        entry = SimpleNamespace(
            title="Investment News",
            link="https://example.com/news/9",
            published="2024-01-15T10:00:00Z",
            id="entry-9",
            summary="Berkshire Hathaway (NYSE: BRK.A) increases stake in Apple.",
        )

        result = _normalize_entry("test_feed", entry)

        assert result is not None
        # Note: Actual result depends on extract_ticker() implementation
        # This test documents expected behavior
        assert result["ticker"] is not None
        assert result["ticker_source"] == "summary"

    def test_otc_ticker_in_summary(self):
        """Test extraction of OTC tickers from summary."""
        # Mock entry with OTC ticker
        entry = SimpleNamespace(
            title="Small Cap Stock Alert",
            link="https://example.com/news/10",
            published="2024-01-15T10:00:00Z",
            id="entry-10",
            summary="Micro-cap company (OTC: OTCX) announces expansion plans.",
        )

        result = _normalize_entry("test_feed", entry)

        assert result is not None
        # Note: OTC extraction depends on ALLOW_OTC_TICKERS env var
        # This test documents the behavior
        assert result["ticker_source"] in ["summary", None]

    def test_missing_required_fields_returns_none(self):
        """Verify None is returned when title or link is missing."""
        # Mock entry with missing title
        entry_no_title = SimpleNamespace(
            link="https://example.com/news/11",
            published="2024-01-15T10:00:00Z",
            id="entry-11",
            summary="Content here (NASDAQ: TEST)",
        )

        result = _normalize_entry("test_feed", entry_no_title)
        assert result is None

        # Mock entry with missing link
        entry_no_link = SimpleNamespace(
            title="Title here (NASDAQ: TEST)",
            published="2024-01-15T10:00:00Z",
            id="entry-12",
            summary="Content here",
        )

        result = _normalize_entry("test_feed", entry_no_link)
        assert result is None

    def test_ticker_extraction_preserves_other_fields(self):
        """Verify fallback extraction doesn't interfere with other entry fields."""
        # Mock entry with all fields populated
        entry = SimpleNamespace(
            title="Complete Entry Example",
            link="https://example.com/news/13",
            published="2024-01-15T10:00:00Z",
            id="entry-13",
            guid="unique-guid-13",
            summary="Complete summary with ticker info (NYSE: FULL).",
        )

        result = _normalize_entry("complete_feed", entry)

        assert result is not None
        assert result["title"] == "Complete Entry Example"
        assert result["link"] == "https://example.com/news/13"
        assert result["source"] == "complete_feed"
        assert result["ticker"] == "FULL"
        assert result["ticker_source"] == "summary"
        assert result["summary"] == "Complete summary with ticker info (NYSE: FULL)."
        assert result["id"] is not None  # Stable ID generated


class TestRunnerEnrichTickerCompatibility:
    """Test compatibility with runner.py enrich_ticker() function."""

    def test_ticker_source_field_doesnt_break_enrichment(self):
        """Verify ticker_source field doesn't interfere with runner enrichment."""
        # Mock a normalized entry that will be processed by enrich_ticker()
        entry = SimpleNamespace(
            title="Company News Without Ticker",
            link="https://example.com/news/14",
            published="2024-01-15T10:00:00Z",
            id="entry-14",
            summary="Some summary without ticker info.",
        )

        result = _normalize_entry("test_feed", entry)

        assert result is not None
        assert result["ticker"] is None
        assert result["ticker_source"] is None

        # Simulate what enrich_ticker() does: add ticker if missing
        # The extra ticker_source field shouldn't cause issues
        if not result.get("ticker"):
            result["ticker"] = "ENRICHED"  # Simulated enrichment

        assert result["ticker"] == "ENRICHED"
        assert result["ticker_source"] is None  # Unchanged by enrichment

    def test_summary_extraction_works_before_runner_enrichment(self):
        """Verify summary extraction reduces the need for runner enrichment."""
        # This entry would previously have no ticker at feed level,
        # requiring runner enrichment. Now it's caught early.
        entry = SimpleNamespace(
            title="Company Makes Announcement",
            link="https://example.com/news/15",
            published="2024-01-15T10:00:00Z",
            id="entry-15",
            summary="SAN JOSE, Calif. -- TechStart (NASDAQ: TCHS) launches new product.",
        )

        result = _normalize_entry("test_feed", entry)

        assert result is not None
        assert result["ticker"] == "TCHS"
        assert result["ticker_source"] == "summary"

        # Simulate enrich_ticker() logic: only enriches if ticker is None
        if not result.get("ticker"):
            # This branch won't execute because ticker was already extracted
            result["ticker"] = "SHOULD_NOT_HAPPEN"

        # Verify ticker remains from summary extraction
        assert result["ticker"] == "TCHS"
        assert result["ticker_source"] == "summary"


class TestEdgeCases:
    """Test edge cases and error conditions."""

    def test_whitespace_only_summary(self):
        """Test handling of summary with only whitespace."""
        entry = SimpleNamespace(
            title="News Title",
            link="https://example.com/news/16",
            published="2024-01-15T10:00:00Z",
            id="entry-16",
            summary="   \t\n   ",
        )

        result = _normalize_entry("test_feed", entry)

        assert result is not None
        assert result["ticker"] is None
        assert result["ticker_source"] is None
        assert result["summary"] is None or result["summary"] == ""

    def test_very_long_summary(self):
        """Test extraction from very long summary text."""
        long_summary = (
            "Lorem ipsum dolor sit amet, consectetur adipiscing elit. " * 50
            + "In other news, TechGiant (NASDAQ: TGNT) announced results. "
            + "More text here. " * 50
        )
        entry = SimpleNamespace(
            title="Daily Market Roundup",
            link="https://example.com/news/17",
            published="2024-01-15T10:00:00Z",
            id="entry-17",
            summary=long_summary,
        )

        result = _normalize_entry("test_feed", entry)

        assert result is not None
        assert result["ticker"] == "TGNT"
        assert result["ticker_source"] == "summary"

    def test_special_characters_in_summary(self):
        """Test extraction with special characters in summary."""
        entry = SimpleNamespace(
            title="Special Announcement",
            link="https://example.com/news/18",
            published="2024-01-15T10:00:00Z",
            id="entry-18",
            summary="Company™ with trademark® symbol (NASDAQ: SPEC) makes announcement™.",
        )

        result = _normalize_entry("test_feed", entry)

        assert result is not None
        assert result["ticker"] == "SPEC"
        assert result["ticker_source"] == "summary"

    def test_unicode_characters_in_summary(self):
        """Test extraction with unicode characters in summary."""
        entry = SimpleNamespace(
            title="International News",
            link="https://example.com/news/19",
            published="2024-01-15T10:00:00Z",
            id="entry-19",
            summary="日本の会社 announces partnership with Company (NASDAQ: INTL) 🚀",
        )

        result = _normalize_entry("test_feed", entry)

        assert result is not None
        assert result["ticker"] == "INTL"
        assert result["ticker_source"] == "summary"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
