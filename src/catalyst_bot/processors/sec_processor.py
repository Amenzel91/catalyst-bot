"""
SEC Filing Processor
====================

Unified processor for SEC filings (8-K, 10-Q, 10-K, 424B5, etc.) using the
centralized LLM Service Hub.

Features:
- Auto-detect 8-K Item complexity
- Extract Material Events, Financial Metrics, Sentiment
- Smart prompt templates optimized for each filing type
- Cost-efficient routing via LLM Service
- Structured output with Pydantic validation

Usage:
    processor = SECProcessor()
    result = await processor.process_8k(
        filing_url="https://www.sec.gov/...",
        ticker="AAPL",
        item="1.01",
        title="Entry into Material Agreement"
    )
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from ..logging_utils import get_logger
from ..services import LLMService, LLMRequest, TaskComplexity
from .base import BaseProcessor

log = get_logger("sec_processor")


@dataclass
class MaterialEvent:
    """Material event extracted from filing."""
    event_type: str  # "M&A", "Partnership", "FDA Approval", etc.
    description: str
    significance: str  # "high", "medium", "low"


@dataclass
class FinancialMetric:
    """Financial metric extracted from filing."""
    metric_name: str  # "deal_size", "shares", "price_per_share", etc.
    value: float
    unit: str  # "USD", "shares", etc.
    context: str  # Additional context


@dataclass
class SECAnalysisResult:
    """Structured result from SEC filing analysis."""

    # Core fields
    ticker: str
    filing_type: str
    item: Optional[str]  # For 8-K filings

    # Extracted information
    material_events: List[MaterialEvent]
    financial_metrics: List[FinancialMetric]
    sentiment: str  # "bullish", "neutral", "bearish"
    sentiment_confidence: float  # 0.0 to 1.0

    # LLM metadata
    llm_summary: str
    llm_provider: str
    llm_cost_usd: float
    llm_latency_ms: float

    # Raw data
    raw_llm_response: str
    filing_url: Optional[str] = None


class SECProcessor(BaseProcessor):
    """
    Unified SEC filing processor using centralized LLM service.

    Handles all SEC filing types with intelligent routing and cost optimization.
    """

    # 8-K Item complexity mapping
    ITEM_COMPLEXITY = {
        "1.01": TaskComplexity.COMPLEX,    # Material agreements (M&A, partnerships)
        "1.02": TaskComplexity.MEDIUM,     # Termination of agreements
        "1.03": TaskComplexity.MEDIUM,     # Bankruptcy/receivership
        "1.04": TaskComplexity.MEDIUM,     # Mine safety disclosures
        "2.01": TaskComplexity.COMPLEX,    # Completion of acquisition
        "2.02": TaskComplexity.COMPLEX,    # Earnings results
        "2.03": TaskComplexity.MEDIUM,     # Creation of obligation
        "2.04": TaskComplexity.MEDIUM,     # Triggering events
        "2.05": TaskComplexity.MEDIUM,     # Costs associated with exit
        "2.06": TaskComplexity.MEDIUM,     # Credit enhancement
        "3.01": TaskComplexity.MEDIUM,     # Notice of delisting
        "3.02": TaskComplexity.MEDIUM,     # Unregistered sales of equity
        "3.03": TaskComplexity.MEDIUM,     # Material modifications
        "4.01": TaskComplexity.MEDIUM,     # Changes in registrant's certifying accountant
        "4.02": TaskComplexity.MEDIUM,     # Non-reliance on financial statements
        "5.01": TaskComplexity.MEDIUM,     # Changes in control
        "5.02": TaskComplexity.MEDIUM,     # Departure of directors/officers
        "5.03": TaskComplexity.MEDIUM,     # Amendments to articles
        "5.04": TaskComplexity.MEDIUM,     # Temporary suspension of trading
        "5.05": TaskComplexity.MEDIUM,     # Amendments to bylaws
        "5.06": TaskComplexity.MEDIUM,     # Change in shell company status
        "5.07": TaskComplexity.MEDIUM,     # Submission of matters to vote
        "5.08": TaskComplexity.MEDIUM,     # Shareholder director nominations
        "7.01": TaskComplexity.MEDIUM,     # Regulation FD disclosure
        "8.01": TaskComplexity.SIMPLE,     # Other events (most common, varied)
        "9.01": TaskComplexity.SIMPLE,     # Financial statements and exhibits
    }

    def __init__(self, config: Dict[str, Any] = None):
        """Initialize SEC processor."""
        super().__init__(config)

        # Initialize LLM service
        self.llm_service = LLMService(config)

        log.info("sec_processor_initialized llm_enabled=%s", self.llm_service.enabled)

    async def process_8k(
        self,
        filing_url: str,
        ticker: str,
        item: str,
        title: str,
        summary: Optional[str] = None
    ) -> SECAnalysisResult:
        """
        Process 8-K filing and extract material information.

        Args:
            filing_url: URL to the SEC filing
            ticker: Stock ticker symbol
            item: 8-K item number (e.g., "1.01", "8.01")
            title: Filing title/headline
            summary: Optional filing summary/excerpt

        Returns:
            SECAnalysisResult with extracted information
        """
        log.info(
            "processing_8k ticker=%s item=%s title=%s",
            ticker,
            item,
            title[:50] if title else "none"
        )

        # Detect complexity based on item
        complexity = self._detect_8k_complexity(item)

        # Build prompt
        prompt = self._build_8k_prompt(item, title, summary)

        # Create LLM request
        request = LLMRequest(
            prompt=prompt,
            complexity=complexity,
            feature_name=f"sec_8k_item_{item}",
            max_tokens=500,
            temperature=0.1,
            enable_cache=True,
            compress_prompt=True
        )

        # Query LLM service
        response = await self.llm_service.query(request)

        # Parse response
        result = self._parse_8k_response(
            response.text,
            ticker=ticker,
            filing_type="8-K",
            item=item,
            filing_url=filing_url,
            llm_provider=response.provider,
            llm_cost_usd=response.cost_usd,
            llm_latency_ms=response.latency_ms,
            raw_response=response.text
        )

        log.info(
            "processing_8k_complete ticker=%s item=%s sentiment=%s events=%d metrics=%d cost=$%.4f",
            ticker,
            item,
            result.sentiment,
            len(result.material_events),
            len(result.financial_metrics),
            result.llm_cost_usd
        )

        return result

    def _detect_8k_complexity(self, item: str) -> TaskComplexity:
        """
        Detect task complexity from 8-K item number.

        Args:
            item: 8-K item number (e.g., "1.01")

        Returns:
            TaskComplexity level
        """
        # Clean item number (remove "Item " prefix if present)
        clean_item = item.replace("Item ", "").strip()

        complexity = self.ITEM_COMPLEXITY.get(clean_item, TaskComplexity.MEDIUM)

        log.debug("detected_8k_complexity item=%s complexity=%s", clean_item, complexity.value)

        return complexity

    def _build_8k_prompt(
        self,
        item: str,
        title: str,
        summary: Optional[str] = None
    ) -> str:
        """
        Build optimized prompt for 8-K analysis.

        Args:
            item: 8-K item number
            title: Filing title
            summary: Optional filing summary

        Returns:
            Formatted prompt string
        """
        # Base prompt template
        prompt = f"""Analyze this SEC 8-K filing and extract key information.

