"""
Real-Time Breakout Feedback System
===================================

Tracks alert performance at multiple time intervals after posting:
- 15 minutes: Early momentum confirmation
- 1 hour: Intraday sustainability
- 4 hours: Extended follow-through
- 1 day: Overnight hold quality

Stores outcomes in SQLite and backfeeds into keyword weight adjustments.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from .logging_utils import get_logger
from .storage import DB_PATH, connect

log = get_logger("breakout_feedback")

# Time intervals for tracking (in minutes)
TRACKING_INTERVALS = {
    "15m": 15,
    "1h": 60,
    "4h": 240,
    "1d": 1440,
}


def migrate_feedback_tables(conn: sqlite3.Connection) -> None:
    """
    Create alert_outcomes table if it doesn't exist.

    Schema:
    - alert_id: Unique identifier from events.jsonl
    - ticker: Stock ticker
    - entry_price: Price at alert time
    - entry_volume: Volume at alert time
    - timestamp: Alert timestamp (UTC)
    - keywords: JSON array of keywords
    - confidence: Model confidence score
    - outcome_15m, outcome_1h, outcome_4h, outcome_1d: JSON objects with:
        - price: Price at interval
        - price_change_pct: % change from entry
        - volume: Volume at interval
        - volume_change_pct: % change from entry
        - timestamp: When measurement was taken
        - breakout_confirmed: Boolean (price_change > 3% and volume > entry_volume)
    - tracked_at: Last update timestamp
    """
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS alert_outcomes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                alert_id TEXT NOT NULL UNIQUE,
                ticker TEXT NOT NULL,
                entry_price REAL NOT NULL,
                entry_volume REAL,
                timestamp INTEGER NOT NULL,
                keywords TEXT,
                confidence REAL,
                outcome_15m TEXT,
                outcome_1h TEXT,
                outcome_4h TEXT,
                outcome_1d TEXT,
                tracked_at INTEGER,
                UNIQUE(alert_id) ON CONFLICT REPLACE
            );
            """
        )

        # Create indexes for efficient querying
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_outcomes_ticker ON alert_outcomes(ticker);"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_outcomes_timestamp ON alert_outcomes(timestamp);"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_outcomes_tracked_at ON alert_outcomes(tracked_at);"
        )

        conn.commit()
        log.info("alert_outcomes_table_ready")
    except Exception as e:
        log.error(f"feedback_migration_failed err={e}")


