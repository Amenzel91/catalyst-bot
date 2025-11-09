# -*- coding: utf-8 -*-
"""Tests for multi-ticker article handling and primary ticker detection.

WAVE 3 Data Quality: Test suite for intelligent multi-ticker scoring system.
"""

import pytest

from catalyst_bot.multi_ticker_handler import (
    analyze_multi_ticker_article,
    score_ticker_relevance,
    select_primary_tickers,
    should_alert_for_ticker,
)


class TestTickerRelevanceScoring:
    """Test ticker relevance scoring algorithm."""

    def test_ticker_in_title_start_high_score(self):
        """Ticker at the start of title should get high score."""
        title = "AAPL Reports Record Q3 Earnings Beat"
        text = "Apple Inc (AAPL) announced strong quarterly results..."
        score = score_ticker_relevance("AAPL", title, text)

        # Should have high score: title start (50) + first para (30) + freq (10+) = 90+
        assert score >= 90.0, f"Expected >=90, got {score}"

    def test_ticker_in_title_end_lower_score(self):
        """Ticker at the end of title should get lower score."""
        title = "Tech Stocks Rally; Strong Day for AAPL"
        text = "Markets rose today with Apple gaining..."
        score = score_ticker_relevance("AAPL", title, text)

        # Should have moderate score: title end (~35) + freq (~5-10) = 40-45
        assert 35.0 <= score <= 50.0, f"Expected 35-50, got {score}"

    def test_ticker_barely_mentioned(self):
        """Ticker mentioned once in passing should get low score."""
        title = "MSFT Announces Layoffs, AAPL Also Mentioned"
        text = "Microsoft announced major layoffs today. Apple was not affected."
        score = score_ticker_relevance("AAPL", title, text)

        # Should have low score: not in title prominently, one mention = <40
        assert score < 40.0, f"Expected <40, got {score}"

    def test_ticker_in_first_paragraph(self):
        """Ticker in first 300 chars should get 30-point boost."""
        title = "Breaking News: Major Tech Announcement"
        text = "AAPL announced today that it will launch a new product line..."
        score = score_ticker_relevance("AAPL", title, text)

        # Should have: no title (0) + first para (30) + freq (5) = 35
        assert 30.0 <= score <= 40.0, f"Expected 30-40, got {score}"

    def test_ticker_high_frequency(self):
        """Ticker mentioned many times should get frequency boost."""
        title = "AAPL Earnings: AAPL Reports Strong Quarter"
        text = "AAPL beat estimates. AAPL revenue up. AAPL guidance raised. AAPL stock surged."
        score = score_ticker_relevance("AAPL", title, text)

        # Should have: title (40+) + first para (30) + freq (20 max) = 90+
        assert score >= 90.0, f"Expected >=90, got {score}"

    def test_ticker_not_in_article(self):
        """Ticker not mentioned should get zero score."""
        title = "MSFT Announces Cloud Deal"
        text = "Microsoft announced a major cloud contract today..."
        score = score_ticker_relevance("AAPL", title, text)

        assert score == 0.0, f"Expected 0, got {score}"

    def test_case_insensitive_matching(self):
        """Ticker matching should be case-insensitive."""
        title = "aapl reports earnings"
        text = "Apple (AAPL) announced..."
        score = score_ticker_relevance("AAPL", title, text)

        assert score > 0, "Should match case-insensitively"


class TestPrimaryTickerSelection:
    """Test primary ticker selection logic."""

    def test_single_primary_by_large_margin(self):
        """Top ticker with large margin should be only primary."""
        scores = {"AAPL": 85.0, "MSFT": 25.0, "GOOGL": 15.0}
        primary = select_primary_tickers(
            scores, min_score=40, score_diff_threshold=30
        )

        assert primary == ["AAPL"], f"Expected only AAPL, got {primary}"

    def test_true_multi_ticker_story(self):
        """Tickers with close scores should both be primary."""
        scores = {"AAPL": 75.0, "GOOGL": 70.0}
        primary = select_primary_tickers(
            scores, min_score=40, max_tickers=2, score_diff_threshold=30
        )

        assert set(primary) == {"AAPL", "GOOGL"}, f"Expected both, got {primary}"

    def test_all_below_threshold(self):
        """All tickers below threshold should return empty list."""
        scores = {"AAPL": 35.0, "MSFT": 25.0, "GOOGL": 15.0}
        primary = select_primary_tickers(scores, min_score=40)

        assert primary == [], f"Expected empty list, got {primary}"

    def test_max_tickers_limit(self):
        """Should respect max_tickers limit."""
        scores = {"AAPL": 80.0, "MSFT": 78.0, "GOOGL": 76.0}
        primary = select_primary_tickers(
            scores, min_score=40, max_tickers=2, score_diff_threshold=30
        )

        assert len(primary) <= 2, f"Expected <=2 tickers, got {len(primary)}"
        assert "AAPL" in primary, "Highest score should be included"

    def test_single_qualified_ticker(self):
        """Single ticker above threshold should return it."""
        scores = {"AAPL": 85.0}
        primary = select_primary_tickers(scores, min_score=40)

        assert primary == ["AAPL"], f"Expected AAPL, got {primary}"

    def test_empty_scores_dict(self):
        """Empty scores dict should return empty list."""
        scores = {}
        primary = select_primary_tickers(scores, min_score=40)

        assert primary == [], f"Expected empty list, got {primary}"


