"""Short interest sentiment amplification module.

This module implements squeeze potential detection and sentiment amplification
based on short interest data. High short interest + bullish catalyst = potential
short squeeze, which amplifies positive sentiment.

Squeeze Multiplier Logic:
------------------------
The multiplier only applies to POSITIVE sentiment (bullish catalysts):
- If short_interest > 20% AND base_sentiment > 0.5: 1.3x boost (30%)
- If short_interest > 30% AND base_sentiment > 0.6: 1.5x boost (50%)
- If short_interest > 40% AND base_sentiment > 0.7: 1.7x boost (70%)

Rationale:
----------
High short interest indicates significant bearish positioning. When a bullish
catalyst emerges, shorts may be forced to cover, amplifying upward price movement.
This is particularly relevant for low-float stocks where short covering can trigger
explosive moves (e.g., GME 2021, AMC 2021).

IMPORTANT: We do NOT amplify negative sentiment. High SI can also mean the market
is correctly pricing in company troubles, so we avoid penalizing negative news.

Feature Flag:
-------------
Enable/disable with environment variable:
    FEATURE_SHORT_INTEREST_BOOST=1  # Enable (default)
    FEATURE_SHORT_INTEREST_BOOST=0  # Disable

Data Source:
------------
Short interest is sourced from FinViz scraping (free, no API required) via the
float_data.py module. Data is cached for 24 hours since SI updates weekly.

Usage:
------
    >>> from catalyst_bot.short_interest_sentiment import calculate_si_sentiment
    >>> si_sentiment, metadata = calculate_si_sentiment(
    ...     ticker="GME",
    ...     base_sentiment=0.65,
    ...     short_interest_pct=25.0
    ... )
    >>> print(f"Amplified sentiment: {si_sentiment:.3f}")
    >>> print(f"Squeeze multiplier: {metadata['squeeze_multiplier']:.2f}x")
"""

from __future__ import annotations

import os
from typing import Optional, Tuple

from .logging_utils import get_logger

log = get_logger("short_interest_sentiment")

# Short interest thresholds (percentage)
SI_THRESHOLD_LEVEL_1 = 20.0  # High short interest
SI_THRESHOLD_LEVEL_2 = 30.0  # Very high short interest
SI_THRESHOLD_LEVEL_3 = 40.0  # Extreme short interest

# Sentiment thresholds (0.0 to 1.0)
SENTIMENT_THRESHOLD_LEVEL_1 = 0.5  # Moderately bullish
SENTIMENT_THRESHOLD_LEVEL_2 = 0.6  # Strongly bullish
SENTIMENT_THRESHOLD_LEVEL_3 = 0.7  # Very strongly bullish

# Squeeze multipliers
MULTIPLIER_LEVEL_1 = 1.3  # 30% boost
MULTIPLIER_LEVEL_2 = 1.5  # 50% boost
MULTIPLIER_LEVEL_3 = 1.7  # 70% boost


def calculate_squeeze_multiplier(
    short_interest_pct: float,
    base_sentiment: float,
) -> Tuple[float, str]:
    """Calculate squeeze multiplier based on short interest and sentiment.

    The multiplier is applied to sentiment to amplify bullish signals when
    short interest is high. Higher SI + stronger sentiment = higher multiplier.

    Args:
        short_interest_pct: Short interest as percentage (e.g., 25.5 for 25.5%)
        base_sentiment: Base sentiment score (-1.0 to +1.0)

    Returns:
        Tuple of (multiplier, reason_string)
        - multiplier: 1.0 (no boost) to 1.7 (max boost)
        - reason: Human-readable explanation

    Examples:
        >>> calculate_squeeze_multiplier(25.0, 0.65)
        (1.3, "high_si_bullish_catalyst")

        >>> calculate_squeeze_multiplier(35.0, 0.75)
        (1.5, "very_high_si_strong_catalyst")

        >>> calculate_squeeze_multiplier(25.0, 0.3)
        (1.0, "si_high_but_sentiment_weak")

        >>> calculate_squeeze_multiplier(8.0, 0.7)
        (1.0, "si_too_low")
    """
    # Only boost positive sentiment (squeeze potential)
    if base_sentiment <= 0:
        return 1.0, "negative_sentiment_no_boost"

    # Level 3: Extreme SI + Very strong bullish sentiment
    if short_interest_pct >= SI_THRESHOLD_LEVEL_3 and base_sentiment >= SENTIMENT_THRESHOLD_LEVEL_3:
        return MULTIPLIER_LEVEL_3, "extreme_si_very_strong_catalyst"

    # Level 2: Very high SI + Strong bullish sentiment
    if short_interest_pct >= SI_THRESHOLD_LEVEL_2 and base_sentiment >= SENTIMENT_THRESHOLD_LEVEL_2:
        return MULTIPLIER_LEVEL_2, "very_high_si_strong_catalyst"

    # Level 1: High SI + Moderate bullish sentiment
    if short_interest_pct >= SI_THRESHOLD_LEVEL_1 and base_sentiment >= SENTIMENT_THRESHOLD_LEVEL_1:
        return MULTIPLIER_LEVEL_1, "high_si_bullish_catalyst"

    # No boost if thresholds not met
    if short_interest_pct >= SI_THRESHOLD_LEVEL_1:
        return 1.0, "si_high_but_sentiment_weak"
    elif base_sentiment >= SENTIMENT_THRESHOLD_LEVEL_1:
        return 1.0, "sentiment_bullish_but_si_low"
    else:
        return 1.0, "no_squeeze_potential"