def register_alert_for_tracking(
    ticker: str,
    entry_price: float,
    entry_volume: Optional[float],
    timestamp: datetime,
    keywords: List[str],
    confidence: float,
    alert_id: Optional[str] = None,
) -> str:
    """
    Register an alert for outcome tracking.

    Parameters
    ----------
    ticker : str
        Stock ticker symbol
    entry_price : float
        Price at alert time
    entry_volume : float, optional
        Volume at alert time
    timestamp : datetime
        Alert timestamp (UTC)
    keywords : list of str
        Keywords/catalysts identified
    confidence : float
        Model confidence score (0-1)
    alert_id : str, optional
        Unique alert ID (auto-generated if not provided)

    Returns
    -------
    str
        Alert ID for reference
    """
    if not alert_id:
        alert_id = f"{ticker}_{int(timestamp.timestamp())}"

    try:
        conn = connect(DB_PATH)
        migrate_feedback_tables(conn)

        ts_unix = int(timestamp.timestamp())
        keywords_json = json.dumps(keywords)

        conn.execute(
            """
            INSERT OR REPLACE INTO alert_outcomes
            (alert_id, ticker, entry_price, entry_volume, timestamp, keywords, confidence)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                alert_id,
                ticker.upper(),
                entry_price,
                entry_volume,
                ts_unix,
                keywords_json,
                confidence,
            ),
        )

        conn.commit()
        conn.close()

        log.info(f"alert_registered id={alert_id} ticker={ticker}")
        return alert_id

    except Exception as e:
        log.error(f"alert_registration_failed ticker={ticker} err={e}")
        return alert_id


def update_alert_outcome(
    alert_id: str,
    interval: str,
    current_price: float,
    current_volume: Optional[float] = None,
) -> bool:
    """
    Update outcome for a specific interval.

    Parameters
    ----------
    alert_id : str
        Alert identifier
    interval : str
        Time interval ('15m', '1h', '4h', '1d')
    current_price : float
        Current price
    current_volume : float, optional
        Current volume

    Returns
    -------
    bool
        True if update succeeded
    """
    if interval not in TRACKING_INTERVALS:
        log.warning(f"invalid_interval interval={interval}")
        return False

    try:
        conn = connect(DB_PATH)
        migrate_feedback_tables(conn)

        # Get alert entry data
        cursor = conn.execute(
            """
            SELECT entry_price, entry_volume, timestamp
            FROM alert_outcomes
            WHERE alert_id = ?
            """,
            (alert_id,),
        )
        row = cursor.fetchone()

        if not row:
            log.warning(f"alert_not_found id={alert_id}")
            conn.close()
            return False

        entry_price, entry_volume, entry_ts = row

        # Calculate changes
        price_change_pct = ((current_price - entry_price) / entry_price) * 100

        volume_change_pct = None
        if current_volume and entry_volume:
            volume_change_pct = ((current_volume - entry_volume) / entry_volume) * 100

        # Breakout confirmation: price up >3% with sustained/higher volume
        breakout_confirmed = price_change_pct > 3.0
        if volume_change_pct is not None:
            breakout_confirmed = breakout_confirmed and volume_change_pct > -20

        # Build outcome JSON
        outcome = {
            "price": current_price,
            "price_change_pct": price_change_pct,
            "volume": current_volume,
            "volume_change_pct": volume_change_pct,
            "timestamp": int(datetime.now(timezone.utc).timestamp()),
            "breakout_confirmed": breakout_confirmed,
        }

        outcome_json = json.dumps(outcome)

        # Update appropriate interval column
        column = f"outcome_{interval}"
        tracked_at = int(datetime.now(timezone.utc).timestamp())

        conn.execute(
            f"""
            UPDATE alert_outcomes
            SET {column} = ?, tracked_at = ?
            WHERE alert_id = ?
            """,
            (outcome_json, tracked_at, alert_id),
        )

        conn.commit()
        conn.close()

        log.info(
            f"outcome_updated id={alert_id} interval={interval} "
            f"price_chg={price_change_pct:.2f}% breakout={breakout_confirmed}"
        )
        return True

    except Exception as e:
        log.error(f"outcome_update_failed id={alert_id} interval={interval} err={e}")
        return False


def get_pending_alerts(interval: str) -> List[Dict[str, Any]]:
    """
    Get alerts that need tracking for a specific interval.

    Parameters
    ----------
    interval : str
        Time interval ('15m', '1h', '4h', '1d')

    Returns
    -------
    list of dict
        Alerts pending tracking for this interval
    """
    if interval not in TRACKING_INTERVALS:
        return []

    try:
        conn = connect(DB_PATH)
        migrate_feedback_tables(conn)

        now = datetime.now(timezone.utc)
        interval_minutes = TRACKING_INTERVALS[interval]
        cutoff = now - timedelta(minutes=interval_minutes + 10)  # +10min grace period
        cutoff_ts = int(cutoff.timestamp())

        column = f"outcome_{interval}"

        # Find alerts:
        # 1. Old enough to track for this interval
        # 2. Don't already have outcome for this interval
        cursor = conn.execute(
            f"""
            SELECT alert_id, ticker, entry_price, entry_volume, timestamp, keywords, confidence
            FROM alert_outcomes
            WHERE timestamp <= ? AND ({column} IS NULL OR {column} = '')
            ORDER BY timestamp ASC
            LIMIT 100
            """,
            (cutoff_ts,),
        )

        results = []
        for row in cursor.fetchall():
            (
                alert_id,
                ticker,
                entry_price,
                entry_volume,
                ts,
                keywords_json,
                confidence,
            ) = row

            keywords = json.loads(keywords_json) if keywords_json else []
            alert_time = datetime.fromtimestamp(ts, tz=timezone.utc)

            results.append(
                {
                    "alert_id": alert_id,
                    "ticker": ticker,
                    "entry_price": entry_price,
                    "entry_volume": entry_volume,
                    "timestamp": alert_time,
                    "keywords": keywords,
                    "confidence": confidence,
                }
            )

        conn.close()

        if results:
            log.info(f"pending_alerts_found interval={interval} count={len(results)}")

        return results

    except Exception as e:
        log.error(f"get_pending_failed interval={interval} err={e}")
        return []


def track_pending_outcomes() -> Dict[str, int]:
    """
    Check and update outcomes for all pending alerts.

    This should be called periodically (e.g., every 5-10 minutes) to update
    alert outcomes across all time intervals.

    Returns
    -------
    dict
        Count of updates per interval
    """
    from .market import get_last_price_change

    update_counts = {interval: 0 for interval in TRACKING_INTERVALS}

    for interval in TRACKING_INTERVALS.keys():
        pending = get_pending_alerts(interval)

        for alert in pending:
            ticker = alert["ticker"]
            alert_id = alert["alert_id"]

            try:
                # Get current price
                price, _ = get_last_price_change(ticker)

                if price:
                    # Volume tracking would require additional API call
                    # Skip for now to reduce API usage
                    success = update_alert_outcome(alert_id, interval, price)

                    if success:
                        update_counts[interval] += 1

            except Exception as e:
                log.warning(
                    f"outcome_tracking_failed ticker={ticker} interval={interval} err={e}"
                )
                continue

    total = sum(update_counts.values())
    if total > 0:
        log.info(f"outcomes_tracked total={total} breakdown={update_counts}")

    return update_counts


def get_keyword_performance_stats(
    lookback_days: int = 7,
    min_sample_size: int = 5,
) -> List[Dict[str, Any]]:
    """
    Analyze keyword performance based on tracked outcomes.

    Parameters
    ----------
    lookback_days : int
        Number of days to analyze
    min_sample_size : int
        Minimum alerts per keyword to include

    Returns
    -------
    list of dict
        Keyword statistics sorted by success rate
    """
    try:
        conn = connect(DB_PATH)
        migrate_feedback_tables(conn)

        cutoff = datetime.now(timezone.utc) - timedelta(days=lookback_days)
        cutoff_ts = int(cutoff.timestamp())

        # Get all alerts with at least 1hr outcome
        cursor = conn.execute(
            """
            SELECT keywords, outcome_1h, outcome_4h, outcome_1d
            FROM alert_outcomes
            WHERE timestamp >= ? AND outcome_1h IS NOT NULL AND outcome_1h != ''
            """,
            (cutoff_ts,),
        )

        # Aggregate by keyword
        keyword_stats: Dict[str, Dict[str, Any]] = {}

        for row in cursor.fetchall():
            keywords_json, outcome_1h_json, outcome_4h_json, outcome_1d_json = row

            keywords = json.loads(keywords_json) if keywords_json else []
            outcome_1h = json.loads(outcome_1h_json) if outcome_1h_json else {}

            # Use 1h outcome as primary metric (most data available)
            breakout_confirmed = outcome_1h.get("breakout_confirmed", False)
            price_change_pct = outcome_1h.get("price_change_pct", 0)

            for keyword in keywords:
                if keyword not in keyword_stats:
                    keyword_stats[keyword] = {
                        "successes": 0,
                        "failures": 0,
                        "total": 0,
                        "avg_return": 0,
                        "total_return": 0,
                    }

                stats = keyword_stats[keyword]
                stats["total"] += 1
                stats["total_return"] += price_change_pct

                if breakout_confirmed or price_change_pct > 5:
                    stats["successes"] += 1
                elif price_change_pct < -5:
                    stats["failures"] += 1

        conn.close()

        # Build results
        results = []
        for keyword, stats in keyword_stats.items():
            if stats["total"] < min_sample_size:
                continue

            success_rate = stats["successes"] / stats["total"]
            avg_return = stats["total_return"] / stats["total"]

            results.append(
                {
                    "keyword": keyword,
                    "success_rate": success_rate,
                    "avg_return": avg_return,
                    "total_alerts": stats["total"],
                    "successes": stats["successes"],
                    "failures": stats["failures"],
                }
            )

        # Sort by success rate descending
        results.sort(key=lambda x: x["success_rate"], reverse=True)

        log.info(
            f"keyword_performance_analyzed count={len(results)} days={lookback_days}"
        )
        return results

    except Exception as e:
        log.error(f"keyword_analysis_failed err={e}")
        return []


def suggest_keyword_weight_adjustments(
    performance_stats: Optional[List[Dict[str, Any]]] = None,
) -> List[Dict[str, Any]]:
    """
    Generate keyword weight adjustment suggestions based on outcomes.

    Parameters
    ----------
    performance_stats : list of dict, optional
        Pre-computed performance stats (will fetch if not provided)

    Returns
    -------
    list of dict
        Suggested adjustments with reasoning
    """
    if performance_stats is None:
        performance_stats = get_keyword_performance_stats(lookback_days=7)

    if not performance_stats:
        return []

    suggestions = []

    # Suggest increases for high performers (>70% success, >10 samples)
    for stat in performance_stats:
        if stat["success_rate"] >= 0.7 and stat["total_alerts"] >= 10:
            suggestions.append(
                {
                    "keyword": stat["keyword"],
                    "action": "increase",
                    "current_weight": None,  # Would need to fetch from config
                    "suggested_weight": None,  # +0.1 or similar
                    "reason": (
                        f"{stat['success_rate']:.0%} success rate over "
                        f"{stat['total_alerts']} alerts, "
                        f"{stat['avg_return']:+.1f}% avg return"
                    ),
                    "impact": "high" if stat["total_alerts"] >= 20 else "medium",
                }
            )

    # Suggest decreases for poor performers (<40% success, >10 samples)
    for stat in performance_stats[-10:]:  # Look at worst performers
        if stat["success_rate"] < 0.4 and stat["total_alerts"] >= 10:
            suggestions.append(
                {
                    "keyword": stat["keyword"],
                    "action": "decrease",
                    "current_weight": None,
                    "suggested_weight": None,  # -0.1 or similar
                    "reason": (
                        f"Only {stat['success_rate']:.0%} success rate over "
                        f"{stat['total_alerts']} alerts, "
                        f"{stat['avg_return']:+.1f}% avg return"
                    ),
                    "impact": "high" if stat["total_alerts"] >= 20 else "medium",
                }
            )

    log.info(f"weight_adjustments_suggested count={len(suggestions)}")
    return suggestions
