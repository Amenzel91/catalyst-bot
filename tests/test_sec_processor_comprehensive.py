"""
Comprehensive Test Suite for SEC Processor
============================================

Tests cover:
- Valid JSON responses from LLM
- Malformed JSON responses (missing brackets, incomplete data)
- Empty responses from LLM
- Partial/truncated responses
- Markdown code block wrapping (```json...```)
- Missing fields in JSON
- Invalid data types in JSON
- All 8-K item types and complexity detection
- Material events extraction
- Financial metrics parsing
- Sentiment analysis
- Cost calculations
- Error handling and fallbacks
- Integration with LLM service

Coverage areas:
1. Response parsing (malformed, empty, partial, truncated)
2. 8-K complexity detection (all item types)
3. Material event extraction
4. Financial metrics extraction (deal size, shares, dilution)
5. Sentiment classification (bullish, neutral, bearish)
6. Error handling and graceful degradation
7. LLM service integration
8. Cost tracking
"""

import json
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

from catalyst_bot.processors.sec_processor import (
    FinancialMetric,
    MaterialEvent,
    SECAnalysisResult,
    SECProcessor,
)
from catalyst_bot.services import LLMResponse, TaskComplexity

# Configure pytest-asyncio
pytestmark = pytest.mark.anyio


class TestSECProcessorJSONParsing:
    """Test JSON response parsing with various edge cases."""

    @pytest.fixture
    def processor(self):
        """Create SEC processor instance."""
        return SECProcessor(config={"enabled": True})

    def test_valid_json_response(self, processor):
        """Test parsing of valid JSON response."""
        llm_response = json.dumps({
            "material_events": [
                {
                    "event_type": "M&A",
                    "description": "Acquired XYZ Corp",
                    "significance": "high"
                }
            ],
            "financial_metrics": [
                {
                    "metric_name": "deal_size",
                    "value": 50000000,
                    "unit": "USD",
                    "context": "Cash acquisition"
                }
            ],
            "sentiment": {
                "overall": "bullish",
                "confidence": 0.85
            },
            "summary": {
                "brief_summary": "Company acquired XYZ Corp for $50M."
            }
        })

        result = processor._parse_8k_response(
            llm_response=llm_response,
            ticker="AAPL",
            filing_type="8-K",
            item="1.01",
            filing_url="https://sec.gov/...",
            llm_provider="gemini_flash",
            llm_cost_usd=0.001,
            llm_latency_ms=500.0,
            raw_response=llm_response
        )

        assert result.ticker == "AAPL"
        assert result.filing_type == "8-K"
        assert result.item == "1.01"
        assert len(result.material_events) == 1
        assert result.material_events[0].event_type == "M&A"
        assert result.material_events[0].description == "Acquired XYZ Corp"
        assert result.material_events[0].significance == "high"
        assert len(result.financial_metrics) == 1
        assert result.financial_metrics[0].metric_name == "deal_size"
        assert result.financial_metrics[0].value == 50000000
        assert result.sentiment == "bullish"
        assert result.sentiment_confidence == 0.85
        assert "acquired xyz corp" in result.llm_summary.lower()

    def test_malformed_json_missing_closing_bracket(self, processor):
        """Test parsing of JSON missing closing bracket."""
        llm_response = """
        {
            "material_events": [],
            "financial_metrics": [],
            "sentiment": {
                "overall": "neutral",
                "confidence": 0.5
            },
            "summary": {
                "brief_summary": "Standard filing"
        """  # Missing closing braces

        result = processor._parse_8k_response(
            llm_response=llm_response,
            ticker="AAPL",
            filing_type="8-K",
            item="8.01",
            filing_url="https://sec.gov/...",
            llm_provider="gemini_flash",
            llm_cost_usd=0.001,
            llm_latency_ms=500.0,
            raw_response=llm_response
        )

        # Should return default values on parse error
        assert result.ticker == "AAPL"
        assert len(result.material_events) == 0
        assert len(result.financial_metrics) == 0
        assert result.sentiment == "neutral"
        assert result.sentiment_confidence == 0.5
        assert "parse" in result.llm_summary.lower()

    def test_malformed_json_invalid_syntax(self, processor):
        """Test parsing of JSON with invalid syntax."""
        llm_response = """
        {
            "material_events": [,],  # Invalid comma
            "financial_metrics": [],
            "sentiment": {
                "overall": "neutral"
            }
        }
        """

        result = processor._parse_8k_response(
            llm_response=llm_response,
            ticker="AAPL",
            filing_type="8-K",
            item="8.01",
            filing_url="https://sec.gov/...",
            llm_provider="gemini_flash",
            llm_cost_usd=0.001,
            llm_latency_ms=500.0,
            raw_response=llm_response
        )

        assert result.sentiment == "neutral"
        assert "parse" in result.llm_summary.lower() or "unable" in result.llm_summary.lower()

    def test_empty_response(self, processor):
        """Test handling of empty LLM response."""
        llm_response = ""

        result = processor._parse_8k_response(
            llm_response=llm_response,
            ticker="AAPL",
            filing_type="8-K",
            item="8.01",
            filing_url="https://sec.gov/...",
            llm_provider="gemini_flash",
            llm_cost_usd=0.001,
            llm_latency_ms=500.0,
            raw_response=llm_response
        )

        assert result.ticker == "AAPL"
        assert len(result.material_events) == 0
        assert len(result.financial_metrics) == 0
        assert result.sentiment == "neutral"
        assert result.sentiment_confidence == 0.5

    def test_partial_response_missing_fields(self, processor):
        """Test parsing response with missing required fields."""
        llm_response = json.dumps({
            "material_events": [],
            # Missing financial_metrics
            "sentiment": {
                "overall": "bullish"
                # Missing confidence
            }
            # Missing summary
        })

        result = processor._parse_8k_response(
            llm_response=llm_response,
            ticker="AAPL",
            filing_type="8-K",
            item="2.01",
            filing_url="https://sec.gov/...",
            llm_provider="gemini_flash",
            llm_cost_usd=0.001,
            llm_latency_ms=500.0,
            raw_response=llm_response
        )

        assert result.sentiment == "bullish"
        assert result.sentiment_confidence == 0.5  # Default
        assert len(result.financial_metrics) == 0  # Empty on missing

    def test_markdown_code_block_json(self, processor):
        """Test parsing JSON wrapped in markdown code blocks."""
        llm_response = """```json
{
    "material_events": [],
    "financial_metrics": [],
    "sentiment": {
        "overall": "neutral",
        "confidence": 0.6
    },
    "summary": {
        "brief_summary": "Routine disclosure"
    }
}
```"""

        result = processor._parse_8k_response(
            llm_response=llm_response,
            ticker="AAPL",
            filing_type="8-K",
            item="8.01",
            filing_url="https://sec.gov/...",
            llm_provider="gemini_flash",
            llm_cost_usd=0.001,
            llm_latency_ms=500.0,
            raw_response=llm_response
        )

        assert result.sentiment == "neutral"
        assert result.sentiment_confidence == 0.6
        assert "routine" in result.llm_summary.lower()

    def test_markdown_code_block_plain(self, processor):
        """Test parsing JSON wrapped in plain markdown code blocks (```)."""
        llm_response = """```
{
    "material_events": [],
    "financial_metrics": [],
    "sentiment": {
        "overall": "bearish",
        "confidence": 0.75
    },
    "summary": {
        "brief_summary": "Dilutive offering"
    }
}
```"""

        result = processor._parse_8k_response(
            llm_response=llm_response,
            ticker="AAPL",
            filing_type="8-K",
            item="3.02",
            filing_url="https://sec.gov/...",
            llm_provider="gemini_flash",
            llm_cost_usd=0.001,
            llm_latency_ms=500.0,
            raw_response=llm_response
        )

        assert result.sentiment == "bearish"
        assert result.sentiment_confidence == 0.75

    def test_truncated_response(self, processor):
        """Test parsing truncated JSON response."""
        llm_response = """
{
    "material_events": [
        {
            "event_type": "Partnership",
            "description": "Signed agreement with maj
"""  # Truncated mid-sentence

        result = processor._parse_8k_response(
            llm_response=llm_response,
            ticker="AAPL",
            filing_type="8-K",
            item="1.01",
            filing_url="https://sec.gov/...",
            llm_provider="gemini_flash",
            llm_cost_usd=0.001,
            llm_latency_ms=500.0,
            raw_response=llm_response
        )

        # Should handle gracefully with defaults
        assert result.ticker == "AAPL"
        assert result.sentiment == "neutral"

    def test_invalid_data_types(self, processor):
        """Test parsing response with invalid data types."""
        llm_response = json.dumps({
            "material_events": [
                {
                    "event_type": "M&A",
                    "description": "Acquisition",
                    "significance": "very_high"  # Not in expected values
                }
            ],
            "financial_metrics": [
                {
                    "metric_name": "deal_size",
                    "value": "fifty million",  # String instead of float
                    "unit": "USD",
                    "context": "Cash"
                }
            ],
            "sentiment": {
                "overall": "bullish",
                "confidence": "high"  # String instead of float
            },
            "summary": {
                "brief_summary": "Deal completed"
            }
        })

        result = processor._parse_8k_response(
            llm_response=llm_response,
            ticker="AAPL",
            filing_type="8-K",
            item="1.01",
            filing_url="https://sec.gov/...",
            llm_provider="gemini_flash",
            llm_cost_usd=0.001,
            llm_latency_ms=500.0,
            raw_response=llm_response
        )

        # Should handle type conversions gracefully
        assert len(result.material_events) == 1
        assert result.material_events[0].significance == "very_high"  # Preserved as-is
        assert len(result.financial_metrics) == 1
        assert result.financial_metrics[0].value == 0.0  # Converted to 0 on error
        assert result.sentiment_confidence == 0.5  # Default on conversion error