Filing Type: 8-K
Item: {item}
Title: {title}
"""

        if summary:
            # Truncate summary to ~500 chars to control token usage
            truncated_summary = summary[:500] + "..." if len(summary) > 500 else summary
            prompt += f"\nSummary: {truncated_summary}\n"

        prompt += """
Extract the following information in JSON format:

1. MATERIAL EVENTS (if any):
   - event_type: Type of event (M&A, Partnership, FDA Approval, Bankruptcy, Leadership Change, etc.)
   - description: Brief description of the event
   - significance: "high", "medium", or "low"

2. FINANCIAL METRICS (if mentioned):
   - metric_name: Name of metric (deal_size, shares, price_per_share, dilution, revenue, etc.)
   - value: Numeric value
   - unit: Unit (USD, shares, percent, etc.)
   - context: Additional context

3. SENTIMENT:
   - overall: "bullish", "neutral", or "bearish"
   - confidence: 0.0 to 1.0 (how confident are you in this assessment?)

4. SUMMARY:
   - brief_summary: 1-2 sentence summary of the key takeaway

Respond ONLY with valid JSON in this exact format:
{
  "material_events": [
    {
      "event_type": "M&A",
      "description": "Company acquired XYZ Corp",
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
    "brief_summary": "Company completed strategic acquisition of XYZ Corp for $50M."
  }
}

If no material events or financial metrics are found, use empty arrays [].
"""
        return prompt

    def _parse_8k_response(
        self,
        llm_response: str,
        ticker: str,
        filing_type: str,
        item: str,
        filing_url: str,
        llm_provider: str,
        llm_cost_usd: float,
        llm_latency_ms: float,
        raw_response: str
    ) -> SECAnalysisResult:
        """
        Parse LLM response into structured result.

        Args:
            llm_response: Raw LLM response text
            ticker: Stock ticker
            filing_type: Type of filing
            item: 8-K item number
            filing_url: URL to filing
            llm_provider: LLM provider used
            llm_cost_usd: Cost of LLM request
            llm_latency_ms: Latency of LLM request
            raw_response: Raw LLM response for debugging

        Returns:
            SECAnalysisResult with parsed data
        """
        # Default values in case parsing fails
        material_events = []
        financial_metrics = []
        sentiment = "neutral"
        sentiment_confidence = 0.5
        summary = "Unable to parse LLM response"

        try:
            # Try to parse JSON response
            # NOTE: Markdown code block stripping is now handled by the LLM provider (gemini.py)
            # The response should already be clean JSON at this point
            clean_response = llm_response.strip()

            data = json.loads(clean_response)

            # Parse material events
            for event_data in data.get("material_events", []):
                material_events.append(MaterialEvent(
                    event_type=event_data.get("event_type", "unknown"),
                    description=event_data.get("description", ""),
                    significance=event_data.get("significance", "medium")
                ))

            # Parse financial metrics
            for metric_data in data.get("financial_metrics", []):
                try:
                    value = float(metric_data.get("value", 0))
                except (ValueError, TypeError):
                    value = 0.0

                financial_metrics.append(FinancialMetric(
                    metric_name=metric_data.get("metric_name", "unknown"),
                    value=value,
                    unit=metric_data.get("unit", ""),
                    context=metric_data.get("context", "")
                ))

            # Parse sentiment with validation
            sentiment_data = data.get("sentiment", {})

            # Validate sentiment value (must be bullish, neutral, or bearish)
            VALID_SENTIMENTS = {"bullish", "neutral", "bearish"}
            raw_sentiment = sentiment_data.get("overall", "neutral")
            if isinstance(raw_sentiment, str):
                raw_sentiment = raw_sentiment.lower().strip()

            if raw_sentiment not in VALID_SENTIMENTS:
                log.warning(
                    "invalid_sentiment_from_llm ticker=%s sentiment=%s defaulting_to_neutral",
                    ticker,
                    raw_sentiment
                )
                sentiment = "neutral"
            else:
                sentiment = raw_sentiment

            # Parse and clamp confidence to [0.0, 1.0]
            try:
                sentiment_confidence = float(sentiment_data.get("confidence", 0.5))
                # Clamp to valid range
                sentiment_confidence = max(0.0, min(1.0, sentiment_confidence))
            except (ValueError, TypeError):
                sentiment_confidence = 0.5

            # Parse summary
            summary_data = data.get("summary", {})
            summary = summary_data.get("brief_summary", "No summary available")

            log.debug(
                "parsed_8k_response ticker=%s events=%d metrics=%d sentiment=%s",
                ticker,
                len(material_events),
                len(financial_metrics),
                sentiment
            )

        except json.JSONDecodeError as e:
            log.warning(
                "failed_to_parse_json ticker=%s err=%s response=%s",
                ticker,
                str(e),
                llm_response[:200]
            )
            summary = "Failed to parse LLM response as JSON"

        except Exception as e:
            log.error(
                "error_parsing_8k_response ticker=%s err=%s",
                ticker,
                str(e),
                exc_info=True
            )
            summary = f"Error parsing response: {str(e)}"

        # Build result
        return SECAnalysisResult(
            ticker=ticker,
            filing_type=filing_type,
            item=item,
            material_events=material_events,
            financial_metrics=financial_metrics,
            sentiment=sentiment,
            sentiment_confidence=sentiment_confidence,
            llm_summary=summary,
            llm_provider=llm_provider,
            llm_cost_usd=llm_cost_usd,
            llm_latency_ms=llm_latency_ms,
            raw_llm_response=raw_response,
            filing_url=filing_url
        )

    async def process(self, *args, **kwargs) -> SECAnalysisResult:
        """
        Generic process method (delegates to specific filing type).

        For now, defaults to process_8k. Can be extended for other filing types.
        """
        return await self.process_8k(*args, **kwargs)
