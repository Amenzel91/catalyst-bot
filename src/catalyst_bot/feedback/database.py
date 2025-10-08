"""
Alert Performance Database
===========================

SQLite database for tracking alert performance metrics over time.
"""

from __future__ import annotations

import json
import os
import sqlite3
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..logging_utils import get_logger

log = get_logger("feedback.database")

# Default database path
DEFAULT_DB_PATH = Path("data/feedback/alert_performance.db")


def _get_db_path() -> Path:
    """Get the database path from env or use default."""
    db_path_str = os.getenv("FEEDBACK_DB_PATH", str(DEFAULT_DB_PATH))
    db_path = Path(db_path_str).resolve()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return db_path


def _get_connection() -> sqlite3.Connection:
    """Get a database connection with row factory."""
    db_path = _get_db_path()
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    return conn


def init_database() -> None:
    """
    Create database and tables if they don't exist.

    This function is idempotent and safe to call multiple times.
    """
    db_path = _get_db_path()
    log.info("initializing_feedback_database path=%s", db_path)

    conn = _get_connection()
    try:
        cursor = conn.cursor()

        # Create main performance tracking table
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS alert_performance (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                alert_id TEXT UNIQUE NOT NULL,
                ticker TEXT NOT NULL,
                source TEXT NOT NULL,
                catalyst_type TEXT NOT NULL,
                keywords TEXT,
                posted_at INTEGER NOT NULL,
                posted_price REAL,

                -- Performance metrics at different timeframes
                price_15m REAL,
                price_1h REAL,
                price_4h REAL,
                price_1d REAL,

                price_change_15m REAL,
                price_change_1h REAL,
                price_change_4h REAL,
                price_change_1d REAL,

                volume_15m REAL,
                volume_1h REAL,
                volume_4h REAL,
                volume_1d REAL,

                volume_change_15m REAL,
                volume_change_1h REAL,
                volume_change_4h REAL,
                volume_change_1d REAL,

                breakout_confirmed BOOLEAN,
                max_gain REAL,
                max_loss REAL,

                -- Evaluation
                outcome TEXT,
                outcome_score REAL,

                updated_at INTEGER NOT NULL
            )
        """
        )

        # Create indexes for efficient queries
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_ticker ON alert_performance(ticker)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_posted_at ON alert_performance(posted_at)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_catalyst_type ON alert_performance(catalyst_type)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_outcome ON alert_performance(outcome)"
        )

        conn.commit()
        log.info("feedback_database_initialized")

    except Exception as e:
        log.error("feedback_database_init_failed error=%s", str(e))
        conn.rollback()
        raise
    finally:
        conn.close()


def record_alert(
    alert_id: str,
    ticker: str,
    source: str,
    catalyst_type: str,
    keywords: Optional[List[str]] = None,
    posted_price: Optional[float] = None,
) -> bool:
    """
    Record a new alert for tracking.

    Parameters
    ----------
    alert_id : str
        Unique identifier for the alert
    ticker : str
        Stock ticker symbol
    source : str
        Alert source (e.g., "finviz", "businesswire")
    catalyst_type : str
        Type of catalyst (e.g., "fda_approval", "partnership")
    keywords : list of str, optional
        Keywords that matched in the alert
    posted_price : float, optional
        Price at time of posting

    Returns
    -------
    bool
        True if successfully recorded, False otherwise
    """
    conn = _get_connection()
    try:
        now = int(time.time())
        keywords_json = json.dumps(keywords or [])

        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT OR IGNORE INTO alert_performance
            (alert_id, ticker, source, catalyst_type, keywords, posted_at, posted_price, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                alert_id,
                ticker.upper(),
                source,
                catalyst_type,
                keywords_json,
                now,
                posted_price,
                now,
            ),
        )

        conn.commit()
        inserted = cursor.rowcount > 0

        if inserted:
            log.info(
                "alert_recorded alert_id=%s ticker=%s catalyst_type=%s",
                alert_id,
                ticker.upper(),
                catalyst_type,
            )
        else:
            log.debug("alert_already_exists alert_id=%s", alert_id)

        return inserted

    except Exception as e:
        log.error("record_alert_failed alert_id=%s error=%s", alert_id, str(e))
        conn.rollback()
        return False
    finally:
        conn.close()


def update_performance(
    alert_id: str,
    timeframe: str,
    price: Optional[float] = None,
    volume: Optional[float] = None,
    price_change: Optional[float] = None,
    volume_change: Optional[float] = None,
) -> bool:
    """
    Update performance metrics for a specific timeframe.

    Parameters
    ----------
    alert_id : str
        Alert identifier
    timeframe : str
        Timeframe to update ('15m', '1h', '4h', '1d')
    price : float, optional
        Current price at this timeframe
    volume : float, optional
        Current volume at this timeframe
    price_change : float, optional
        Price change percentage from posted_price
    volume_change : float, optional
        Volume change percentage from initial volume

    Returns
    -------
    bool
        True if updated successfully
    """
    if timeframe not in ("15m", "1h", "4h", "1d"):
        log.error("invalid_timeframe alert_id=%s timeframe=%s", alert_id, timeframe)
        return False

    conn = _get_connection()
    try:
        now = int(time.time())

        # Build dynamic update query based on what's provided
        updates = []
        params = []

        if price is not None:
            updates.append(f"price_{timeframe} = ?")
            params.append(price)

        if volume is not None:
            updates.append(f"volume_{timeframe} = ?")
            params.append(volume)

        if price_change is not None:
            updates.append(f"price_change_{timeframe} = ?")
            params.append(price_change)

        if volume_change is not None:
            updates.append(f"volume_change_{timeframe} = ?")
            params.append(volume_change)

        updates.append("updated_at = ?")
        params.append(now)

        params.append(alert_id)

        cursor = conn.cursor()
        cursor.execute(
            f"UPDATE alert_performance SET {', '.join(updates)} WHERE alert_id = ?",
            params,
        )

        conn.commit()
        updated = cursor.rowcount > 0

        if updated:
            log.debug(
                "performance_updated alert_id=%s timeframe=%s price=%s volume=%s",
                alert_id,
                timeframe,
                price,
                volume,
            )
        else:
            log.warning("alert_not_found_for_update alert_id=%s", alert_id)

        return updated

    except Exception as e:
        log.error(
            "update_performance_failed alert_id=%s timeframe=%s error=%s",
            alert_id,
            timeframe,
            str(e),
        )
        conn.rollback()
        return False
    finally:
        conn.close()


def update_outcome(alert_id: str, outcome: str, score: float) -> bool:
    """
    Update the outcome classification and score for an alert.

    Parameters
    ----------
    alert_id : str
        Alert identifier
    outcome : str
        Outcome classification ('win', 'loss', 'neutral')
    score : float
        Outcome score (-1.0 to +1.0)

    Returns
    -------
    bool
        True if updated successfully
    """
    if outcome not in ("win", "loss", "neutral"):
        log.error("invalid_outcome alert_id=%s outcome=%s", alert_id, outcome)
        return False

    conn = _get_connection()
    try:
        now = int(time.time())

        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE alert_performance
            SET outcome = ?, outcome_score = ?, updated_at = ?
            WHERE alert_id = ?
            """,
            (outcome, score, now, alert_id),
        )

        conn.commit()
        updated = cursor.rowcount > 0

        if updated:
            log.info(
                "outcome_updated alert_id=%s outcome=%s score=%.2f",
                alert_id,
                outcome,
                score,
            )
        else:
            log.warning("alert_not_found_for_outcome alert_id=%s", alert_id)

        return updated

    except Exception as e:
        log.error(
            "update_outcome_failed alert_id=%s outcome=%s error=%s",
            alert_id,
            outcome,
            str(e),
        )
        conn.rollback()
        return False
    finally:
        conn.close()


