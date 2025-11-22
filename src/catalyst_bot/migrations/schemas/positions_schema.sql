-- ============================================================================
-- POSITIONS DATABASE SCHEMA
-- Database: data/positions.db
-- Migration: 001_create_positions_tables.py
-- ============================================================================
-- This file contains the complete SQL schema for the positions database.
-- It tracks open positions and historical closed positions for the paper
-- trading bot.
-- ============================================================================

-- ============================================================================
-- TABLE: positions
-- ============================================================================
-- Tracks currently open trading positions with real-time P&L tracking.
-- ============================================================================

CREATE TABLE IF NOT EXISTS positions (
    -- Primary key
    position_id TEXT PRIMARY KEY,

    -- Position details
    ticker TEXT NOT NULL,
    side TEXT NOT NULL CHECK(side IN ('long', 'short')),
    quantity INTEGER NOT NULL CHECK(quantity > 0),

    -- Pricing
    entry_price REAL NOT NULL CHECK(entry_price > 0),
    current_price REAL NOT NULL CHECK(current_price > 0),

    -- Profit/Loss tracking
    unrealized_pnl REAL NOT NULL DEFAULT 0.0,
    unrealized_pnl_pct REAL NOT NULL DEFAULT 0.0,

    -- Risk management
    stop_loss_price REAL,
    take_profit_price REAL,

    -- Timestamps
    opened_at INTEGER NOT NULL,
    updated_at INTEGER NOT NULL,

    -- Strategy metadata
    strategy TEXT,
    signal_score REAL CHECK(signal_score >= 0 AND signal_score <= 1),

    -- Market context at entry
    atr_at_entry REAL,
    rvol_at_entry REAL,
    market_regime TEXT,

    -- Additional context (JSON)
    metadata TEXT,

    -- Constraints
    CONSTRAINT valid_stop_loss CHECK(
        (side = 'long' AND (stop_loss_price IS NULL OR stop_loss_price < entry_price))
        OR (side = 'short' AND (stop_loss_price IS NULL OR stop_loss_price > entry_price))
    ),
    CONSTRAINT valid_take_profit CHECK(
        (side = 'long' AND (take_profit_price IS NULL OR take_profit_price > entry_price))
        OR (side = 'short' AND (take_profit_price IS NULL OR take_profit_price < entry_price))
    )
);

-- ============================================================================
-- TABLE: closed_positions
-- ============================================================================
-- Historical record of all closed positions with realized P&L and exit details.
-- ============================================================================

CREATE TABLE IF NOT EXISTS closed_positions (
    -- Primary key
    position_id TEXT PRIMARY KEY,

    -- Position details
    ticker TEXT NOT NULL,
    side TEXT NOT NULL CHECK(side IN ('long', 'short')),
    quantity INTEGER NOT NULL CHECK(quantity > 0),

    -- Pricing
    entry_price REAL NOT NULL CHECK(entry_price > 0),
    exit_price REAL NOT NULL CHECK(exit_price > 0),

    -- Profit/Loss (realized)
    realized_pnl REAL NOT NULL,
    realized_pnl_pct REAL NOT NULL,

    -- Risk management levels
    stop_loss_price REAL,
    take_profit_price REAL,

    -- Timestamps
    opened_at INTEGER NOT NULL,
    closed_at INTEGER NOT NULL,
    updated_at INTEGER NOT NULL,

    -- Trade metrics
    holding_period_hours REAL NOT NULL,
    exit_reason TEXT NOT NULL,

    -- Strategy metadata
    strategy TEXT,
    signal_score REAL CHECK(signal_score >= 0 AND signal_score <= 1),

    -- Market context at entry
    atr_at_entry REAL,
    rvol_at_entry REAL,
    market_regime TEXT,

    -- Execution costs
    commission REAL DEFAULT 0.0,
    slippage REAL DEFAULT 0.0,

    -- Excursion tracking (for post-analysis)
    max_favorable_excursion REAL,  -- Best price during holding period
    max_adverse_excursion REAL,    -- Worst price during holding period

    -- Additional context (JSON)
    metadata TEXT,

    -- Constraints
    CONSTRAINT valid_exit_reason CHECK(
        exit_reason IN (
            'stop_loss',
            'take_profit',
            'trailing_stop',
            'time_exit',
            'manual',
            'risk_limit',
            'circuit_breaker',
            'market_close'
        )
    ),
    CONSTRAINT valid_holding_period CHECK(holding_period_hours >= 0),
    CONSTRAINT valid_closed_at CHECK(closed_at >= opened_at)
);

-- ============================================================================
-- INDEXES
-- ============================================================================
-- Indexes for common query patterns and performance optimization.
-- ============================================================================

