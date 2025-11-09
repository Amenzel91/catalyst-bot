"""Tests for LLM chain pipeline."""

import json
from unittest.mock import Mock, patch

import pytest

from catalyst_bot.llm_chain import (
    ExtractionOutput,
    KeywordOutput,
    LLMChainOutput,
    SentimentOutput,
    SummaryOutput,
    _stage1_extraction,
    _stage2_summary,
    _stage3_keywords,
    _stage4_sentiment,
    get_filing_sentiment,
    get_filing_summary,
    run_llm_chain,
)
from catalyst_bot.numeric_extractor import NumericMetrics, RevenueData


@pytest.fixture
def mock_llm_router():
    """Mock the LLM router to return predefined responses."""
    with patch("catalyst_bot.llm_chain.route_request") as mock:
        yield mock


def test_stage1_extraction(mock_llm_router):
    """Test Stage 1: Extraction."""
    mock_response = json.dumps(
        {
            "key_facts": ["Company acquired XYZ for $500M", "Deal closes in Q2 2025"],
            "parties": ["Acme Corp", "XYZ Industries"],
            "dates": ["Q2 2025", "May 15, 2025"],
            "dollar_amounts": ["$500M", "$2.50 per share"],
        }
    )
    mock_llm_router.return_value = mock_response

    filing_text = "Acme Corp announces acquisition of XYZ Industries for $500M..."
    output = _stage1_extraction(filing_text, None, None, max_retries=1)

    assert len(output.key_facts) == 2
    assert "Acme Corp" in output.parties
    assert "XYZ Industries" in output.parties
    assert "Q2 2025" in output.dates
    assert "$500M" in output.dollar_amounts


def test_stage2_summary(mock_llm_router):
    """Test Stage 2: Summary generation."""
    mock_summary = (
        "Acme Corp has acquired XYZ Industries for $500 million in cash and stock. "
        "The deal is expected to close in Q2 2025 and will expand Acme's market share "
        "in the industrial sector by 30%. This is a significant strategic move that "
        "could drive revenue growth."
    )
    mock_llm_router.return_value = mock_summary

    extraction = ExtractionOutput(
        key_facts=["Acquisition announced", "Deal closes Q2 2025"],
        parties=["Acme Corp"],
        dates=["Q2 2025"],
        dollar_amounts=["$500M"],
        raw_response="",
    )

    output = _stage2_summary(extraction, max_retries=1)

    assert len(output.summary) > 50
    assert "Acme Corp" in output.summary or "acquisition" in output.summary.lower()


def test_stage3_keywords(mock_llm_router):
    """Test Stage 3: Keyword tagging."""
    mock_response = json.dumps({"keywords": ["acquisition", "merger", "expansion"]})
    mock_llm_router.return_value = mock_response

    extraction = ExtractionOutput(
        key_facts=["Acquisition of XYZ"], parties=[], dates=[], dollar_amounts=[], raw_response=""
    )
    summary = SummaryOutput(summary="Acme acquires XYZ", raw_response="")

    output = _stage3_keywords(extraction, summary, max_retries=1)

    assert "acquisition" in output.keywords
    assert len(output.keywords) <= 5


def test_stage4_sentiment(mock_llm_router):
    """Test Stage 4: Sentiment analysis."""
    mock_response = json.dumps(
        {
            "score": 0.7,
            "justification": "Major acquisition that expands market share is bullish",
            "confidence": 0.85,
        }
    )
    mock_llm_router.return_value = mock_response

    extraction = ExtractionOutput(
        key_facts=["Acquisition"], parties=[], dates=[], dollar_amounts=[], raw_response=""
    )
    summary = SummaryOutput(summary="Acme acquires XYZ", raw_response="")
    keywords = KeywordOutput(keywords=["acquisition"], raw_response="")

    output = _stage4_sentiment(extraction, summary, keywords, max_retries=1)

    assert output.score == 0.7
    assert output.confidence == 0.85
    assert "bullish" in output.justification.lower()


def test_run_llm_chain_complete(mock_llm_router):
    """Test complete 4-stage pipeline."""
    # Mock responses for all 4 stages
    responses = [
        # Stage 1: Extraction
        json.dumps(
            {
                "key_facts": ["Revenue grew 25% YoY"],
                "parties": ["Acme Corp"],
                "dates": ["Q1 2025"],
                "dollar_amounts": ["$150M"],
            }
        ),
        # Stage 2: Summary
        "Acme Corp reported strong Q1 2025 results with revenue of $150M, up 25% year-over-year.",
        # Stage 3: Keywords
        json.dumps({"keywords": ["earnings", "revenue_beat"]}),
        # Stage 4: Sentiment
        json.dumps(
            {
                "score": 0.8,
                "justification": "Strong revenue growth indicates positive momentum",
                "confidence": 0.9,
            }
        ),
    ]

    mock_llm_router.side_effect = responses

    filing_text = "Q1 2025 earnings report: Revenue $150M..."
    output = run_llm_chain(filing_text, max_retries=1)

    assert output.stages_completed == 4
    assert len(output.extraction.key_facts) > 0
    assert len(output.summary.summary) > 0
    assert len(output.keywords.keywords) > 0
    assert output.sentiment.score > 0
    assert output.total_time_sec >= 0


