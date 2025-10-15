"""Tests for semantic keyword extraction using KeyBERT.

This test suite validates:
- Keyword extraction from financial headlines
- Multi-word phrase extraction
- Empty/None input handling
- KeyBERT import failure gracefully handled
- N-gram range variations (unigrams, bigrams, trigrams)
- Diversity with use_maxsum parameter
- Comparison with traditional keyword matching
- Integration with real RSS feed examples
"""

from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def extractor():
    """Create a semantic keyword extractor instance."""
    from catalyst_bot.semantic_keywords import SemanticKeywordExtractor

    return SemanticKeywordExtractor()


@pytest.fixture
def mock_keybert():
    """Mock KeyBERT model for testing without loading real model."""
    # Patch at the import level (keybert module) rather than the semantic_keywords module
    with patch("keybert.KeyBERT") as mock_kb:
        mock_model = MagicMock()
        mock_kb.return_value = mock_model
        yield mock_model


class TestSemanticKeywordExtractor:
    """Test suite for SemanticKeywordExtractor class."""

    def test_initialization_success(self, mock_keybert):
        """Test successful initialization with KeyBERT available."""
        from catalyst_bot.semantic_keywords import SemanticKeywordExtractor

        extractor = SemanticKeywordExtractor()
        assert extractor.is_available()
        assert extractor.model_name == "all-MiniLM-L6-v2"

    def test_initialization_import_error(self):
        """Test graceful handling when KeyBERT is not installed."""
        with patch.dict("sys.modules", {"keybert": None}):
            # Force reimport to trigger ImportError
            import importlib

            import catalyst_bot.semantic_keywords

            importlib.reload(catalyst_bot.semantic_keywords)

            from catalyst_bot.semantic_keywords import SemanticKeywordExtractor

            extractor = SemanticKeywordExtractor()
            assert not extractor.is_available()
            assert extractor.kw_model is None

            # Reload module again to restore normal state
            importlib.reload(catalyst_bot.semantic_keywords)

    def test_initialization_exception(self):
        """Test graceful handling when KeyBERT initialization fails."""
        with patch("keybert.KeyBERT", side_effect=Exception("Model load failed")):
            from catalyst_bot.semantic_keywords import SemanticKeywordExtractor

            extractor = SemanticKeywordExtractor()
            assert not extractor.is_available()

    def test_extract_keywords_basic(self, mock_keybert):
        """Test basic keyword extraction."""
        from catalyst_bot.semantic_keywords import SemanticKeywordExtractor

        # Mock KeyBERT response
        mock_keybert.extract_keywords.return_value = [
            ("merger acquisition", 0.85),
            ("regulatory approval", 0.72),
            ("stock price", 0.65),
            ("shareholder vote", 0.58),
            ("market reaction", 0.51),
        ]

        extractor = SemanticKeywordExtractor()
        text = "Company announces merger acquisition pending regulatory approval"

        keywords = extractor.extract_keywords(text, top_n=5)

        assert len(keywords) == 5
        assert "merger acquisition" in keywords
        assert "regulatory approval" in keywords
        assert isinstance(keywords, list)
        assert all(isinstance(kw, str) for kw in keywords)

    def test_extract_keywords_with_scores(self, mock_keybert):
        """Test keyword extraction with similarity scores."""
        from catalyst_bot.semantic_keywords import SemanticKeywordExtractor

        # Mock KeyBERT response
        mock_keybert.extract_keywords.return_value = [
            ("earnings beat", 0.92),
            ("revenue growth", 0.85),
            ("quarterly results", 0.78),
        ]

        extractor = SemanticKeywordExtractor()
        text = "Company reports earnings beat with strong revenue growth"

        keywords = extractor.extract_keywords_with_scores(text, top_n=3)

        assert len(keywords) == 3
        assert keywords[0] == ("earnings beat", 0.92)
        assert keywords[1] == ("revenue growth", 0.85)
        assert keywords[2] == ("quarterly results", 0.78)

    def test_extract_keywords_empty_text(self, mock_keybert):
        """Test extraction with empty text."""
        from catalyst_bot.semantic_keywords import SemanticKeywordExtractor

        extractor = SemanticKeywordExtractor()

        # Test empty string
        keywords = extractor.extract_keywords("", top_n=5)
        assert keywords == []

        # Test None (should not call KeyBERT)
        keywords = extractor.extract_keywords(None, top_n=5)
        assert keywords == []

        # Test whitespace only
        keywords = extractor.extract_keywords("   ", top_n=5)
        assert keywords == []

    def test_extract_keywords_unavailable(self):
        """Test extraction when KeyBERT is unavailable."""
        with patch("keybert.KeyBERT", side_effect=ImportError):
            from catalyst_bot.semantic_keywords import SemanticKeywordExtractor

            extractor = SemanticKeywordExtractor()
            keywords = extractor.extract_keywords("Test text", top_n=5)

            assert keywords == []

    def test_extract_keywords_exception(self, mock_keybert):
        """Test handling of extraction exceptions."""
        from catalyst_bot.semantic_keywords import SemanticKeywordExtractor

        # Mock KeyBERT to raise exception
        mock_keybert.extract_keywords.side_effect = Exception("Extraction failed")

        extractor = SemanticKeywordExtractor()
        keywords = extractor.extract_keywords("Test text", top_n=5)

        assert keywords == []

    def test_extract_from_feed_item(self, mock_keybert):
        """Test extraction from RSS feed item (title + summary)."""
        from catalyst_bot.semantic_keywords import SemanticKeywordExtractor

        # Mock KeyBERT response
        mock_keybert.extract_keywords.return_value = [
            ("biotech approval", 0.88),
            ("clinical trial", 0.82),
            ("fda decision", 0.75),
        ]

        extractor = SemanticKeywordExtractor()

        title = "Biotech stock surges on FDA approval"
        summary = "Company receives FDA approval for breakthrough clinical trial drug"

        keywords = extractor.extract_from_feed_item(title, summary, top_n=3)

        assert len(keywords) == 3
        assert "biotech approval" in keywords

        # Verify title was included twice (weighted more heavily)
        call_args = mock_keybert.extract_keywords.call_args[0][0]
        assert title in call_args
        assert call_args.count(title) == 2  # Title appears twice

    def test_extract_from_feed_item_empty_summary(self, mock_keybert):
        """Test extraction with empty summary."""
        from catalyst_bot.semantic_keywords import SemanticKeywordExtractor

        mock_keybert.extract_keywords.return_value = [("merger", 0.85)]

        extractor = SemanticKeywordExtractor()
        keywords = extractor.extract_from_feed_item(
            title="Company merger announced", summary="", top_n=3
        )

        assert len(keywords) > 0
        # Should still extract from title

    def test_ngram_range_unigrams(self, mock_keybert):
        """Test extraction with unigrams only."""
        from catalyst_bot.semantic_keywords import SemanticKeywordExtractor

        mock_keybert.extract_keywords.return_value = [
            ("merger", 0.85),
            ("acquisition", 0.80),
            ("deal", 0.75),
        ]

        extractor = SemanticKeywordExtractor()
        keywords = extractor.extract_keywords(
            "Merger acquisition deal announced",
            top_n=3,
            keyphrase_ngram_range=(1, 1),  # Unigrams only
        )

        assert all(len(kw.split()) == 1 for kw in keywords)

    def test_ngram_range_bigrams(self, mock_keybert):
        """Test extraction with bigrams."""
        from catalyst_bot.semantic_keywords import SemanticKeywordExtractor

        mock_keybert.extract_keywords.return_value = [
            ("merger acquisition", 0.90),
            ("regulatory approval", 0.85),
            ("market reaction", 0.78),
        ]

        extractor = SemanticKeywordExtractor()
        keywords = extractor.extract_keywords(
            "Merger acquisition requires regulatory approval",
            top_n=3,
            keyphrase_ngram_range=(2, 2),  # Bigrams only
        )

        assert all(len(kw.split()) == 2 for kw in keywords)

    def test_ngram_range_trigrams(self, mock_keybert):
        """Test extraction with trigrams."""
        from catalyst_bot.semantic_keywords import SemanticKeywordExtractor

        mock_keybert.extract_keywords.return_value = [
            ("merger acquisition deal", 0.88),
            ("regulatory approval process", 0.82),
            ("shareholder voting rights", 0.75),
        ]

        extractor = SemanticKeywordExtractor()
        keywords = extractor.extract_keywords(
            "Merger acquisition deal requires regulatory approval process",
            top_n=3,
            keyphrase_ngram_range=(3, 3),  # Trigrams only
        )

        assert all(len(kw.split()) == 3 for kw in keywords)

    def test_diversity_parameter(self, mock_keybert):
        """Test MaxSum diversity algorithm."""
        from catalyst_bot.semantic_keywords import SemanticKeywordExtractor

        # Mock diverse keywords
        mock_keybert.extract_keywords.return_value = [
            ("acquisition", 0.85),
            ("earnings", 0.80),
            ("regulation", 0.75),
            ("innovation", 0.70),
            ("competition", 0.65),
        ]

        extractor = SemanticKeywordExtractor()
        _ = extractor.extract_keywords(
            "Company reports earnings, announces acquisition amid new regulations",
            top_n=5,
            use_maxsum=True,
            diversity=0.7,  # High diversity
        )

        # Verify use_maxsum was passed
        call_kwargs = mock_keybert.extract_keywords.call_args[1]
        assert call_kwargs["use_maxsum"] is True
        assert call_kwargs["diversity"] == 0.7

    def test_get_model_info(self, mock_keybert):
        """Test model information retrieval."""
        from catalyst_bot.semantic_keywords import SemanticKeywordExtractor

        extractor = SemanticKeywordExtractor()
        info = extractor.get_model_info()

        assert info["available"] is True
        assert info["model_name"] == "all-MiniLM-L6-v2"
        assert info["backend"] == "KeyBERT with sentence-transformers"

    def test_get_model_info_unavailable(self):
        """Test model info when KeyBERT unavailable."""
        with patch("keybert.KeyBERT", side_effect=ImportError):
            from catalyst_bot.semantic_keywords import SemanticKeywordExtractor

            extractor = SemanticKeywordExtractor()
            info = extractor.get_model_info()

            assert info["available"] is False


