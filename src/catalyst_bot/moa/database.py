"""
MOA Rejected Items Database.

SQLite database for tracking rejected items and their price outcomes.
Enables real-time MOA analysis with fresh data.
"""

import sqlite3
from pathlib import Path
from typing import Optional

from ..logging_utils import get_logger

log = get_logger("moa.database")

# Database path
DB_PATH = Path("data/moa/rejected_tracking.db")


def get_db_path() -> Path:
    """Get the database path, ensuring directory exists."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    return DB_PATH


def get_connection() -> sqlite3.Connection:
    """Get a database connection with row factory enabled."""
    conn = sqlite3.connect(get_db_path())
    conn.row_factory = sqlite3.Row
    return conn


def init_database() -> bool:
    """
    Initialize the rejected items database schema.

    Returns:
        True if successful, False otherwise
    """
    try:
        db_path = get_db_path()

        with sqlite3.connect(db_path) as conn:
            # Enable WAL mode for better concurrent access
            conn.execute("PRAGMA journal_mode=WAL")

            # Create rejected_items table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS rejected_items (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ticker TEXT NOT NULL,
                    rejected_at TIMESTAMP NOT NULL,
                    rejection_reason TEXT NOT NULL,
                    rejection_score REAL,
                    entry_price REAL NOT NULL,
                    keywords TEXT,
                    source TEXT,
                    headline TEXT,

                    -- Price outcomes (updated incrementally)
                    price_1h REAL,
                    price_4h REAL,
                    price_24h REAL,
                    price_7d REAL,

                    -- Calculated returns
                    return_1h_pct REAL,
                    return_4h_pct REAL,
                    return_24h_pct REAL,
                    return_7d_pct REAL,

                    -- Tracking status
                    tracking_complete BOOLEAN DEFAULT FALSE,
                    last_updated TIMESTAMP,

                    -- Prevent duplicate entries
                    UNIQUE(ticker, rejected_at)
                )
            """)

            # Create indexes for efficient queries
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_rejected_pending
                ON rejected_items(tracking_complete, rejected_at)
            """)

            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_rejected_ticker
                ON rejected_items(ticker)
            """)

            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_rejected_reason
                ON rejected_items(rejection_reason)
            """)

            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_rejected_date
                ON rejected_items(rejected_at DESC)
            """)

            # ================================================================
            # Manual Captures Table (Jan 2026)
            # Stores manually submitted missed opportunities from Discord
            # ================================================================
            conn.execute("""
                CREATE TABLE IF NOT EXISTS manual_captures (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ticker TEXT NOT NULL,
                    submitted_at TIMESTAMP NOT NULL,
                    discord_user_id TEXT,
                    discord_message_id TEXT,

                    -- Article extraction (from vision LLM)
                    headline TEXT,
                    source TEXT,
                    article_timestamp TEXT,
                    catalyst_type TEXT,
                    keywords TEXT,
                    sentiment TEXT,

                    -- Chart extraction (from vision LLM)
                    chart_timeframe TEXT,
                    chart_pattern TEXT,
                    entry_price REAL,
                    peak_price REAL,
                    pct_move REAL,
                    volume_spike BOOLEAN,

                    -- Enrichment
                    current_price REAL,
                    was_in_rejected BOOLEAN DEFAULT FALSE,
                    rejection_id INTEGER REFERENCES rejected_items(id),

                    -- Image storage
                    article_image_path TEXT,
                    chart_5m_image_path TEXT,
                    chart_daily_image_path TEXT,

                    -- User notes
                    user_notes TEXT,

                    -- Processing status
                    processed BOOLEAN DEFAULT FALSE,
                    llm_response TEXT,

                    -- Prevent duplicate entries
                    UNIQUE(ticker, submitted_at)
                )
            """)

            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_manual_ticker
                ON manual_captures(ticker)
            """)

            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_manual_catalyst
                ON manual_captures(catalyst_type)
            """)

            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_manual_date
                ON manual_captures(submitted_at DESC)
            """)

            conn.commit()

        # Run migration to add tracking columns to manual_captures
        migrate_manual_captures_add_tracking()

        log.info("moa_database_initialized path=%s", db_path)
        return True

    except Exception as e:
        log.error("moa_database_init_failed error=%s", e, exc_info=True)
        return False


def get_pending_count() -> int:
    """Get count of items pending outcome tracking."""
    try:
        with get_connection() as conn:
            cursor = conn.execute("""
                SELECT COUNT(*) FROM rejected_items
                WHERE tracking_complete = FALSE
                AND rejected_at > datetime('now', '-8 days')
            """)
            return cursor.fetchone()[0]
    except Exception as e:
        log.warning("get_pending_count_failed error=%s", e)
        return 0


def get_total_count() -> int:
    """Get total count of tracked rejections."""
    try:
        with get_connection() as conn:
            cursor = conn.execute("SELECT COUNT(*) FROM rejected_items")
            return cursor.fetchone()[0]
    except Exception as e:
        log.warning("get_total_count_failed error=%s", e)
        return 0


def purge_old_records(days: int = 30) -> int:
    """
    Remove records older than specified days.

    Args:
        days: Records older than this will be deleted

    Returns:
        Number of records deleted
    """
    try:
        with get_connection() as conn:
            cursor = conn.execute("""
                DELETE FROM rejected_items
                WHERE rejected_at < datetime('now', ? || ' days')
            """, (f"-{days}",))
            conn.commit()
            deleted = cursor.rowcount
            if deleted > 0:
                log.info("moa_records_purged count=%d days=%d", deleted, days)
            return deleted
    except Exception as e:
        log.warning("purge_old_records_failed error=%s", e)
        return 0


def migrate_manual_captures_add_tracking() -> bool:
    """
    Migrate manual_captures table to add forward price tracking columns.
    Safe to run multiple times (checks if columns already exist).

    Returns:
        True if successful, False otherwise
    """
    try:
        db_path = get_db_path()

        with sqlite3.connect(db_path) as conn:
            # Check if columns already exist
            cursor = conn.execute("PRAGMA table_info(manual_captures)")
            columns = {row[1] for row in cursor.fetchall()}

            if "price_1h" in columns:
                log.debug("manual_captures_tracking_columns_already_exist")
                return True

            # Add new columns for forward price tracking (matching rejected_items)
            conn.execute("ALTER TABLE manual_captures ADD COLUMN price_1h REAL")
            conn.execute("ALTER TABLE manual_captures ADD COLUMN price_4h REAL")
            conn.execute("ALTER TABLE manual_captures ADD COLUMN price_24h REAL")
            conn.execute("ALTER TABLE manual_captures ADD COLUMN price_7d REAL")

            conn.execute("ALTER TABLE manual_captures ADD COLUMN return_1h_pct REAL")
            conn.execute("ALTER TABLE manual_captures ADD COLUMN return_4h_pct REAL")
            conn.execute("ALTER TABLE manual_captures ADD COLUMN return_24h_pct REAL")
            conn.execute("ALTER TABLE manual_captures ADD COLUMN return_7d_pct REAL")

            conn.execute(
                "ALTER TABLE manual_captures ADD COLUMN tracking_complete BOOLEAN DEFAULT FALSE"
            )
            conn.execute("ALTER TABLE manual_captures ADD COLUMN last_updated TIMESTAMP")

            # Create index for efficient pending queries
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_manual_pending
                ON manual_captures(tracking_complete, submitted_at)
            """)

            conn.commit()

            log.info("manual_captures_migration_complete added_tracking_columns")
            return True

    except Exception as e:
        log.error("manual_captures_migration_failed error=%s", e, exc_info=True)
        return False


