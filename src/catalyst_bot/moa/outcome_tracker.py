"""
MOA Outcome Price Tracker.

Tracks price outcomes for rejected items at multiple timeframes.
Exports outcomes to outcomes.jsonl for MOA analysis.
"""

import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from ..config import get_settings
from ..logging_utils import get_logger
from ..market import get_last_price_snapshot
from .database import get_db_path, init_database

log = get_logger("moa.outcome_tracker")

# Timeframes to track (name -> timedelta)
TIMEFRAMES: Dict[str, timedelta] = {
    "1h": timedelta(hours=1),
    "4h": timedelta(hours=4),
    "24h": timedelta(hours=24),
    "7d": timedelta(days=7),
}

# Threshold for "missed opportunity" classification
MISSED_OPPORTUNITY_THRESHOLD_PCT = 10.0


def get_pending_outcomes(limit: int = 100) -> List[Dict[str, Any]]:
    """
    Get items that need price outcome updates from both rejected_items and manual_captures.

    Args:
        limit: Maximum number of items to return

    Returns:
        List of records needing updates (includes 'source_table' field)
    """
    try:
        db_path = get_db_path()

        with sqlite3.connect(db_path) as conn:
            conn.row_factory = sqlite3.Row
            # UNION query: fetch from both tables
            cursor = conn.execute(
                """
                SELECT
                    'rejected_items' as source_table,
                    id, ticker, rejected_at as tracked_at,
                    entry_price, rejection_reason,
                    price_1h, price_4h, price_24h, price_7d,
                    return_1h_pct, return_4h_pct, return_24h_pct, return_7d_pct,
                    tracking_complete
                FROM rejected_items
                WHERE tracking_complete = FALSE
                AND rejected_at > datetime('now', '-8 days')

                UNION ALL

                SELECT
                    'manual_captures' as source_table,
                    id, ticker, submitted_at as tracked_at,
                    entry_price,
                    CASE
                        WHEN was_in_rejected = 1 AND rejection_id IS NOT NULL THEN
                            COALESCE(
                                (SELECT rejection_reason FROM rejected_items
                                 WHERE id = manual_captures.rejection_id),
                                'MISSED_COMPLETELY'
                            )
                        ELSE 'MISSED_COMPLETELY'
                    END as rejection_reason,
                    price_1h, price_4h, price_24h, price_7d,
                    return_1h_pct, return_4h_pct, return_24h_pct, return_7d_pct,
                    COALESCE(tracking_complete, FALSE) as tracking_complete
                FROM manual_captures
                WHERE COALESCE(tracking_complete, FALSE) = FALSE
                AND submitted_at > datetime('now', '-8 days')

                ORDER BY tracked_at ASC
                LIMIT ?
            """,
                (limit,),
            )
            return [dict(row) for row in cursor.fetchall()]

    except Exception as e:
        log.warning("get_pending_outcomes_failed error=%s", e)
        return []


def _fetch_price(ticker: str) -> Optional[float]:
    """Fetch current price for a ticker."""
    try:
        price, _ = get_last_price_snapshot(ticker)
        return float(price) if price else None
    except Exception as e:
        log.debug("price_fetch_failed ticker=%s error=%s", ticker, e)
        return None


def _calculate_return(entry_price: float, current_price: float) -> float:
    """Calculate percentage return."""
    if entry_price <= 0:
        return 0.0
    return ((current_price - entry_price) / entry_price) * 100


