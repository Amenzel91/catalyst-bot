"""Offering Sentiment Correction Module (Wave 3 - Data Quality Improvements).

This module addresses the critical misclassification of public offering news by
detecting the stage of the offering process and applying appropriate sentiment.

PROBLEM STATEMENT:
- "Closing of public offering" was incorrectly labeled as dilutive/bearish
- This confuses traders who see bearish alerts for actually positive news
- Offering completion means dilution is DONE (neutral or bullish)

SOLUTION:
Detect offering stage and assign proper sentiment:
- ANNOUNCEMENT: "announces offering" → Bearish (-0.6) - NEW dilution
- PRICING: "prices offering at $X" → Bearish (-0.5) - dilution confirmed
- UPSIZE: "upsizes offering" → Very Bearish (-0.7) - MORE dilution
- CLOSING: "closes offering" → Slightly Bullish (+0.2) - COMPLETION, anti-dilutive

This runs BEFORE general classification to override incorrect sentiment.
"""

from __future__ import annotations

import re
from typing import Optional, Tuple

from .logging_utils import get_logger

log = get_logger(__name__)

# Offering stage patterns (regex for flexible matching)
OFFERING_PATTERNS = {
    "closing": [
        r"closing\s+of.*?offering",
        r"closes.*?offering",
        r"closed.*?offering",
        r"completed.*?offering",
        r"announces?\s+the\s+closing",
        r"announced?\s+the\s+closing",
        r"completion\s+of.*?offering",
        r"consummation\s+of.*?offering",
        r"finalized.*?offering",
    ],
    "announcement": [
        r"announces?.*?offering",
        r"announced?.*?offering",
        r"files?.*?offering",
        r"filed.*?offering",
        r"intends?\s+to\s+offer",
        r"plans?\s+to\s+offer",
        r"proposes?.*?offering",
        r"proposed.*?offering",
        r"registr(?:ation|ing).*?offering",
        r"shelf.*?offering",
        r"preliminary.*?prospectus",
    ],
    "pricing": [
        r"prices?.*?offering\s+at",
        r"priced.*?offering",
        r"pricing\s+of.*?offering",
        r"offering\s+priced\s+at",
        r"sets?\s+price\s+at",
        r"per\s+share\s+in.*?offering",
    ],
    "upsize": [
        r"upsizes?.*?offering",
        r"upsized.*?offering",
        r"increases?.*?offering.*?size",
        r"increased.*?offering.*?size",
        r"expands?.*?offering",
        r"expanded.*?offering",
        r"enlarges?.*?offering",
    ],
}

# Sentiment scores by offering stage
# These override default classification sentiment
OFFERING_SENTIMENT = {
    "closing": 0.2,        # Slightly bullish - completion, no more dilution
    "announcement": -0.6,  # Bearish - new dilution coming
    "pricing": -0.5,       # Bearish - dilution confirmed at price
    "upsize": -0.7,        # Very bearish - MORE dilution than expected
}

# Confidence level for each stage detection
# Used to determine if we should override existing sentiment
OFFERING_CONFIDENCE = {
    "closing": 0.9,        # High confidence - very specific language
    "announcement": 0.85,  # High confidence - clear announcement
    "pricing": 0.9,        # High confidence - specific price action
    "upsize": 0.95,        # Very high confidence - explicit size increase
}

# Keywords that must be present to consider it an offering
OFFERING_KEYWORDS = [
    "offering",
    "offer",  # Catches "intends to offer", "plans to offer"
    "priced",
    "upsized",
    "shares",
    "public offering",
    "secondary offering",
    "registered direct",
    "shelf offering",
    "underwritten",
    "notes",
    "debt",
]

# Debt/notes offering indicators (NON-DILUTIVE - neutral to positive)
# These don't dilute equity shareholders
DEBT_OFFERING_KEYWORDS = [
    "notes offering",
    "note offering",
    "unsecured notes",
    "secured notes",
    "convertible notes",
    "debt offering",
    "bond offering",
    "senior notes",
    "subordinated notes",
    "institutional notes",
]


def is_offering_news(title: str, text: str = "") -> bool:
    """
    Check if news is about a public offering.

    This is a quick filter to avoid running expensive regex on non-offering news.

    Parameters
    ----------
    title : str
        News headline
    text : str, optional
        News body/description

    Returns
    -------
    bool
        True if news appears to be about an offering

    Examples
    --------
    >>> is_offering_news("Apple closes $50M public offering")
    True
    >>> is_offering_news("Apple releases new iPhone")
    False
    """
    combined = (title + " " + text).lower()

    # Check for at least one offering keyword
    return any(keyword in combined for keyword in OFFERING_KEYWORDS)