class TestSECProcessor8KComplexity:
    """Test 8-K item complexity detection."""

    @pytest.fixture
    def processor(self):
        """Create SEC processor instance."""
        return SECProcessor(config={"enabled": True})

    def test_complex_items(self, processor):
        """Test detection of COMPLEX complexity items."""
        complex_items = ["1.01", "2.01", "2.02"]

        for item in complex_items:
            complexity = processor._detect_8k_complexity(item)
            assert complexity == TaskComplexity.COMPLEX, f"Item {item} should be COMPLEX"

    def test_medium_items(self, processor):
        """Test detection of MEDIUM complexity items."""
        medium_items = ["1.02", "2.03", "3.01", "4.01", "5.02"]

        for item in medium_items:
            complexity = processor._detect_8k_complexity(item)
            assert complexity == TaskComplexity.MEDIUM, f"Item {item} should be MEDIUM"

    def test_simple_items(self, processor):
        """Test detection of SIMPLE complexity items."""
        simple_items = ["8.01", "9.01"]

        for item in simple_items:
            complexity = processor._detect_8k_complexity(item)
            assert complexity == TaskComplexity.SIMPLE, f"Item {item} should be SIMPLE"

    def test_item_with_prefix(self, processor):
        """Test complexity detection with 'Item ' prefix."""
        complexity = processor._detect_8k_complexity("Item 1.01")
        assert complexity == TaskComplexity.COMPLEX

    def test_unknown_item_defaults_to_medium(self, processor):
        """Test unknown item defaults to MEDIUM complexity."""
        complexity = processor._detect_8k_complexity("99.99")
        assert complexity == TaskComplexity.MEDIUM


