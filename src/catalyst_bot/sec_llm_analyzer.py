"""
SEC Filing LLM Analyzer
========================

Uses local LLM (Ollama/Mistral) to analyze SEC filings and extract:
- Deal size and terms
- Dilution risk
- Warrant coverage
- Overall sentiment (-1 to +1)
- Key catalysts

Designed to work with 8-K, 424B5, FWP, and other material filings.
"""

from __future__ import annotations

import os
import re
from typing import Any, Dict, Optional

from .llm_client import query_llm
from .logging_utils import get_logger

log = get_logger("sec_llm_analyzer")


def _extract_amount(text: str) -> Optional[float]:
    """Extract dollar amount from text (e.g., '$5.2 million' -> 5200000)."""
    if not text:
        return None

    # Match patterns like "$5.2M", "$10 million", "5.2MM"
    patterns = [
        r"\$?(\d+\.?\d*)\s*million",
        r"\$?(\d+\.?\d*)\s*M(?:M)?(?!\w)",
        r"\$(\d+,?\d*,?\d*)",
    ]

    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            value_str = match.group(1).replace(",", "")
            try:
                value = float(value_str)
                if "million" in pattern or "M" in pattern:
                    return value * 1_000_000
                return value
            except ValueError:
                continue

    return None


def analyze_sec_filing(
    title: str,
    filing_type: str,
    summary: Optional[str] = None,
    timeout: float = 20.0,
) -> Dict[str, Any]:
    """
    Analyze SEC filing using LLM.

    Parameters
    ----------
    title : str
        Filing title/headline
    filing_type : str
        Type of filing (e.g., '8-K', '424B5', 'FWP')
    summary : str, optional
        Optional filing summary or first paragraph
    timeout : float
        LLM query timeout in seconds

    Returns
    -------
    dict
        Analysis results with keys:
        - llm_sentiment: float (-1 to +1)
        - llm_confidence: float (0 to 1)
        - deal_size_usd: float or None
        - dilution_pct: float or None
        - has_warrants: bool
        - catalysts: list of str
        - summary: str (LLM-generated summary)
        - risk_level: str ('low', 'medium', 'high')
    """
    # Check if LLM is enabled
    if not os.getenv("FEATURE_LLM_CLASSIFIER", "0") in ("1", "true", "yes", "on"):
        log.debug("llm_disabled skipping_sec_analysis")
        return {}

    # Build context-aware prompt
    filing_context = f"Filing Type: {filing_type}\nTitle: {title}"
    if summary:
        filing_context += f"\nSummary: {summary[:500]}"  # Limit to 500 chars

    system_prompt = """You are a financial analyst specializing in SEC filings for penny stocks.
Analyze the filing and respond with a JSON object containing:
{
  "sentiment": <float from -1 (very bearish) to +1 (very bullish)>,
  "confidence": <float from 0 to 1>,
  "deal_size": "<amount with unit, e.g., '$5.2 million' or 'N/A'>",
  "dilution": "<estimated dilution percentage or 'N/A'>",
  "has_warrants": <true/false>,
  "catalysts": [<list of key catalysts like "capital raise", "debt conversion", etc.>],
  "summary": "<1-2 sentence summary>",
  "risk_level": "<'low', 'medium', or 'high'>"
}

Key factors:
- 424B5/FWP: Usually offerings (dilutive, bearish unless priced well)
- 8-K Item 1.01: Material agreements (context-dependent)
- 8-K Item 2.02: Earnings (positive if beats, negative if misses)
- 8-K Item 8.01: General updates (neutral to positive)
- Warrants/convertibles: Dilution risk (bearish)
- Large deal size relative to market cap: Higher dilution (bearish)
- Institutional investment: Bullish signal
"""

    user_prompt = f"""Analyze this SEC filing:

{filing_context}

Respond ONLY with valid JSON. No additional text."""

    try:
        response = query_llm(
            prompt=user_prompt,
            system=system_prompt,
            timeout=timeout,
        )

        if not response:
            log.warning("llm_no_response filing_type=%s", filing_type)
            return {}

        # Parse JSON response
        import json

        # Try to extract JSON from response
        json_match = re.search(r"\{.*\}", response, re.DOTALL)
        if json_match:
            response = json_match.group(0)

        analysis = json.loads(response)

        # Normalize and validate
        result = {
            "llm_sentiment": float(analysis.get("sentiment", 0.0)),
            "llm_confidence": float(analysis.get("confidence", 0.5)),
            "deal_size_str": str(analysis.get("deal_size", "N/A")),
            "dilution_str": str(analysis.get("dilution", "N/A")),
            "has_warrants": bool(analysis.get("has_warrants", False)),
            "catalysts": list(analysis.get("catalysts", [])),
            "summary": str(analysis.get("summary", "")),
            "risk_level": str(analysis.get("risk_level", "medium")),
        }

        # Extract numeric values
        result["deal_size_usd"] = _extract_amount(result["deal_size_str"])

        dilution_match = re.search(r"(\d+\.?\d*)%?", result["dilution_str"])
        if dilution_match:
            try:
                result["dilution_pct"] = float(dilution_match.group(1))
            except ValueError:
                result["dilution_pct"] = None
        else:
            result["dilution_pct"] = None

        log.info(
            f"sec_analysis_complete filing={filing_type} "
            f"sentiment={result['llm_sentiment']:.2f} "
            f"risk={result['risk_level']}"
        )

        return result

    except json.JSONDecodeError as e:
        log.warning(f"llm_json_parse_failed filing={filing_type} err={e}")
        return {}
    except Exception as e:
        log.error(f"sec_analysis_failed filing={filing_type} err={e}")
        return {}