def is_debt_offering(title: str, text: str = "") -> bool:
    """
    Check if offering is debt/notes (non-dilutive) rather than equity.

    Debt offerings (bonds, notes) don't dilute existing shareholders and are
    often viewed neutrally or positively as they indicate access to capital
    without dilution.

    Parameters
    ----------
    title : str
        News headline
    text : str, optional
        News body/description

    Returns
    -------
    bool
        True if this appears to be a debt/notes offering (non-dilutive)

    Examples
    --------
    >>> is_debt_offering("PSEC prices $167M unsecured notes offering")
    True
    >>> is_debt_offering("POET closes $150M registered direct offering")
    False
    """
    combined = (title + " " + text).lower()

    # Check for debt offering indicators
    return any(keyword in combined for keyword in DEBT_OFFERING_KEYWORDS)


def detect_offering_stage(title: str, text: str = "") -> Optional[Tuple[str, float]]:
    """
    Detect which stage of offering process this news represents.

    Analyzes title and text to determine offering stage using pattern matching.
    Returns the stage and confidence score.

    Parameters
    ----------
    title : str
        News headline
    text : str, optional
        News body/description

    Returns
    -------
    tuple of (str, float) or None
        (stage_name, confidence) where stage is one of:
        - "closing": Offering completion
        - "announcement": New offering announcement
        - "pricing": Offering pricing
        - "upsize": Offering size increase
        Returns None if no offering detected

    Examples
    --------
    >>> detect_offering_stage("Company closes $50M public offering")
    ('closing', 0.9)
    >>> detect_offering_stage("Company announces $50M public offering")
    ('announcement', 0.85)
    >>> detect_offering_stage("Company prices offering at $10/share")
    ('pricing', 0.9)
    >>> detect_offering_stage("Company upsizes offering to $75M")
    ('upsize', 0.95)
    """
    # Quick filter: check if this is offering-related at all
    if not is_offering_news(title, text):
        return None

    combined = (title + " " + text).lower()

    # Check stages in priority order:
    # 1. Upsize (most specific - can occur with other stages)
    # 2. Closing (specific language, should override others)
    # 3. Pricing (specific action)
    # 4. Announcement (catch-all for new offerings)

    # Note: Order matters! Upsize can happen alongside pricing/closing
    # but we want to capture the upsize as primary signal

    stage_matches = {}

    for stage in ["upsize", "closing", "pricing", "announcement"]:
        for pattern in OFFERING_PATTERNS[stage]:
            if re.search(pattern, combined, re.IGNORECASE):
                # Track all matches with their confidence
                if stage not in stage_matches:
                    stage_matches[stage] = OFFERING_CONFIDENCE[stage]
                    log.debug(
                        "offering_stage_match stage=%s pattern=%s",
                        stage,
                        pattern[:30]
                    )

    # No matches found
    if not stage_matches:
        return None

    # Priority resolution when multiple stages detected:
    # - Upsize takes precedence (most material change)
    # - Then closing (most recent stage)
    # - Then pricing (more specific than announcement)
    # - Then announcement (general)
    priority_order = ["upsize", "closing", "pricing", "announcement"]

    for stage in priority_order:
        if stage in stage_matches:
            confidence = stage_matches[stage]
            log.info(
                "offering_stage_detected stage=%s confidence=%.2f all_matches=%s",
                stage,
                confidence,
                list(stage_matches.keys())
            )
            return stage, confidence

    return None


def get_offering_sentiment(stage: str) -> float:
    """
    Get sentiment score for an offering stage.

    Parameters
    ----------
    stage : str
        Offering stage: "closing", "announcement", "pricing", or "upsize"

    Returns
    -------
    float
        Sentiment score from -1.0 (bearish) to +1.0 (bullish)
        Default to -0.5 (bearish) if stage unknown

    Examples
    --------
    >>> get_offering_sentiment("closing")
    0.2
    >>> get_offering_sentiment("upsize")
    -0.7
    >>> get_offering_sentiment("unknown")
    -0.5
    """
    sentiment = OFFERING_SENTIMENT.get(stage, -0.5)
    log.debug("offering_sentiment_lookup stage=%s sentiment=%.2f", stage, sentiment)
    return sentiment