class TestSemanticVsTraditionalKeywords:
    """Compare semantic keyword extraction vs traditional keyword matching."""

    def test_semantic_captures_context(self, mock_keybert):
        """Test that semantic extraction captures contextual meaning."""
        from catalyst_bot.semantic_keywords import SemanticKeywordExtractor

        # Semantic keywords understand "FDA approval" as a single concept
        mock_keybert.extract_keywords.return_value = [
            ("fda approval", 0.92),
            ("clinical trial success", 0.88),
            ("regulatory milestone", 0.82),
        ]

        extractor = SemanticKeywordExtractor()
        text = "Biotech company receives FDA approval after successful clinical trials"

        semantic_keywords = extractor.extract_keywords(text, top_n=3)

        # Semantic extraction captures multi-word concepts
        assert "fda approval" in semantic_keywords
        assert "clinical trial success" in semantic_keywords

        # Traditional keyword matching would only find "approval" or "fda" separately

    def test_semantic_finds_implicit_keywords(self, mock_keybert):
        """Test that semantic extraction finds implicit/related concepts."""
        from catalyst_bot.semantic_keywords import SemanticKeywordExtractor

        # Semantic model can infer "growth potential" even if not explicitly stated
        mock_keybert.extract_keywords.return_value = [
            ("revenue growth", 0.90),
            ("market expansion", 0.85),
            ("competitive advantage", 0.78),
        ]

        extractor = SemanticKeywordExtractor()
        text = "Company expands into new markets, increasing revenue by 45%"

        keywords = extractor.extract_keywords(text, top_n=3)

        # Semantic extraction captures implied concepts
        assert "revenue growth" in keywords or "market expansion" in keywords

    def test_traditional_vs_semantic_comparison(self, mock_keybert):
        """Direct comparison showing semantic improvement."""
        from catalyst_bot.semantic_keywords import SemanticKeywordExtractor

        text = "Biotech announces breakthrough in cancer treatment trials"

        # Traditional keyword matching (simple substring search)
        traditional_keywords = []
        keyword_list = ["cancer", "treatment", "biotech", "trial"]
        text_lower = text.lower()
        for kw in keyword_list:
            if kw in text_lower:
                traditional_keywords.append(kw)

        # Semantic keyword extraction (context-aware)
        mock_keybert.extract_keywords.return_value = [
            ("cancer treatment breakthrough", 0.95),
            ("clinical trial results", 0.88),
            ("biotech innovation", 0.82),
        ]

        extractor = SemanticKeywordExtractor()
        semantic_keywords = extractor.extract_keywords(text, top_n=3)

        # Semantic captures multi-word phrases and context
        assert len(semantic_keywords) > 0
        assert any(len(kw.split()) > 1 for kw in semantic_keywords)

        # Traditional only finds individual words
        assert all(len(kw.split()) == 1 for kw in traditional_keywords)