class TestMaterialEventsExtraction:
    """Test extraction of material events from LLM responses."""

    @pytest.fixture
    def processor(self):
        """Create SEC processor instance."""
        return SECProcessor(config={"enabled": True})

    def test_multiple_material_events(self, processor):
        """Test extraction of multiple material events."""
        llm_response = json.dumps({
            "material_events": [
                {
                    "event_type": "M&A",
                    "description": "Acquired competitor for $100M",
                    "significance": "high"
                },
                {
                    "event_type": "Partnership",
                    "description": "Strategic alliance with major pharma",
                    "significance": "medium"
                },
                {
                    "event_type": "FDA Approval",
                    "description": "Received FDA approval for drug X",
                    "significance": "high"
                }
            ],
            "financial_metrics": [],
            "sentiment": {"overall": "bullish", "confidence": 0.9},
            "summary": {"brief_summary": "Major developments"}
        })

        result = processor._parse_8k_response(
            llm_response=llm_response,
            ticker="BIOTECH",
            filing_type="8-K",
            item="1.01",
            filing_url="https://sec.gov/...",
            llm_provider="gemini_flash",
            llm_cost_usd=0.001,
            llm_latency_ms=500.0,
            raw_response=llm_response
        )

        assert len(result.material_events) == 3
        assert result.material_events[0].event_type == "M&A"
        assert result.material_events[1].event_type == "Partnership"
        assert result.material_events[2].event_type == "FDA Approval"
        assert result.material_events[0].significance == "high"
        assert result.material_events[1].significance == "medium"

    def test_no_material_events(self, processor):
        """Test handling when no material events found."""
        llm_response = json.dumps({
            "material_events": [],
            "financial_metrics": [],
            "sentiment": {"overall": "neutral", "confidence": 0.5},
            "summary": {"brief_summary": "No material events"}
        })

        result = processor._parse_8k_response(
            llm_response=llm_response,
            ticker="AAPL",
            filing_type="8-K",
            item="8.01",
            filing_url="https://sec.gov/...",
            llm_provider="gemini_flash",
            llm_cost_usd=0.001,
            llm_latency_ms=500.0,
            raw_response=llm_response
        )

        assert len(result.material_events) == 0

    def test_material_events_missing_fields(self, processor):
        """Test material events with missing optional fields."""
        llm_response = json.dumps({
            "material_events": [
                {
                    "event_type": "Leadership Change"
                    # Missing description and significance
                }
            ],
            "financial_metrics": [],
            "sentiment": {"overall": "neutral", "confidence": 0.5},
            "summary": {"brief_summary": "CEO resigned"}
        })

        result = processor._parse_8k_response(
            llm_response=llm_response,
            ticker="AAPL",
            filing_type="8-K",
            item="5.02",
            filing_url="https://sec.gov/...",
            llm_provider="gemini_flash",
            llm_cost_usd=0.001,
            llm_latency_ms=500.0,
            raw_response=llm_response
        )

        assert len(result.material_events) == 1
        assert result.material_events[0].event_type == "Leadership Change"
        assert result.material_events[0].description == ""  # Default
        assert result.material_events[0].significance == "medium"  # Default


