"""Forward guidance extractor for earnings filings.

This module detects and extracts forward-looking statements from SEC filings,
particularly earnings releases (8-K Item 2.02) and quarterly reports (10-Q).

Forward guidance includes:
- Revenue projections ("expect Q2 revenue of $150M-$175M")
- EPS forecasts ("anticipate full-year EPS of $2.50-$2.75")
- Margin expectations ("targeting 45% gross margin")
- Qualitative guidance ("expect strong growth in H2")

The module identifies guidance that was:
- RAISED (increased from prior guidance)
- LOWERED (decreased from prior guidance)
- MAINTAINED (reaffirmed existing guidance)
- NEW (first-time guidance provided)

References:
- SEC Guidance on Forward-Looking Statements: https://www.sec.gov/rules/interp/33-8350.htm
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

try:
    from .logging_utils import get_logger
    from .numeric_extractor import GuidanceRange
except Exception:
    import logging

    logging.basicConfig(level=logging.INFO)

    def get_logger(_):
        return logging.getLogger("guidance_extractor")


log = get_logger("guidance_extractor")


@dataclass
class ForwardGuidance:
    """Structured forward guidance data."""

    guidance_type: str  # revenue, eps, margin, qualitative
    metric: str  # "Q2 2025 revenue", "FY2025 EPS", etc.
    value_text: str  # "$150M-$175M", "strong growth", etc.
    temporal_scope: str  # Q1 2025, FY2025, H2 2025, etc.
    change_direction: str  # raised, lowered, maintained, new
    confidence_level: str  # strong, moderate, uncertain
    source_text: str  # Original text snippet


@dataclass
class GuidanceAnalysis:
    """Complete guidance analysis output."""

    has_guidance: bool
    guidance_items: list[ForwardGuidance]
    overall_direction: str  # positive, negative, mixed, neutral
    summary: str  # Human-readable summary


# ============================================================================
# Detection Patterns
# ============================================================================

# Guidance trigger phrases
GUIDANCE_TRIGGERS = [
    "expect",
    "anticipate",
    "forecast",
    "project",
    "outlook",
    "guidance",
    "target",
    "estimate",
    "believe",
    "plan to",
    "intend to",
]

# Change direction indicators
RAISED_INDICATORS = [
    "rais",
    "increas",
    "upward",
    "higher",
    "improv",
    "stronger",
    "better than",
    "exceed",
    "above",
]

LOWERED_INDICATORS = [
    "lower",
    "reduc",
    "downward",
    "decreas",
    "weaker",
    "below",
    "under",
    "miss",
]

MAINTAINED_INDICATORS = [
    "reaffirm",
    "maintain",
    "reiterat",
    "confirm",
    "unchanged",
    "consistent",
]

# Temporal scope patterns
TEMPORAL_PATTERNS = [
    re.compile(r"(Q[1-4]\s+\d{4})", re.IGNORECASE),  # Q1 2025
    re.compile(r"(FY\s*\d{4})", re.IGNORECASE),  # FY2025
    re.compile(r"(fiscal year\s+\d{4})", re.IGNORECASE),  # fiscal year 2025
    re.compile(r"(H[12]\s+\d{4})", re.IGNORECASE),  # H1 2025, H2 2025
    re.compile(r"(full[- ]year)", re.IGNORECASE),  # full-year
    re.compile(r"(next quarter)", re.IGNORECASE),
    re.compile(r"(remainder of (?:the )?year)", re.IGNORECASE),
]

# Confidence indicators
STRONG_CONFIDENCE = ["confident", "expect", "will", "committed to"]
MODERATE_CONFIDENCE = ["anticipate", "believe", "plan to", "target"]
UNCERTAIN_CONFIDENCE = ["may", "could", "possible", "potential", "subject to"]


# ============================================================================
# Extraction Functions
# ============================================================================


def extract_forward_guidance(filing_text: str, filing_type: str = "8-K") -> GuidanceAnalysis:
    """Extract forward guidance from SEC filing.

    Parameters
    ----------
    filing_text : str
        SEC filing text (focus on Item 2.02 for 8-K)
    filing_type : str
        "8-K", "10-Q", or "10-K"

    Returns
    -------
    GuidanceAnalysis
        Structured guidance with all detected items

    Examples
    --------
    >>> text = "We expect Q2 2025 revenue of $150M-$175M, up from prior guidance of $140M-$160M"
    >>> analysis = extract_forward_guidance(text)
    >>> analysis.has_guidance
    True
    >>> analysis.overall_direction
    'positive'
    """
    guidance_items = []

    # Split into sentences for analysis
    sentences = _split_into_sentences(filing_text)

    for sentence in sentences:
        # Check if sentence contains guidance trigger
        if not _contains_guidance_trigger(sentence):
            continue

        # Extract guidance from this sentence
        guidance = _extract_guidance_from_sentence(sentence)
        if guidance:
            guidance_items.append(guidance)

    # Determine overall direction
    overall_direction = _determine_overall_direction(guidance_items)

    # Generate summary
    summary = _generate_guidance_summary(guidance_items, overall_direction)

    log.info(f"Extracted {len(guidance_items)} guidance items, direction={overall_direction}")

    return GuidanceAnalysis(
        has_guidance=len(guidance_items) > 0,
        guidance_items=guidance_items,
        overall_direction=overall_direction,
        summary=summary,
    )


def is_earnings_filing(filing_text: str, filing_type: str) -> bool:
    """Determine if filing is an earnings-related filing.

    Parameters
    ----------
    filing_text : str
        Filing text
    filing_type : str
        Filing type (8-K, 10-Q, 10-K)

    Returns
    -------
    bool
        True if earnings-related
    """
    if filing_type in ("10-Q", "10-K"):
        return True

    # For 8-K, check if Item 2.02 (earnings) is present
    if filing_type == "8-K":
        item_202_pattern = re.compile(r"Item\s+2\.02", re.IGNORECASE)
        return bool(item_202_pattern.search(filing_text))

    return False


def _split_into_sentences(text: str) -> list[str]:
    """Split text into sentences."""
    # Simple sentence splitting (could be improved with NLP)
    sentences = re.split(r"[.!?]\s+", text)
    # Filter out very short sentences
    return [s.strip() for s in sentences if len(s.strip()) > 20]


def _contains_guidance_trigger(sentence: str) -> bool:
    """Check if sentence contains guidance trigger phrase."""
    sentence_lower = sentence.lower()
    return any(trigger in sentence_lower for trigger in GUIDANCE_TRIGGERS)


def _extract_guidance_from_sentence(sentence: str) -> Optional[ForwardGuidance]:
    """Extract guidance information from a single sentence."""
    sentence_lower = sentence.lower()

    # Determine guidance type
    if "revenue" in sentence_lower or "sales" in sentence_lower:
        guidance_type = "revenue"
        metric = "revenue"
    elif "eps" in sentence_lower or "earnings per share" in sentence_lower:
        guidance_type = "eps"
        metric = "EPS"
    elif "margin" in sentence_lower:
        guidance_type = "margin"
        metric = "margin"
    elif "income" in sentence_lower or "profit" in sentence_lower:
        guidance_type = "income"
        metric = "income"
    else:
        guidance_type = "qualitative"
        metric = "business outlook"

    # Extract temporal scope
    temporal_scope = _extract_temporal_scope(sentence)

    # Extract value (if quantitative)
    value_text = _extract_value_text(sentence, guidance_type)

    # Determine change direction
    change_direction = _determine_change_direction(sentence_lower)

    # Determine confidence level
    confidence_level = _determine_confidence_level(sentence_lower)

    return ForwardGuidance(
        guidance_type=guidance_type,
        metric=f"{temporal_scope} {metric}" if temporal_scope else metric,
        value_text=value_text,
        temporal_scope=temporal_scope or "unspecified",
        change_direction=change_direction,
        confidence_level=confidence_level,
        source_text=sentence[:200],  # Truncate for storage
    )


def _extract_temporal_scope(sentence: str) -> Optional[str]:
    """Extract temporal scope from sentence."""
    for pattern in TEMPORAL_PATTERNS:
        match = pattern.search(sentence)
        if match:
            return match.group(1)
    return None


def _extract_value_text(sentence: str, guidance_type: str) -> str:
    """Extract the value/range from guidance sentence."""
    # Look for dollar amounts
    dollar_pattern = re.compile(r"\$\s*[\d.]+\s*(?:million|billion|M|B)?(?:\s*(?:to|-)\s*\$\s*[\d.]+\s*(?:million|billion|M|B)?)?", re.IGNORECASE)
    dollar_match = dollar_pattern.search(sentence)
    if dollar_match:
        return dollar_match.group(0)

    # Look for percentage
    pct_pattern = re.compile(r"\d+(?:\.\d+)?%(?:\s*(?:to|-)\s*\d+(?:\.\d+)?%)?")
    pct_match = pct_pattern.search(sentence)
    if pct_match:
        return pct_match.group(0)

    # Look for EPS values
    eps_pattern = re.compile(r"\$\s*\d+\.\d+(?:\s*(?:to|-)\s*\$\s*\d+\.\d+)?\s*per share", re.IGNORECASE)
    eps_match = eps_pattern.search(sentence)
    if eps_match:
        return eps_match.group(0)

    # Qualitative if no numbers found
    qualitative_terms = ["strong", "weak", "robust", "solid", "challenging", "improved", "growth"]
    for term in qualitative_terms:
        if term in sentence.lower():
            return term

    return "unspecified"


def _determine_change_direction(sentence_lower: str) -> str:
    """Determine if guidance was raised, lowered, maintained, or new."""
    # Check for raised indicators
    if any(indicator in sentence_lower for indicator in RAISED_INDICATORS):
        return "raised"

    # Check for lowered indicators
    if any(indicator in sentence_lower for indicator in LOWERED_INDICATORS):
        return "lowered"

    # Check for maintained indicators
    if any(indicator in sentence_lower for indicator in MAINTAINED_INDICATORS):
        return "maintained"

    # Default to "new" if no change indicators found
    return "new"


def _determine_confidence_level(sentence_lower: str) -> str:
    """Determine confidence level of guidance."""
    if any(term in sentence_lower for term in UNCERTAIN_CONFIDENCE):
        return "uncertain"

    if any(term in sentence_lower for term in STRONG_CONFIDENCE):
        return "strong"

    return "moderate"


def _determine_overall_direction(guidance_items: list[ForwardGuidance]) -> str:
    """Determine overall direction from multiple guidance items."""
    if not guidance_items:
        return "neutral"

    raised_count = sum(1 for g in guidance_items if g.change_direction == "raised")
    lowered_count = sum(1 for g in guidance_items if g.change_direction == "lowered")

    if raised_count > lowered_count and raised_count > 0:
        return "positive"
    elif lowered_count > raised_count and lowered_count > 0:
        return "negative"
    elif raised_count == lowered_count and raised_count > 0:
        return "mixed"
    else:
        return "neutral"


def _generate_guidance_summary(guidance_items: list[ForwardGuidance], overall_direction: str) -> str:
    """Generate human-readable guidance summary."""
    if not guidance_items:
        return "No forward guidance provided"

    # Count by type
    raised = sum(1 for g in guidance_items if g.change_direction == "raised")
    lowered = sum(1 for g in guidance_items if g.change_direction == "lowered")
    maintained = sum(1 for g in guidance_items if g.change_direction == "maintained")
    new = sum(1 for g in guidance_items if g.change_direction == "new")

    parts = []
    if raised > 0:
        parts.append(f"{raised} raised")
    if lowered > 0:
        parts.append(f"{lowered} lowered")
    if maintained > 0:
        parts.append(f"{maintained} maintained")
    if new > 0:
        parts.append(f"{new} new")

    summary = f"Guidance: {', '.join(parts)}. Overall direction: {overall_direction}."

    # Add specific metrics
    metrics = [g.metric for g in guidance_items[:3]]  # Top 3
    if metrics:
        summary += f" Covers: {', '.join(metrics)}."

    return summary


# ============================================================================
# Convenience Functions
# ============================================================================


def has_raised_guidance(filing_text: str) -> bool:
    """Quick check if filing contains raised guidance.

    Parameters
    ----------
    filing_text : str
        Filing text

    Returns
    -------
    bool
        True if any guidance was raised
    """
    analysis = extract_forward_guidance(filing_text)
    return any(g.change_direction == "raised" for g in analysis.guidance_items)


def has_lowered_guidance(filing_text: str) -> bool:
    """Quick check if filing contains lowered guidance.

    Parameters
    ----------
    filing_text : str
        Filing text

    Returns
    -------
    bool
        True if any guidance was lowered
    """
    analysis = extract_forward_guidance(filing_text)
    return any(g.change_direction == "lowered" for g in analysis.guidance_items)
