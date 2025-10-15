"""Fundamental data scoring for catalyst classification.

This module integrates float shares and short interest data into the
classification scoring system. Research shows float shares is 4.2x stronger
volatility predictor than other factors, and short interest >15% indicates
squeeze potential.

Scoring Logic:
--------------
Float Shares:
- Very low float (<10M shares): HIGH boost (+0.3 to +0.5)
- Low float (10M-50M): Medium boost (+0.1 to +0.3)
- Medium float (50M-100M): Neutral to small boost (0 to +0.1)
- High float (>100M): Neutral or slight penalty (0 to -0.1)

Short Interest:
- Very high SI (>20%): HIGH boost (+0.3 to +0.5)
- High SI (15-20%): Medium boost (+0.2 to +0.3)
- Moderate SI (10-15%): Small boost (+0.1 to +0.2)
- Low SI (<10%): Neutral (0)

Feature Flag:
-------------
Enable/disable with environment variable:
    FEATURE_FUNDAMENTAL_SCORING=1  # Enable
    FEATURE_FUNDAMENTAL_SCORING=0  # Disable (default)

Usage:
------
    >>> from catalyst_bot.fundamental_scoring import calculate_fundamental_score
    >>> score, metadata = calculate_fundamental_score("AAPL")
    >>> if score > 0:
    >>>     print(f"Fundamental boost: +{score:.2f}")
"""

from __future__ import annotations

import os
from typing import Optional, Tuple

from .fundamental_data import get_fundamentals
from .logging_utils import get_logger

log = get_logger("fundamental_scoring")

# Scoring thresholds (in shares)
FLOAT_VERY_LOW = 10_000_000  # 10M
FLOAT_LOW = 50_000_000  # 50M
FLOAT_MEDIUM = 100_000_000  # 100M

# Short interest thresholds (percentage)
SI_MODERATE = 10.0
SI_HIGH = 15.0
SI_VERY_HIGH = 20.0

# Score boosts
FLOAT_VERY_LOW_BOOST = 0.5
FLOAT_LOW_BOOST = 0.3
FLOAT_MEDIUM_BOOST = 0.1
FLOAT_HIGH_PENALTY = -0.1

SI_VERY_HIGH_BOOST = 0.5
SI_HIGH_BOOST = 0.3
SI_MODERATE_BOOST = 0.15


def score_float_shares(float_shares: float) -> Tuple[float, str]:
    """Calculate score boost based on float shares.

    Lower float = higher volatility potential = higher score boost.

    Args:
        float_shares: Number of float shares

    Returns:
        Tuple of (score_boost, reason_string)

    Examples:
        >>> score_float_shares(5_000_000)
        (0.5, "very_low_float_<10M")

        >>> score_float_shares(30_000_000)
        (0.3, "low_float_10M-50M")

        >>> score_float_shares(150_000_000)
        (-0.1, "high_float_>100M")
    """
    if float_shares < FLOAT_VERY_LOW:
        return FLOAT_VERY_LOW_BOOST, "very_low_float_<10M"
    elif float_shares < FLOAT_LOW:
        return FLOAT_LOW_BOOST, "low_float_10M-50M"
    elif float_shares < FLOAT_MEDIUM:
        return FLOAT_MEDIUM_BOOST, "medium_float_50M-100M"
    else:
        return FLOAT_HIGH_PENALTY, "high_float_>100M"


def score_short_interest(short_pct: float) -> Tuple[float, str]:
    """Calculate score boost based on short interest percentage.

    Higher short interest = squeeze potential = higher score boost.

    Args:
        short_pct: Short interest as percentage (e.g., 25.5 for 25.5%)

    Returns:
        Tuple of (score_boost, reason_string)

    Examples:
        >>> score_short_interest(25.0)
        (0.5, "very_high_si_>20%")

        >>> score_short_interest(17.5)
        (0.3, "high_si_15-20%")

        >>> score_short_interest(5.0)
        (0.0, "low_si_<10%")
    """
    if short_pct >= SI_VERY_HIGH:
        return SI_VERY_HIGH_BOOST, "very_high_si_>20%"
    elif short_pct >= SI_HIGH:
        return SI_HIGH_BOOST, "high_si_15-20%"
    elif short_pct >= SI_MODERATE:
        return SI_MODERATE_BOOST, "moderate_si_10-15%"
    else:
        return 0.0, "low_si_<10%"


