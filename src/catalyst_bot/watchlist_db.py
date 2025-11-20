"""
Watchlist Performance Database
===============================

SQLite database for tracking watchlist tickers with HOT/WARM/COOL states
and their performance over time.

This module provides Phase 1 functionality for watchlist monitoring:
- Add/update tickers with rich trigger context
- Record performance snapshots at intervals
- Query tickers by state (HOT/WARM/COOL)
- Track lifecycle and state transitions

Phase 2-5 expansion ready: Schema includes reserved columns for technical
indicators, breakout detection, and signal generation.
"""

from __future__ import annotations

import json
import os
import sqlite3
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .logging_utils import get_logger

log = get_logger("watchlist_db")

# Default database path
DEFAULT_DB_PATH = Path("data/watchlist/performance.db")


def _get_db_path() -> Path:
    """Get the database path from env or use default."""
    db_path_str = os.getenv("WATCHLIST_PERFORMANCE_DB_PATH", str(DEFAULT_DB_PATH))
    db_path = Path(db_path_str).resolve()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return db_path


def _get_connection() -> sqlite3.Connection:
    """Get a database connection with row factory and optimized pragmas."""
    from .storage import init_optimized_connection

    db_path = _get_db_path()
    conn = init_optimized_connection(str(db_path))
    conn.row_factory = sqlite3.Row
    return conn


def init_database() -> None:
    """
    Create database and tables if they don't exist.

    This function is idempotent and safe to call multiple times.
    Loads schema from docs/schema/watchlist_performance_schema.sql
    """
    db_path = _get_db_path()
    log.info("initializing_watchlist_database path=%s", db_path)

    # Read schema file
    schema_path = Path(__file__).parent.parent.parent / "docs" / "schema" / "watchlist_performance_schema.sql"

    if not schema_path.exists():
        log.warning("schema_file_not_found path=%s falling_back_to_inline", schema_path)
        # Fallback: create tables inline if schema file not found
        _create_tables_inline()
        return

    conn = _get_connection()
    try:
        with open(schema_path, "r", encoding="utf-8") as f:
            schema_sql = f.read()

        conn.executescript(schema_sql)
        conn.commit()
        log.info("watchlist_database_initialized from_file=%s", schema_path)

    except Exception as e:
        log.error("watchlist_database_init_failed error=%s", str(e))
        conn.rollback()
        raise
    finally:
        conn.close()


