"""
Migration 004: Add Discord Message Tracking
============================================

Adds columns to track Discord message IDs and thread IDs for alerts,
enabling thread-based trade notifications.

Run with:
    python -m catalyst_bot.migrations.migrate

Tables modified:
    - alert_performance: Add discord_message_id, discord_channel_id, discord_thread_id

New table created:
    - trade_notifications: Track trade notification messages
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

MIGRATION_ID = "004_add_discord_tracking"


def upgrade(conn: sqlite3.Connection) -> None:
    """
    Add Discord tracking columns to alert_performance table.
    Create trade_notifications table for trade message tracking.
    """
    cursor = conn.cursor()

    # Add Discord columns to alert_performance if they don't exist
    # SQLite doesn't support IF NOT EXISTS for ALTER TABLE, so we check first
    cursor.execute("PRAGMA table_info(alert_performance)")
    existing_columns = {row[1] for row in cursor.fetchall()}

    if "discord_message_id" not in existing_columns:
        cursor.execute(
            "ALTER TABLE alert_performance ADD COLUMN discord_message_id TEXT"
        )

    if "discord_channel_id" not in existing_columns:
        cursor.execute(
            "ALTER TABLE alert_performance ADD COLUMN discord_channel_id TEXT"
        )

    if "discord_thread_id" not in existing_columns:
        cursor.execute(
            "ALTER TABLE alert_performance ADD COLUMN discord_thread_id TEXT"
        )

    # Create index for message ID lookups
    cursor.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_alert_discord_message
        ON alert_performance(discord_message_id)
        """
    )

    # Create trade_notifications table for tracking trade embeds
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS trade_notifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,

            -- Links to alert and position
            alert_id TEXT NOT NULL,
            position_id TEXT NOT NULL,

            -- Discord identifiers
            thread_id TEXT NOT NULL,
            entry_message_id TEXT,
            exit_message_id TEXT,

            -- Trade details for reference
            ticker TEXT NOT NULL,
            side TEXT NOT NULL,
            quantity INTEGER NOT NULL,
            entry_price REAL NOT NULL,
            exit_price REAL,

            -- P&L tracking
            realized_pnl REAL,
            realized_pnl_pct REAL,

            -- Timestamps
            entry_notified_at INTEGER NOT NULL,
            exit_notified_at INTEGER,

            -- Status
            status TEXT NOT NULL DEFAULT 'open',

            UNIQUE(alert_id, position_id)
        )
        """
    )

    # Indexes for efficient queries
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_trade_notif_alert ON trade_notifications(alert_id)"
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_trade_notif_position ON trade_notifications(position_id)"
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_trade_notif_thread ON trade_notifications(thread_id)"
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_trade_notif_status ON trade_notifications(status)"
    )

    conn.commit()


def downgrade(conn: sqlite3.Connection) -> None:
    """
    Remove Discord tracking (for rollback).

    Note: SQLite doesn't support DROP COLUMN in older versions,
    so we only drop the trade_notifications table.
    """
    cursor = conn.cursor()

    cursor.execute("DROP TABLE IF EXISTS trade_notifications")
    cursor.execute("DROP INDEX IF EXISTS idx_alert_discord_message")

    conn.commit()


def check_applied(conn: sqlite3.Connection) -> bool:
    """Check if migration has been applied."""
    cursor = conn.cursor()

    # Check if trade_notifications table exists
    cursor.execute(
        """
        SELECT name FROM sqlite_master
        WHERE type='table' AND name='trade_notifications'
        """
    )
    return cursor.fetchone() is not None


if __name__ == "__main__":
    # Allow running migration directly for testing
    import os
    import sys

    # Add parent to path for imports
    sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

    from catalyst_bot.feedback.database import _get_db_path

    db_path = _get_db_path()
    print(f"Running migration on: {db_path}")

    conn = sqlite3.connect(str(db_path))
    try:
        if check_applied(conn):
            print("Migration already applied")
        else:
            upgrade(conn)
            print("Migration applied successfully")
    finally:
        conn.close()