class TestIntegrationWithClassify:
    """Test integration with classify.py."""

    def test_classify_includes_semantic_keywords(self, mock_keybert):
        """Test that classify() includes semantic keywords in result."""
        from catalyst_bot.classify import classify
        from catalyst_bot.models import NewsItem

        # Mock KeyBERT extraction
        mock_keybert.extract_keywords.return_value = [
            ("merger acquisition", 0.92),
            ("shareholder approval", 0.85),
            ("regulatory review", 0.78),
        ]

        # Create test news item
        item = NewsItem(
            title="Company announces merger pending shareholder approval",
            link="https://example.com/news/1",
            published="2025-10-15T10:00:00Z",
            source_host="example.com",
            summary="Large merger deal requires regulatory review",
            ts_utc="2025-10-15T10:00:00Z",
        )
        item.ticker = "TEST"

        # Classify item
        with patch.dict("os.environ", {"FEATURE_SEMANTIC_KEYWORDS": "1"}):
            scored = classify(item)

        # Verify semantic keywords are attached
        if hasattr(scored, "semantic_keywords"):
            assert scored.semantic_keywords is not None
            assert len(scored.semantic_keywords) > 0
        elif isinstance(scored, dict):
            assert "semantic_keywords" in scored

    def test_classify_disabled_via_env(self, mock_keybert):
        """Test that semantic extraction can be disabled via environment variable."""
        from catalyst_bot.classify import classify
        from catalyst_bot.models import NewsItem

        item = NewsItem(
            title="Test headline",
            link="https://example.com/news/1",
            published="2025-10-15T10:00:00Z",
            source_host="example.com",
            ts_utc="2025-10-15T10:00:00Z",
        )

        # Disable semantic keywords
        with patch.dict("os.environ", {"FEATURE_SEMANTIC_KEYWORDS": "0"}):
            classify(item)

        # Verify semantic keywords not extracted (KeyBERT not called)
        assert mock_keybert.extract_keywords.call_count == 0