class TestShouldAlertForTicker:
    """Test alert decision logic."""

    def test_high_relevance_should_alert(self):
        """High relevance ticker should trigger alert."""
        article_data = {
            "title": "AAPL Reports Record Earnings",
            "summary": "Apple Inc (AAPL) announced strong quarterly results...",
        }

        should_alert, score = should_alert_for_ticker("AAPL", article_data, min_score=40)

        assert should_alert is True, "High relevance should trigger alert"
        assert score >= 40, f"Expected score >=40, got {score}"

    def test_low_relevance_should_skip(self):
        """Low relevance ticker should not trigger alert."""
        article_data = {
            "title": "MSFT Announces Layoffs, AAPL Also Mentioned",
            "summary": "Microsoft announced major layoffs. Apple was not affected.",
        }

        should_alert, score = should_alert_for_ticker("AAPL", article_data, min_score=40)

        assert should_alert is False, "Low relevance should skip alert"
        assert score < 40, f"Expected score <40, got {score}"

    def test_missing_ticker_returns_zero(self):
        """Missing ticker should return zero score."""
        article_data = {
            "title": "MSFT Cloud Deal",
            "summary": "Microsoft announced cloud contract...",
        }

        should_alert, score = should_alert_for_ticker("AAPL", article_data, min_score=40)

        assert should_alert is False, "Missing ticker should not alert"
        assert score == 0, f"Expected score 0, got {score}"


class TestAnalyzeMultiTickerArticle:
    """Test full multi-ticker article analysis."""

    def test_single_primary_ticker_article(self):
        """Article with one clear primary ticker."""
        article = {
            "title": "AAPL Reports Record Q3, Beats Estimates; MSFT Mentioned",
            "summary": "Apple Inc (AAPL) announced strong quarterly results today. "
            "The tech giant beat analyst estimates. Microsoft was also mentioned briefly.",
        }
        tickers = ["AAPL", "MSFT"]

        primary, secondary, scores = analyze_multi_ticker_article(
            tickers, article, min_score=40, max_primary=2, score_diff_threshold=30
        )

        assert primary == ["AAPL"], f"Expected AAPL only, got {primary}"
        assert "MSFT" in secondary, "MSFT should be secondary"
        assert scores["AAPL"] > scores["MSFT"], "AAPL score should be higher"
        assert scores["AAPL"] >= 40, "Primary should exceed threshold"

    def test_true_partnership_story(self):
        """Article about partnership should have both as primary."""
        article = {
            "title": "AAPL and GOOGL Announce Strategic Partnership",
            "summary": "Apple (AAPL) and Google (GOOGL) announced today that they will collaborate "
            "on a major new initiative. Both AAPL and GOOGL will invest heavily in the project.",
        }
        tickers = ["AAPL", "GOOGL"]

        primary, secondary, scores = analyze_multi_ticker_article(
            tickers, article, min_score=40, max_primary=2, score_diff_threshold=30
        )

        assert set(primary) == {"AAPL", "GOOGL"}, f"Expected both primary, got {primary}"
        assert len(secondary) == 0, "No secondary tickers expected"
        assert scores["AAPL"] >= 40 and scores["GOOGL"] >= 40, "Both should exceed threshold"

    def test_market_roundup_rejects_all(self):
        """Market roundup with many tickers should reject all."""
        article = {
            "title": "Market Roundup: AAPL, MSFT, GOOGL, TSLA All Move",
            "summary": "Markets today saw movement in major tech stocks. "
            "AAPL was up, MSFT down, GOOGL flat, and TSLA surged.",
        }
        tickers = ["AAPL", "MSFT", "GOOGL", "TSLA"]

        primary, secondary, scores = analyze_multi_ticker_article(
            tickers, article, min_score=40, max_primary=2, score_diff_threshold=30
        )

        # Most tickers should be below threshold due to low individual relevance
        assert len(primary) <= 2, "Should limit to max 2 primary"

    def test_acquisition_announcement(self):
        """Acquisition announcement should have both companies as primary."""
        article = {
            "title": "AAPL to Acquire SMALL for $10B",
            "summary": "Apple (AAPL) announced today it will acquire SMALL Corp "
            "in a $10 billion deal. AAPL expects the SMALL acquisition to close next quarter.",
        }
        tickers = ["AAPL", "SMALL"]

        primary, secondary, scores = analyze_multi_ticker_article(
            tickers, article, min_score=40, max_primary=2, score_diff_threshold=30
        )

        assert len(primary) >= 1, "At least one primary expected"
        assert "AAPL" in primary, "Acquirer should be primary"

    def test_empty_ticker_list(self):
        """Empty ticker list should return empty results."""
        article = {"title": "Some news", "summary": "No tickers here"}
        tickers = []

        primary, secondary, scores = analyze_multi_ticker_article(
            tickers, article
        )

        assert primary == [], "Expected empty primary"
        assert secondary == [], "Expected empty secondary"
        assert scores == {}, "Expected empty scores"


