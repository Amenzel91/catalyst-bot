"""SEC filing sentiment analysis with LLM-powered scoring.

This module provides sentiment scoring specifically for SEC filings, integrating
with the existing sentiment_sources.py aggregation system. It adds LLM-powered
nuanced analysis that understands filing-specific context.

Key features:
- LLM-based sentiment scoring (-1.0 to +1.0)
- Filing-type-specific weights (8-K Item 1.01 = high impact)
- Justification for every score (explainability)
- Integration with existing 6-component sentiment system

This becomes the 7th sentiment source in the aggregation pipeline.

Environment Variable:
- SENTIMENT_WEIGHT_SEC_LLM: Weight for SEC sentiment (default: 0.10)
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional

try:
    from .llm_chain import run_llm_chain
    from .logging_utils import get_logger
    from .numeric_extractor import NumericMetrics
    from .sec_parser import FilingSection
except Exception:
    import logging

    logging.basicConfig(level=logging.INFO)

    def get_logger(_):
        return logging.getLogger("sec_sentiment")


log = get_logger("sec_sentiment")


# Default weight for SEC sentiment in aggregation
DEFAULT_SEC_SENTIMENT_WEIGHT = 0.10

# Filing-type impact multipliers
FILING_IMPACT_WEIGHTS = {
    "8-K": {
        "1.01": 3.0,  # Material agreements (M&A) - very high impact
        "1.03": 3.0,  # Bankruptcy - very high impact
        "2.02": 2.5,  # Earnings - high impact
        "3.02": 2.0,  # Equity sales (dilution) - medium-high impact
        "5.02": 1.8,  # Leadership changes - medium impact
        "7.01": 1.5,  # Regulation FD - medium impact
        "8.01": 1.3,  # Other events - medium-low impact
    },
    "10-Q": 2.0,  # Quarterly reports - high impact
    "10-K": 2.5,  # Annual reports - very high impact
    "S-1": 2.0,  # IPO filings - high impact
    "424B5": 1.5,  # Offering prospectus - medium impact
}


@dataclass
class SECSentimentOutput:
    """SEC filing sentiment result."""

    score: float  # -1.0 (bearish) to +1.0 (bullish)
    weighted_score: float  # Score adjusted by filing impact weight
    justification: str  # Explanation for the score
    confidence: float  # 0.0 to 1.0
    filing_type: str  # 8-K, 10-Q, etc.
    impact_weight: float  # Filing-specific multiplier


def get_sec_sentiment_weight() -> float:
    """Get SEC sentiment weight from environment.

    Returns
    -------
    float
        Weight to use for SEC sentiment in aggregation
    """
    try:
        return float(os.getenv("SENTIMENT_WEIGHT_SEC_LLM", DEFAULT_SEC_SENTIMENT_WEIGHT))
    except (ValueError, TypeError):
        return DEFAULT_SEC_SENTIMENT_WEIGHT


def get_filing_impact_weight(filing: FilingSection) -> float:
    """Get impact weight for a specific filing.

    Parameters
    ----------
    filing : FilingSection
        Filing section from sec_parser

    Returns
    -------
    float
        Impact weight (1.0 = baseline, higher = more important)

    Examples
    --------
    >>> filing = FilingSection(item_code="1.01", filing_type="8-K", ...)
    >>> get_filing_impact_weight(filing)
    3.0  # Very high impact
    """
    filing_type = filing.filing_type

    # Check 8-K item-specific weights
    if filing_type == "8-K" and filing.item_code:
        return FILING_IMPACT_WEIGHTS.get("8-K", {}).get(filing.item_code, 1.0)

    # Check other filing types
    return FILING_IMPACT_WEIGHTS.get(filing_type, 1.0)


def analyze_sec_filing_sentiment(
    filing: FilingSection,
    numeric_metrics: Optional[NumericMetrics] = None,
) -> SECSentimentOutput:
    """Analyze sentiment of an SEC filing using LLM.

    This function runs the full 4-stage LLM chain and extracts the
    sentiment score with justification. The score is then weighted by
    filing type importance.

    Parameters
    ----------
    filing : FilingSection
        Parsed SEC filing section
    numeric_metrics : NumericMetrics, optional
        Pre-extracted numeric data

    Returns
    -------
    SECSentimentOutput
        Sentiment score with justification and impact weighting

    Examples
    --------
    >>> filing = FilingSection(
    ...     item_code="2.02",
    ...     text="Q1 revenue grew 25% YoY...",
    ...     filing_type="8-K",
    ...     catalyst_type="earnings",
    ...     filing_url="https://..."
    ... )
    >>> result = analyze_sec_filing_sentiment(filing)
    >>> result.score  # 0.7 (bullish)
    >>> result.weighted_score  # 1.75 (0.7 * 2.5 for Item 2.02)
    """
    log.info(f"Analyzing SEC sentiment for {filing.filing_type} {filing.item_code}")

    try:
        # Run full LLM chain
        chain_output = run_llm_chain(
            filing.text,
            numeric_metrics=numeric_metrics,
            max_retries=2,
        )

        # Extract sentiment
        sentiment = chain_output.sentiment
        raw_score = sentiment.score
        confidence = sentiment.confidence
        justification = sentiment.justification

        # Get filing-specific impact weight
        impact_weight = get_filing_impact_weight(filing)

        # Calculate weighted score (clamped to [-1, 1])
        weighted_score = max(-1.0, min(1.0, raw_score * impact_weight))

        log.info(
            f"SEC sentiment: raw={raw_score:.2f}, weighted={weighted_score:.2f}, "
            f"impact={impact_weight:.1f}x, confidence={confidence:.2f}"
        )

        return SECSentimentOutput(
            score=raw_score,
            weighted_score=weighted_score,
            justification=justification,
            confidence=confidence,
            filing_type=filing.filing_type,
            impact_weight=impact_weight,
        )

    except Exception as e:
        log.error(f"SEC sentiment analysis failed: {e}")
        # Return neutral sentiment on failure
        return SECSentimentOutput(
            score=0.0,
            weighted_score=0.0,
            justification=f"Analysis failed: {str(e)[:100]}",
            confidence=0.0,
            filing_type=filing.filing_type,
            impact_weight=1.0,
        )


def quick_sec_sentiment(filing_text: str, filing_type: str = "8-K") -> float:
    """Quick sentiment score without full analysis.

    This is a lightweight version that skips the full LLM chain and just
    returns a simple sentiment score. Useful for batch processing or
    when detailed justification isn't needed.

    Parameters
    ----------
    filing_text : str
        Filing text content
    filing_type : str
        Type of filing (8-K, 10-Q, etc.)

    Returns
    -------
    float
        Sentiment score -1.0 to +1.0
    """
    # Use simple keyword-based sentiment for quick check
    positive_keywords = [
        "strong",
        "growth",
        "beat",
        "exceeded",
        "record",
        "approved",
        "success",
        "partnership",
        "acquisition",
        "expansion",
    ]

    negative_keywords = [
        "weak",
        "decline",
        "miss",
        "below",
        "loss",
        "bankruptcy",
        "delisting",
        "warning",
        "lawsuit",
        "dilution",
        "offering",
    ]

    text_lower = filing_text.lower()

    positive_count = sum(1 for kw in positive_keywords if kw in text_lower)
    negative_count = sum(1 for kw in negative_keywords if kw in text_lower)

    if positive_count + negative_count == 0:
        return 0.0

    # Normalize to [-1, 1]
    score = (positive_count - negative_count) / (positive_count + negative_count)

    return max(-1.0, min(1.0, score))


# ============================================================================
# Integration with sentiment_sources.py
# ============================================================================


def get_sec_filing_sentiment_for_aggregation(
    filing: FilingSection,
    numeric_metrics: Optional[NumericMetrics] = None,
) -> tuple[float, float]:
    """Get SEC sentiment for aggregation in sentiment_sources.py.

    This function is designed to be called from the existing sentiment
    aggregation pipeline. It returns both the sentiment score and weight.

    Parameters
    ----------
    filing : FilingSection
        SEC filing to analyze
    numeric_metrics : NumericMetrics, optional
        Pre-extracted metrics

    Returns
    -------
    tuple[float, float]
        (sentiment_score, weight) where:
        - sentiment_score: -1.0 to +1.0
        - weight: configured weight for this source

    Examples
    --------
    Integration in sentiment_sources.py:

    >>> # After existing sentiment sources (VADER, FinBERT, etc.)
    >>> if sec_filing_data:
    ...     sec_score, sec_weight = get_sec_filing_sentiment_for_aggregation(
    ...         sec_filing_data
    ...     )
    ...     weighted_scores.append(sec_score * sec_weight)
    ...     total_weight += sec_weight
    """
    result = analyze_sec_filing_sentiment(filing, numeric_metrics)

    # Use weighted score (already adjusted for filing importance)
    # Return with configured weight from environment
    weight = get_sec_sentiment_weight()

    return result.weighted_score, weight


def is_sec_sentiment_enabled() -> bool:
    """Check if SEC sentiment analysis is enabled.

    Returns
    -------
    bool
        True if SEC sentiment should be included in aggregation
    """
    # Check if weight is > 0 and LLM is available
    weight = get_sec_sentiment_weight()
    return weight > 0.0