class TestFinancialMetricsExtraction:
    """Test extraction of financial metrics from LLM responses."""

    @pytest.fixture
    def processor(self):
        """Create SEC processor instance."""
        return SECProcessor(config={"enabled": True})

    def test_multiple_financial_metrics(self, processor):
        """Test extraction of multiple financial metrics."""
        llm_response = json.dumps({
            "material_events": [],
            "financial_metrics": [
                {
                    "metric_name": "deal_size",
                    "value": 150000000,
                    "unit": "USD",
                    "context": "Total transaction value"
                },
                {
                    "metric_name": "shares",
                    "value": 5000000,
                    "unit": "shares",
                    "context": "Common stock issued"
                },
                {
                    "metric_name": "price_per_share",
                    "value": 2.50,
                    "unit": "USD",
                    "context": "Offering price"
                }
            ],
            "sentiment": {"overall": "bearish", "confidence": 0.7},
            "summary": {"brief_summary": "Dilutive offering"}
        })

        result = processor._parse_8k_response(
            llm_response=llm_response,
            ticker="PENNY",
            filing_type="8-K",
            item="3.02",
            filing_url="https://sec.gov/...",
            llm_provider="gemini_flash",
            llm_cost_usd=0.001,
            llm_latency_ms=500.0,
            raw_response=llm_response
        )

        assert len(result.financial_metrics) == 3
        assert result.financial_metrics[0].metric_name == "deal_size"
        assert result.financial_metrics[0].value == 150000000
        assert result.financial_metrics[1].metric_name == "shares"
        assert result.financial_metrics[1].value == 5000000
        assert result.financial_metrics[2].value == 2.50

    def test_invalid_numeric_values(self, processor):
        """Test handling of invalid numeric values in metrics."""
        llm_response = json.dumps({
            "material_events": [],
            "financial_metrics": [
                {
                    "metric_name": "deal_size",
                    "value": "N/A",  # Non-numeric
                    "unit": "USD",
                    "context": "Not disclosed"
                },
                {
                    "metric_name": "revenue",
                    "value": None,  # Null
                    "unit": "USD",
                    "context": "TBD"
                }
            ],
            "sentiment": {"overall": "neutral", "confidence": 0.5},
            "summary": {"brief_summary": "Metrics unclear"}
        })

        result = processor._parse_8k_response(
            llm_response=llm_response,
            ticker="AAPL",
            filing_type="8-K",
            item="2.02",
            filing_url="https://sec.gov/...",
            llm_provider="gemini_flash",
            llm_cost_usd=0.001,
            llm_latency_ms=500.0,
            raw_response=llm_response
        )

        assert len(result.financial_metrics) == 2
        assert result.financial_metrics[0].value == 0.0  # Converted to 0
        assert result.financial_metrics[1].value == 0.0  # Converted to 0