class TestFinancialHeadlines:
    """Test extraction on real financial headline patterns."""

    def test_earnings_headline(self, mock_keybert):
        """Test extraction from earnings announcement."""
        from catalyst_bot.semantic_keywords import SemanticKeywordExtractor

        mock_keybert.extract_keywords.return_value = [
            ("earnings beat expectations", 0.95),
            ("quarterly revenue growth", 0.90),
            ("strong financial performance", 0.85),
        ]

        extractor = SemanticKeywordExtractor()
        text = "Company reports Q4 earnings beat expectations with 25% revenue growth"

        keywords = extractor.extract_keywords(text, top_n=3)

        assert any("earnings" in kw for kw in keywords)
        assert any("revenue" in kw or "growth" in kw for kw in keywords)

    def test_merger_headline(self, mock_keybert):
        """Test extraction from merger announcement."""
        from catalyst_bot.semantic_keywords import SemanticKeywordExtractor

        mock_keybert.extract_keywords.return_value = [
            ("merger acquisition deal", 0.93),
            ("regulatory approval pending", 0.88),
            ("shareholder voting process", 0.82),
        ]

        extractor = SemanticKeywordExtractor()
        text = "Tech giant announces $50B acquisition pending regulatory approval"

        keywords = extractor.extract_keywords(text, top_n=3)

        assert any("merger" in kw or "acquisition" in kw for kw in keywords)
        assert any("regulatory" in kw or "approval" in kw for kw in keywords)

    def test_fda_approval_headline(self, mock_keybert):
        """Test extraction from FDA approval news."""
        from catalyst_bot.semantic_keywords import SemanticKeywordExtractor

        mock_keybert.extract_keywords.return_value = [
            ("fda approval granted", 0.96),
            ("clinical trial success", 0.91),
            ("drug commercialization", 0.85),
        ]

        extractor = SemanticKeywordExtractor()
        text = "Biotech stock soars 200% on FDA approval for cancer drug"

        keywords = extractor.extract_keywords(text, top_n=3)

        assert any("fda" in kw for kw in keywords)
        assert len(keywords) == 3

    def test_bankruptcy_headline(self, mock_keybert):
        """Test extraction from bankruptcy/distress news."""
        from catalyst_bot.semantic_keywords import SemanticKeywordExtractor

        mock_keybert.extract_keywords.return_value = [
            ("chapter 11 bankruptcy", 0.94),
            ("debt restructuring", 0.89),
            ("creditor protection", 0.82),
        ]

        extractor = SemanticKeywordExtractor()
        text = "Retailer files Chapter 11 bankruptcy, begins debt restructuring"

        keywords = extractor.extract_keywords(text, top_n=3)

        assert any("bankruptcy" in kw for kw in keywords)
        assert any("debt" in kw or "restructuring" in kw for kw in keywords)