def _create_tables_inline() -> None:
    """Fallback: create core tables inline if schema file not found."""
    conn = _get_connection()
    try:
        cursor = conn.cursor()

        # Create main tickers table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS watchlist_tickers (
                ticker TEXT PRIMARY KEY NOT NULL,
                state TEXT NOT NULL DEFAULT 'HOT'
                    CHECK(state IN ('HOT', 'WARM', 'COOL')),
                last_state_change INTEGER NOT NULL,
                previous_state TEXT
                    CHECK(previous_state IS NULL OR previous_state IN ('HOT', 'WARM', 'COOL')),
                state_transition_count INTEGER DEFAULT 1,
                promoted_count INTEGER DEFAULT 1,

                -- Trigger context
                trigger_reason TEXT,
                trigger_title TEXT,
                trigger_summary TEXT,
                catalyst_type TEXT,
                trigger_score REAL,
                trigger_sentiment REAL,
                trigger_price REAL,
                trigger_volume REAL,
                trigger_timestamp INTEGER NOT NULL,
                alert_id TEXT,

                -- Monitoring config
                check_interval_seconds INTEGER,
                next_check_at INTEGER NOT NULL,
                last_checked_at INTEGER,
                check_count INTEGER DEFAULT 0,
                monitoring_enabled INTEGER DEFAULT 1
                    CHECK(monitoring_enabled IN (0, 1)),

                -- Performance summary
                latest_price REAL,
                latest_volume REAL,
                latest_rvol REAL,
                latest_vwap REAL,
                price_change_pct REAL,
                price_change_since_hot REAL,
                max_price_seen REAL,
                min_price_seen REAL,
                snapshot_count INTEGER DEFAULT 0,
                last_snapshot_at INTEGER,

                -- Reserved for Phase 2-5
                rsi_14 REAL,
                macd_signal REAL,
                bb_position REAL,
                volume_sma_20 REAL,
                atr_14 REAL,
                breakout_confirmed INTEGER DEFAULT 0
                    CHECK(breakout_confirmed IN (0, 1)),
                breakout_type TEXT,
                breakout_timestamp INTEGER,
                resistance_level REAL,
                support_level REAL,
                risk_score REAL,
                position_size_suggested REAL,
                stop_loss_price REAL,
                take_profit_price REAL,

                -- Metadata
                tags TEXT,
                metadata TEXT,
                notes TEXT,

                -- Timestamps
                created_at INTEGER NOT NULL,
                updated_at INTEGER NOT NULL,
                removed_at INTEGER,

                CHECK(trigger_price IS NULL OR trigger_price > 0),
                CHECK(trigger_volume IS NULL OR trigger_volume >= 0),
                CHECK(check_interval_seconds IS NULL OR check_interval_seconds > 0),
                CHECK(snapshot_count >= 0),
                CHECK(check_count >= 0)
            )
        """)

        # Create snapshots table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS performance_snapshots (
                snapshot_id INTEGER PRIMARY KEY AUTOINCREMENT,
                ticker TEXT NOT NULL,
                snapshot_at INTEGER NOT NULL,

                -- Price data
                price REAL NOT NULL,
                price_change_pct REAL,
                price_change_since_last REAL,
                high_since_last REAL,
                low_since_last REAL,

                -- Volume data
                volume REAL,
                volume_change_pct REAL,
                rvol REAL,
                volume_surge INTEGER DEFAULT 0
                    CHECK(volume_surge IN (0, 1)),

                -- Trading data
                vwap REAL,
                bid REAL,
                ask REAL,
                spread REAL,
                trade_count INTEGER,

                -- Market context
                market_state TEXT
                    CHECK(market_state IS NULL OR
                          market_state IN ('premarket', 'regular', 'aftermarket', 'closed')),

                -- Reserved for Phase 2-5
                rsi_14 REAL,
                rsi_trend TEXT,
                macd_value REAL,
                macd_signal REAL,
                macd_histogram REAL,
                bb_upper REAL,
                bb_middle REAL,
                bb_lower REAL,
                bb_width REAL,
                sma_20 REAL,
                sma_50 REAL,
                ema_12 REAL,
                ema_26 REAL,
                atr_14 REAL,
                obv REAL,
                pattern_detected TEXT,
                pattern_confidence REAL,
                trend_direction TEXT,
                momentum_score REAL,
                buy_signal INTEGER DEFAULT 0
                    CHECK(buy_signal IN (0, 1)),
                sell_signal INTEGER DEFAULT 0
                    CHECK(sell_signal IN (0, 1)),
                signal_strength REAL,
                signal_type TEXT,

                -- Metadata
                data_source TEXT,
                data_quality REAL DEFAULT 1.0,
                is_estimated INTEGER DEFAULT 0
                    CHECK(is_estimated IN (0, 1)),
                snapshot_metadata TEXT,

                FOREIGN KEY (ticker) REFERENCES watchlist_tickers(ticker)
                    ON DELETE CASCADE
                    ON UPDATE CASCADE,

                CHECK(price > 0),
                CHECK(volume IS NULL OR volume >= 0),
                CHECK(rvol IS NULL OR rvol >= 0)
            )
        """)

        # Create schema_version table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS schema_version (
                version INTEGER PRIMARY KEY,
                applied_at INTEGER NOT NULL DEFAULT (strftime('%s', 'now')),
                description TEXT
            )
        """)

        cursor.execute("""
            INSERT OR IGNORE INTO schema_version (version, description)
            VALUES (1, 'Initial watchlist performance tracking schema')
        """)

        # Create indexes
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_tickers_state_monitoring
            ON watchlist_tickers(state, monitoring_enabled)
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_tickers_next_check
            ON watchlist_tickers(next_check_at, monitoring_enabled)
            WHERE monitoring_enabled = 1
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_tickers_catalyst_type
            ON watchlist_tickers(catalyst_type)
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_tickers_trigger_timestamp
            ON watchlist_tickers(trigger_timestamp DESC)
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_tickers_state_change
            ON watchlist_tickers(state, last_state_change)
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_tickers_removed_at
            ON watchlist_tickers(removed_at)
            WHERE removed_at IS NULL
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_tickers_alert_id
            ON watchlist_tickers(alert_id)
            WHERE alert_id IS NOT NULL
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_snapshots_ticker_time
            ON performance_snapshots(ticker, snapshot_at DESC)
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_snapshots_time
            ON performance_snapshots(snapshot_at DESC)
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_snapshots_signals
            ON performance_snapshots(buy_signal, sell_signal)
            WHERE buy_signal = 1 OR sell_signal = 1
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_snapshots_volume_surge
            ON performance_snapshots(ticker, snapshot_at)
            WHERE volume_surge = 1
        """)

        conn.commit()
        log.info("watchlist_database_initialized inline_tables")

    except Exception as e:
        log.error("watchlist_database_init_failed error=%s", str(e))
        conn.rollback()
        raise
    finally:
        conn.close()


