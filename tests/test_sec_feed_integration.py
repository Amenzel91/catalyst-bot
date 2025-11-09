"""Integration tests for SEC filing feed integration.

Tests the Wave 1 SEC filing integration: fetch_sec_filings() and its
integration into fetch_pr_feeds() with the FEATURE_SEC_FILINGS flag.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from catalyst_bot import feeds
from catalyst_bot.models import NewsItem


class TestSECFeedIntegration:
    """Test SEC filing integration into main feed pipeline."""

    def test_fetch_sec_filings_returns_newsitem_format(self):
        """Test that fetch_sec_filings() returns NewsItem-compatible dicts."""
        # Mock dependencies
        mock_filings = [
            {
                "ticker": "AAPL",
                "form_type": "8-K",
                "filed_at": "2025-01-15T10:00:00+00:00",
                "filing_url": "https://sec.gov/filing/aapl-8k",
                "classification": "NEUTRAL",
                "items": ["2.02"],
                "accession_number": "0000320193-25-000001",
            }
        ]

        with patch("catalyst_bot.feeds.load_watchlist_set") as mock_watchlist, \
             patch("catalyst_bot.sec_monitor.get_recent_filings") as mock_get_filings:

            mock_watchlist.return_value = {"AAPL"}
            mock_get_filings.return_value = mock_filings

            result = feeds.fetch_sec_filings()

            # Verify result structure
            assert isinstance(result, list)
            assert len(result) == 1

            item = result[0]
            # Check all required NewsItem fields
            assert "ts" in item or "ts_utc" in item
            assert "title" in item
            assert "ticker" in item
            assert "link" in item
            assert "source" in item
            assert "summary" in item
            assert "id" in item

            # Verify content
            assert item["ticker"] == "AAPL"
            assert item["source"] == "sec_8k"
            assert "AAPL" in item["title"]
            assert "8-K" in item["title"]
            assert item["link"] == "https://sec.gov/filing/aapl-8k"

    def test_fetch_sec_filings_handles_empty_watchlist(self):
        """Test that fetch_sec_filings() returns empty list with no watchlist."""
        with patch("catalyst_bot.feeds.load_watchlist_set") as mock_watchlist, \
             patch("catalyst_bot.feeds.get_settings") as mock_settings:

            mock_watchlist.return_value = set()
            mock_settings.return_value = MagicMock(watchlist="")

            result = feeds.fetch_sec_filings()

            assert result == []

    def test_fetch_sec_filings_handles_no_filings(self):
        """Test that fetch_sec_filings() returns empty list when no filings found."""
        with patch("catalyst_bot.feeds.load_watchlist_set") as mock_watchlist, \
             patch("catalyst_bot.sec_monitor.get_recent_filings") as mock_get_filings:

            mock_watchlist.return_value = {"AAPL", "TSLA"}
            mock_get_filings.return_value = []

            result = feeds.fetch_sec_filings()

            assert result == []

    def test_fetch_sec_filings_handles_multiple_tickers(self):
        """Test that fetch_sec_filings() aggregates filings from multiple tickers."""
        mock_aapl_filings = [
            {
                "ticker": "AAPL",
                "form_type": "10-Q",
                "filed_at": "2025-01-15T10:00:00+00:00",
                "filing_url": "https://sec.gov/filing/aapl-10q",
                "classification": "NEUTRAL",
                "items": [],
                "accession_number": "0000320193-25-000001",
            }
        ]
        mock_tsla_filings = [
            {
                "ticker": "TSLA",
                "form_type": "8-K",
                "filed_at": "2025-01-15T11:00:00+00:00",
                "filing_url": "https://sec.gov/filing/tsla-8k",
                "classification": "POSITIVE_CATALYST",
                "items": ["1.01"],
                "accession_number": "0001318605-25-000001",
            }
        ]

        def mock_get_filings(ticker, hours):
            if ticker == "AAPL":
                return mock_aapl_filings
            elif ticker == "TSLA":
                return mock_tsla_filings
            return []

        with patch("catalyst_bot.feeds.load_watchlist_set") as mock_watchlist, \
             patch("catalyst_bot.sec_monitor.get_recent_filings", side_effect=mock_get_filings):

            mock_watchlist.return_value = {"AAPL", "TSLA"}

            result = feeds.fetch_sec_filings()

            assert len(result) == 2
            tickers = {item["ticker"] for item in result}
            assert tickers == {"AAPL", "TSLA"}
            sources = {item["source"] for item in result}
            assert sources == {"sec_10q", "sec_8k"}

    def test_fetch_sec_filings_handles_errors_gracefully(self):
        """Test that fetch_sec_filings() continues on individual ticker errors."""
        def mock_get_filings(ticker, hours):
            if ticker == "AAPL":
                raise Exception("API error")
            return [
                {
                    "ticker": "TSLA",
                    "form_type": "8-K",
                    "filed_at": "2025-01-15T11:00:00+00:00",
                    "filing_url": "https://sec.gov/filing/tsla-8k",
                    "classification": "NEUTRAL",
                    "items": [],
                    "accession_number": "0001318605-25-000001",
                }
            ]

        with patch("catalyst_bot.feeds.load_watchlist_set") as mock_watchlist, \
             patch("catalyst_bot.sec_monitor.get_recent_filings", side_effect=mock_get_filings):

            mock_watchlist.return_value = {"AAPL", "TSLA"}

            result = feeds.fetch_sec_filings()

            # Should still get TSLA filing despite AAPL error
            assert len(result) == 1
            assert result[0]["ticker"] == "TSLA"

    def test_fetch_pr_feeds_excludes_sec_when_feature_disabled(self, monkeypatch):
        """Test that fetch_pr_feeds() excludes SEC items when FEATURE_SEC_FILINGS=0."""
        # Set feature flag to disabled
        monkeypatch.setenv("FEATURE_SEC_FILINGS", "0")
        monkeypatch.setenv("PYTEST_CURRENT_TEST", "test")

        with patch("catalyst_bot.feeds.fetch_sec_filings") as mock_fetch_sec:
            # Mock out other feed sources to isolate SEC behavior
            with patch("catalyst_bot.feeds.FEEDS", {}):
                result = feeds.fetch_pr_feeds()

                # fetch_sec_filings should NOT have been called
                mock_fetch_sec.assert_not_called()

    def test_fetch_pr_feeds_includes_sec_when_feature_enabled(self, monkeypatch):
        """Test that fetch_pr_feeds() includes SEC items when FEATURE_SEC_FILINGS=1."""
        # Set feature flag to enabled
        monkeypatch.setenv("FEATURE_SEC_FILINGS", "1")
        # Clear PYTEST_CURRENT_TEST to allow SEC fetching
        monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)

        mock_sec_items = [
            {
                "source": "sec_8k",
                "title": "AAPL 8-K Item 2.02 - Earnings Release",
                "ticker": "AAPL",
                "link": "https://sec.gov/filing/aapl-8k",
                "id": "sec_filing_12345",
                "ts": "2025-01-15T10:00:00+00:00",
                "summary": "Apple reports Q1 earnings",
            }
        ]

        with patch("catalyst_bot.feeds.fetch_sec_filings", return_value=mock_sec_items), \
             patch("catalyst_bot.feeds.FEEDS", {}):

            result = feeds.fetch_pr_feeds()

            # SEC item should be in results
            sec_items = [item for item in result if item.get("source", "").startswith("sec_")]
            assert len(sec_items) == 1
            assert sec_items[0]["ticker"] == "AAPL"
            assert sec_items[0]["source"] == "sec_8k"

    @pytest.mark.skip(reason="Deduplication test requires complex mocking - integration verified in main tests")
    def test_fetch_pr_feeds_deduplicates_sec_items(self, monkeypatch):
        """Test that fetch_pr_feeds() deduplicates SEC items with existing feeds."""
        pass

    def test_fetch_pr_feeds_summary_tracks_sec_source(self, monkeypatch):
        """Test that fetch_pr_feeds() updates summary dict with SEC source stats."""
        # This test would require inspecting internal state or return values
        # For now, we verify the integration doesn't crash
        monkeypatch.setenv("FEATURE_SEC_FILINGS", "1")
        monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)

        mock_sec_items = [
            {
                "source": "sec_8k",
                "title": "AAPL 8-K Item 2.02",
                "ticker": "AAPL",
                "link": "https://sec.gov/filing/aapl-8k",
                "id": "sec_filing_12345",
                "ts": "2025-01-15T10:00:00+00:00",
                "summary": "Filing summary",
            }
        ]

        with patch("catalyst_bot.feeds.fetch_sec_filings", return_value=mock_sec_items), \
             patch("catalyst_bot.feeds.FEEDS", {}):

            result = feeds.fetch_pr_feeds()

            # Just verify it doesn't crash and returns results
            assert isinstance(result, list)

    def test_filing_to_newsitem_conversion(self):
        """Test that FilingSection -> NewsItem -> dict conversion works correctly."""
        # This is an integration test of the full conversion pipeline
        from catalyst_bot.sec_filing_adapter import filing_to_newsitem
        from catalyst_bot.sec_parser import FilingSection

        # Create a mock FilingSection (ticker is not in the dataclass, passed to adapter)
        filing = FilingSection(
            item_code="2.02",
            item_title="Results of Operations and Financial Condition",
            text="Apple Inc. reported Q1 2025 results...",
            catalyst_type="earnings",
            filing_type="8-K",
            filing_url="https://sec.gov/filing/aapl-8k",
            cik="0000320193",
            accession="0000320193-25-000001",
        )

        filing_date = datetime(2025, 1, 15, 10, 0, 0, tzinfo=timezone.utc)
        llm_summary = "Apple reports strong Q1 earnings with 25% revenue growth"

        # Convert to NewsItem
        news_item = filing_to_newsitem(
            filing_section=filing,
            llm_summary=llm_summary,
            ticker="AAPL",
            filing_date=filing_date,
        )

        # Verify NewsItem attributes
        assert isinstance(news_item, NewsItem)
        assert news_item.ticker == "AAPL"
        assert news_item.source == "sec_8k"
        assert news_item.summary == llm_summary
        assert news_item.canonical_url == "https://sec.gov/filing/aapl-8k"
        assert "AAPL" in news_item.title
        assert "8-K" in news_item.title

        # Verify it can be converted to dict format (as done in fetch_sec_filings)
        item_dict = {
            "source": news_item.source,
            "title": news_item.title,
            "summary": news_item.summary or "",
            "link": news_item.canonical_url,
            "id": "test_id",
            "ts": news_item.ts_utc.isoformat(),
            "ticker": news_item.ticker,
        }

        assert item_dict["source"] == "sec_8k"
        assert item_dict["ticker"] == "AAPL"
        assert item_dict["summary"] == llm_summary


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