def calculate_fundamental_score(
    ticker: str,
) -> Tuple[float, dict]:
    """Calculate total fundamental score for a ticker.

    Combines float shares and short interest scoring. Handles missing data
    gracefully by returning neutral score (0.0) when data unavailable.

    Args:
        ticker: Stock ticker symbol

    Returns:
        Tuple of (total_score, metadata_dict)
        - total_score: Combined boost from fundamental factors (0.0 if disabled/unavailable)
        - metadata_dict: Contains detailed scoring breakdown

    Examples:
        >>> score, meta = calculate_fundamental_score("GME")
        >>> print(f"Score: {score:.2f}")
        >>> print(f"Float: {meta['float_shares']:,.0f}")
        >>> print(f"Short Interest: {meta['short_interest']:.1f}%")
    """
    # Check feature flag
    if not os.getenv("FEATURE_FUNDAMENTAL_SCORING", "0") == "1":
        return 0.0, {"enabled": False, "reason": "feature_disabled"}

    if not ticker or not ticker.strip():
        return 0.0, {"enabled": True, "reason": "invalid_ticker"}

    # Fetch fundamental data
    try:
        float_shares, short_interest = get_fundamentals(ticker)
    except Exception as e:
        log.warning(
            "fundamental_data_fetch_failed ticker=%s error=%s",
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
        "float_shares": float_shares,
        "short_interest": short_interest,
        "float_score": 0.0,
        "float_reason": None,
        "si_score": 0.0,
        "si_reason": None,
    }

    total_score = 0.0

    # Score float shares
    if float_shares is not None:
        float_score, float_reason = score_float_shares(float_shares)
        total_score += float_score
        metadata["float_score"] = float_score
        metadata["float_reason"] = float_reason

        log.info(
            "fundamental_float_scored ticker=%s float=%.0f score=%.3f reason=%s",
            ticker,
            float_shares,
            float_score,
            float_reason,
        )
    else:
        metadata["float_reason"] = "data_unavailable"
        log.debug(
            "fundamental_float_missing ticker=%s",
            ticker,
        )

    # Score short interest
    if short_interest is not None:
        si_score, si_reason = score_short_interest(short_interest)
        total_score += si_score
        metadata["si_score"] = si_score
        metadata["si_reason"] = si_reason

        log.info(
            "fundamental_si_scored ticker=%s short_pct=%.2f score=%.3f reason=%s",
            ticker,
            short_interest,
            si_score,
            si_reason,
        )
    else:
        metadata["si_reason"] = "data_unavailable"
        log.debug(
            "fundamental_si_missing ticker=%s",
            ticker,
        )

    # Log final score
    if total_score > 0:
        log.info(
            "fundamental_score_calculated ticker=%s total_score=%.3f float_score=%.3f si_score=%.3f",
            ticker,
            total_score,
            metadata["float_score"],
            metadata["si_score"],
        )
    elif float_shares is None and short_interest is None:
        metadata["reason"] = "no_data_available"
        log.debug(
            "fundamental_score_unavailable ticker=%s reason=no_data",
            ticker,
        )

    return total_score, metadata


def is_fundamental_scoring_enabled() -> bool:
    """Check if fundamental scoring is enabled via feature flag.

    Returns:
        True if FEATURE_FUNDAMENTAL_SCORING=1, False otherwise
    """
    return os.getenv("FEATURE_FUNDAMENTAL_SCORING", "0") == "1"


# Public API
__all__ = [
    "calculate_fundamental_score",
    "score_float_shares",
    "score_short_interest",
    "is_fundamental_scoring_enabled",
]