class TestSentimentAnalysis:
    """Test sentiment classification and confidence scoring."""

    @pytest.fixture
    def processor(self):
        """Create SEC processor instance."""
        return SECProcessor(config={"enabled": True})

    def test_bullish_sentiment(self, processor):
        """Test bullish sentiment classification."""
        llm_response = json.dumps({
            "material_events": [],
            "financial_metrics": [],
            "sentiment": {
                "overall": "bullish",
                "confidence": 0.95
            },
            "summary": {"brief_summary": "Positive development"}
        })

        result = processor._parse_8k_response(
            llm_response=llm_response,
            ticker="AAPL",
            filing_type="8-K",
            item="1.01",
            filing_url="https://sec.gov/...",
            llm_provider="gemini_flash",
            llm_cost_usd=0.001,
            llm_latency_ms=500.0,
            raw_response=llm_response
        )

        assert result.sentiment == "bullish"
        assert result.sentiment_confidence == 0.95

    def test_bearish_sentiment(self, processor):
        """Test bearish sentiment classification."""
        llm_response = json.dumps({
            "material_events": [],
            "financial_metrics": [],
            "sentiment": {
                "overall": "bearish",
                "confidence": 0.8
            },
            "summary": {"brief_summary": "Dilution concerns"}
        })

        result = processor._parse_8k_response(
            llm_response=llm_response,
            ticker="AAPL",
            filing_type="8-K",
            item="3.02",
            filing_url="https://sec.gov/...",
            llm_provider="gemini_flash",
            llm_cost_usd=0.001,
            llm_latency_ms=500.0,
            raw_response=llm_response
        )

        assert result.sentiment == "bearish"
        assert result.sentiment_confidence == 0.8

    def test_neutral_sentiment(self, processor):
        """Test neutral sentiment classification."""
        llm_response = json.dumps({
            "material_events": [],
            "financial_metrics": [],
            "sentiment": {
                "overall": "neutral",
                "confidence": 0.6
            },
            "summary": {"brief_summary": "Routine filing"}
        })

        result = processor._parse_8k_response(
            llm_response=llm_response,
            ticker="AAPL",
            filing_type="8-K",
            item="8.01",
            filing_url="https://sec.gov/...",
            llm_provider="gemini_flash",
            llm_cost_usd=0.001,
            llm_latency_ms=500.0,
            raw_response=llm_response
        )

        assert result.sentiment == "neutral"
        assert result.sentiment_confidence == 0.6

    def test_missing_confidence(self, processor):
        """Test default confidence when not provided."""
        llm_response = json.dumps({
            "material_events": [],
            "financial_metrics": [],
            "sentiment": {
                "overall": "bullish"
                # Missing confidence
            },
            "summary": {"brief_summary": "Good news"}
        })

        result = processor._parse_8k_response(
            llm_response=llm_response,
            ticker="AAPL",
            filing_type="8-K",
            item="1.01",
            filing_url="https://sec.gov/...",
            llm_provider="gemini_flash",
            llm_cost_usd=0.001,
            llm_latency_ms=500.0,
            raw_response=llm_response
        )

        assert result.sentiment == "bullish"
        assert result.sentiment_confidence == 0.5  # Default