def add_ticker(
    ticker: str,
    state: str = "HOT",
    *,
    trigger_reason: Optional[str] = None,
    trigger_title: Optional[str] = None,
    trigger_summary: Optional[str] = None,
    catalyst_type: Optional[str] = None,
    trigger_score: Optional[float] = None,
    trigger_sentiment: Optional[float] = None,
    trigger_price: Optional[float] = None,
    trigger_volume: Optional[float] = None,
    alert_id: Optional[str] = None,
    check_interval_seconds: Optional[int] = None,
    tags: Optional[List[str]] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> bool:
    """
    Add or update a ticker in the watchlist.

    If ticker already exists, updates trigger context and resets to specified state.
    If ticker is new, creates a new record with trigger context.

    Parameters
    ----------
    ticker : str
        Ticker symbol (will be uppercased)
    state : str, default 'HOT'
        Initial state: HOT, WARM, or COOL
    trigger_reason : str, optional
        Short reason for addition (e.g., "FDA approval catalyst")
    trigger_title : str, optional
        Alert/news title that triggered addition
    trigger_summary : str, optional
        Longer summary of catalyst
    catalyst_type : str, optional
        Category: fda_approval, earnings, sec_filing, partnership, etc.
    trigger_score : float, optional
        Alert score (0.0-1.0)
    trigger_sentiment : float, optional
        Sentiment score (-1.0 to +1.0)
    trigger_price : float, optional
        Price when added
    trigger_volume : float, optional
        Volume when added
    alert_id : str, optional
        Link to original alert
    check_interval_seconds : int, optional
        Custom check interval (overrides state default)
    tags : list of str, optional
        Tags for categorization (e.g., ["biotech", "smallcap"])
    metadata : dict, optional
        Additional key-value pairs

    Returns
    -------
    bool
        True if successful, False otherwise
    """
    ticker = ticker.strip().upper()
    state = state.strip().upper()

    if state not in ("HOT", "WARM", "COOL"):
        log.error("invalid_state ticker=%s state=%s", ticker, state)
        return False

    conn = _get_connection()
    try:
        cursor = conn.cursor()
        now = int(time.time())

        # Serialize JSON fields
        tags_json = json.dumps(tags) if tags else None
        metadata_json = json.dumps(metadata) if metadata else None

        # Calculate next check time (use interval if provided, else default to 5 min)
        interval = check_interval_seconds if check_interval_seconds is not None else 300
        next_check = now + interval

        # Check if ticker exists
        cursor.execute(
            "SELECT ticker, promoted_count FROM watchlist_tickers WHERE ticker = ?",
            (ticker,)
        )
        existing = cursor.fetchone()

        if existing:
            # Update existing ticker
            log.info(
                "updating_ticker ticker=%s new_state=%s",
                ticker,
                state
            )

            # Increment promoted_count if returning to HOT
            promoted_count = existing["promoted_count"]
            if state == "HOT":
                promoted_count += 1

            cursor.execute("""
                UPDATE watchlist_tickers
                SET state = ?,
                    last_state_change = ?,
                    trigger_reason = COALESCE(?, trigger_reason),
                    trigger_title = COALESCE(?, trigger_title),
                    trigger_summary = COALESCE(?, trigger_summary),
                    catalyst_type = COALESCE(?, catalyst_type),
                    trigger_score = COALESCE(?, trigger_score),
                    trigger_sentiment = COALESCE(?, trigger_sentiment),
                    trigger_price = COALESCE(?, trigger_price),
                    trigger_volume = COALESCE(?, trigger_volume),
                    alert_id = COALESCE(?, alert_id),
                    check_interval_seconds = COALESCE(?, check_interval_seconds),
                    next_check_at = ?,
                    promoted_count = ?,
                    tags = COALESCE(?, tags),
                    metadata = COALESCE(?, metadata),
                    updated_at = ?,
                    removed_at = NULL
                WHERE ticker = ?
            """, (
                state,
                now,
                trigger_reason,
                trigger_title,
                trigger_summary,
                catalyst_type,
                trigger_score,
                trigger_sentiment,
                trigger_price,
                trigger_volume,
                alert_id,
                check_interval_seconds,
                next_check,
                promoted_count,
                tags_json,
                metadata_json,
                now,
                ticker
            ))
        else:
            # Insert new ticker
            log.info(
                "adding_ticker ticker=%s state=%s catalyst_type=%s",
                ticker,
                state,
                catalyst_type
            )

            cursor.execute("""
                INSERT INTO watchlist_tickers (
                    ticker, state, last_state_change, trigger_reason,
                    trigger_title, trigger_summary, catalyst_type,
                    trigger_score, trigger_sentiment, trigger_price,
                    trigger_volume, trigger_timestamp, alert_id,
                    check_interval_seconds, next_check_at,
                    monitoring_enabled, tags, metadata,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?, ?)
            """, (
                ticker,
                state,
                now,
                trigger_reason,
                trigger_title,
                trigger_summary,
                catalyst_type,
                trigger_score,
                trigger_sentiment,
                trigger_price,
                trigger_volume,
                now,
                alert_id,
                check_interval_seconds,
                next_check,
                tags_json,
                metadata_json,
                now,
                now
            ))

        conn.commit()
        return True

    except Exception as e:
        log.error("add_ticker_failed ticker=%s error=%s", ticker, str(e))
        conn.rollback()
        return False
    finally:
        conn.close()


def record_snapshot(
    ticker: str,
    price: float,
    *,
    volume: Optional[float] = None,
    rvol: Optional[float] = None,
    vwap: Optional[float] = None,
    price_change_pct: Optional[float] = None,
    volume_change_pct: Optional[float] = None,
    volume_surge: bool = False,
    market_state: Optional[str] = None,
    data_source: Optional[str] = None,
    snapshot_metadata: Optional[Dict[str, Any]] = None,
) -> bool:
    """
    Record a performance snapshot for a ticker.

    Automatically updates the watchlist_tickers table with latest performance data.

    Parameters
    ----------
    ticker : str
        Ticker symbol
    price : float
        Current price (required)
    volume : float, optional
        Current volume
    rvol : float, optional
        Relative volume (vs average)
    vwap : float, optional
        Volume-weighted average price
    price_change_pct : float, optional
        % change from trigger price
    volume_change_pct : float, optional
        % change from trigger volume
    volume_surge : bool, default False
        Whether a volume surge was detected
    market_state : str, optional
        Market state: premarket, regular, aftermarket, closed
    data_source : str, optional
        Data source: tiingo, polygon, yahoo, etc.
    snapshot_metadata : dict, optional
        Additional snapshot data

    Returns
    -------
    bool
        True if successful, False otherwise
    """
    ticker = ticker.strip().upper()

    conn = _get_connection()
    try:
        cursor = conn.cursor()
        now = int(time.time())

        # Serialize metadata
        metadata_json = json.dumps(snapshot_metadata) if snapshot_metadata else None

        # Insert snapshot
        cursor.execute("""
            INSERT INTO performance_snapshots (
                ticker, snapshot_at, price, volume, rvol, vwap,
                price_change_pct, volume_change_pct, volume_surge,
                market_state, data_source, snapshot_metadata
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            ticker,
            now,
            price,
            volume,
            rvol,
            vwap,
            price_change_pct,
            volume_change_pct,
            1 if volume_surge else 0,
            market_state,
            data_source,
            metadata_json
        ))

        # Update ticker's latest performance (denormalized for fast queries)
        cursor.execute("""
            UPDATE watchlist_tickers
            SET latest_price = ?,
                latest_volume = ?,
                latest_rvol = ?,
                latest_vwap = ?,
                price_change_pct = ?,
                snapshot_count = snapshot_count + 1,
                last_snapshot_at = ?,
                last_checked_at = ?,
                check_count = check_count + 1,
                max_price_seen = MAX(COALESCE(max_price_seen, ?), ?),
                min_price_seen = MIN(COALESCE(min_price_seen, ?), ?),
                updated_at = ?
            WHERE ticker = ?
        """, (
            price,
            volume,
            rvol,
            vwap,
            price_change_pct,
            now,
            now,
            price, price,
            price, price,
            now,
            ticker
        ))

        conn.commit()
        log.debug(
            "snapshot_recorded ticker=%s price=%.2f volume=%s rvol=%s",
            ticker,
            price,
            volume,
            rvol
        )
        return True

    except Exception as e:
        log.error("record_snapshot_failed ticker=%s error=%s", ticker, str(e))
        conn.rollback()
        return False
    finally:
        conn.close()


def get_tickers_by_state(
    state: str,
    include_removed: bool = False
) -> List[Dict[str, Any]]:
    """
    Get all tickers in a specific state.

    Parameters
    ----------
    state : str
        State to filter by: HOT, WARM, or COOL
    include_removed : bool, default False
        Whether to include soft-deleted tickers

    Returns
    -------
    list of dict
        List of ticker records with all fields
    """
    state = state.strip().upper()

    conn = _get_connection()
    try:
        cursor = conn.cursor()

        query = """
            SELECT * FROM watchlist_tickers
            WHERE state = ? AND monitoring_enabled = 1
        """

        if not include_removed:
            query += " AND removed_at IS NULL"

        query += " ORDER BY trigger_timestamp DESC"

        cursor.execute(query, (state,))
        rows = cursor.fetchall()

        return [dict(row) for row in rows]

    except Exception as e:
        log.error("get_tickers_by_state_failed state=%s error=%s", state, str(e))
        return []
    finally:
        conn.close()


def get_tickers_needing_check(limit: Optional[int] = None) -> List[Dict[str, Any]]:
    """
    Get tickers that need performance check based on next_check_at.

    Parameters
    ----------
    limit : int, optional
        Maximum number of tickers to return

    Returns
    -------
    list of dict
        List of tickers needing check, ordered by next_check_at (oldest first)
    """
    conn = _get_connection()
    try:
        cursor = conn.cursor()
        now = int(time.time())

        query = """
            SELECT * FROM watchlist_tickers
            WHERE next_check_at <= ?
                AND monitoring_enabled = 1
                AND removed_at IS NULL
            ORDER BY next_check_at ASC
        """

        params = [now]

        if limit is not None:
            query += " LIMIT ?"
            params.append(limit)

        cursor.execute(query, params)
        rows = cursor.fetchall()

        return [dict(row) for row in rows]

    except Exception as e:
        log.error("get_tickers_needing_check_failed error=%s", str(e))
        return []
    finally:
        conn.close()


def get_snapshots(
    ticker: str,
    limit: Optional[int] = None,
    since: Optional[int] = None
) -> List[Dict[str, Any]]:
    """
    Get performance snapshots for a ticker.

    Parameters
    ----------
    ticker : str
        Ticker symbol
    limit : int, optional
        Maximum number of snapshots to return (latest first)
    since : int, optional
        Unix timestamp - only return snapshots after this time

    Returns
    -------
    list of dict
        List of snapshot records, ordered by snapshot_at DESC
    """
    ticker = ticker.strip().upper()

    conn = _get_connection()
    try:
        cursor = conn.cursor()

        query = """
            SELECT * FROM performance_snapshots
            WHERE ticker = ?
        """

        params = [ticker]

        if since is not None:
            query += " AND snapshot_at >= ?"
            params.append(since)

        query += " ORDER BY snapshot_at DESC"

        if limit is not None:
            query += " LIMIT ?"
            params.append(limit)

        cursor.execute(query, params)
        rows = cursor.fetchall()

        return [dict(row) for row in rows]

    except Exception as e:
        log.error("get_snapshots_failed ticker=%s error=%s", ticker, str(e))
        return []
    finally:
        conn.close()


def update_next_check_time(ticker: str, interval_seconds: int) -> bool:
    """
    Update the next check time for a ticker.

    Parameters
    ----------
    ticker : str
        Ticker symbol
    interval_seconds : int
        Seconds until next check

    Returns
    -------
    bool
        True if successful, False otherwise
    """
    ticker = ticker.strip().upper()

    conn = _get_connection()
    try:
        cursor = conn.cursor()
        now = int(time.time())
        next_check = now + interval_seconds

        cursor.execute("""
            UPDATE watchlist_tickers
            SET next_check_at = ?,
                updated_at = ?
            WHERE ticker = ?
        """, (next_check, now, ticker))

        conn.commit()
        return cursor.rowcount > 0

    except Exception as e:
        log.error("update_next_check_failed ticker=%s error=%s", ticker, str(e))
        conn.rollback()
        return False
    finally:
        conn.close()


def get_state_counts() -> Dict[str, int]:
    """
    Get count of tickers by state.

    Returns
    -------
    dict
        Dictionary with state names as keys and counts as values
        Example: {'HOT': 5, 'WARM': 12, 'COOL': 3}
    """
    conn = _get_connection()
    try:
        cursor = conn.cursor()

        cursor.execute("""
            SELECT state, COUNT(*) as count
            FROM watchlist_tickers
            WHERE removed_at IS NULL
            GROUP BY state
        """)

        rows = cursor.fetchall()
        return {row["state"]: row["count"] for row in rows}

    except Exception as e:
        log.error("get_state_counts_failed error=%s", str(e))
        return {}
    finally:
        conn.close()


def remove_ticker(ticker: str, soft_delete: bool = True) -> bool:
    """
    Remove a ticker from the watchlist.

    Parameters
    ----------
    ticker : str
        Ticker symbol
    soft_delete : bool, default True
        If True, sets removed_at timestamp (preserves history)
        If False, deletes record permanently (CASCADE deletes snapshots)

    Returns
    -------
    bool
        True if successful, False otherwise
    """
    ticker = ticker.strip().upper()

    conn = _get_connection()
    try:
        cursor = conn.cursor()
        now = int(time.time())

        if soft_delete:
            cursor.execute("""
                UPDATE watchlist_tickers
                SET removed_at = ?,
                    monitoring_enabled = 0,
                    updated_at = ?
                WHERE ticker = ?
            """, (now, now, ticker))
            log.info("ticker_soft_deleted ticker=%s", ticker)
        else:
            cursor.execute("""
                DELETE FROM watchlist_tickers
                WHERE ticker = ?
            """, (ticker,))
            log.info("ticker_hard_deleted ticker=%s", ticker)

        conn.commit()
        return cursor.rowcount > 0

    except Exception as e:
        log.error("remove_ticker_failed ticker=%s error=%s", ticker, str(e))
        conn.rollback()
        return False
    finally:
        conn.close()