def get_alert_performance(alert_id: str) -> Optional[Dict[str, Any]]:
    """
    Get full performance record for an alert.

    Parameters
    ----------
    alert_id : str
        Alert identifier

    Returns
    -------
    dict or None
        Performance record as dictionary, or None if not found
    """
    conn = _get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM alert_performance WHERE alert_id = ?",
            (alert_id,),
        )

        row = cursor.fetchone()
        if row is None:
            return None

        # Convert sqlite3.Row to dict
        result = dict(row)

        # Parse keywords JSON
        if result.get("keywords"):
            try:
                result["keywords"] = json.loads(result["keywords"])
            except Exception:
                result["keywords"] = []

        return result

    except Exception as e:
        log.error("get_alert_performance_failed alert_id=%s error=%s", alert_id, str(e))
        return None
    finally:
        conn.close()


def get_pending_updates(max_age_hours: int = 24) -> List[Dict[str, Any]]:
    """
    Get alerts that need price/volume updates.

    Returns alerts posted within the last max_age_hours that are missing
    any timeframe data.

    Parameters
    ----------
    max_age_hours : int, optional
        Maximum age in hours to consider (default: 24)

    Returns
    -------
    list of dict
        List of alert records that need updates
    """
    conn = _get_connection()
    try:
        now = int(time.time())
        cutoff = now - (max_age_hours * 3600)

        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT * FROM alert_performance
            WHERE posted_at >= ?
            AND outcome IS NULL
            ORDER BY posted_at ASC
            """,
            (cutoff,),
        )

        rows = cursor.fetchall()
        results = []

        for row in rows:
            result = dict(row)

            # Parse keywords JSON
            if result.get("keywords"):
                try:
                    result["keywords"] = json.loads(result["keywords"])
                except Exception:
                    result["keywords"] = []

            results.append(result)

        log.debug("found_pending_updates count=%d", len(results))
        return results

    except Exception as e:
        log.error("get_pending_updates_failed error=%s", str(e))
        return []
    finally:
        conn.close()


def get_alerts_by_keyword(
    keyword: str, lookback_days: int = 7, outcome_filter: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Get all alerts containing a specific keyword.

    Parameters
    ----------
    keyword : str
        Keyword to search for
    lookback_days : int, optional
        Number of days to look back (default: 7)
    outcome_filter : str, optional
        Filter by outcome ('win', 'loss', 'neutral')

    Returns
    -------
    list of dict
        List of alert records matching the keyword
    """
    conn = _get_connection()
    try:
        now = int(time.time())
        cutoff = now - (lookback_days * 86400)

        cursor = conn.cursor()

        # Base query
        query = """
            SELECT * FROM alert_performance
            WHERE posted_at >= ?
            AND keywords LIKE ?
        """
        params = [cutoff, f'%"{keyword}"%']

        # Add outcome filter if specified
        if outcome_filter:
            query += " AND outcome = ?"
            params.append(outcome_filter)

        query += " ORDER BY posted_at DESC"

        cursor.execute(query, params)
        rows = cursor.fetchall()

        results = []
        for row in rows:
            result = dict(row)
            if result.get("keywords"):
                try:
                    result["keywords"] = json.loads(result["keywords"])
                except Exception:
                    result["keywords"] = []
            results.append(result)

        return results

    except Exception as e:
        log.error("get_alerts_by_keyword_failed keyword=%s error=%s", keyword, str(e))
        return []
    finally:
        conn.close()


