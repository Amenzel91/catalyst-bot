"""
Outcome Scoring System
======================

Evaluates alert success based on price and volume action.
"""

from __future__ import annotations

from typing import Dict, Tuple

from ..logging_utils import get_logger
from .database import get_pending_updates, update_outcome

log = get_logger("feedback.outcome_scorer")


def calculate_outcome(perf: Dict) -> Tuple[str, float]:
    """
    Calculate outcome classification and score for an alert.

    Scoring logic:
    - Win: Price up >3% AND volume up >50%, OR price up >5%
    - Loss: Price down >2% OR volume change <20%
    - Neutral: Everything else

    Score range: -1.0 (worst) to +1.0 (best)

    Parameters
    ----------
    perf : dict
        Performance record with price and volume metrics

    Returns
    -------
    tuple of (outcome, score)
        outcome: 'win', 'loss', or 'neutral'
        score: float in range -1.0 to +1.0
    """
    # Extract 24-hour metrics (primary evaluation window)
    price_change = perf.get("price_change_1d") or 0.0
    volume_change = perf.get("volume_change_1d") or 0.0

    # Fallback to 4h if 1d not available yet
    if price_change == 0.0 and perf.get("price_change_4h") is not None:
        price_change = perf.get("price_change_4h") or 0.0
        volume_change = perf.get("volume_change_4h") or 0.0

    score = 0.0

    # Price component (70% weight)
    if price_change > 5.0:  # >5%
        score += 0.7
    elif price_change > 3.0:  # >3%
        score += 0.4
    elif price_change > 1.0:  # >1%
        score += 0.2
    elif price_change < -3.0:  # <-3%
        score -= 0.5
    elif price_change < -1.5:  # <-1.5%
        score -= 0.3

    # Volume component (30% weight)
    # Note: volume_change is calculated as percentage if we have baseline
    if volume_change > 100.0:  # 2x volume
        score += 0.3
    elif volume_change > 50.0:  # 1.5x volume
        score += 0.15
    elif volume_change < 20.0 and volume_change != 0.0:  # Low volume
        score -= 0.2

    # Classify outcome based on score
    if score > 0.5:
        outcome = "win"
    elif score < -0.3:
        outcome = "loss"
    else:
        outcome = "neutral"

    # Clamp score to valid range
    score = max(-1.0, min(1.0, score))

    log.debug(
        "outcome_calculated alert_id=%s outcome=%s score=%.2f "
        "price_change=%.2f%% volume_change=%.2f%%",
        perf.get("alert_id"),
        outcome,
        score,
        price_change,
        volume_change,
    )

    return outcome, score


def score_pending_alerts() -> int:
    """
    Score all alerts that have 24-hour data but no outcome yet.

    Returns
    -------
    int
        Number of alerts scored
    """
    log.debug("score_pending_alerts_start")

    # Get all pending alerts
    pending = get_pending_updates(max_age_hours=48)  # Look back 48h to catch stragglers

    scored_count = 0

    for alert in pending:
        # Skip if already scored
        if alert.get("outcome") is not None:
            continue

        # Check if we have 1d data (or at least 4h data for older alerts)
        has_data = (
            alert.get("price_change_1d") is not None
            or alert.get("price_change_4h") is not None
        )

        if not has_data:
            continue

        # Calculate outcome
        outcome, score = calculate_outcome(alert)

        # Update database
        success = update_outcome(alert["alert_id"], outcome, score)

        if success:
            scored_count += 1
            log.info(
                "alert_scored alert_id=%s ticker=%s outcome=%s score=%.2f",
                alert["alert_id"],
                alert["ticker"],
                outcome,
                score,
            )

    log.info("score_pending_alerts_complete scored=%d", scored_count)
    return scored_count


def get_outcome_distribution(lookback_days: int = 7) -> Dict[str, int]:
    """
    Get distribution of outcomes for recent alerts.

    Parameters
    ----------
    lookback_days : int, optional
        Number of days to analyze

    Returns
    -------
    dict
        Counts for each outcome category
    """
    from .database import _get_connection

    conn = _get_connection()
    try:
        import time

        now = int(time.time())
        cutoff = now - (lookback_days * 86400)

        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT
                outcome,
                COUNT(*) as count
            FROM alert_performance
            WHERE posted_at >= ?
            AND outcome IS NOT NULL
            GROUP BY outcome
            """,
            (cutoff,),
        )

        rows = cursor.fetchall()
        distribution = {row["outcome"]: row["count"] for row in rows}

        return distribution

    except Exception as e:
        log.error("get_outcome_distribution_failed error=%s", str(e))
        return {}
    finally:
        conn.close()