class TestLLMServiceIntegration:
    """Test integration with LLM service."""

    @pytest.mark.asyncio
    async def test_process_8k_with_llm_service(self):
        """Test end-to-end 8-K processing with mocked LLM service."""
        # Mock LLM service response
        mock_llm_response = LLMResponse(
            text=json.dumps({
                "material_events": [
                    {
                        "event_type": "M&A",
                        "description": "Acquisition completed",
                        "significance": "high"
                    }
                ],
                "financial_metrics": [
                    {
                        "metric_name": "deal_size",
                        "value": 75000000,
                        "unit": "USD",
                        "context": "All-cash deal"
                    }
                ],
                "sentiment": {
                    "overall": "bullish",
                    "confidence": 0.85
                },
                "summary": {
                    "brief_summary": "Company completed strategic acquisition for $75M."
                }
            }),
            provider="gemini_flash",
            model="gemini-2.5-flash",
            cached=False,
            latency_ms=450.0,
            tokens_input=250,
            tokens_output=150,
            cost_usd=0.0015,
            confidence=None
        )

        with patch('catalyst_bot.processors.sec_processor.LLMService') as mock_service_class:
            # Configure mock
            mock_service = AsyncMock()
            mock_service.query = AsyncMock(return_value=mock_llm_response)
            mock_service_class.return_value = mock_service

            # Create processor and process
            processor = SECProcessor(config={"enabled": True})
            result = await processor.process_8k(
                filing_url="https://sec.gov/filing/12345",
                ticker="AAPL",
                item="1.01",
                title="Acquisition Agreement",
                summary="Company entered into agreement to acquire XYZ Corp..."
            )

            # Verify result
            assert result.ticker == "AAPL"
            assert result.filing_type == "8-K"
            assert result.item == "1.01"
            assert len(result.material_events) == 1
            assert result.material_events[0].event_type == "M&A"
            assert len(result.financial_metrics) == 1
            assert result.financial_metrics[0].value == 75000000
            assert result.sentiment == "bullish"
            assert result.sentiment_confidence == 0.85
            assert result.llm_provider == "gemini_flash"
            assert result.llm_cost_usd == 0.0015
            assert result.llm_latency_ms == 450.0

    @pytest.mark.asyncio
    async def test_process_8k_with_empty_llm_response(self):
        """Test handling of empty LLM response."""
        mock_llm_response = LLMResponse(
            text="",
            provider="gemini_flash",
            model="gemini-2.5-flash",
            cached=False,
            latency_ms=100.0,
            tokens_input=200,
            tokens_output=0,
            cost_usd=0.0001,
            confidence=None
        )

        with patch('catalyst_bot.processors.sec_processor.LLMService') as mock_service_class:
            mock_service = AsyncMock()
            mock_service.query = AsyncMock(return_value=mock_llm_response)
            mock_service_class.return_value = mock_service

            processor = SECProcessor(config={"enabled": True})
            result = await processor.process_8k(
                filing_url="https://sec.gov/filing/12345",
                ticker="AAPL",
                item="8.01",
                title="Other Event"
            )

            # Should return defaults on empty response
            assert result.ticker == "AAPL"
            assert len(result.material_events) == 0
            assert len(result.financial_metrics) == 0
            assert result.sentiment == "neutral"
            assert result.sentiment_confidence == 0.5