def test_run_llm_chain_with_metrics(mock_llm_router):
    """Test LLM chain with pre-extracted numeric metrics."""
    mock_llm_router.side_effect = [
        json.dumps({"key_facts": ["Revenue beat"], "parties": [], "dates": [], "dollar_amounts": []}),
        "Summary text",
        json.dumps({"keywords": ["earnings"]}),
        json.dumps({"score": 0.5, "justification": "Neutral", "confidence": 0.7}),
    ]

    metrics = NumericMetrics(revenue=[RevenueData(value=150, unit="millions", period="Q1 2025")])

    output = run_llm_chain("Filing text", numeric_metrics=metrics, max_retries=1)

    assert output.stages_completed == 4


def test_get_filing_summary(mock_llm_router):
    """Test quick summary function."""
    mock_llm_router.side_effect = [
        json.dumps({"key_facts": ["Key fact"], "parties": [], "dates": [], "dollar_amounts": []}),
        "This is a concise summary of the filing.",
    ]

    summary = get_filing_summary("Filing text")

    assert len(summary) > 10
    assert isinstance(summary, str)


def test_get_filing_sentiment(mock_llm_router):
    """Test quick sentiment function."""
    mock_llm_router.side_effect = [
        json.dumps({"key_facts": ["Fact"], "parties": [], "dates": [], "dollar_amounts": []}),
        "Summary",
        json.dumps({"keywords": ["earnings"]}),
        json.dumps({"score": 0.6, "justification": "Positive earnings", "confidence": 0.8}),
    ]

    score, justification = get_filing_sentiment("Filing text")

    assert -1.0 <= score <= 1.0
    assert len(justification) > 5


def test_stage1_extraction_fallback_parsing(mock_llm_router):
    """Test Stage 1 fallback when JSON parsing fails."""
    mock_llm_router.return_value = "Not valid JSON response"

    output = _stage1_extraction("Filing text", None, None, max_retries=1)

    # Should return fallback output
    assert "Failed to parse" in output.key_facts[0]
    assert len(output.parties) == 0


def test_stage3_keywords_fallback(mock_llm_router):
    """Test Stage 3 fallback when JSON parsing fails."""
    mock_llm_router.return_value = "Not valid JSON"

    extraction = ExtractionOutput(key_facts=[], parties=[], dates=[], dollar_amounts=[], raw_response="")
    summary = SummaryOutput(summary="Summary", raw_response="")

    output = _stage3_keywords(extraction, summary, max_retries=1)

    # Should return empty keywords list
    assert isinstance(output.keywords, list)


def test_stage4_sentiment_clamping(mock_llm_router):
    """Test that sentiment scores are clamped to [-1, 1]."""
    mock_response = json.dumps(
        {
            "score": 5.0,  # Invalid: too high
            "justification": "Test",
            "confidence": 2.0,  # Invalid: too high
        }
    )
    mock_llm_router.return_value = mock_response

    extraction = ExtractionOutput(key_facts=[], parties=[], dates=[], dollar_amounts=[], raw_response="")
    summary = SummaryOutput(summary="Summary", raw_response="")
    keywords = KeywordOutput(keywords=[], raw_response="")

    output = _stage4_sentiment(extraction, summary, keywords, max_retries=1)

    assert -1.0 <= output.score <= 1.0
    assert 0.0 <= output.confidence <= 1.0


def test_extraction_output_dataclass():
    """Test ExtractionOutput dataclass."""
    output = ExtractionOutput(
        key_facts=["Fact 1", "Fact 2"],
        parties=["Company A"],
        dates=["Q1 2025"],
        dollar_amounts=["$100M"],
        raw_response="Raw text",
    )

    assert len(output.key_facts) == 2
    assert output.parties[0] == "Company A"


def test_llm_chain_output_dataclass():
    """Test LLMChainOutput dataclass."""
    extraction = ExtractionOutput(key_facts=[], parties=[], dates=[], dollar_amounts=[], raw_response="")
    summary = SummaryOutput(summary="Summary", raw_response="")
    keywords = KeywordOutput(keywords=["tag1"], raw_response="")
    sentiment = SentimentOutput(score=0.5, justification="Neutral", confidence=0.7, raw_response="")

    output = LLMChainOutput(
        extraction=extraction,
        summary=summary,
        keywords=keywords,
        sentiment=sentiment,
        total_time_sec=10.5,
        stages_completed=4,
    )

    assert output.stages_completed == 4
    assert output.total_time_sec == 10.5
    assert output.keywords.keywords[0] == "tag1"


def test_llm_retry_logic(mock_llm_router):
    """Test that LLM calls retry on failure."""
    # First call fails, second succeeds
    mock_llm_router.side_effect = [
        Exception("API error"),
        json.dumps({"key_facts": ["Success"], "parties": [], "dates": [], "dollar_amounts": []}),
    ]

    output = _stage1_extraction("Filing text", None, None, max_retries=2)

    assert "Success" in output.key_facts
    assert mock_llm_router.call_count == 2


def test_llm_max_retries_exceeded(mock_llm_router):
    """Test that LLM chain fails after max retries."""
    mock_llm_router.side_effect = Exception("API error")

    with pytest.raises(RuntimeError, match="failed after"):
        _stage1_extraction("Filing text", None, None, max_retries=2)