def update_outcome_prices(batch_size: int = 50) -> Tuple[int, int]:
    """
    Update price outcomes for pending rejected items.

    This function:
    1. Gets items that need outcome updates
    2. Checks if enough time has passed for each timeframe
    3. Fetches current prices and calculates returns
    4. Updates the database

    Args:
        batch_size: Maximum items to process per call

    Returns:
        Tuple of (items_updated, items_completed)
    """
    settings = get_settings()

    # Check if feature is enabled
    if not getattr(settings, "feature_moa_outcome_tracking", True):
        return (0, 0)

    pending = get_pending_outcomes(limit=batch_size)
    if not pending:
        return (0, 0)

    updated_count = 0
    completed_count = 0
    now = datetime.now(timezone.utc)

    for item in pending:
        try:
            ticker = item["ticker"]
            entry_price = item["entry_price"]

            # Parse timestamp (unified as tracked_at in UNION query)
            tracked_at_str = item.get("tracked_at") or item.get("rejected_at")
            if tracked_at_str.endswith("Z"):
                tracked_at_str = tracked_at_str[:-1] + "+00:00"
            tracked_at = datetime.fromisoformat(tracked_at_str)

            # Make timezone-aware if needed
            if tracked_at.tzinfo is None:
                tracked_at = tracked_at.replace(tzinfo=timezone.utc)

            updates = {}
            all_complete = True
            needs_price_fetch = False

            # Check each timeframe
            for tf_name, tf_delta in TIMEFRAMES.items():
                col_price = f"price_{tf_name}"
                col_return = f"return_{tf_name}_pct"

                # Skip if already populated
                if item.get(col_price) is not None:
                    continue

                # Check if enough time has passed
                target_time = tracked_at + tf_delta
                if now < target_time:
                    all_complete = False
                    continue

                # Need to fetch price for this timeframe
                needs_price_fetch = True

            # Fetch price once if needed
            if needs_price_fetch:
                current_price = _fetch_price(ticker)

                if current_price and entry_price:
                    # Update all ready timeframes with current price
                    for tf_name, tf_delta in TIMEFRAMES.items():
                        col_price = f"price_{tf_name}"
                        col_return = f"return_{tf_name}_pct"

                        if item.get(col_price) is not None:
                            continue

                        target_time = tracked_at + tf_delta
                        if now >= target_time:
                            return_pct = _calculate_return(entry_price, current_price)
                            updates[col_price] = current_price
                            updates[col_return] = round(return_pct, 2)

            # Apply updates to database
            if updates:
                db_path = get_db_path()

                with sqlite3.connect(db_path) as conn:
                    # Build SET clause
                    set_parts = [f"{k} = ?" for k in updates.keys()]
                    set_parts.append("tracking_complete = ?")
                    set_parts.append("last_updated = datetime('now')")
                    set_clause = ", ".join(set_parts)

                    values = list(updates.values())
                    values.append(all_complete)
                    values.append(item["id"])

                    # Validate and update the correct table based on source_table field
                    table_name = item.get("source_table", "rejected_items")
                    if table_name not in ("rejected_items", "manual_captures"):
                        log.error("invalid_source_table table=%s", table_name)
                        continue

                    conn.execute(
                        f"UPDATE {table_name} SET {set_clause} WHERE id = ?",
                        values,
                    )
                    conn.commit()

                updated_count += 1
                if all_complete:
                    completed_count += 1

                log.debug(
                    "outcome_updated ticker=%s updates=%d complete=%s",
                    ticker,
                    len(updates),
                    all_complete,
                )

        except Exception as e:
            log.warning(
                "outcome_update_failed ticker=%s error=%s",
                item.get("ticker", "unknown"),
                e,
            )
            continue

    if updated_count > 0:
        log.info(
            "outcome_tracking_batch_complete updated=%d completed=%d pending=%d",
            updated_count,
            completed_count,
            len(pending),
        )

    return (updated_count, completed_count)