def calculate_si_sentiment(
    ticker: str,
    base_sentiment: float,
    short_interest_pct: Optional[float] = None,
) -> Tuple[float, dict]:
    """Calculate sentiment boost from short interest squeeze potential.

    This function amplifies positive sentiment when high short interest creates
    squeeze potential. It fetches short interest data if not provided and applies
    the appropriate multiplier based on SI and sentiment levels.

    Args:
        ticker: Stock ticker symbol
        base_sentiment: Base sentiment score (-1.0 to +1.0)
        short_interest_pct: Optional SI percentage (fetched if not provided)

    Returns:
        Tuple of (sentiment_contribution, metadata_dict)
        - sentiment_contribution: Weighted sentiment value for aggregation
        - metadata_dict: Contains detailed scoring breakdown

    Examples:
        >>> sentiment, meta = calculate_si_sentiment("GME", 0.65, 25.0)
        >>> print(f"Contribution: {sentiment:.3f}")
        >>> print(f"Multiplier: {meta['squeeze_multiplier']:.2f}x")
        >>> print(f"Squeeze potential: {meta['squeeze_potential']}")
    """
    # Check feature flag
    if not os.getenv("FEATURE_SHORT_INTEREST_BOOST", "1") == "1":
        return 0.0, {"enabled": False, "reason": "feature_disabled"}

    if not ticker or not ticker.strip():
        return 0.0, {"enabled": True, "reason": "invalid_ticker"}

    # Fetch short interest if not provided
    if short_interest_pct is None:
        try:
            from .float_data import get_float_data

            float_data = get_float_data(ticker)
            short_interest_pct = float_data.get("short_interest_pct")
        except Exception as e:
            log.warning(
                "si_data_fetch_failed ticker=%s error=%s",
                ticker,
                e.__class__.__name__,
            )
            return 0.0, {
                "enabled": True,
                "reason": "fetch_error",
                "error": str(e),
            }

    # Initialize metadata
    metadata = {
        "enabled": True,
        "ticker": ticker.upper(),
        "short_interest_pct": short_interest_pct,
        "base_sentiment": base_sentiment,
        "squeeze_multiplier": 1.0,
        "squeeze_potential": "NONE",
        "squeeze_reason": None,
    }

    # Return neutral if no SI data available
    if short_interest_pct is None:
        metadata["reason"] = "si_data_unavailable"
        log.debug("si_sentiment_unavailable ticker=%s reason=no_data", ticker)
        return 0.0, metadata

    # Calculate squeeze multiplier
    multiplier, reason = calculate_squeeze_multiplier(short_interest_pct, base_sentiment)

    metadata["squeeze_multiplier"] = multiplier
    metadata["squeeze_reason"] = reason

    # Classify squeeze potential
    if multiplier >= MULTIPLIER_LEVEL_3:
        metadata["squeeze_potential"] = "EXTREME"
    elif multiplier >= MULTIPLIER_LEVEL_2:
        metadata["squeeze_potential"] = "HIGH"
    elif multiplier >= MULTIPLIER_LEVEL_1:
        metadata["squeeze_potential"] = "MODERATE"
    else:
        metadata["squeeze_potential"] = "LOW"

    # Calculate amplified sentiment
    # We return the BOOST amount (amplified - base) as the sentiment contribution
    # This allows the aggregator to properly weight this signal
    amplified_sentiment = base_sentiment * multiplier
    sentiment_boost = amplified_sentiment - base_sentiment

    # Log when significant boost occurs
    if multiplier > 1.0:
        log.info(
            "si_sentiment_boost ticker=%s si_pct=%.2f base_sentiment=%.3f "
            "multiplier=%.2f amplified_sentiment=%.3f boost=%.3f potential=%s",
            ticker,
            short_interest_pct,
            base_sentiment,
            multiplier,
            amplified_sentiment,
            sentiment_boost,
            metadata["squeeze_potential"],
        )
    else:
        log.debug(
            "si_sentiment_no_boost ticker=%s si_pct=%.2f base_sentiment=%.3f reason=%s",
            ticker,
            short_interest_pct or 0.0,
            base_sentiment,
            reason,
        )

    # Return the boost as the sentiment contribution
    # Weight is applied by the aggregator (default: 0.08 as specified)
    return sentiment_boost, metadata


def is_short_interest_boost_enabled() -> bool:
    """Check if short interest sentiment boost is enabled via feature flag.

    Returns:
        True if FEATURE_SHORT_INTEREST_BOOST=1, False otherwise
    """
    return os.getenv("FEATURE_SHORT_INTEREST_BOOST", "1") == "1"


# Public API
__all__ = [
    "calculate_si_sentiment",
    "calculate_squeeze_multiplier",
    "is_short_interest_boost_enabled",
]