def get_database_stats() -> dict:
    """Get database statistics for monitoring."""
    try:
        with get_connection() as conn:
            stats = {}

            # Total records
            cursor = conn.execute("SELECT COUNT(*) FROM rejected_items")
            stats["total_records"] = cursor.fetchone()[0]

            # Pending tracking
            cursor = conn.execute("""
                SELECT COUNT(*) FROM rejected_items
                WHERE tracking_complete = FALSE
                AND rejected_at > datetime('now', '-8 days')
            """)
            stats["pending_tracking"] = cursor.fetchone()[0]

            # Completed tracking
            cursor = conn.execute("""
                SELECT COUNT(*) FROM rejected_items
                WHERE tracking_complete = TRUE
            """)
            stats["completed_tracking"] = cursor.fetchone()[0]

            # Records by rejection reason
            cursor = conn.execute("""
                SELECT rejection_reason, COUNT(*) as count
                FROM rejected_items
                GROUP BY rejection_reason
                ORDER BY count DESC
                LIMIT 10
            """)
            stats["by_reason"] = {row[0]: row[1] for row in cursor.fetchall()}

            # Average returns for completed items
            cursor = conn.execute("""
                SELECT
                    AVG(return_1h_pct) as avg_1h,
                    AVG(return_4h_pct) as avg_4h,
                    AVG(return_24h_pct) as avg_24h,
                    AVG(return_7d_pct) as avg_7d,
                    MAX(return_24h_pct) as max_24h
                FROM rejected_items
                WHERE tracking_complete = TRUE
                AND return_24h_pct IS NOT NULL
            """)
            row = cursor.fetchone()
            if row:
                stats["avg_returns"] = {
                    "1h": round(row[0] or 0, 2),
                    "4h": round(row[1] or 0, 2),
                    "24h": round(row[2] or 0, 2),
                    "7d": round(row[3] or 0, 2),
                    "max_24h": round(row[4] or 0, 2),
                }

            return stats

    except Exception as e:
        log.warning("get_database_stats_failed error=%s", e)
        return {"error": str(e)}


# Initialize database on module import
init_database()