def export_outcomes_to_jsonl(days: int = 14) -> int:
    """
    Export tracked outcomes to outcomes.jsonl for MOA analysis.

    This creates a fresh outcomes.jsonl file with recent data from both
    rejected_items and manual_captures tables for the MOA historical analyzer.

    Args:
        days: Number of days to include in export

    Returns:
        Number of outcomes exported
    """
    try:
        db_path = get_db_path()
        output_path = Path("data/moa/outcomes.jsonl")
        output_path.parent.mkdir(parents=True, exist_ok=True)

        outcomes = []

        with sqlite3.connect(db_path) as conn:
            conn.row_factory = sqlite3.Row

            # Part 1: Export from rejected_items (auto-tracked rejections)
            cursor = conn.execute(
                """
                SELECT
                    'rejected' as outcome_type,
                    ticker, rejected_at as outcome_ts, rejection_reason,
                    rejection_score, entry_price, keywords, source, headline,
                    price_1h, price_4h, price_24h, price_7d,
                    return_1h_pct, return_4h_pct, return_24h_pct, return_7d_pct
                FROM rejected_items
                WHERE rejected_at > datetime('now', ? || ' days')
                AND return_24h_pct IS NOT NULL
            """,
                (f"-{days}",),
            )

            for row in cursor.fetchall():
                outcome = _build_outcome_record(row)
                outcomes.append(outcome)

            # Part 2: Export from manual_captures (user-submitted misses)
            cursor = conn.execute(
                """
                SELECT
                    'manual_capture' as outcome_type,
                    ticker, submitted_at as outcome_ts,
                    CASE
                        WHEN was_in_rejected = 1 AND rejection_id IS NOT NULL THEN
                            COALESCE(
                                (SELECT rejection_reason FROM rejected_items
                                 WHERE id = manual_captures.rejection_id),
                                'MISSED_COMPLETELY'
                            )
                        ELSE 'MISSED_COMPLETELY'
                    END as rejection_reason,
                    pct_move as rejection_score,
                    entry_price, keywords, source, headline,
                    price_1h, price_4h, price_24h, price_7d,
                    return_1h_pct, return_4h_pct, return_24h_pct, return_7d_pct
                FROM manual_captures
                WHERE submitted_at > datetime('now', ? || ' days')
                AND (return_24h_pct IS NOT NULL OR pct_move IS NOT NULL)
            """,
                (f"-{days}",),
            )

            for row in cursor.fetchall():
                outcome = _build_outcome_record(row)
                outcomes.append(outcome)

        # Sort by timestamp descending
        outcomes.sort(key=lambda x: x.get("rejection_ts", ""), reverse=True)

        # Write to outcomes.jsonl
        with open(output_path, "w", encoding="utf-8") as f:
            for outcome in outcomes:
                f.write(json.dumps(outcome) + "\n")

        # Count by type for logging
        rejected_count = sum(1 for o in outcomes if o.get("outcome_type") == "rejected")
        manual_count = sum(
            1 for o in outcomes if o.get("outcome_type") == "manual_capture"
        )

        log.info(
            "outcomes_exported count=%d rejected=%d manual=%d path=%s days=%d",
            len(outcomes),
            rejected_count,
            manual_count,
            output_path,
            days,
        )
        return len(outcomes)

    except Exception as e:
        log.error("outcomes_export_failed error=%s", e, exc_info=True)
        return 0


def _build_outcome_record(row: sqlite3.Row) -> Dict[str, Any]:
    """
    Build a standardized outcome record from a database row.

    Args:
        row: Database row (from rejected_items or manual_captures query)

    Returns:
        Outcome dictionary in MOA format
    """
    # Calculate max return across all timeframes
    returns = [
        row["return_1h_pct"] or 0,
        row["return_4h_pct"] or 0,
        row["return_24h_pct"] or 0,
        row["return_7d_pct"] or 0,
    ]
    max_return = max(returns)

    # Parse keywords
    try:
        keywords = json.loads(row["keywords"] or "[]")
    except json.JSONDecodeError:
        keywords = []

    # Build outcome record in MOA format
    return {
        "ticker": row["ticker"],
        "outcome_type": row["outcome_type"],
        "rejection_ts": row["outcome_ts"],
        "rejection_reason": row["rejection_reason"],
        "rejection_score": row["rejection_score"],
        "entry_price": row["entry_price"],
        "keywords": keywords,
        "source": row["source"],
        "headline": row["headline"],
        "outcomes": {
            "1h": {
                "price": row["price_1h"],
                "return_pct": row["return_1h_pct"],
            },
            "4h": {
                "price": row["price_4h"],
                "return_pct": row["return_4h_pct"],
            },
            "24h": {
                "price": row["price_24h"],
                "return_pct": row["return_24h_pct"],
            },
            "7d": {
                "price": row["price_7d"],
                "return_pct": row["return_7d_pct"],
            },
        },
        "max_return_pct": round(max_return, 2),
        "is_missed_opportunity": max_return >= MISSED_OPPORTUNITY_THRESHOLD_PCT,
    }


