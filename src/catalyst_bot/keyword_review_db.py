"""
MOA Keyword Review Database Module
===================================

SQLite database for managing keyword review workflow with audit trail.

Tables:
- keyword_reviews: Main review record with state tracking
- keyword_changes: Individual keyword changes with evidence
- keyword_stats_snapshots: Full snapshots for rollback capability

Author: Claude Code (MOA Human-in-the-Loop Enhancement)
Date: 2025-11-12
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from .logging_utils import get_logger

log = get_logger("keyword_review_db")

# Database path
DB_PATH = Path("data/keyword_review.db")


def init_review_database() -> Path:
    """
    Initialize keyword review database with tables and indexes.

    Returns
    -------
    Path
        Path to initialized database file

    Notes
    -----
    Uses WAL mode for concurrent read/write access.
    Creates tables if they don't exist.
    """
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA foreign_keys=ON")

    # Table 1: keyword_reviews - Main review record
    conn.execute("""
        CREATE TABLE IF NOT EXISTS keyword_reviews (
            review_id TEXT PRIMARY KEY,
            state TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            expires_at TEXT,
            total_keywords INTEGER NOT NULL,
            approved_count INTEGER DEFAULT 0,
            rejected_count INTEGER DEFAULT 0,
            skipped_count INTEGER DEFAULT 0,
            applied_at TEXT,
            applied_by TEXT,
            reviewer_id TEXT,
            discord_message_id TEXT,
            source_analysis_path TEXT,
            notes TEXT
        )
    """)

    # Table 2: keyword_changes - Individual keyword changes
    conn.execute("""
        CREATE TABLE IF NOT EXISTS keyword_changes (
            change_id INTEGER PRIMARY KEY AUTOINCREMENT,
            review_id TEXT NOT NULL,
            keyword TEXT NOT NULL,
            old_weight REAL,
            new_weight REAL NOT NULL,
            weight_delta REAL NOT NULL,
            confidence REAL NOT NULL,
            occurrences INTEGER NOT NULL,
            success_rate REAL NOT NULL,
            avg_return_pct REAL NOT NULL,
            evidence_json TEXT,
            status TEXT NOT NULL,
            reviewed_at TEXT,
            FOREIGN KEY (review_id) REFERENCES keyword_reviews(review_id) ON DELETE CASCADE
        )
    """)

    # Table 3: keyword_stats_snapshots - Rollback support
    conn.execute("""
        CREATE TABLE IF NOT EXISTS keyword_stats_snapshots (
            snapshot_id INTEGER PRIMARY KEY AUTOINCREMENT,
            review_id TEXT NOT NULL,
            snapshot_at TEXT NOT NULL,
            snapshot_data TEXT NOT NULL,
            FOREIGN KEY (review_id) REFERENCES keyword_reviews(review_id) ON DELETE CASCADE
        )
    """)

    # Indexes for fast queries
    conn.execute("CREATE INDEX IF NOT EXISTS idx_reviews_state ON keyword_reviews(state)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_reviews_created ON keyword_reviews(created_at)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_reviews_expires ON keyword_reviews(expires_at)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_changes_review ON keyword_changes(review_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_changes_keyword ON keyword_changes(keyword)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_changes_status ON keyword_changes(status)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_snapshots_review ON keyword_stats_snapshots(review_id)")

    conn.commit()
    conn.close()

    log.info(f"keyword_review_db_initialized path={DB_PATH}")
    return DB_PATH


def get_connection() -> sqlite3.Connection:
    """
    Get optimized database connection with row factory.

    Returns
    -------
    sqlite3.Connection
        Database connection with Row factory enabled
    """
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def create_review_record(
    review_id: str,
    total_keywords: int,
    expires_at: Optional[str] = None,
    source_analysis_path: Optional[str] = None,
) -> bool:
    """
    Create new review record in PENDING state.

    Parameters
    ----------
    review_id : str
        Unique review identifier (e.g., "moa_review_2025-11-12_01-30")
    total_keywords : int
        Total number of keywords in this review
    expires_at : str, optional
        ISO timestamp when review expires and auto-applies
    source_analysis_path : str, optional
        Path to MOA analysis_report.json that generated recommendations

    Returns
    -------
    bool
        True if created successfully, False if already exists
    """
    now = datetime.now(timezone.utc).isoformat()

    try:
        conn = get_connection()
        conn.execute("""
            INSERT INTO keyword_reviews (
                review_id, state, created_at, updated_at, expires_at,
                total_keywords, source_analysis_path
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (review_id, "PENDING", now, now, expires_at, total_keywords, source_analysis_path))
        conn.commit()
        conn.close()

        log.info(f"review_record_created review_id={review_id} keywords={total_keywords} expires_at={expires_at}")
        return True

    except sqlite3.IntegrityError:
        log.warning(f"review_record_exists review_id={review_id}")
        return False