def get_performance_stats(lookback_days: int = 7) -> Dict[str, Any]:
    """
    Get aggregate performance statistics.

    Parameters
    ----------
    lookback_days : int, optional
        Number of days to analyze (default: 7)

    Returns
    -------
    dict
        Statistics including total alerts, win rate, avg return, etc.
    """
    conn = _get_connection()
    try:
        now = int(time.time())
        cutoff = now - (lookback_days * 86400)

        cursor = conn.cursor()

        # Get overall counts
        cursor.execute(
            """
            SELECT
                COUNT(*) as total_alerts,
                COUNT(CASE WHEN outcome = 'win' THEN 1 END) as wins,
                COUNT(CASE WHEN outcome = 'loss' THEN 1 END) as losses,
                COUNT(CASE WHEN outcome = 'neutral' THEN 1 END) as neutral,
                AVG(CASE WHEN outcome IS NOT NULL THEN outcome_score END) as avg_score,
                AVG(CASE WHEN price_change_1d IS NOT NULL THEN price_change_1d END) as avg_return_1d
            FROM alert_performance
            WHERE posted_at >= ?
            """,
            (cutoff,),
        )

        row = cursor.fetchone()
        stats = dict(row) if row else {}

        # Calculate win rate
        total_scored = (
            (stats.get("wins", 0) or 0)
            + (stats.get("losses", 0) or 0)
            + (stats.get("neutral", 0) or 0)
        )
        if total_scored > 0:
            stats["win_rate"] = (stats.get("wins", 0) or 0) / total_scored
        else:
            stats["win_rate"] = 0.0

        return stats

    except Exception as e:
        log.error("get_performance_stats_failed error=%s", str(e))
        return {}
    finally:
        conn.close()