def get_missed_opportunities(days: int = 7, threshold_pct: float = 10.0) -> List[dict]:
    """
    Get items that were missed opportunities (rejected but went up significantly).

    Args:
        days: Look back period in days
        threshold_pct: Minimum return to be considered "missed"

    Returns:
        List of missed opportunity records
    """
    try:
        db_path = get_db_path()

        with sqlite3.connect(db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                """
                SELECT * FROM rejected_items
                WHERE rejected_at > datetime('now', ? || ' days')
                AND (
                    return_1h_pct >= ?
                    OR return_4h_pct >= ?
                    OR return_24h_pct >= ?
                    OR return_7d_pct >= ?
                )
                ORDER BY
                    COALESCE(return_24h_pct, 0) DESC,
                    COALESCE(return_7d_pct, 0) DESC
                LIMIT 50
            """,
                (f"-{days}", threshold_pct, threshold_pct, threshold_pct, threshold_pct),
            )
            return [dict(row) for row in cursor.fetchall()]

    except Exception as e:
        log.warning("get_missed_opportunities_failed error=%s", e)
        return []


def get_outcome_summary(days: int = 7) -> dict:
    """
    Get summary statistics for outcome tracking.

    Args:
        days: Look back period

    Returns:
        Dictionary with summary statistics
    """
    try:
        db_path = get_db_path()

        with sqlite3.connect(db_path) as conn:
            summary = {}

            # Total tracked
            cursor = conn.execute(
                """
                SELECT COUNT(*) FROM rejected_items
                WHERE rejected_at > datetime('now', ? || ' days')
            """,
                (f"-{days}",),
            )
            summary["total_rejections"] = cursor.fetchone()[0]

            # With complete tracking
            cursor = conn.execute(
                """
                SELECT COUNT(*) FROM rejected_items
                WHERE rejected_at > datetime('now', ? || ' days')
                AND tracking_complete = TRUE
            """,
                (f"-{days}",),
            )
            summary["tracking_complete"] = cursor.fetchone()[0]

            # Missed opportunities
            cursor = conn.execute(
                """
                SELECT COUNT(*) FROM rejected_items
                WHERE rejected_at > datetime('now', ? || ' days')
                AND (
                    return_24h_pct >= 10
                    OR return_7d_pct >= 10
                )
            """,
                (f"-{days}",),
            )
            summary["missed_opportunities"] = cursor.fetchone()[0]

            # Average returns
            cursor = conn.execute(
                """
                SELECT
                    AVG(return_1h_pct),
                    AVG(return_4h_pct),
                    AVG(return_24h_pct),
                    AVG(return_7d_pct)
                FROM rejected_items
                WHERE rejected_at > datetime('now', ? || ' days')
                AND return_24h_pct IS NOT NULL
            """,
                (f"-{days}",),
            )
            row = cursor.fetchone()
            if row and row[0] is not None:
                summary["avg_returns"] = {
                    "1h": round(row[0] or 0, 2),
                    "4h": round(row[1] or 0, 2),
                    "24h": round(row[2] or 0, 2),
                    "7d": round(row[3] or 0, 2),
                }

            # Miss rate
            if summary["total_rejections"] > 0:
                summary["miss_rate_pct"] = round(
                    (summary["missed_opportunities"] / summary["total_rejections"])
                    * 100,
                    1,
                )

            return summary

    except Exception as e:
        log.warning("get_outcome_summary_failed error=%s", e)
        return {"error": str(e)}