def apply_offering_sentiment_correction(
    title: str,
    text: str = "",
    current_sentiment: float = 0.0,
    min_confidence: float = 0.7,
) -> Tuple[float, Optional[str], bool]:
    """
    Apply offering sentiment correction if applicable.

    This is the main entry point for the offering sentiment correction system.
    It detects offering stage and overrides sentiment if confidence is high enough.

    Parameters
    ----------
    title : str
        News headline
    text : str, optional
        News body/description
    current_sentiment : float
        Current sentiment score from classification
    min_confidence : float
        Minimum confidence to override sentiment (default: 0.7)

    Returns
    -------
    tuple of (float, str or None, bool)
        (corrected_sentiment, offering_stage, was_corrected)
        - corrected_sentiment: New sentiment if correction applied, else current
        - offering_stage: Detected stage name or None
        - was_corrected: True if sentiment was overridden

    Examples
    --------
    >>> apply_offering_sentiment_correction(
    ...     "Company closes $50M offering",
    ...     current_sentiment=-0.5
    ... )
    (0.2, 'closing', True)

    >>> apply_offering_sentiment_correction(
    ...     "Apple releases new iPhone",
    ...     current_sentiment=0.3
    ... )
    (0.3, None, False)
    """
    # FIRST: Check if this is a debt/notes offering (non-dilutive)
    # Debt offerings don't dilute equity and should be treated neutrally or positively
    if is_debt_offering(title, text):
        log.info(
            "debt_offering_detected treating_as_neutral_or_positive "
            "prev_sentiment=%.3f new_sentiment=0.3",
            current_sentiment
        )
        # Debt offerings are neutral to slightly positive (access to capital, no dilution)
        # Return with a "debt" stage marker and high confidence
        return 0.3, "debt", True

    # Detect offering stage
    detection = detect_offering_stage(title, text)

    if not detection:
        # Not an offering or couldn't detect stage
        return current_sentiment, None, False

    stage, confidence = detection

    # Check if confidence is high enough to override
    if confidence < min_confidence:
        log.debug(
            "offering_correction_skipped stage=%s confidence=%.2f min=%.2f",
            stage,
            confidence,
            min_confidence
        )
        return current_sentiment, stage, False

    # Get offering-specific sentiment
    offering_sentiment = get_offering_sentiment(stage)

    # Calculate sentiment difference
    sentiment_diff = offering_sentiment - current_sentiment

    log.info(
        "offering_sentiment_correction_applied "
        "stage=%s prev_sentiment=%.3f new_sentiment=%.3f diff=%.3f confidence=%.2f",
        stage,
        current_sentiment,
        offering_sentiment,
        sentiment_diff,
        confidence
    )

    return offering_sentiment, stage, True


def get_offering_stage_label(stage: Optional[str]) -> str:
    """
    Get human-readable label for offering stage.

    Used for badge display and logging.

    Parameters
    ----------
    stage : str or None
        Offering stage identifier

    Returns
    -------
    str
        Human-readable stage label

    Examples
    --------
    >>> get_offering_stage_label("closing")
    'CLOSING'
    >>> get_offering_stage_label("upsize")
    'UPSIZED'
    >>> get_offering_stage_label(None)
    'OFFERING'
    """
    stage_labels = {
        "closing": "CLOSING",
        "announcement": "ANNOUNCED",
        "pricing": "PRICED",
        "upsize": "UPSIZED",
        "debt": "DEBT OFFERING",
    }

    if stage in stage_labels:
        return stage_labels[stage]

    return "OFFERING"


def get_offering_emoji(stage: Optional[str]) -> str:
    """
    Get emoji for offering stage visualization.

    Used for Discord badge display.

    Parameters
    ----------
    stage : str or None
        Offering stage identifier

    Returns
    -------
    str
        Emoji representing the stage

    Examples
    --------
    >>> get_offering_emoji("closing")
    '✅'
    >>> get_offering_emoji("upsize")
    '📉'
    >>> get_offering_emoji("announcement")
    '💰'
    """
    stage_emojis = {
        "closing": "✅",      # Checkmark - completion (positive)
        "announcement": "💰", # Money bag - new offering (neutral/negative)
        "pricing": "💵",      # Dollar bill - pricing action (negative)
        "upsize": "📉",       # Down chart - more dilution (very negative)
        "debt": "📄",         # Document - debt/notes (neutral/positive, no dilution)
    }

    return stage_emojis.get(stage, "💰")