-- Positions table indexes
CREATE INDEX IF NOT EXISTS idx_positions_ticker ON positions(ticker);
CREATE INDEX IF NOT EXISTS idx_positions_strategy ON positions(strategy);
CREATE INDEX IF NOT EXISTS idx_positions_opened_at ON positions(opened_at DESC);
CREATE INDEX IF NOT EXISTS idx_positions_unrealized_pnl ON positions(unrealized_pnl DESC);
CREATE INDEX IF NOT EXISTS idx_positions_ticker_side ON positions(ticker, side);

-- Closed positions table indexes
CREATE INDEX IF NOT EXISTS idx_closed_positions_ticker ON closed_positions(ticker);
CREATE INDEX IF NOT EXISTS idx_closed_positions_closed_at ON closed_positions(closed_at DESC);
CREATE INDEX IF NOT EXISTS idx_closed_positions_exit_reason ON closed_positions(exit_reason);
CREATE INDEX IF NOT EXISTS idx_closed_positions_strategy ON closed_positions(strategy);
CREATE INDEX IF NOT EXISTS idx_closed_positions_realized_pnl ON closed_positions(realized_pnl DESC);
CREATE INDEX IF NOT EXISTS idx_closed_positions_holding_period ON closed_positions(holding_period_hours);

-- ============================================================================
-- VIEWS
-- ============================================================================
-- Pre-built views for common queries with calculated fields.
-- ============================================================================

-- View: Position summary with current P&L
CREATE VIEW IF NOT EXISTS v_position_summary AS
SELECT
    ticker,
    side,
    quantity,
    entry_price,
    current_price,
    unrealized_pnl,
    unrealized_pnl_pct,
    (current_price - entry_price) * quantity AS pnl_dollars,
    strategy,
    datetime(opened_at, 'unixepoch') AS opened_datetime,
    datetime(updated_at, 'unixepoch') AS updated_datetime,
    CAST((julianday('now') - julianday(opened_at, 'unixepoch')) * 24 AS REAL) AS hours_held
FROM positions
ORDER BY unrealized_pnl DESC;

-- View: Recent closed trades with performance metrics
CREATE VIEW IF NOT EXISTS v_recent_closed_trades AS
SELECT
    ticker,
    side,
    quantity,
    entry_price,
    exit_price,
    realized_pnl,
    realized_pnl_pct,
    exit_reason,
    strategy,
    holding_period_hours,
    datetime(opened_at, 'unixepoch') AS opened_datetime,
    datetime(closed_at, 'unixepoch') AS closed_datetime,
    CASE
        WHEN realized_pnl > 0 THEN 'WIN'
        WHEN realized_pnl < 0 THEN 'LOSS'
        ELSE 'BREAKEVEN'
    END AS outcome
FROM closed_positions
ORDER BY closed_at DESC
LIMIT 100;

-- ============================================================================
-- SAMPLE QUERIES
-- ============================================================================

/*
-- Get all open positions
SELECT * FROM positions ORDER BY opened_at DESC;

-- Get total unrealized P&L
SELECT SUM(unrealized_pnl) as total_unrealized_pnl FROM positions;

-- Get positions for a specific ticker
SELECT * FROM positions WHERE ticker = 'AAPL';

-- Get win rate for closed positions
SELECT
    COUNT(CASE WHEN realized_pnl > 0 THEN 1 END) * 1.0 / COUNT(*) as win_rate,
    COUNT(*) as total_trades,
    SUM(realized_pnl) as total_realized_pnl
FROM closed_positions;

-- Get average holding period by exit reason
SELECT
    exit_reason,
    COUNT(*) as count,
    AVG(holding_period_hours) as avg_hours,
    AVG(realized_pnl) as avg_pnl
FROM closed_positions
GROUP BY exit_reason
ORDER BY count DESC;

-- Get best and worst trades
SELECT ticker, realized_pnl, realized_pnl_pct, exit_reason
FROM closed_positions
ORDER BY realized_pnl DESC
LIMIT 10;

-- Get positions by strategy performance
SELECT
    strategy,
    COUNT(*) as trades,
    AVG(realized_pnl) as avg_pnl,
    SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END) * 1.0 / COUNT(*) as win_rate
FROM closed_positions
GROUP BY strategy
ORDER BY avg_pnl DESC;

-- Get positions that hit stop loss
SELECT ticker, entry_price, exit_price, realized_pnl
FROM closed_positions
WHERE exit_reason = 'stop_loss'
ORDER BY closed_at DESC;

-- Use the pre-built views
SELECT * FROM v_position_summary;
SELECT * FROM v_recent_closed_trades;
*/
