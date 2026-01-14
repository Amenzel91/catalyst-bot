"""
MOA Rejection Recorder.

Records rejected items during classification for outcome tracking.
This enables the MOA system to analyze fresh missed opportunities.
"""

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import List, Optional

from ..config import get_settings
from ..logging_utils import get_logger
from .database import get_db_path, init_database

log = get_logger("moa.rejection_recorder")


@dataclass
class RejectionEvent:
    """Data class representing a rejected item event."""

    ticker: str
    rejected_at: datetime
    rejection_reason: str
    rejection_score: float
    entry_price: float
    keywords: List[str]
    source: str
    headline: str


def record_rejection(event: RejectionEvent) -> bool:
    """
    Record a rejected item for outcome tracking.

    This function is called from classify.py when an item is rejected.
    The rejection is stored in the database for later price tracking.

    Args:
        event: RejectionEvent containing rejection details

    Returns:
        True if recorded successfully, False otherwise
    """
    settings = get_settings()

    # Check if MOA outcome tracking is enabled
    if not getattr(settings, "feature_moa_outcome_tracking", True):
        return False

    # Skip if no valid ticker or price
    if not event.ticker or not event.entry_price or event.entry_price <= 0:
        log.debug(
            "rejection_skipped_invalid ticker=%s price=%s",
            event.ticker,
            event.entry_price,
        )
        return False

    try:
        # Ensure database is initialized
        db_path = get_db_path()

        with sqlite3.connect(db_path) as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO rejected_items
                (ticker, rejected_at, rejection_reason, rejection_score,
                 entry_price, keywords, source, headline)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    event.ticker.upper(),
                    event.rejected_at.isoformat(),
                    event.rejection_reason,
                    event.rejection_score,
                    event.entry_price,
                    json.dumps(event.keywords) if event.keywords else "[]",
                    event.source or "unknown",
                    (event.headline[:500] if event.headline else "")[:500],
                ),
            )
            conn.commit()

            # Check if actually inserted (not a duplicate)
            if conn.total_changes > 0:
                log.debug(
                    "rejection_recorded ticker=%s reason=%s score=%.2f price=%.2f",
                    event.ticker,
                    event.rejection_reason,
                    event.rejection_score or 0,
                    event.entry_price,
                )
                return True
            else:
                log.debug(
                    "rejection_duplicate_skipped ticker=%s ts=%s",
                    event.ticker,
                    event.rejected_at.isoformat(),
                )
                return False

    except sqlite3.IntegrityError:
        # Duplicate entry - this is expected and OK
        log.debug(
            "rejection_duplicate ticker=%s ts=%s",
            event.ticker,
            event.rejected_at.isoformat(),
        )
        return False

    except Exception as e:
        log.warning(
            "rejection_record_failed ticker=%s error=%s",
            event.ticker,
            str(e),
        )
        return False


def record_rejection_simple(
    ticker: str,
    reason: str,
    score: float,
    price: float,
    keywords: Optional[List[str]] = None,
    source: str = "unknown",
    headline: str = "",
) -> bool:
    """
    Simplified rejection recording interface.

    Convenience function that creates a RejectionEvent internally.

    Args:
        ticker: Stock ticker symbol
        reason: Rejection reason code
        score: Score at rejection time
        price: Entry price when rejected
        keywords: List of keyword hits (optional)
        source: Feed source name
        headline: Article headline

    Returns:
        True if recorded successfully
    """
    event = RejectionEvent(
        ticker=ticker,
        rejected_at=datetime.now(timezone.utc),
        rejection_reason=reason,
        rejection_score=score,
        entry_price=price,
        keywords=keywords or [],
        source=source,
        headline=headline,
    )
    return record_rejection(event)


def get_recent_rejections(hours: int = 24, limit: int = 100) -> List[dict]:
    """
    Get recent rejection records for debugging/monitoring.

    Args:
        hours: Look back this many hours
        limit: Maximum records to return

    Returns:
        List of rejection dictionaries
    """
    try:
        db_path = get_db_path()

        with sqlite3.connect(db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                """
                SELECT * FROM rejected_items
                WHERE rejected_at > datetime('now', ? || ' hours')
                ORDER BY rejected_at DESC
                LIMIT ?
            """,
                (f"-{hours}", limit),
            )
            return [dict(row) for row in cursor.fetchall()]

    except Exception as e:
        log.warning("get_recent_rejections_failed error=%s", e)
        return []


def get_rejection_stats(hours: int = 24) -> dict:
    """
    Get rejection statistics for monitoring.

    Args:
        hours: Look back period in hours

    Returns:
        Dictionary with rejection statistics
    """
    try:
        db_path = get_db_path()

        with sqlite3.connect(db_path) as conn:
            stats = {}

            # Total rejections in period
            cursor = conn.execute(
                """
                SELECT COUNT(*) FROM rejected_items
                WHERE rejected_at > datetime('now', ? || ' hours')
            """,
                (f"-{hours}",),
            )
            stats["total_rejections"] = cursor.fetchone()[0]

            # By reason
            cursor = conn.execute(
                """
                SELECT rejection_reason, COUNT(*) as count
                FROM rejected_items
                WHERE rejected_at > datetime('now', ? || ' hours')
                GROUP BY rejection_reason
                ORDER BY count DESC
            """,
                (f"-{hours}",),
            )
            stats["by_reason"] = {row[0]: row[1] for row in cursor.fetchall()}

            # Average score by reason
            cursor = conn.execute(
                """
                SELECT rejection_reason, AVG(rejection_score) as avg_score
                FROM rejected_items
                WHERE rejected_at > datetime('now', ? || ' hours')
                AND rejection_score IS NOT NULL
                GROUP BY rejection_reason
            """,
                (f"-{hours}",),
            )
            stats["avg_score_by_reason"] = {
                row[0]: round(row[1], 3) for row in cursor.fetchall()
            }

            return stats

    except Exception as e:
        log.warning("get_rejection_stats_failed error=%s", e)
        return {"error": str(e)}
