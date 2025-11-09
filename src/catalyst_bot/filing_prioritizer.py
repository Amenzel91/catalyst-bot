"""SEC filing prioritization system for alert fatigue reduction.

This module scores filings by urgency × impact × relevance to determine which
filings should trigger immediate Discord alerts vs being queued for daily digest.

Scoring Formula:
    total_priority = (urgency × 0.4) + (impact × 0.4) + (relevance × 0.2)

Components:
- Urgency: Time sensitivity (earnings=0.9, M&A=0.8, routine=0.3)
- Impact: Market impact (sentiment magnitude + guidance changes + filing weight)
- Relevance: User relevance (watchlist match, sector filter)

Alert Thresholds:
- Critical (≥0.8): Always alert (M&A, earnings beats/misses)
- High (≥0.6): Alert if user online or on watchlist
- Medium (≥0.4): Queue for daily digest
- Low (<0.4): Log only

Environment Variables:
- PRIORITY_ALERT_THRESHOLD: Minimum score for immediate alert (default: 0.6)
- PRIORITY_WATCHLIST_BOOST: Bonus for watchlist tickers (default: 0.3)
- PRIORITY_DIGEST_ENABLED: Enable daily digest (default: true)

Example:
    >>> from filing_prioritizer import calculate_priority, should_send_alert
    >>> priority = calculate_priority(filing, sentiment, guidance, user_watchlist=["AAPL"])
    >>> priority.total
    0.85  # Critical priority
    >>> should_send_alert(priority, user_status="online")
    True  # Send immediate alert
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional

try:
    from .logging_utils import get_logger
except Exception:
    import logging

    logging.basicConfig(level=logging.INFO)

    def get_logger(_):
        return logging.getLogger("filing_prioritizer")


log = get_logger("filing_prioritizer")


# ============================================================================
# Configuration
# ============================================================================

DEFAULT_ALERT_THRESHOLD = 0.6
DEFAULT_WATCHLIST_BOOST = 0.3

# Alert threshold tiers
ALERT_THRESHOLDS = {
    "critical": 0.8,  # Always alert (M&A, earnings beats/misses)
    "high": 0.6,  # Alert if user online or watchlist
    "medium": 0.4,  # Queue for daily digest
    "low": 0.2,  # Log only, no alert
}

# Filing type urgency scores (0.0-1.0)
# Higher urgency = more time-sensitive
FILING_URGENCY = {
    # 8-K Items (time-sensitive events)
    ("8-K", "2.02"): 0.9,  # Earnings - very time-sensitive
    ("8-K", "1.01"): 0.8,  # Material agreements (M&A)
    ("8-K", "1.03"): 0.9,  # Bankruptcy - critical
    ("8-K", "3.02"): 0.7,  # Equity sales (dilution)
    ("8-K", "5.02"): 0.6,  # Leadership changes
    ("8-K", "7.01"): 0.5,  # Regulation FD disclosure
    ("8-K", "8.01"): 0.3,  # Other events - routine
    # Quarterly/Annual reports
    "10-Q": 0.7,  # Quarterly - moderately time-sensitive
    "10-K": 0.6,  # Annual - important but less urgent
    # Other filings
    "S-1": 0.8,  # IPO registration - high interest
    "424B5": 0.5,  # Offering prospectus
}


# ============================================================================
# Data Models
# ============================================================================


@dataclass
class PriorityScore:
    """Filing priority score breakdown."""

    urgency: float  # 0-1: Time sensitivity
    impact: float  # 0-1: Market impact potential
    relevance: float  # 0-1: User relevance
    total: float  # Weighted sum
    tier: str  # "critical", "high", "medium", "low"
    reasons: list[str]  # Human-readable reasons for score

    def should_alert(self, user_status: str = "offline") -> bool:
        """
        Determine if filing should trigger immediate alert.

        Parameters
        ----------
        user_status : str
            User status: "online", "offline", "away"

        Returns
        -------
        bool
            True if should send immediate alert
        """
        # Critical always alerts
        if self.tier == "critical":
            return True

        # High alerts if user online or on watchlist
        if self.tier == "high" and user_status == "online":
            return True

        # Medium/low go to digest or log
        return False


# ============================================================================
# Urgency Scoring
# ============================================================================


def calculate_urgency(filing_section) -> tuple[float, list[str]]:
    """
    Calculate filing urgency score (0-1).

    Urgency factors:
    - Filing type and item code
    - Time-sensitive events score higher
    - Routine filings score lower

    Parameters
    ----------
    filing_section : FilingSection
        Parsed SEC filing from sec_parser.py

    Returns
    -------
    tuple[float, list[str]]
        (urgency_score, reasons)

    Examples
    --------
    >>> filing = FilingSection(filing_type="8-K", item_code="2.02", ...)
    >>> urgency, reasons = calculate_urgency(filing)
    >>> urgency
    0.9  # Earnings is very urgent
    >>> reasons
    ['8-K Item 2.02 (earnings) - very time-sensitive']
    """
    reasons = []

    # Check 8-K item-specific urgency
    if filing_section.filing_type == "8-K" and filing_section.item_code:
        key = ("8-K", filing_section.item_code)
        if key in FILING_URGENCY:
            urgency = FILING_URGENCY[key]
            reasons.append(f"8-K Item {filing_section.item_code} ({filing_section.catalyst_type or 'event'})")
            return urgency, reasons

    # Check general filing type urgency
    if filing_section.filing_type in FILING_URGENCY:
        urgency = FILING_URGENCY[filing_section.filing_type]
        reasons.append(f"{filing_section.filing_type} filing")
        return urgency, reasons

    # Default: routine filing
    reasons.append("Routine filing")
    return 0.3, reasons


# ============================================================================
# Impact Scoring
# ============================================================================


def calculate_impact(
    filing_section,
    sentiment_output,
    guidance_analysis,
) -> tuple[float, list[str]]:
    """
    Calculate filing market impact score (0-1).

    Impact factors:
    - Sentiment magnitude (abs(weighted_score))
    - Guidance changes (raised/lowered = +0.3)
    - Filing impact weight (from SEC_SENTIMENT_FILING_IMPACT_WEIGHTS)

    Parameters
    ----------
    filing_section : FilingSection
        Parsed SEC filing
    sentiment_output : SECSentimentOutput
        Sentiment analysis from sec_sentiment.py
    guidance_analysis : GuidanceAnalysis
        Forward guidance from guidance_extractor.py

    Returns
    -------
    tuple[float, list[str]]
        (impact_score, reasons)

    Examples
    --------
    >>> impact, reasons = calculate_impact(filing, sentiment, guidance)
    >>> impact
    0.85  # High impact (strong sentiment + raised guidance)
    >>> reasons
    ['Strong bullish sentiment (+0.8)', 'Guidance raised (revenue)']
    """
    reasons = []
    score = 0.0

    # Factor 1: Sentiment magnitude (0.0-0.5)
    if sentiment_output:
        sent_magnitude = abs(sentiment_output.weighted_score)
        score += min(0.5, sent_magnitude)

        if sentiment_output.score > 0.5:
            reasons.append(f"Strong bullish sentiment (+{sentiment_output.score:.1f})")
        elif sentiment_output.score < -0.5:
            reasons.append(f"Strong bearish sentiment ({sentiment_output.score:.1f})")

    # Factor 2: Guidance changes (0.0-0.3)
    if guidance_analysis and guidance_analysis.has_guidance:
        raised = sum(1 for g in guidance_analysis.guidance_items if g.change_direction == "raised")
        lowered = sum(1 for g in guidance_analysis.guidance_items if g.change_direction == "lowered")

        if raised > 0:
            score += 0.3
            types = ", ".join(g.guidance_type for g in guidance_analysis.guidance_items if g.change_direction == "raised")
            reasons.append(f"Guidance raised ({types})")
        elif lowered > 0:
            score += 0.3
            types = ", ".join(g.guidance_type for g in guidance_analysis.guidance_items if g.change_direction == "lowered")
            reasons.append(f"Guidance lowered ({types})")

    # Factor 3: Filing impact weight (0.0-0.2)
    # Use the same weights as sec_sentiment.py
    if filing_section.filing_type == "8-K" and filing_section.item_code:
        high_impact_items = ["1.01", "1.03", "2.02", "3.02"]
        if filing_section.item_code in high_impact_items:
            score += 0.2
            reasons.append(f"High-impact filing type")

    return min(1.0, score), reasons


# ============================================================================
# Relevance Scoring
# ============================================================================


def calculate_relevance(
    filing_section,
    user_watchlist: Optional[list[str]] = None,
    user_sectors: Optional[list[str]] = None,
) -> tuple[float, list[str]]:
    """
    Calculate filing relevance to user (0-1).

    Relevance factors:
    - On watchlist = 1.0
    - In tracked sector = 0.7
    - Not tracked = 0.3 (still has baseline relevance)

    Parameters
    ----------
    filing_section : FilingSection
        Parsed SEC filing
    user_watchlist : list[str], optional
        User's watchlist tickers
    user_sectors : list[str], optional
        User's tracked sectors (e.g., ["tech", "biotech"])

    Returns
    -------
    tuple[float, list[str]]
        (relevance_score, reasons)

    Examples
    --------
    >>> relevance, reasons = calculate_relevance(filing, user_watchlist=["AAPL"])
    >>> relevance
    1.0  # On watchlist
    >>> reasons
    ['On watchlist']
    """
    reasons = []

    # Factor 1: Watchlist match (highest priority)
    if user_watchlist and filing_section.ticker in user_watchlist:
        reasons.append("On watchlist")
        return 1.0, reasons

    # Factor 2: Sector match (medium priority)
    if user_sectors:
        # Would need sector classification (future enhancement)
        # For now, skip this factor
        pass

    # Factor 3: Baseline relevance (everyone gets some relevance)
    reasons.append("General market interest")
    return 0.3, reasons


# ============================================================================
# Priority Calculation
# ============================================================================


def calculate_priority(
    filing_section,
    sentiment_output,
    guidance_analysis=None,
    user_watchlist: Optional[list[str]] = None,
    user_sectors: Optional[list[str]] = None,
) -> PriorityScore:
    """
    Calculate comprehensive filing priority score.

    Formula:
        total = (urgency × 0.4) + (impact × 0.4) + (relevance × 0.2)

    Parameters
    ----------
    filing_section : FilingSection
        Parsed SEC filing
    sentiment_output : SECSentimentOutput
        Sentiment analysis result
    guidance_analysis : GuidanceAnalysis, optional
        Forward guidance analysis
    user_watchlist : list[str], optional
        User's watchlist tickers
    user_sectors : list[str], optional
        User's tracked sectors

    Returns
    -------
    PriorityScore
        Complete priority breakdown

    Examples
    --------
    >>> priority = calculate_priority(
    ...     filing=filing_section,
    ...     sentiment=sentiment_output,
    ...     guidance=guidance_analysis,
    ...     user_watchlist=["AAPL"]
    ... )
    >>> priority.total
    0.85
    >>> priority.tier
    'critical'
    >>> priority.should_alert(user_status="online")
    True
    """
    # Calculate component scores
    urgency, urgency_reasons = calculate_urgency(filing_section)
    impact, impact_reasons = calculate_impact(filing_section, sentiment_output, guidance_analysis)
    relevance, relevance_reasons = calculate_relevance(filing_section, user_watchlist, user_sectors)

    # Apply watchlist boost
    if user_watchlist and filing_section.ticker in user_watchlist:
        watchlist_boost = float(os.getenv("PRIORITY_WATCHLIST_BOOST", DEFAULT_WATCHLIST_BOOST))
        # Boost impact and urgency slightly
        urgency = min(1.0, urgency + watchlist_boost * 0.5)
        impact = min(1.0, impact + watchlist_boost * 0.5)

    # Weighted combination
    total = (urgency * 0.4) + (impact * 0.4) + (relevance * 0.2)

    # Determine tier
    if total >= ALERT_THRESHOLDS["critical"]:
        tier = "critical"
    elif total >= ALERT_THRESHOLDS["high"]:
        tier = "high"
    elif total >= ALERT_THRESHOLDS["medium"]:
        tier = "medium"
    else:
        tier = "low"

    # Combine reasons
    all_reasons = []
    if urgency_reasons:
        all_reasons.append(f"Urgency: {', '.join(urgency_reasons)}")
    if impact_reasons:
        all_reasons.append(f"Impact: {', '.join(impact_reasons)}")
    if relevance_reasons:
        all_reasons.append(f"Relevance: {', '.join(relevance_reasons)}")

    log.info(
        f"Priority score for {filing_section.ticker} {filing_section.filing_type}: "
        f"{total:.2f} ({tier}) - urgency={urgency:.2f}, impact={impact:.2f}, relevance={relevance:.2f}"
    )

    return PriorityScore(
        urgency=urgency,
        impact=impact,
        relevance=relevance,
        total=total,
        tier=tier,
        reasons=all_reasons,
    )


# ============================================================================
# Alert Decision Logic
# ============================================================================


def should_send_alert(priority: PriorityScore, user_status: str = "offline") -> bool:
    """
    Determine if filing should trigger immediate Discord alert.

    Decision logic:
    - Critical (≥0.8): Always alert
    - High (≥0.6): Alert if user online
    - Medium/Low: Queue for digest or log only

    Parameters
    ----------
    priority : PriorityScore
        Calculated priority score
    user_status : str
        User status: "online", "offline", "away"

    Returns
    -------
    bool
        True if should send immediate alert

    Examples
    --------
    >>> priority = PriorityScore(urgency=0.9, impact=0.8, relevance=1.0, total=0.88, tier="critical", reasons=[])
    >>> should_send_alert(priority, user_status="offline")
    True  # Critical always alerts
    >>> priority = PriorityScore(urgency=0.6, impact=0.5, relevance=0.7, total=0.58, tier="medium", reasons=[])
    >>> should_send_alert(priority, user_status="online")
    False  # Medium goes to digest
    """
    # Check configured threshold override
    threshold = float(os.getenv("PRIORITY_ALERT_THRESHOLD", DEFAULT_ALERT_THRESHOLD))

    # Critical always alerts
    if priority.tier == "critical":
        log.info(f"Alert decision: SEND (critical priority {priority.total:.2f})")
        return True

    # High alerts if above threshold and user online
    if priority.total >= threshold:
        if user_status == "online":
            log.info(f"Alert decision: SEND (high priority {priority.total:.2f}, user online)")
            return True
        else:
            log.info(f"Alert decision: QUEUE (high priority {priority.total:.2f}, user offline)")
            return False

    # Below threshold: queue or ignore
    log.info(f"Alert decision: QUEUE/IGNORE (priority {priority.total:.2f} < threshold {threshold})")
    return False


def should_queue_for_digest(priority: PriorityScore) -> bool:
    """
    Determine if filing should be queued for daily digest.

    Queue if:
    - Medium tier (0.4-0.6)
    - Daily digest is enabled

    Parameters
    ----------
    priority : PriorityScore
        Calculated priority score

    Returns
    -------
    bool
        True if should queue for digest
    """
    digest_enabled = os.getenv("PRIORITY_DIGEST_ENABLED", "true").lower() in ("true", "1", "yes")

    if not digest_enabled:
        return False

    # Queue medium-priority filings
    if priority.tier in ("medium", "high"):
        log.info(f"Queuing for digest: {priority.tier} priority ({priority.total:.2f})")
        return True

    return False


# ============================================================================
# Configuration Helpers
# ============================================================================


def get_alert_threshold() -> float:
    """Get configured alert threshold."""
    try:
        return float(os.getenv("PRIORITY_ALERT_THRESHOLD", DEFAULT_ALERT_THRESHOLD))
    except (ValueError, TypeError):
        return DEFAULT_ALERT_THRESHOLD


def get_watchlist_boost() -> float:
    """Get configured watchlist boost."""
    try:
        return float(os.getenv("PRIORITY_WATCHLIST_BOOST", DEFAULT_WATCHLIST_BOOST))
    except (ValueError, TypeError):
        return DEFAULT_WATCHLIST_BOOST


def is_digest_enabled() -> bool:
    """Check if daily digest is enabled."""
    return os.getenv("PRIORITY_DIGEST_ENABLED", "true").lower() in ("true", "1", "yes")