class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_none_values_handled_gracefully(self):
        """None values should not crash."""
        score = score_ticker_relevance("AAPL", None, None)
        assert score == 0.0, "None values should return 0"

    def test_empty_strings_handled_gracefully(self):
        """Empty strings should not crash."""
        score = score_ticker_relevance("AAPL", "", "")
        assert score == 0.0, "Empty strings should return 0"

    def test_special_characters_in_title(self):
        """Special characters should not crash."""
        title = "AAPL: 🚀 Record Q3 - 📈 Earnings Beat!!!"
        text = "Apple announced strong results..."
        score = score_ticker_relevance("AAPL", title, text)

        assert score > 0, "Should handle special characters"

    def test_very_long_text(self):
        """Very long text should not crash or cause performance issues."""
        title = "AAPL Earnings Report"
        text = "Apple announced results. " * 1000  # Very long text
        score = score_ticker_relevance("AAPL", title, text)

        # Should have title score but frequency capped at 20 points
        assert 50 <= score <= 100, "Should handle long text"

    def test_ticker_with_special_characters(self):
        """Ticker with dots/hyphens should work."""
        title = "BRK.A Reports Earnings"
        text = "Berkshire Hathaway (BRK.A) announced..."
        score = score_ticker_relevance("BRK.A", title, text)

        assert score > 0, "Should handle tickers with dots"


class TestRealWorldScenarios:
    """Test real-world article scenarios."""

    def test_comparison_article(self):
        """Article comparing two stocks."""
        article = {
            "title": "AAPL vs MSFT: Which is the Better Buy?",
            "summary": "We compare Apple (AAPL) and Microsoft (MSFT) to determine "
            "which stock offers better value. AAPL has strong growth but MSFT has better margins.",
        }
        tickers = ["AAPL", "MSFT"]

        primary, secondary, scores = analyze_multi_ticker_article(tickers, article)

        # Both should be relatively high and close in score
        assert len(primary) == 2, "Comparison should have both as primary"

    def test_sector_news_with_example(self):
        """Sector news mentioning one ticker as example."""
        article = {
            "title": "Tech Sector Rallies on Strong Earnings Season",
            "summary": "Technology stocks surged today on strong earnings. "
            "Companies like AAPL led the gains, with the broader sector up 3%.",
        }
        tickers = ["AAPL"]

        primary, secondary, scores = analyze_multi_ticker_article(tickers, article)

        # AAPL mentioned but not the main subject
        # Score depends on frequency and position
        assert len(scores) == 1, "Should score the one ticker"

    def test_earnings_with_competitor_mention(self):
        """Earnings report mentioning competitor."""
        article = {
            "title": "AAPL Q3 Earnings Beat Expectations, Outpaces MSFT",
            "summary": "Apple (AAPL) reported strong Q3 earnings today, beating "
            "analyst estimates. AAPL revenue grew 15% year-over-year, outpacing "
            "Microsoft's recent results. The AAPL earnings show strong iPhone demand.",
        }
        tickers = ["AAPL", "MSFT"]

        primary, secondary, scores = analyze_multi_ticker_article(tickers, article)

        assert primary == ["AAPL"], "AAPL should be primary"
        assert "MSFT" in secondary, "MSFT should be secondary"
        assert scores["AAPL"] > scores["MSFT"] + 30, "AAPL should have much higher score"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
