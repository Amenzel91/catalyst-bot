# Watchlist Performance Tracking Schema Design

**Author:** Database Architect (Claude Code)
**Date:** 2025-11-20
**Schema Version:** 1.0
**Database:** SQLite 3.x

---

## Executive Summary

This document describes the database schema for the Catalyst Bot watchlist performance tracking system. The schema enables tracking of tickers through HOT/WARM/COOL states with comprehensive performance monitoring and historical analysis.

### Key Features

- **State-based tracking**: HOT → WARM → COOL lifecycle management
- **Rich trigger context**: Captures why each ticker was added (catalyst, score, sentiment)
- **Unlimited snapshots**: Time-series performance data with proper indexing
- **Per-ticker configuration**: Override monitoring intervals per ticker
- **Query optimization**: Indexes designed for common access patterns
- **Future-proof**: Reserved columns for Phase 2-5 features (technical indicators, breakouts)

---

## Table of Contents

1. [Schema Overview](#schema-overview)
2. [Table Designs](#table-designs)
3. [Index Strategy](#index-strategy)
4. [Query Patterns](#query-patterns)
5. [Implementation Guide](#implementation-guide)
6. [Performance Considerations](#performance-considerations)
7. [Migration Path](#migration-path)
8. [Testing Recommendations](#testing-recommendations)

---

## Schema Overview

### Architecture Decisions

#### Two-Table Design

**watchlist_tickers** (Main Table)
- One row per ticker
- Current state and configuration
- Denormalized latest performance data
- Rich trigger context

**performance_snapshots** (Time-Series Table)
- Many rows per ticker (unlimited)
- Historical performance tracking
- Optimized for time-based queries

**Why not three tables?**
- Considered: `tickers`, `state_history`, `snapshots`
- Rejected: Additional JOIN complexity for marginal benefits
- Triggers maintain state transition history in main table

#### SQLite vs PostgreSQL

**Current: SQLite**
- Embedded, zero-config
- Excellent for <1M rows
- Sufficient for initial deployment

**Future: PostgreSQL + TimescaleDB**
- Migrate when snapshot count > 1M
- TimescaleDB for time-series optimization
- Better concurrent write performance

---

## Table Designs

### watchlist_tickers

#### Design Philosophy

**Single source of truth** for each ticker's current state. Contains:
1. Identity (ticker symbol)
2. State management (HOT/WARM/COOL)
3. Trigger context (why added)
4. Monitoring config (when to check)
5. Performance summary (latest snapshot, denormalized)
6. Future expansion columns (reserved but unused)

#### Column Categories

**State Management**
```sql
state                    -- HOT, WARM, or COOL
last_state_change        -- When state last changed
previous_state           -- For transition analysis
state_transition_count   -- Lifecycle tracking
promoted_count           -- Times returned to HOT
```

**Trigger Context** (Why was ticker added?)
```sql
trigger_reason           -- "FDA approval catalyst"
trigger_title            -- News headline
trigger_summary          -- Full description
catalyst_type            -- fda_approval, earnings, etc.
trigger_score            -- Alert score (0.0-1.0)
trigger_sentiment        -- Sentiment (-1.0 to +1.0)
trigger_price            -- Price at addition
trigger_volume           -- Volume at addition
trigger_timestamp        -- When added
alert_id                 -- Link to original alert
```

**Monitoring Configuration**
```sql
check_interval_seconds   -- Override default interval
next_check_at            -- Next scheduled check (INDEXED)
last_checked_at          -- Last check time
check_count              -- Number of checks performed
monitoring_enabled       -- Pause/resume per ticker
```

**Performance Summary** (Denormalized from latest snapshot)
```sql
latest_price             -- Most recent price
latest_volume            -- Most recent volume
latest_rvol              -- Relative volume
latest_vwap              -- VWAP
price_change_pct         -- % change from trigger
price_change_since_hot   -- % change since first HOT
max_price_seen           -- Peak tracking
min_price_seen           -- Trough tracking
snapshot_count           -- Number of snapshots
last_snapshot_at         -- Last snapshot timestamp
```

**Future Expansion** (Phase 2-5)
```sql
-- Technical indicators (Phase 2)
rsi_14, macd_signal, bb_position, volume_sma_20, atr_14

-- Breakout detection (Phase 3)
breakout_confirmed, breakout_type, breakout_timestamp
resistance_level, support_level

-- Risk management (Phase 4-5)
risk_score, position_size_suggested
stop_loss_price, take_profit_price
```

#### Why Denormalize Performance Data?

**Problem**: Joining to get latest snapshot is expensive
```sql
-- Without denormalization (SLOW)
SELECT t.*, s.price, s.volume
FROM watchlist_tickers t
LEFT JOIN (
    SELECT ticker, price, volume
    FROM performance_snapshots
    WHERE snapshot_id IN (
        SELECT MAX(snapshot_id)
        FROM performance_snapshots
        GROUP BY ticker
    )
) s ON t.ticker = s.ticker
WHERE t.state = 'HOT';
```

**Solution**: Store latest snapshot in main table (FAST)
```sql
-- With denormalization (FAST)
SELECT ticker, state, latest_price, latest_volume
FROM watchlist_tickers
WHERE state = 'HOT';
```

**Trade-off**:
- Pro: 10-100x faster for common queries
- Con: Redundant data (acceptable for small columns)
- Maintenance: Update on each snapshot insert

---

### performance_snapshots

#### Design Philosophy

**Append-only time-series table** for historical analysis. Each snapshot is immutable once written.

#### Column Categories

**Core Data**
```sql
snapshot_id              -- Primary key (autoincrement)
ticker                   -- Denormalized for query speed
snapshot_at              -- Unix timestamp (INDEXED)
price                    -- Current price (required)
volume                   -- Current volume
rvol                     -- Relative volume
vwap                     -- VWAP
```

**Price Analysis**
```sql
price_change_pct         -- % change from trigger
price_change_since_last  -- % change from last snapshot
high_since_last          -- High since last snapshot
low_since_last           -- Low since last snapshot
```

**Volume Analysis**
```sql
volume_change_pct        -- % change from trigger
volume_surge             -- Boolean: surge detected
trade_count              -- Number of trades
```

**Market Context**
```sql
market_state             -- premarket, regular, aftermarket, closed
bid, ask, spread         -- Order book data (if available)
```

**Future Expansion** (Phase 2-5)
```sql
-- Technical indicators
rsi_14, macd_value, bb_upper, bb_middle, bb_lower
sma_20, sma_50, ema_12, ema_26, atr_14, obv

-- Pattern detection
pattern_detected, pattern_confidence
trend_direction, momentum_score

-- Signal generation
buy_signal, sell_signal, signal_strength, signal_type
```

**Data Quality**
```sql
data_source              -- tiingo, polygon, yahoo
data_quality             -- Quality score (0.0-1.0)
is_estimated             -- Boolean: estimated data
```

#### Why Denormalize ticker?

**Alternative**: Store ticker_id FK instead of ticker symbol

**Decision**: Store ticker symbol directly

**Reasoning**:
- Simplifies queries (no JOIN needed)
- Ticker symbols are small (4-6 bytes)
- Read performance > storage efficiency
- Matches existing codebase patterns

**Trade-off**:
- Pro: Faster queries, simpler code
- Con: ~5 extra bytes per snapshot
- At 1M snapshots: ~5MB overhead (acceptable)

---

## Index Strategy

### Design Principles

1. **Index WHERE clause columns** in common queries
2. **Composite indexes** for multi-column filters
3. **Partial indexes** for filtered subsets (SQLite 3.8+)
4. **Descending indexes** for ORDER BY DESC queries
5. **Cover indexes** avoid table lookups (not used here due to row size)

### watchlist_tickers Indexes

#### idx_tickers_state_monitoring
```sql
CREATE INDEX idx_tickers_state_monitoring
    ON watchlist_tickers(state, monitoring_enabled);
```
**Purpose**: "Get all HOT tickers" (most common query)
**Query Pattern**:
```sql
SELECT * FROM watchlist_tickers
WHERE state = 'HOT' AND monitoring_enabled = 1;
```
**Expected Selectivity**: ~10-30% of rows

#### idx_tickers_next_check
```sql
CREATE INDEX idx_tickers_next_check
    ON watchlist_tickers(next_check_at, monitoring_enabled)
    WHERE monitoring_enabled = 1;
```
**Purpose**: "Get tickers needing check" (scheduled monitoring)
**Query Pattern**:
```sql
SELECT * FROM watchlist_tickers
WHERE next_check_at <= ? AND monitoring_enabled = 1
ORDER BY next_check_at;
```
**Partial Index**: Only indexes active tickers (smaller, faster)
**Expected Selectivity**: ~1-5% of rows

#### idx_tickers_catalyst_type
```sql
CREATE INDEX idx_tickers_catalyst_type
    ON watchlist_tickers(catalyst_type);
```
**Purpose**: Analytics queries by catalyst type
**Query Pattern**:
```sql
SELECT * FROM watchlist_tickers WHERE catalyst_type = 'fda_approval';
```

#### idx_tickers_trigger_timestamp
```sql
CREATE INDEX idx_tickers_trigger_timestamp
    ON watchlist_tickers(trigger_timestamp DESC);
```
**Purpose**: "Get recently added tickers"
**Query Pattern**:
```sql
SELECT * FROM watchlist_tickers
ORDER BY trigger_timestamp DESC LIMIT 10;
```
**DESC Index**: Optimizes descending ORDER BY

#### idx_tickers_removed_at
```sql
CREATE INDEX idx_tickers_removed_at
    ON watchlist_tickers(removed_at)
    WHERE removed_at IS NULL;
```
**Purpose**: Filter out soft-deleted tickers
**Partial Index**: Only indexes active records
**Query Pattern**:
```sql
SELECT * FROM watchlist_tickers WHERE removed_at IS NULL;
```

### performance_snapshots Indexes

#### idx_snapshots_ticker_time
```sql
CREATE INDEX idx_snapshots_ticker_time
    ON performance_snapshots(ticker, snapshot_at DESC);
```
**Purpose**: "Get snapshots for ticker" (primary query)
**Query Patterns**:
```sql
-- Time-series analysis
SELECT * FROM performance_snapshots
WHERE ticker = 'AAPL'
ORDER BY snapshot_at DESC;

-- Latest snapshot
SELECT * FROM performance_snapshots
WHERE ticker = 'AAPL'
ORDER BY snapshot_at DESC
LIMIT 1;
```
**Composite Index**: Covers both WHERE and ORDER BY
**DESC**: Optimizes latest-first queries

#### idx_snapshots_time
```sql
CREATE INDEX idx_snapshots_time
    ON performance_snapshots(snapshot_at DESC);
```
**Purpose**: Time range queries across all tickers
**Query Pattern**:
```sql
SELECT * FROM performance_snapshots
WHERE snapshot_at BETWEEN ? AND ?
ORDER BY snapshot_at DESC;
```

#### idx_snapshots_signals (Phase 4-5)
```sql
CREATE INDEX idx_snapshots_signals
    ON performance_snapshots(buy_signal, sell_signal)
    WHERE buy_signal = 1 OR sell_signal = 1;
```
**Purpose**: Find snapshots with generated signals
**Partial Index**: Only indexes signal events (~1% of rows)

---

## Query Patterns

### Common Queries (Production)

#### 1. Get All HOT Tickers
```sql
-- Using view (recommended)
SELECT * FROM v_hot_tickers;

-- Using table directly
SELECT ticker, trigger_reason, latest_price, price_change_pct
FROM watchlist_tickers
WHERE state = 'HOT'
    AND monitoring_enabled = 1
    AND removed_at IS NULL
ORDER BY trigger_timestamp DESC;
```
**Index Used**: `idx_tickers_state_monitoring`
**Expected Rows**: 10-50
**Performance**: <1ms

#### 2. Get Tickers Needing Check
```sql
-- Using view (recommended)
SELECT * FROM v_tickers_needing_check;

-- Using table directly
SELECT ticker, state, next_check_at
FROM watchlist_tickers
WHERE next_check_at <= strftime('%s', 'now')
    AND monitoring_enabled = 1
    AND removed_at IS NULL
ORDER BY next_check_at ASC;
```
**Index Used**: `idx_tickers_next_check`
**Expected Rows**: 5-20 (depends on check intervals)
**Performance**: <1ms

#### 3. Get Snapshots for Ticker
```sql
-- All snapshots
SELECT snapshot_at, price, volume, rvol, vwap
FROM performance_snapshots
WHERE ticker = 'AAPL'
ORDER BY snapshot_at DESC;

-- Last N snapshots
SELECT snapshot_at, price, volume, rvol, vwap
FROM performance_snapshots
WHERE ticker = 'AAPL'
ORDER BY snapshot_at DESC
LIMIT 100;

-- Latest snapshot only
SELECT snapshot_at, price, volume, rvol, vwap
FROM performance_snapshots
WHERE ticker = 'AAPL'
ORDER BY snapshot_at DESC
LIMIT 1;
```
**Index Used**: `idx_snapshots_ticker_time`
**Expected Rows**: 100-10000 per ticker
**Performance**: <5ms for latest, <50ms for all

#### 4. Get Performance Summary
```sql
-- Using view (recommended)
SELECT * FROM v_ticker_performance_summary
WHERE price_change_pct > 5.0
ORDER BY price_change_pct DESC;

-- Aggregation across snapshots
SELECT
    ticker,
    COUNT(*) as snapshot_count,
    MIN(price) as min_price,
    MAX(price) as max_price,
    AVG(volume) as avg_volume,
    MAX(rvol) as max_rvol
FROM performance_snapshots
WHERE ticker = 'AAPL'
    AND snapshot_at >= strftime('%s', 'now') - 86400  -- Last 24h
GROUP BY ticker;
```

### Analytics Queries (Periodic)

#### 5. Count Tickers by State
```sql
SELECT
    state,
    COUNT(*) as count,
    AVG(price_change_pct) as avg_change,
    AVG(snapshot_count) as avg_snapshots
FROM watchlist_tickers
WHERE removed_at IS NULL
GROUP BY state;
```
**Performance**: <10ms
**Use Case**: Dashboard stats

#### 6. Find Top Performers
```sql
SELECT
    ticker,
    catalyst_type,
    trigger_price,
    latest_price,
    price_change_pct,
    max_price_seen,
    ROUND((max_price_seen - trigger_price) / trigger_price * 100, 2) as peak_gain_pct
FROM watchlist_tickers
WHERE removed_at IS NULL
    AND price_change_pct > 0
ORDER BY price_change_pct DESC
LIMIT 10;
```
**Performance**: <10ms
**Use Case**: Success analysis

#### 7. Catalyst Type Performance
```sql
SELECT
    catalyst_type,
    COUNT(*) as ticker_count,
    AVG(price_change_pct) as avg_change,
    COUNT(CASE WHEN price_change_pct > 0 THEN 1 END) as winners,
    COUNT(CASE WHEN price_change_pct < 0 THEN 1 END) as losers,
    ROUND(
        COUNT(CASE WHEN price_change_pct > 0 THEN 1 END) * 100.0 / COUNT(*),
        1
    ) as win_rate_pct
FROM watchlist_tickers
WHERE removed_at IS NULL
    AND catalyst_type IS NOT NULL
GROUP BY catalyst_type
ORDER BY avg_change DESC;
```
**Index Used**: `idx_tickers_catalyst_type`
**Performance**: <20ms
**Use Case**: Strategy optimization

#### 8. State Transition Analysis
```sql
SELECT
    state,
    previous_state,
    COUNT(*) as transition_count,
    AVG(state_transition_count) as avg_transitions,
    AVG(promoted_count) as avg_promotions
FROM watchlist_tickers
WHERE previous_state IS NOT NULL
    AND removed_at IS NULL
GROUP BY state, previous_state
ORDER BY state, previous_state;
```
**Performance**: <10ms
**Use Case**: Lifecycle analysis

---

## Implementation Guide

### Python Database Module

```python
"""
Watchlist Performance Database Module

Provides high-level API for interacting with watchlist tracking database.
Follows patterns from existing catalyst_bot.feedback.database module.
"""

from __future__ import annotations

import sqlite3
import time
from pathlib import Path
from typing import Dict, List, Optional, Any

from ..logging_utils import get_logger
from ..storage import init_optimized_connection

log = get_logger("watchlist.database")

DEFAULT_DB_PATH = Path("data/watchlist/performance.db")


def _get_db_path() -> Path:
    """Get database path from env or use default."""
    import os
    db_path_str = os.getenv("WATCHLIST_DB_PATH", str(DEFAULT_DB_PATH))
    db_path = Path(db_path_str).resolve()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return db_path


def _get_connection() -> sqlite3.Connection:
    """Get database connection with row factory and optimized pragmas."""
    db_path = _get_db_path()
    conn = init_optimized_connection(str(db_path))
    conn.row_factory = sqlite3.Row
    return conn


def init_database() -> None:
    """
    Initialize database schema.

    This function is idempotent and safe to call multiple times.
    Executes the full schema from watchlist_performance_schema.sql.
    """
    db_path = _get_db_path()
    log.info("initializing_watchlist_database path=%s", db_path)

    # Read schema file
    schema_path = Path(__file__).parent.parent.parent / "docs" / "schema" / "watchlist_performance_schema.sql"

    if not schema_path.exists():
        log.error("schema_file_not_found path=%s", schema_path)
        raise FileNotFoundError(f"Schema file not found: {schema_path}")

    with open(schema_path, 'r', encoding='utf-8') as f:
        schema_sql = f.read()

    conn = _get_connection()
    try:
        conn.executescript(schema_sql)
        conn.commit()
        log.info("watchlist_database_initialized")
    except Exception as e:
        log.error("watchlist_database_init_failed error=%s", str(e))
        conn.rollback()
        raise
    finally:
        conn.close()


# ============================================================================
# Ticker Management Functions
# ============================================================================

def add_ticker(
    ticker: str,
    trigger_reason: str,
    trigger_price: float,
    trigger_volume: Optional[float] = None,
    catalyst_type: Optional[str] = None,
    trigger_title: Optional[str] = None,
    trigger_summary: Optional[str] = None,
    trigger_score: Optional[float] = None,
    trigger_sentiment: Optional[float] = None,
    alert_id: Optional[str] = None,
    state: str = "HOT",
    check_interval_seconds: Optional[int] = None,
) -> bool:
    """
    Add a ticker to the watchlist.

    Parameters
    ----------
    ticker : str
        Ticker symbol (uppercase)
    trigger_reason : str
        Reason for adding (e.g., "FDA approval catalyst")
    trigger_price : float
        Price at time of addition
    trigger_volume : float, optional
        Volume at time of addition
    catalyst_type : str, optional
        Catalyst category (e.g., "fda_approval")
    trigger_title : str, optional
        Alert/news title
    trigger_summary : str, optional
        Longer summary
    trigger_score : float, optional
        Alert score (0.0-1.0)
    trigger_sentiment : float, optional
        Sentiment score (-1.0 to +1.0)
    alert_id : str, optional
        Link to original alert
    state : str, default "HOT"
        Initial state (HOT, WARM, or COOL)
    check_interval_seconds : int, optional
        Custom check interval (overrides state default)

    Returns
    -------
    bool
        True if added, False if already exists or error
    """
    ticker = ticker.upper().strip()
    now = int(time.time())

    # Calculate next_check_at based on interval or state
    if check_interval_seconds:
        next_check = now + check_interval_seconds
    else:
        # Default intervals by state (configurable via env later)
        defaults = {"HOT": 60, "WARM": 300, "COOL": 3600}
        next_check = now + defaults.get(state, 60)

    conn = _get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT OR IGNORE INTO watchlist_tickers (
                ticker, state, last_state_change, trigger_reason,
                trigger_title, trigger_summary, catalyst_type,
                trigger_score, trigger_sentiment, trigger_price,
                trigger_volume, trigger_timestamp, alert_id,
                check_interval_seconds, next_check_at,
                created_at, updated_at,
                max_price_seen, min_price_seen
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            ticker, state, now, trigger_reason,
            trigger_title, trigger_summary, catalyst_type,
            trigger_score, trigger_sentiment, trigger_price,
            trigger_volume, now, alert_id,
            check_interval_seconds, next_check,
            now, now,
            trigger_price, trigger_price  # Initialize max/min to trigger price
        ))

        inserted = cursor.rowcount > 0
        conn.commit()

        if inserted:
            log.info("ticker_added ticker=%s state=%s catalyst_type=%s",
                     ticker, state, catalyst_type)
        else:
            log.debug("ticker_already_exists ticker=%s", ticker)

        return inserted

    except Exception as e:
        log.error("add_ticker_failed ticker=%s error=%s", ticker, str(e))
        conn.rollback()
        return False
    finally:
        conn.close()


def update_ticker_state(
    ticker: str,
    new_state: str,
) -> bool:
    """
    Update ticker state (HOT -> WARM -> COOL).

    Triggers will automatically handle:
    - Setting previous_state
    - Incrementing state_transition_count
    - Updating last_state_change
    - Incrementing promoted_count if returning to HOT

    Parameters
    ----------
    ticker : str
        Ticker symbol
    new_state : str
        New state (HOT, WARM, or COOL)

    Returns
    -------
    bool
        True if updated, False if error
    """
    ticker = ticker.upper().strip()
    new_state = new_state.upper().strip()

    if new_state not in ("HOT", "WARM", "COOL"):
        log.error("invalid_state ticker=%s state=%s", ticker, new_state)
        return False

    conn = _get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE watchlist_tickers
            SET state = ?
            WHERE ticker = ?
                AND state != ?
                AND removed_at IS NULL
        """, (new_state, ticker, new_state))

        updated = cursor.rowcount > 0
        conn.commit()

        if updated:
            log.info("ticker_state_updated ticker=%s new_state=%s",
                     ticker, new_state)

        return updated

    except Exception as e:
        log.error("update_ticker_state_failed ticker=%s error=%s",
                  ticker, str(e))
        conn.rollback()
        return False
    finally:
        conn.close()


def record_snapshot(
    ticker: str,
    price: float,
    volume: Optional[float] = None,
    rvol: Optional[float] = None,
    vwap: Optional[float] = None,
    market_state: Optional[str] = None,
    price_change_pct: Optional[float] = None,
    volume_surge: bool = False,
) -> bool:
    """
    Record a performance snapshot for a ticker.

    Also updates denormalized performance data in watchlist_tickers.

    Parameters
    ----------
    ticker : str
        Ticker symbol
    price : float
        Current price
    volume : float, optional
        Current volume
    rvol : float, optional
        Relative volume
    vwap : float, optional
        VWAP
    market_state : str, optional
        Market state (premarket, regular, aftermarket, closed)
    price_change_pct : float, optional
        Price change % from trigger
    volume_surge : bool, default False
        Whether volume surge detected

    Returns
    -------
    bool
        True if recorded, False if error
    """
    ticker = ticker.upper().strip()
    now = int(time.time())

    conn = _get_connection()
    try:
        cursor = conn.cursor()

        # Insert snapshot
        cursor.execute("""
            INSERT INTO performance_snapshots (
                ticker, snapshot_at, price, volume, rvol, vwap,
                price_change_pct, volume_surge, market_state
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            ticker, now, price, volume, rvol, vwap,
            price_change_pct, 1 if volume_surge else 0, market_state
        ))

        # Update denormalized data in main table
        cursor.execute("""
            UPDATE watchlist_tickers
            SET
                latest_price = ?,
                latest_volume = ?,
                latest_rvol = ?,
                latest_vwap = ?,
                price_change_pct = ?,
                snapshot_count = snapshot_count + 1,
                last_snapshot_at = ?,
                last_checked_at = ?,
                check_count = check_count + 1
            WHERE ticker = ?
                AND removed_at IS NULL
        """, (
            price, volume, rvol, vwap,
            price_change_pct, now, now, ticker
        ))

        conn.commit()

        log.debug("snapshot_recorded ticker=%s price=%.2f volume=%s",
                  ticker, price, volume)

        return True

    except Exception as e:
        log.error("record_snapshot_failed ticker=%s error=%s",
                  ticker, str(e))
        conn.rollback()
        return False
    finally:
        conn.close()


def update_next_check_time(
    ticker: str,
    next_check_at: int,
) -> bool:
    """
    Update next scheduled check time for a ticker.

    Parameters
    ----------
    ticker : str
        Ticker symbol
    next_check_at : int
        Unix timestamp of next check

    Returns
    -------
    bool
        True if updated
    """
    ticker = ticker.upper().strip()

    conn = _get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE watchlist_tickers
            SET next_check_at = ?
            WHERE ticker = ?
                AND removed_at IS NULL
        """, (next_check_at, ticker))

        conn.commit()
        return cursor.rowcount > 0

    except Exception as e:
        log.error("update_next_check_failed ticker=%s error=%s",
                  ticker, str(e))
        conn.rollback()
        return False
    finally:
        conn.close()


# ============================================================================
# Query Functions
# ============================================================================

def get_hot_tickers() -> List[Dict[str, Any]]:
    """
    Get all active HOT tickers.

    Returns list of ticker dicts with current state and performance.
    """
    conn = _get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM v_hot_tickers")
        rows = cursor.fetchall()
        return [dict(row) for row in rows]
    except Exception as e:
        log.error("get_hot_tickers_failed error=%s", str(e))
        return []
    finally:
        conn.close()


def get_tickers_needing_check() -> List[Dict[str, Any]]:
    """
    Get tickers that need performance check now.

    Returns list of ticker dicts ordered by next_check_at (most overdue first).
    """
    conn = _get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM v_tickers_needing_check")
        rows = cursor.fetchall()
        return [dict(row) for row in rows]
    except Exception as e:
        log.error("get_tickers_needing_check_failed error=%s", str(e))
        return []
    finally:
        conn.close()


def get_ticker_snapshots(
    ticker: str,
    limit: Optional[int] = None,
    since: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """
    Get performance snapshots for a ticker.

    Parameters
    ----------
    ticker : str
        Ticker symbol
    limit : int, optional
        Maximum number of snapshots (most recent first)
    since : int, optional
        Only snapshots after this Unix timestamp

    Returns
    -------
    list of dict
        Snapshot records ordered by time (newest first)
    """
    ticker = ticker.upper().strip()

    conn = _get_connection()
    try:
        cursor = conn.cursor()

        query = """
            SELECT * FROM performance_snapshots
            WHERE ticker = ?
        """
        params = [ticker]

        if since:
            query += " AND snapshot_at >= ?"
            params.append(since)

        query += " ORDER BY snapshot_at DESC"

        if limit:
            query += " LIMIT ?"
            params.append(limit)

        cursor.execute(query, params)
        rows = cursor.fetchall()
        return [dict(row) for row in rows]

    except Exception as e:
        log.error("get_ticker_snapshots_failed ticker=%s error=%s",
                  ticker, str(e))
        return []
    finally:
        conn.close()


def get_ticker_info(ticker: str) -> Optional[Dict[str, Any]]:
    """
    Get full info for a ticker including latest performance.

    Parameters
    ----------
    ticker : str
        Ticker symbol

    Returns
    -------
    dict or None
        Ticker record, or None if not found
    """
    ticker = ticker.upper().strip()

    conn = _get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM watchlist_tickers
            WHERE ticker = ?
                AND removed_at IS NULL
        """, (ticker,))

        row = cursor.fetchone()
        return dict(row) if row else None

    except Exception as e:
        log.error("get_ticker_info_failed ticker=%s error=%s",
                  ticker, str(e))
        return None
    finally:
        conn.close()


def get_performance_summary() -> List[Dict[str, Any]]:
    """
    Get comprehensive performance summary for all active tickers.

    Returns list of ticker summaries with calculated metrics.
    """
    conn = _get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM v_ticker_performance_summary")
        rows = cursor.fetchall()
        return [dict(row) for row in rows]
    except Exception as e:
        log.error("get_performance_summary_failed error=%s", str(e))
        return []
    finally:
        conn.close()


def get_state_counts() -> Dict[str, int]:
    """
    Get count of tickers in each state.

    Returns
    -------
    dict
        {"HOT": 10, "WARM": 25, "COOL": 15}
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
```

### Usage Examples

```python
from catalyst_bot.watchlist.database import (
    init_database,
    add_ticker,
    record_snapshot,
    get_hot_tickers,
    get_tickers_needing_check,
    update_ticker_state,
)

# Initialize database (call once on startup)
init_database()

# Add a ticker to watchlist
add_ticker(
    ticker="AAPL",
    trigger_reason="FDA approval for new device",
    trigger_price=150.25,
    trigger_volume=1500000,
    catalyst_type="fda_approval",
    trigger_score=0.85,
    trigger_sentiment=0.75,
    alert_id="alert_12345",
    state="HOT",
)

# Record performance snapshot
record_snapshot(
    ticker="AAPL",
    price=152.50,
    volume=1800000,
    rvol=1.2,
    vwap=151.80,
    market_state="regular",
    price_change_pct=1.5,
    volume_surge=True,
)

# Get HOT tickers for monitoring
hot = get_hot_tickers()
for t in hot:
    print(f"{t['ticker']}: {t['price_change_pct']}% ({t['state']})")

# Get tickers needing check
tickers_to_check = get_tickers_needing_check()
for t in tickers_to_check:
    # Fetch latest data and record snapshot
    print(f"Checking {t['ticker']} (overdue by {t['seconds_overdue']}s)")

# Update ticker state (decay)
update_ticker_state("AAPL", "WARM")
```

---

## Performance Considerations

### Query Performance

**Target Latencies** (at 10K tickers, 1M snapshots):
- Get HOT tickers: <5ms
- Get tickers needing check: <5ms
- Get latest snapshot: <10ms
- Get all snapshots for ticker: <50ms
- Performance summary: <100ms

### Index Maintenance

**ANALYZE** after bulk operations:
```sql
ANALYZE;
```

**VACUUM** after many deletes:
```sql
VACUUM;
```

### Write Performance

**Snapshots per second**: 100-1000 (depends on state distribution)

**Batch inserts** for better performance:
```python
conn.executemany("""
    INSERT INTO performance_snapshots (...)
    VALUES (?, ?, ?, ...)
""", snapshot_rows)
```

### Storage Estimates

**watchlist_tickers**: ~1KB per row
- 100 tickers = 100KB
- 1,000 tickers = 1MB
- 10,000 tickers = 10MB

**performance_snapshots**: ~200 bytes per row
- 100K snapshots = 20MB
- 1M snapshots = 200MB
- 10M snapshots = 2GB

**Total at scale** (1K tickers, 10M snapshots): ~2GB

---

## Migration Path

### Phase 1: SQLite (Current)
- Development & initial production
- <1K active tickers
- <1M snapshots
- Single-process writes

### Phase 2: SQLite with WAL Mode
```sql
PRAGMA journal_mode=WAL;
```
- Better concurrent reads
- <10K tickers
- <10M snapshots

### Phase 3: PostgreSQL
- Production scale
- >10K tickers
- >10M snapshots
- Multi-process writes
- Better JSON support
- Full-text search

### Phase 4: PostgreSQL + TimescaleDB
- Time-series optimization
- >100K tickers
- >100M snapshots
- Automatic data retention
- Continuous aggregates
- Compression

### Migration Script Template

```python
def migrate_to_postgres():
    """Migrate SQLite data to PostgreSQL."""
    import sqlite3
    import psycopg2

    # Connect to both databases
    sqlite_conn = sqlite3.connect("data/watchlist/performance.db")
    pg_conn = psycopg2.connect("postgresql://...")

    # Create PostgreSQL schema (adapt SQL for PG)
    # ... execute schema SQL ...

    # Migrate tickers
    tickers = sqlite_conn.execute("SELECT * FROM watchlist_tickers").fetchall()
    # ... insert into PostgreSQL ...

    # Migrate snapshots (in batches)
    batch_size = 10000
    offset = 0
    while True:
        snapshots = sqlite_conn.execute(
            f"SELECT * FROM performance_snapshots LIMIT {batch_size} OFFSET {offset}"
        ).fetchall()
        if not snapshots:
            break
        # ... insert into PostgreSQL ...
        offset += batch_size

    pg_conn.commit()
```

---

## Testing Recommendations

### Unit Tests

```python
import pytest
from catalyst_bot.watchlist.database import *

def test_add_ticker():
    """Test adding ticker to watchlist."""
    init_database()  # Use test database

    result = add_ticker(
        ticker="TEST",
        trigger_reason="Test catalyst",
        trigger_price=10.0,
        catalyst_type="test",
    )

    assert result is True

    # Verify ticker exists
    info = get_ticker_info("TEST")
    assert info["ticker"] == "TEST"
    assert info["state"] == "HOT"
    assert info["trigger_price"] == 10.0


def test_record_snapshot():
    """Test recording performance snapshot."""
    add_ticker("TEST", "Test", 10.0)

    result = record_snapshot(
        ticker="TEST",
        price=11.0,
        volume=1000,
    )

    assert result is True

    # Verify snapshot recorded
    snapshots = get_ticker_snapshots("TEST")
    assert len(snapshots) == 1
    assert snapshots[0]["price"] == 11.0


def test_state_transition():
    """Test state transitions."""
    add_ticker("TEST", "Test", 10.0, state="HOT")

    # Transition to WARM
    update_ticker_state("TEST", "WARM")

    info = get_ticker_info("TEST")
    assert info["state"] == "WARM"
    assert info["previous_state"] == "HOT"
    assert info["state_transition_count"] == 2  # Initial HOT + WARM
```

### Integration Tests

```python
def test_full_lifecycle():
    """Test complete ticker lifecycle: HOT -> WARM -> COOL."""
    init_database()

    # Add as HOT
    add_ticker("LIFE", "Lifecycle test", 100.0, state="HOT")

    # Record snapshots
    for i in range(5):
        record_snapshot("LIFE", 100.0 + i, volume=1000)

    # Transition to WARM
    update_ticker_state("LIFE", "WARM")

    # Record more snapshots
    for i in range(5):
        record_snapshot("LIFE", 105.0 + i, volume=1000)

    # Transition to COOL
    update_ticker_state("LIFE", "COOL")

    # Verify final state
    info = get_ticker_info("LIFE")
    assert info["state"] == "COOL"
    assert info["snapshot_count"] == 10
    assert info["state_transition_count"] == 3  # HOT -> WARM -> COOL


def test_query_performance():
    """Test query performance with larger dataset."""
    import time

    init_database()

    # Add 100 tickers
    for i in range(100):
        add_ticker(
            ticker=f"TST{i:03d}",
            trigger_reason=f"Test {i}",
            trigger_price=float(i),
            state="HOT" if i < 50 else "WARM",
        )

    # Record 10 snapshots per ticker (1000 total)
    for i in range(100):
        ticker = f"TST{i:03d}"
        for j in range(10):
            record_snapshot(ticker, float(i + j), volume=1000)

    # Test query performance
    start = time.time()
    hot = get_hot_tickers()
    elapsed = time.time() - start

    assert len(hot) == 50
    assert elapsed < 0.01  # < 10ms

    print(f"Query took {elapsed*1000:.2f}ms")
```

### Load Tests

```python
def test_high_frequency_snapshots():
    """Test high-frequency snapshot recording."""
    import time

    init_database()
    add_ticker("HFREQ", "High frequency test", 100.0)

    # Record 1000 snapshots as fast as possible
    start = time.time()
    for i in range(1000):
        record_snapshot("HFREQ", 100.0 + i * 0.01, volume=1000)
    elapsed = time.time() - start

    print(f"Recorded 1000 snapshots in {elapsed:.2f}s ({1000/elapsed:.0f} snapshots/sec)")

    # Verify all recorded
    snapshots = get_ticker_snapshots("HFREQ")
    assert len(snapshots) == 1000
```

---

## Appendix A: Reserved Columns Reference

### watchlist_tickers

**Phase 2: Technical Indicators**
- `rsi_14`: 14-period Relative Strength Index
- `macd_signal`: MACD signal line
- `bb_position`: Bollinger Band position (0.0-1.0)
- `volume_sma_20`: 20-day volume moving average
- `atr_14`: Average True Range (14-period)

**Phase 3: Breakout Detection**
- `breakout_confirmed`: Boolean flag
- `breakout_type`: volume_breakout, price_breakout, technical_breakout
- `breakout_timestamp`: When detected
- `resistance_level`: Key resistance price
- `support_level`: Key support price

**Phase 4-5: Risk Management**
- `risk_score`: Computed risk (0.0-1.0)
- `position_size_suggested`: % of portfolio
- `stop_loss_price`: Suggested stop loss
- `take_profit_price`: Suggested take profit

### performance_snapshots

**Phase 2: Technical Indicators**
- RSI: `rsi_14`, `rsi_trend`
- MACD: `macd_value`, `macd_signal`, `macd_histogram`
- Bollinger: `bb_upper`, `bb_middle`, `bb_lower`, `bb_width`
- Moving Averages: `sma_20`, `sma_50`, `ema_12`, `ema_26`
- Other: `atr_14`, `obv`

**Phase 3: Pattern Detection**
- `pattern_detected`: Pattern name (hammer, doji, etc.)
- `pattern_confidence`: 0.0-1.0
- `trend_direction`: up, down, sideways
- `momentum_score`: -1.0 to +1.0

**Phase 4-5: Signal Generation**
- `buy_signal`, `sell_signal`: Boolean flags
- `signal_strength`: 0.0-1.0
- `signal_type`: breakout, reversal, continuation

---

## Appendix B: Sample Data

### Sample watchlist_tickers

| ticker | state | trigger_reason | trigger_price | latest_price | price_change_pct | snapshot_count |
|--------|-------|----------------|---------------|--------------|------------------|----------------|
| AAPL | HOT | FDA approval | 150.00 | 155.50 | 3.67 | 45 |
| TSLA | WARM | Earnings beat | 220.00 | 218.00 | -0.91 | 120 |
| NVDA | HOT | Partnership news | 480.00 | 495.00 | 3.13 | 30 |
| MRNA | COOL | Clinical trial | 180.00 | 175.00 | -2.78 | 200 |

### Sample performance_snapshots

| snapshot_id | ticker | snapshot_at | price | volume | rvol | vwap | price_change_pct |
|-------------|--------|-------------|-------|--------|------|------|------------------|
| 1001 | AAPL | 1700000000 | 151.20 | 1200000 | 1.1 | 150.80 | 0.80 |
| 1002 | AAPL | 1700000060 | 151.50 | 1250000 | 1.2 | 151.00 | 1.00 |
| 1003 | AAPL | 1700000120 | 152.00 | 1300000 | 1.3 | 151.30 | 1.33 |
| 1004 | AAPL | 1700000180 | 152.50 | 1350000 | 1.4 | 151.60 | 1.67 |

---

**End of Design Document**