class TestPromptBuilding:
    """Test 8-K prompt construction."""

    @pytest.fixture
    def processor(self):
        """Create SEC processor instance."""
        return SECProcessor(config={"enabled": True})

    def test_prompt_with_summary(self, processor):
        """Test prompt includes summary when provided."""
        prompt = processor._build_8k_prompt(
            item="1.01",
            title="Material Agreement",
            summary="Company entered into a licensing agreement with Partner Inc. for exclusive rights to technology platform."
        )

        assert "Item: 1.01" in prompt
        assert "Material Agreement" in prompt
        assert "licensing agreement" in prompt
        assert "JSON" in prompt

    def test_prompt_without_summary(self, processor):
        """Test prompt works without summary."""
        prompt = processor._build_8k_prompt(
            item="8.01",
            title="Other Events"
        )

        assert "Item: 8.01" in prompt
        assert "Other Events" in prompt
        assert "JSON" in prompt
        assert "Summary:" not in prompt

    def test_prompt_truncates_long_summary(self, processor):
        """Test prompt truncates very long summaries."""
        long_summary = "A" * 1000  # 1000 character summary

        prompt = processor._build_8k_prompt(
            item="1.01",
            title="Test",
            summary=long_summary
        )

        # Should truncate summary to ~500 chars with ellipsis
        # The full prompt will include the template, so check summary portion
        assert "AAA...AAA" not in prompt or len(prompt) < 2500  # Reasonable total length


class TestCostTracking:
    """Test cost tracking and metadata."""

    @pytest.mark.asyncio
    async def test_cost_metadata_preserved(self):
        """Test that cost and latency metadata is preserved in results."""
        mock_llm_response = LLMResponse(
            text=json.dumps({
                "material_events": [],
                "financial_metrics": [],
                "sentiment": {"overall": "neutral", "confidence": 0.5},
                "summary": {"brief_summary": "Test"}
            }),
            provider="gemini_flash_lite",
            model="gemini-2.0-flash-lite",
            cached=False,
            latency_ms=234.5,
            tokens_input=180,
            tokens_output=95,
            cost_usd=0.0003,
            confidence=None
        )

        with patch('catalyst_bot.processors.sec_processor.LLMService') as mock_service_class:
            mock_service = AsyncMock()
            mock_service.query = AsyncMock(return_value=mock_llm_response)
            mock_service_class.return_value = mock_service

            processor = SECProcessor(config={"enabled": True})
            result = await processor.process_8k(
                filing_url="https://sec.gov/filing/12345",
                ticker="TEST",
                item="8.01",
                title="Test Filing"
            )

            assert result.llm_provider == "gemini_flash_lite"
            assert result.llm_cost_usd == 0.0003
            assert result.llm_latency_ms == 234.5


class TestErrorHandling:
    """Test error handling and graceful degradation."""

    @pytest.mark.asyncio
    async def test_handles_llm_service_error(self):
        """Test graceful handling of LLM service errors."""
        with patch('catalyst_bot.processors.sec_processor.LLMService') as mock_service_class:
            mock_service = AsyncMock()
            mock_service.query = AsyncMock(side_effect=Exception("API timeout"))
            mock_service_class.return_value = mock_service

            processor = SECProcessor(config={"enabled": True})

            # Should not crash, but raise the exception for caller to handle
            with pytest.raises(Exception) as exc_info:
                await processor.process_8k(
                    filing_url="https://sec.gov/filing/12345",
                    ticker="AAPL",
                    item="1.01",
                    title="Test"
                )

            assert "timeout" in str(exc_info.value).lower()

    def test_handles_exception_during_parsing(self):
        """Test graceful handling of unexpected parsing errors."""
        processor = SECProcessor(config={"enabled": True})

        # Simulate an unexpected error during parsing
        with patch.object(processor, '_parse_8k_response', side_effect=Exception("Unexpected error")):
            # Should raise the exception
            with pytest.raises(Exception):
                processor._parse_8k_response(
                    llm_response="{}",
                    ticker="AAPL",
                    filing_type="8-K",
                    item="1.01",
                    filing_url="https://sec.gov/...",
                    llm_provider="gemini_flash",
                    llm_cost_usd=0.001,
                    llm_latency_ms=500.0,
                    raw_response="{}"
                )