def enhance_classification_with_llm(
    title: str,
    current_score: float,
    current_confidence: float,
    keywords: list[str],
    source: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Use LLM to enhance classification when keyword scanner has low confidence.

    Parameters
    ----------
    title : str
        News headline
    current_score : float
        Current aggregate score
    current_confidence : float
        Confidence level (0-1)
    keywords : list of str
        Keywords detected by scanner
    source : str, optional
        Source of the news

    Returns
    -------
    dict
        Enhanced classification with:
        - llm_sentiment: float
        - llm_tags: list of str
        - llm_confidence: float
        - should_boost: bool (True if LLM recommends alerting)
    """
    # Only invoke LLM for low-confidence items
    confidence_threshold = float(os.getenv("LLM_CONFIDENCE_THRESHOLD", "0.6"))

    if current_confidence >= confidence_threshold:
        return {}

    if not os.getenv("FEATURE_LLM_FALLBACK", "0") in ("1", "true", "yes", "on"):
        return {}

    system_prompt = """You are a trading catalyst detector for penny stocks.
Analyze the headline and determine if it represents a meaningful trading catalyst.

Respond with JSON:
{
  "is_catalyst": <true/false>,
  "sentiment": <-1 to +1>,
  "confidence": <0 to 1>,
  "catalysts": [<list of catalyst types>],
  "reason": "<brief explanation>"
}

Catalyst types: earnings, fda, merger, acquisition, partnership, contract,
upgrade, downgrade, insider_buying, short_squeeze, dilution, bankruptcy, halt"""

    user_prompt = f"""Headline: {title}
Keywords detected: {', '.join(keywords) if keywords else 'None'}
Source: {source or 'Unknown'}

Is this a meaningful catalyst? Respond with JSON only."""

    try:
        response = query_llm(
            prompt=user_prompt,
            system=system_prompt,
            timeout=15.0,
        )

        if not response:
            return {}

        import json

        json_match = re.search(r"\{.*\}", response, re.DOTALL)
        if json_match:
            response = json_match.group(0)

        analysis = json.loads(response)

        result = {
            "llm_sentiment": float(analysis.get("sentiment", 0.0)),
            "llm_tags": list(analysis.get("catalysts", [])),
            "llm_confidence": float(analysis.get("confidence", 0.5)),
            "should_boost": bool(analysis.get("is_catalyst", False)),
            "llm_reason": str(analysis.get("reason", "")),
        }

        if result["should_boost"]:
            log.info(
                f"llm_boost_recommended title='{title[:50]}...' "
                f"sentiment={result['llm_sentiment']:.2f}"
            )

        return result

    except Exception as e:
        log.debug(f"llm_fallback_failed err={e}")
        return {}


def should_use_llm_for_filing(filing_type: str) -> bool:
    """Check if LLM analysis should be used for this filing type."""
    # High-value filings that benefit from LLM analysis
    llm_worthy_filings = {
        "8-K",
        "424B5",  # Prospectus supplement (offerings)
        "FWP",  # Free writing prospectus
        "13D",  # Beneficial ownership (5%+)
        "13G",  # Passive ownership
        "SC 13D",
        "SC 13G",
    }

    return filing_type.upper() in llm_worthy_filings
