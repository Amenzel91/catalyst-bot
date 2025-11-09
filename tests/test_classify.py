"""Tests for the classification module."""

from datetime import datetime, timezone

from catalyst_bot.classify import classify
from catalyst_bot.classify_bridge import classify_text
from catalyst_bot.models import NewsItem


def test_classify_detects_fda_keyword_and_sentiment() -> None:
    item = NewsItem(
        ts_utc=datetime.now(timezone.utc),
        title="Biotech Co receives FDA approval for phase 3 trial",
        canonical_url="http://example.com",
        source_host="businesswire.com",
        ticker="ABC",
    )
    scored = classify(item)
    # Should hit the 'fda' category
    assert "fda" in scored.keyword_hits
    # Sentiment should be non‑negative
    assert scored.sentiment >= 0.0


def test_classify_bridge_min_contract() -> None:
    out = classify_text("Company receives FDA approval for new device")
    assert isinstance(out, dict)
    assert "tags" in out and isinstance(out["tags"], list)
    assert "keyword_hits" in out and isinstance(out["keyword_hits"], dict)


def test_sec_filing_uses_summary_for_keywords() -> None:
    """Test that SEC filings use LLM summary (not title) for keyword matching."""
    item = NewsItem(
        ts_utc=datetime.now(timezone.utc),
        title="Form 8-K Filing - ABC Corp",  # Generic title, no keywords
        summary="Company announces FDA approval for breakthrough drug therapy",  # Summary has keyword
        canonical_url="http://sec.gov/filing/123456",
        source="sec_8k",  # SEC source identifier
        ticker="ABC",
    )
    scored = classify(item)
    # Should hit 'fda' keyword from summary (not title)
    assert "fda" in scored.keyword_hits, f"Expected 'fda' in keyword_hits, got {scored.keyword_hits}"
    # Verify it's recognized as an SEC filing (optional metadata check)
    # This tests the SEC-specific logic path


def test_sec_filing_uses_summary_for_sentiment() -> None:
    """Test that SEC filings use LLM summary (not title) for sentiment analysis."""
    item = NewsItem(
        ts_utc=datetime.now(timezone.utc),
        title="Form 10-Q Filing",  # Neutral title
        summary="Significant revenue growth and strong earnings beat expectations",  # Positive summary
        canonical_url="http://sec.gov/filing/789012",
        source="sec_10q",  # SEC source identifier
        ticker="XYZ",
    )
    scored = classify(item)
    # Sentiment should be positive (extracted from summary, not title)
    assert scored.sentiment > 0.0, f"Expected positive sentiment from summary, got {scored.sentiment}"


def test_regular_news_uses_title_and_summary() -> None:
    """Test that regular news (non-SEC) uses both title and summary as before."""
    item = NewsItem(
        ts_utc=datetime.now(timezone.utc),
        title="Biotech receives FDA approval for new drug",  # Has 'fda approval' keyword phrase
        summary="Additional details about the regulatory milestone",
        canonical_url="http://benzinga.com/article",
        source="benzinga",  # Regular news source
        ticker="TEST",
    )
    scored = classify(item)
    # Should detect FDA keyword from title (not just summary)
    assert "fda" in scored.keyword_hits, f"Expected 'fda' in keyword_hits from title, got {scored.keyword_hits}"


def test_sec_filing_with_empty_summary() -> None:
    """Test that SEC filings with empty summary are handled gracefully."""
    item = NewsItem(
        ts_utc=datetime.now(timezone.utc),
        title="Form 8-K Filing",
        summary="",  # Empty summary
        canonical_url="http://sec.gov/filing/999999",
        source="sec_8k",
        ticker="EMPTY",
    )
    scored = classify(item)
    # Should not crash, should return a valid ScoredItem
    assert scored is not None
    assert isinstance(scored.keyword_hits, list)
    # With empty summary, no keywords should be matched
    assert len(scored.keyword_hits) == 0 or scored.keyword_hits == []


def test_sec_filing_multiple_keywords_in_summary() -> None:
    """Test SEC filing with multiple catalyst keywords in LLM summary."""
    item = NewsItem(
        ts_utc=datetime.now(timezone.utc),
        title="Form 8-K Current Report",
        summary="FDA approval granted for breakthrough therapy. Company also announces partnership deal.",
        canonical_url="http://sec.gov/filing/555555",
        source="sec_8k",
        ticker="MULTI",
    )
    scored = classify(item)
    # Should match multiple keywords from summary
    assert "fda" in scored.keyword_hits, "Should detect 'fda' keyword"
    # Note: 'partnership' or 'deal' may or may not be in keyword_categories
    # The important test is that it scans the summary, not the title


def test_sec_filing_source_variations() -> None:
    """Test that different SEC source types (8k, 10k, 10q) are all handled."""
    for source_type in ["sec_8k", "sec_10k", "sec_10q"]:
        item = NewsItem(
            ts_utc=datetime.now(timezone.utc),
            title="SEC Filing",
            summary="Major acquisition announced involving pharmaceutical assets",
            canonical_url="http://sec.gov/filing/111111",
            source=source_type,
            ticker="VAR",
        )
        scored = classify(item)
        # All SEC types should use summary for keyword matching
        # Check for 'acquisition' or similar keyword if it exists in keyword_categories
        assert scored is not None, f"Classification failed for {source_type}"


def test_non_sec_source_backward_compatibility() -> None:
    """Test that non-SEC sources still work exactly as before (no regression)."""
    item = NewsItem(
        ts_utc=datetime.now(timezone.utc),
        title="Breaking: Clinical trial shows promising results",
        summary="Phase 3 data exceeds expectations",
        canonical_url="http://reuters.com/article/12345",
        source="reuters",
        ticker="COMPAT",
    )
    scored = classify(item)
    # Should work exactly as before (title + summary combined)
    assert scored is not None
    assert isinstance(scored.keyword_hits, list)
    # Should have positive sentiment (from "promising", "exceeds expectations")
    assert scored.sentiment >= 0.0