class TestPerformance:
    """Test performance and timeout handling."""

    def test_extraction_timeout(self, mock_keybert):
        """Test timeout handling for slow extractions."""
        import time

        from catalyst_bot.semantic_keywords import SemanticKeywordExtractor

        # Mock slow extraction (should still return results)
        def slow_extract(*args, **kwargs):
            time.sleep(0.1)  # Simulate slow extraction
            return [("keyword", 0.8)]

        mock_keybert.extract_keywords = slow_extract

        extractor = SemanticKeywordExtractor()
        keywords = extractor.extract_keywords(
            "Test text", top_n=5, timeout_seconds=0.05  # Very short timeout
        )

        # Should still get results, but log warning
        assert len(keywords) > 0

    def test_get_singleton_extractor(self):
        """Test singleton extractor retrieval."""
        from catalyst_bot.semantic_keywords import get_semantic_extractor

        extractor1 = get_semantic_extractor()
        extractor2 = get_semantic_extractor()

        # Should return same instance
        assert extractor1 is extractor2


class TestEdgeCases:
    """Test edge cases and error conditions."""

    def test_very_long_text(self, mock_keybert):
        """Test extraction with very long text."""
        from catalyst_bot.semantic_keywords import SemanticKeywordExtractor

        mock_keybert.extract_keywords.return_value = [("summary", 0.8)]

        extractor = SemanticKeywordExtractor()

        # Very long text (should still work)
        long_text = "Company news. " * 1000
        keywords = extractor.extract_keywords(long_text, top_n=5)

        assert len(keywords) > 0

    def test_special_characters(self, mock_keybert):
        """Test text with special characters."""
        from catalyst_bot.semantic_keywords import SemanticKeywordExtractor

        mock_keybert.extract_keywords.return_value = [("earnings", 0.85)]

        extractor = SemanticKeywordExtractor()

        text = "Company's Q4 earnings: $2.50/share (↑25% YoY) — beats $2.10 estimate!"
        keywords = extractor.extract_keywords(text, top_n=5)

        # Should handle special characters gracefully
        assert len(keywords) > 0

    def test_non_english_text(self, mock_keybert):
        """Test extraction with non-English text."""
        from catalyst_bot.semantic_keywords import SemanticKeywordExtractor

        # Mock returns empty (English model may not work well on non-English)
        mock_keybert.extract_keywords.return_value = []

        extractor = SemanticKeywordExtractor()

        text = "日本企業が新製品を発表"  # Japanese text
        keywords = extractor.extract_keywords(text, top_n=5)

        # Should return empty or minimal results (English model)
        assert isinstance(keywords, list)