def insert_keyword_change(
    review_id: str,
    keyword: str,
    old_weight: Optional[float],
    new_weight: float,
    confidence: float,
    occurrences: int,
    success_rate: float,
    avg_return_pct: float,
    evidence: Optional[Dict[str, Any]] = None,
) -> bool:
    """
    Insert individual keyword change for review.

    Parameters
    ----------
    review_id : str
        Parent review ID
    keyword : str
        Keyword being changed
    old_weight : float, optional
        Current weight (None for new keywords)
    new_weight : float
        Recommended new weight
    confidence : float
        Confidence level (0.0-1.0)
    occurrences : int
        Number of times keyword appeared
    success_rate : float
        Success rate (0.0-1.0)
    avg_return_pct : float
        Average return percentage
    evidence : dict, optional
        Additional evidence (top tickers, timeframe breakdown, etc.)

    Returns
    -------
    bool
        True if inserted successfully
    """
    weight_delta = new_weight - (old_weight or 1.0)
    evidence_json = json.dumps(evidence) if evidence else None

    try:
        conn = get_connection()
        conn.execute("""
            INSERT INTO keyword_changes (
                review_id, keyword, old_weight, new_weight, weight_delta,
                confidence, occurrences, success_rate, avg_return_pct,
                evidence_json, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            review_id, keyword, old_weight, new_weight, weight_delta,
            confidence, occurrences, success_rate, avg_return_pct,
            evidence_json, "PENDING"
        ))
        conn.commit()
        conn.close()

        log.debug(f"keyword_change_inserted review_id={review_id} keyword={keyword} delta={weight_delta:+.2f}")
        return True

    except Exception as e:
        log.error(f"keyword_change_insert_failed review_id={review_id} keyword={keyword} err={e}")
        return False


def create_snapshot(review_id: str, snapshot_data: Dict[str, Any]) -> bool:
    """
    Create snapshot of current keyword_stats.json for rollback.

    Parameters
    ----------
    review_id : str
        Review ID this snapshot belongs to
    snapshot_data : dict
        Full content of keyword_stats.json

    Returns
    -------
    bool
        True if snapshot created successfully
    """
    now = datetime.now(timezone.utc).isoformat()
    snapshot_json = json.dumps(snapshot_data)

    try:
        conn = get_connection()
        conn.execute("""
            INSERT INTO keyword_stats_snapshots (review_id, snapshot_at, snapshot_data)
            VALUES (?, ?, ?)
        """, (review_id, now, snapshot_json))
        conn.commit()
        conn.close()

        log.info(f"snapshot_created review_id={review_id} size={len(snapshot_json)} bytes")
        return True

    except Exception as e:
        log.error(f"snapshot_create_failed review_id={review_id} err={e}")
        return False


def get_review(review_id: str) -> Optional[Dict[str, Any]]:
    """
    Get review record by ID.

    Parameters
    ----------
    review_id : str
        Review identifier

    Returns
    -------
    dict or None
        Review record as dictionary, or None if not found
    """
    try:
        conn = get_connection()
        cursor = conn.execute("""
            SELECT * FROM keyword_reviews WHERE review_id = ?
        """, (review_id,))
        row = cursor.fetchone()
        conn.close()

        if row:
            return dict(row)
        return None

    except Exception as e:
        log.error(f"get_review_failed review_id={review_id} err={e}")
        return None


def get_keyword_changes(review_id: str, status: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Get all keyword changes for a review, optionally filtered by status.

    Parameters
    ----------
    review_id : str
        Review identifier
    status : str, optional
        Filter by status (PENDING, APPROVED, REJECTED, SKIPPED)

    Returns
    -------
    list of dict
        List of keyword change records
    """
    try:
        conn = get_connection()

        if status:
            cursor = conn.execute("""
                SELECT * FROM keyword_changes
                WHERE review_id = ? AND status = ?
                ORDER BY confidence DESC, avg_return_pct DESC
            """, (review_id, status))
        else:
            cursor = conn.execute("""
                SELECT * FROM keyword_changes
                WHERE review_id = ?
                ORDER BY confidence DESC, avg_return_pct DESC
            """, (review_id,))

        rows = cursor.fetchall()
        conn.close()

        return [dict(row) for row in rows]

    except Exception as e:
        log.error(f"get_keyword_changes_failed review_id={review_id} err={e}")
        return []


def update_review_state(review_id: str, new_state: str, **kwargs) -> bool:
    """
    Update review state and optional fields.

    Parameters
    ----------
    review_id : str
        Review identifier
    new_state : str
        New state (PENDING, APPROVED, REJECTED, APPLIED, ROLLED_BACK)
    **kwargs : dict
        Additional fields to update (reviewer_id, applied_at, applied_by, notes, etc.)

    Returns
    -------
    bool
        True if updated successfully
    """
    now = datetime.now(timezone.utc).isoformat()

    # Build dynamic update query
    fields = ["state = ?", "updated_at = ?"]
    values = [new_state, now]

    for key, value in kwargs.items():
        fields.append(f"{key} = ?")
        values.append(value)

    values.append(review_id)

    try:
        conn = get_connection()
        query = f"UPDATE keyword_reviews SET {', '.join(fields)} WHERE review_id = ?"
        conn.execute(query, values)
        conn.commit()
        conn.close()

        log.info(f"review_state_updated review_id={review_id} new_state={new_state} fields={list(kwargs.keys())}")
        return True

    except Exception as e:
        log.error(f"update_review_state_failed review_id={review_id} err={e}")
        return False


def update_keyword_status(
    review_id: str,
    keyword: str,
    new_status: str,
    reviewer_id: Optional[str] = None,
) -> bool:
    """
    Update status of individual keyword change.

    Parameters
    ----------
    review_id : str
        Review identifier
    keyword : str
        Keyword to update
    new_status : str
        New status (APPROVED, REJECTED, SKIPPED)
    reviewer_id : str, optional
        ID of user who made the decision

    Returns
    -------
    bool
        True if updated successfully
    """
    now = datetime.now(timezone.utc).isoformat()

    try:
        conn = get_connection()
        conn.execute("""
            UPDATE keyword_changes
            SET status = ?, reviewed_at = ?
            WHERE review_id = ? AND keyword = ?
        """, (new_status, now, review_id, keyword))

        # Update parent review counts
        conn.execute(f"""
            UPDATE keyword_reviews
            SET {new_status.lower()}_count = (
                SELECT COUNT(*) FROM keyword_changes
                WHERE review_id = ? AND status = ?
            ),
            updated_at = ?
            WHERE review_id = ?
        """, (review_id, new_status, now, review_id))

        conn.commit()
        conn.close()

        log.debug(f"keyword_status_updated review_id={review_id} keyword={keyword} status={new_status}")
        return True

    except Exception as e:
        log.error(f"update_keyword_status_failed review_id={review_id} keyword={keyword} err={e}")
        return False


def get_pending_reviews() -> List[Dict[str, Any]]:
    """
    Get all reviews in PENDING state.

    Returns
    -------
    list of dict
        List of pending review records
    """
    try:
        conn = get_connection()
        cursor = conn.execute("""
            SELECT * FROM keyword_reviews
            WHERE state = 'PENDING'
            ORDER BY created_at DESC
        """)
        rows = cursor.fetchall()
        conn.close()

        return [dict(row) for row in rows]

    except Exception as e:
        log.error(f"get_pending_reviews_failed err={e}")
        return []


def get_expired_reviews(timeout_hours: int = 48) -> List[Dict[str, Any]]:
    """
    Get all PENDING reviews that have expired.

    Parameters
    ----------
    timeout_hours : int
        Hours after which a review is considered expired (default: 48)

    Returns
    -------
    list of dict
        List of expired review records
    """
    try:
        now = datetime.now(timezone.utc).isoformat()

        conn = get_connection()
        cursor = conn.execute("""
            SELECT * FROM keyword_reviews
            WHERE state = 'PENDING' AND expires_at IS NOT NULL AND expires_at < ?
            ORDER BY expires_at ASC
        """, (now,))
        rows = cursor.fetchall()
        conn.close()

        return [dict(row) for row in rows]

    except Exception as e:
        log.error(f"get_expired_reviews_failed err={e}")
        return []


def get_latest_snapshot(review_id: str) -> Optional[Dict[str, Any]]:
    """
    Get most recent snapshot for a review (for rollback).

    Parameters
    ----------
    review_id : str
        Review identifier

    Returns
    -------
    dict or None
        Snapshot data as dictionary, or None if no snapshot found
    """
    try:
        conn = get_connection()
        cursor = conn.execute("""
            SELECT snapshot_data FROM keyword_stats_snapshots
            WHERE review_id = ?
            ORDER BY snapshot_at DESC
            LIMIT 1
        """, (review_id,))
        row = cursor.fetchone()
        conn.close()

        if row:
            return json.loads(row["snapshot_data"])
        return None

    except Exception as e:
        log.error(f"get_latest_snapshot_failed review_id={review_id} err={e}")
        return None
