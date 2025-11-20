-- ============================================================================
-- Watchlist Performance Tracking Schema
-- ============================================================================
--
-- Purpose: SQLite database schema for tracking watchlist tickers with
--          HOT/WARM/COOL states and their performance over time.
--
-- Design Goals:
--   1. Track ticker lifecycle through HOT -> WARM -> COOL states
--   2. Store rich trigger context (why ticker was added)
--   3. Capture unlimited performance snapshots for analysis
--   4. Support per-state and per-ticker monitoring configurations
--   5. Optimize for common queries (get HOT tickers, get snapshots, etc.)
--   6. Include extensibility for Phase 2-5 features
--
-- Database: SQLite 3.x
-- Author: Database Architect (Claude Code)
-- Date: 2025-11-20
--
-- ============================================================================

-- ============================================================================
-- TABLE: watchlist_tickers
-- ============================================================================
--
-- Main tracking table for watchlist entries. Each ticker has:
--   - Current state (HOT/WARM/COOL) and lifecycle timestamps
--   - Trigger context (reason for addition, catalyst details)
--   - Monitoring configuration (can override defaults per ticker)
--   - Performance summary (latest snapshot data for quick access)
--   - Future expansion fields (technical indicators, breakout flags)
--
-- Design Decisions:
--   - ticker is PRIMARY KEY (one entry per ticker, updated as state changes)
--   - state + last_state_change indexed for "get all HOT tickers" queries
--   - next_check_at indexed for "get tickers needing check" queries
--   - JSON fields used sparingly for flexible metadata storage
--   - Reserved columns for Phase 2-5 features to avoid ALTER TABLE later
--
-- ============================================================================

CREATE TABLE IF NOT EXISTS watchlist_tickers (
    -- ========================================================================
    -- Primary Key & Identity
    -- ========================================================================
    ticker TEXT PRIMARY KEY NOT NULL,           -- Uppercase ticker symbol (e.g., "AAPL")

    -- ========================================================================
    -- State Management (HOT/WARM/COOL Cascade)
    -- ========================================================================
    state TEXT NOT NULL DEFAULT 'HOT'           -- Current state: HOT, WARM, or COOL
        CHECK(state IN ('HOT', 'WARM', 'COOL')),

    last_state_change INTEGER NOT NULL,         -- Unix timestamp of last state transition
                                                -- Used for decay calculations

    previous_state TEXT                         -- Previous state (for transition analysis)
        CHECK(previous_state IS NULL OR previous_state IN ('HOT', 'WARM', 'COOL')),

    state_transition_count INTEGER DEFAULT 1,   -- Number of state changes (lifecycle tracking)

    promoted_count INTEGER DEFAULT 1,           -- Times promoted back to HOT (re-catalyst events)

    -- ========================================================================
    -- Trigger Context (Why Ticker Was Added)
    -- ========================================================================
    -- This captures the catalyst/reason for adding to watchlist

    trigger_reason TEXT,                        -- Short reason string (e.g., "FDA approval catalyst")

    trigger_title TEXT,                         -- Alert/news title that triggered addition

    trigger_summary TEXT,                       -- Longer summary/description of catalyst

    catalyst_type TEXT,                         -- Category: fda_approval, earnings, sec_filing,
                                                -- partnership, offering, insider_buy, etc.

    trigger_score REAL,                         -- Alert score that triggered addition (0.0-1.0)

    trigger_sentiment REAL,                     -- Sentiment score at trigger time (-1.0 to +1.0)

    trigger_price REAL,                         -- Price when added to watchlist

    trigger_volume REAL,                        -- Volume when added to watchlist

    trigger_timestamp INTEGER NOT NULL,         -- Unix timestamp when ticker was added

    alert_id TEXT,                              -- Link to original alert (if from alert system)

    -- ========================================================================
    -- Monitoring Configuration (Per-Ticker Overrides)
    -- ========================================================================
    -- Allows per-ticker monitoring intervals that override state defaults

    check_interval_seconds INTEGER,             -- Custom check interval (NULL = use state default)
                                                -- Overrides hot_check_interval, warm_check_interval, etc.

    next_check_at INTEGER NOT NULL,             -- Unix timestamp of next scheduled check
                                                -- INDEXED for "get tickers needing check" query

    last_checked_at INTEGER,                    -- Unix timestamp of last performance check

    check_count INTEGER DEFAULT 0,              -- Number of times checked (useful for analytics)

    monitoring_enabled INTEGER DEFAULT 1        -- Boolean: 1=enabled, 0=paused
        CHECK(monitoring_enabled IN (0, 1)),    -- Allows pausing specific tickers

    -- ========================================================================
    -- Performance Summary (Latest Snapshot - Denormalized for Speed)
    -- ========================================================================
    -- Duplicates latest snapshot data for fast access without JOIN
    -- Updated each time a new snapshot is recorded

    latest_price REAL,                          -- Most recent price

    latest_volume REAL,                         -- Most recent volume

    latest_rvol REAL,                           -- Most recent relative volume

    latest_vwap REAL,                           -- Most recent VWAP

    price_change_pct REAL,                      -- % change from trigger_price to latest_price

    price_change_since_hot REAL,               -- % change since first added as HOT

    max_price_seen REAL,                        -- Highest price observed (peak tracking)

    min_price_seen REAL,                        -- Lowest price observed (trough tracking)

    snapshot_count INTEGER DEFAULT 0,           -- Number of snapshots captured

    last_snapshot_at INTEGER,                   -- Unix timestamp of last snapshot

    -- ========================================================================
    -- Phase 2-5: Technical Indicators (Reserved for Future Use)
    -- ========================================================================
    -- Pre-defined columns for planned features to avoid schema migrations

    rsi_14 REAL,                                -- 14-period RSI (future: technical analysis)

    macd_signal REAL,                           -- MACD signal (future: momentum indicators)

    bb_position REAL,                           -- Bollinger Band position (future: volatility)

    volume_sma_20 REAL,                         -- 20-day volume moving average (future)

    atr_14 REAL,                                -- Average True Range (future: volatility)

    -- ========================================================================
    -- Phase 3-5: Breakout Detection (Reserved for Future Use)
    -- ========================================================================

    breakout_confirmed INTEGER DEFAULT 0        -- Boolean: breakout detected (future)
        CHECK(breakout_confirmed IN (0, 1)),

    breakout_type TEXT                          -- Type: volume_breakout, price_breakout, etc. (future)
        CHECK(breakout_type IS NULL OR
              breakout_type IN ('volume_breakout', 'price_breakout', 'technical_breakout')),

    breakout_timestamp INTEGER,                 -- When breakout was detected (future)

    resistance_level REAL,                      -- Price resistance level (future: technical)

    support_level REAL,                         -- Price support level (future: technical)

    -- ========================================================================
    -- Phase 4-5: Risk & Position Management (Reserved for Future Use)
    -- ========================================================================

    risk_score REAL,                            -- Computed risk score (future: 0.0-1.0)

    position_size_suggested REAL,               -- Suggested position size % (future)

    stop_loss_price REAL,                       -- Suggested stop loss (future: risk mgmt)

    take_profit_price REAL,                     -- Suggested take profit (future: risk mgmt)

    -- ========================================================================
    -- Metadata & Extensibility
    -- ========================================================================

    tags TEXT,                                  -- JSON array of tags (e.g., ["biotech", "smallcap"])
                                                -- Allows flexible categorization

    metadata TEXT,                              -- JSON object for additional key-value pairs
                                                -- Allows extension without schema changes

    notes TEXT,                                 -- Free-form notes (admin/user notes)

    -- ========================================================================
    -- Timestamps (Audit Trail)
    -- ========================================================================

    created_at INTEGER NOT NULL,                -- Unix timestamp when record created

    updated_at INTEGER NOT NULL,                -- Unix timestamp of last update

    removed_at INTEGER,                         -- Unix timestamp if removed (soft delete)
                                                -- NULL = active, NOT NULL = archived

    -- ========================================================================
    -- Foreign Key Constraints
    -- ========================================================================
    -- (None - this is the root table)

    -- ========================================================================
    -- Check Constraints
    -- ========================================================================
    CHECK(trigger_price IS NULL OR trigger_price > 0),
    CHECK(trigger_volume IS NULL OR trigger_volume >= 0),
    CHECK(check_interval_seconds IS NULL OR check_interval_seconds > 0),
    CHECK(snapshot_count >= 0),
    CHECK(check_count >= 0)
);

-- ============================================================================
-- TABLE: performance_snapshots
-- ============================================================================
--
-- Time-series table for capturing performance data at regular intervals.
-- Unlimited snapshots per ticker for detailed historical analysis.
--
-- Design Decisions:
--   - AUTOINCREMENT PRIMARY KEY for fast inserts
--   - (ticker, snapshot_at) indexed for "get snapshots for ticker" queries
--   - snapshot_at indexed globally for time-based queries
--   - Denormalized: stores ticker directly (not just ID) for query simplicity
--   - Reserved columns for Phase 2-5 technical indicators
--   - Designed for high-frequency writes during market hours
--
-- Query Patterns:
--   1. Get all snapshots for ticker: WHERE ticker = ? ORDER BY snapshot_at
--   2. Get latest snapshot: WHERE ticker = ? ORDER BY snapshot_at DESC LIMIT 1
--   3. Get snapshots in time range: WHERE snapshot_at BETWEEN ? AND ?
--   4. Aggregate analysis: GROUP BY ticker with time windows
--
-- ============================================================================

CREATE TABLE IF NOT EXISTS performance_snapshots (
    -- ========================================================================
    -- Primary Key
    -- ========================================================================
    snapshot_id INTEGER PRIMARY KEY AUTOINCREMENT,

    -- ========================================================================
    -- Foreign Key & Timestamp
    -- ========================================================================
    ticker TEXT NOT NULL,                       -- Ticker symbol (denormalized for performance)

    snapshot_at INTEGER NOT NULL,               -- Unix timestamp of this snapshot
                                                -- INDEXED for time-based queries

    -- ========================================================================
    -- Price Data
    -- ========================================================================
    price REAL NOT NULL,                        -- Current price at snapshot time

    price_change_pct REAL,                      -- % change from trigger_price
                                                -- Duplicated from calculation for query speed

    price_change_since_last REAL,              -- % change from previous snapshot

    high_since_last REAL,                       -- Highest price since last snapshot

    low_since_last REAL,                        -- Lowest price since last snapshot

    -- ========================================================================
    -- Volume Data
    -- ========================================================================
    volume REAL,                                -- Current volume

    volume_change_pct REAL,                     -- % change from trigger_volume

    rvol REAL,                                  -- Relative volume (vs average)

    volume_surge INTEGER DEFAULT 0              -- Boolean: volume surge detected
        CHECK(volume_surge IN (0, 1)),

    -- ========================================================================
    -- Trading Data
    -- ========================================================================
    vwap REAL,                                  -- Volume-weighted average price

    bid REAL,                                   -- Bid price (if available)

    ask REAL,                                   -- Ask price (if available)

    spread REAL,                                -- Bid-ask spread (if available)

    trade_count INTEGER,                        -- Number of trades in interval (if available)

    -- ========================================================================
    -- Market Context
    -- ========================================================================
    market_state TEXT                           -- Market state: premarket, regular, aftermarket, closed
        CHECK(market_state IS NULL OR
              market_state IN ('premarket', 'regular', 'aftermarket', 'closed')),

    -- ========================================================================
    -- Phase 2-5: Technical Indicators (Reserved for Future Use)
    -- ========================================================================
    -- Pre-defined columns for planned technical analysis features

    rsi_14 REAL,                                -- 14-period RSI at snapshot time

    rsi_trend TEXT                              -- RSI trend: oversold, neutral, overbought
        CHECK(rsi_trend IS NULL OR
              rsi_trend IN ('oversold', 'neutral', 'overbought')),

    macd_value REAL,                            -- MACD value

    macd_signal REAL,                           -- MACD signal line

    macd_histogram REAL,                        -- MACD histogram

    bb_upper REAL,                              -- Bollinger Band upper

    bb_middle REAL,                             -- Bollinger Band middle (SMA)

    bb_lower REAL,                              -- Bollinger Band lower

    bb_width REAL,                              -- Bollinger Band width (volatility measure)

    sma_20 REAL,                                -- 20-period simple moving average

    sma_50 REAL,                                -- 50-period simple moving average

    ema_12 REAL,                                -- 12-period exponential moving average

    ema_26 REAL,                                -- 26-period exponential moving average

    atr_14 REAL,                                -- Average True Range (14-period)

    obv REAL,                                   -- On-Balance Volume

    -- ========================================================================
    -- Phase 3-5: Pattern Detection (Reserved for Future Use)
    -- ========================================================================

    pattern_detected TEXT,                      -- Candlestick/chart pattern detected
                                                -- e.g., "hammer", "doji", "breakout"

    pattern_confidence REAL,                    -- Pattern confidence score (0.0-1.0)

    trend_direction TEXT                        -- Trend: up, down, sideways
        CHECK(trend_direction IS NULL OR
              trend_direction IN ('up', 'down', 'sideways')),

    momentum_score REAL,                        -- Momentum indicator (-1.0 to +1.0)

    -- ========================================================================
    -- Phase 4-5: Signal Generation (Reserved for Future Use)
    -- ========================================================================

    buy_signal INTEGER DEFAULT 0                -- Boolean: buy signal generated
        CHECK(buy_signal IN (0, 1)),

    sell_signal INTEGER DEFAULT 0               -- Boolean: sell signal generated
        CHECK(sell_signal IN (0, 1)),

    signal_strength REAL,                       -- Signal strength (0.0-1.0)

    signal_type TEXT,                           -- Signal type: breakout, reversal, continuation, etc.

    -- ========================================================================
    -- Data Source & Quality
    -- ========================================================================

    data_source TEXT,                           -- Data source: tiingo, polygon, yahoo, etc.

    data_quality REAL DEFAULT 1.0,              -- Data quality score (0.0-1.0)
                                                -- Lower if delayed, partial, or estimated

    is_estimated INTEGER DEFAULT 0              -- Boolean: data is estimated/interpolated
        CHECK(is_estimated IN (0, 1)),

    -- ========================================================================
    -- Metadata
    -- ========================================================================

    snapshot_metadata TEXT,                     -- JSON object for additional snapshot data
                                                -- Allows extension without schema changes

    -- ========================================================================
    -- Foreign Key Constraints
    -- ========================================================================
    FOREIGN KEY (ticker) REFERENCES watchlist_tickers(ticker)
        ON DELETE CASCADE                       -- Delete snapshots when ticker removed
        ON UPDATE CASCADE,                      -- Update if ticker changes (rare)

    -- ========================================================================
    -- Check Constraints
    -- ========================================================================
    CHECK(price > 0),
    CHECK(volume IS NULL OR volume >= 0),
    CHECK(rvol IS NULL OR rvol >= 0)
);

-- ============================================================================
-- INDEXES: Optimized for Common Query Patterns
-- ============================================================================
--
-- Index Strategy:
--   1. Cover all WHERE clause columns in common queries
--   2. Optimize for both point lookups and range scans
--   3. Consider index size vs query speed tradeoff
--   4. Use composite indexes for multi-column filters
--
-- ============================================================================

-- ----------------------------------------------------------------------------
-- watchlist_tickers indexes
-- ----------------------------------------------------------------------------

-- Query: "Get all HOT tickers" (most common query)
-- SELECT * FROM watchlist_tickers WHERE state = 'HOT' AND monitoring_enabled = 1
CREATE INDEX IF NOT EXISTS idx_tickers_state_monitoring
    ON watchlist_tickers(state, monitoring_enabled);

-- Query: "Get tickers needing check" (scheduled monitoring)
-- SELECT * FROM watchlist_tickers WHERE next_check_at <= ? AND monitoring_enabled = 1
CREATE INDEX IF NOT EXISTS idx_tickers_next_check
    ON watchlist_tickers(next_check_at, monitoring_enabled)
    WHERE monitoring_enabled = 1;  -- Partial index for active tickers only

-- Query: "Get tickers by catalyst type" (analytics)
-- SELECT * FROM watchlist_tickers WHERE catalyst_type = ?
CREATE INDEX IF NOT EXISTS idx_tickers_catalyst_type
    ON watchlist_tickers(catalyst_type);

-- Query: "Get recently added tickers" (monitoring)
-- SELECT * FROM watchlist_tickers ORDER BY trigger_timestamp DESC LIMIT 10
CREATE INDEX IF NOT EXISTS idx_tickers_trigger_timestamp
    ON watchlist_tickers(trigger_timestamp DESC);

-- Query: "Get tickers by state transition" (lifecycle analysis)
-- SELECT * FROM watchlist_tickers WHERE state = ? AND last_state_change > ?
CREATE INDEX IF NOT EXISTS idx_tickers_state_change
    ON watchlist_tickers(state, last_state_change);

-- Query: "Get active tickers" (exclude soft-deleted)
-- SELECT * FROM watchlist_tickers WHERE removed_at IS NULL
CREATE INDEX IF NOT EXISTS idx_tickers_removed_at
    ON watchlist_tickers(removed_at)
    WHERE removed_at IS NULL;  -- Partial index for active records

-- Query: "Find tickers by alert_id" (traceability)
-- SELECT * FROM watchlist_tickers WHERE alert_id = ?
CREATE INDEX IF NOT EXISTS idx_tickers_alert_id
    ON watchlist_tickers(alert_id)
    WHERE alert_id IS NOT NULL;

-- ----------------------------------------------------------------------------
-- performance_snapshots indexes
-- ----------------------------------------------------------------------------

-- Query: "Get all snapshots for ticker" (time-series analysis)
-- SELECT * FROM performance_snapshots WHERE ticker = ? ORDER BY snapshot_at
CREATE INDEX IF NOT EXISTS idx_snapshots_ticker_time
    ON performance_snapshots(ticker, snapshot_at DESC);

-- Query: "Get latest snapshot for ticker" (current state)
-- SELECT * FROM performance_snapshots WHERE ticker = ? ORDER BY snapshot_at DESC LIMIT 1
-- (Covered by idx_snapshots_ticker_time)

-- Query: "Get snapshots in time range" (historical analysis)
-- SELECT * FROM performance_snapshots WHERE snapshot_at BETWEEN ? AND ?
CREATE INDEX IF NOT EXISTS idx_snapshots_time
    ON performance_snapshots(snapshot_at DESC);

-- Query: "Get snapshots with signals" (Phase 4-5 feature)
-- SELECT * FROM performance_snapshots WHERE buy_signal = 1 OR sell_signal = 1
CREATE INDEX IF NOT EXISTS idx_snapshots_signals
    ON performance_snapshots(buy_signal, sell_signal)
    WHERE buy_signal = 1 OR sell_signal = 1;  -- Partial index for signals only

-- Query: "Get volume surge events" (spike detection)
-- SELECT * FROM performance_snapshots WHERE volume_surge = 1
CREATE INDEX IF NOT EXISTS idx_snapshots_volume_surge
    ON performance_snapshots(ticker, snapshot_at)
    WHERE volume_surge = 1;  -- Partial index for surges only

-- ============================================================================
-- VIEWS: Convenient Queries for Common Use Cases
-- ============================================================================

-- ----------------------------------------------------------------------------
-- VIEW: v_hot_tickers
-- Usage: Quick access to all active HOT tickers with latest performance
-- ----------------------------------------------------------------------------
CREATE VIEW IF NOT EXISTS v_hot_tickers AS
SELECT
    ticker,
    trigger_reason,
    catalyst_type,
    trigger_timestamp,
    latest_price,
    price_change_pct,
    latest_volume,
    latest_rvol,
    next_check_at,
    snapshot_count
FROM watchlist_tickers
WHERE state = 'HOT'
    AND monitoring_enabled = 1
    AND removed_at IS NULL
ORDER BY trigger_timestamp DESC;

-- ----------------------------------------------------------------------------
-- VIEW: v_warm_tickers
-- Usage: Quick access to all active WARM tickers
-- ----------------------------------------------------------------------------
CREATE VIEW IF NOT EXISTS v_warm_tickers AS
SELECT
    ticker,
    trigger_reason,
    catalyst_type,
    trigger_timestamp,
    latest_price,
    price_change_pct,
    latest_volume,
    latest_rvol,
    next_check_at,
    snapshot_count,
    last_state_change
FROM watchlist_tickers
WHERE state = 'WARM'
    AND monitoring_enabled = 1
    AND removed_at IS NULL
ORDER BY last_state_change DESC;

-- ----------------------------------------------------------------------------
-- VIEW: v_cool_tickers
-- Usage: Quick access to all COOL tickers (candidates for removal)
-- ----------------------------------------------------------------------------
CREATE VIEW IF NOT EXISTS v_cool_tickers AS
SELECT
    ticker,
    trigger_reason,
    catalyst_type,
    trigger_timestamp,
    latest_price,
    price_change_pct,
    snapshot_count,
    last_state_change,
    CAST((strftime('%s', 'now') - last_state_change) / 86400.0 AS INTEGER) as days_in_cool
FROM watchlist_tickers
WHERE state = 'COOL'
    AND removed_at IS NULL
ORDER BY last_state_change ASC;

-- ----------------------------------------------------------------------------
-- VIEW: v_tickers_needing_check
-- Usage: Get all tickers that need performance check now
-- ----------------------------------------------------------------------------
CREATE VIEW IF NOT EXISTS v_tickers_needing_check AS
SELECT
    ticker,
    state,
    next_check_at,
    check_interval_seconds,
    last_checked_at,
    latest_price,
    snapshot_count,
    CAST((strftime('%s', 'now') - next_check_at) AS INTEGER) as seconds_overdue
FROM watchlist_tickers
WHERE next_check_at <= strftime('%s', 'now')
    AND monitoring_enabled = 1
    AND removed_at IS NULL
ORDER BY next_check_at ASC;

-- ----------------------------------------------------------------------------
-- VIEW: v_ticker_performance_summary
-- Usage: Comprehensive performance summary per ticker
-- ----------------------------------------------------------------------------
CREATE VIEW IF NOT EXISTS v_ticker_performance_summary AS
SELECT
    t.ticker,
    t.state,
    t.catalyst_type,
    t.trigger_price,
    t.trigger_timestamp,
    t.latest_price,
    t.price_change_pct,
    t.max_price_seen,
    t.min_price_seen,
    t.snapshot_count,
    -- Calculate days since trigger
    CAST((strftime('%s', 'now') - t.trigger_timestamp) / 86400.0 AS INTEGER) as days_tracked,
    -- Calculate days in current state
    CAST((strftime('%s', 'now') - t.last_state_change) / 86400.0 AS INTEGER) as days_in_state,
    -- Peak gain/loss
    ROUND((t.max_price_seen - t.trigger_price) / t.trigger_price * 100, 2) as peak_gain_pct,
    ROUND((t.min_price_seen - t.trigger_price) / t.trigger_price * 100, 2) as max_loss_pct
FROM watchlist_tickers t
WHERE t.removed_at IS NULL
ORDER BY t.trigger_timestamp DESC;

-- ----------------------------------------------------------------------------
-- VIEW: v_recent_snapshots
-- Usage: Latest 100 snapshots across all tickers (recent activity)
-- ----------------------------------------------------------------------------
CREATE VIEW IF NOT EXISTS v_recent_snapshots AS
SELECT
    s.ticker,
    s.snapshot_at,
    s.price,
    s.volume,
    s.rvol,
    s.vwap,
    s.price_change_pct,
    s.volume_surge,
    t.state,
    t.catalyst_type
FROM performance_snapshots s
JOIN watchlist_tickers t ON s.ticker = t.ticker
WHERE t.removed_at IS NULL
ORDER BY s.snapshot_at DESC
LIMIT 100;

-- ============================================================================
-- TRIGGERS: Maintain Data Integrity & Automation
-- ============================================================================

-- ----------------------------------------------------------------------------
-- TRIGGER: update_ticker_timestamp
-- Purpose: Automatically update updated_at timestamp on ticker changes
-- ----------------------------------------------------------------------------
CREATE TRIGGER IF NOT EXISTS update_ticker_timestamp
AFTER UPDATE ON watchlist_tickers
FOR EACH ROW
BEGIN
    UPDATE watchlist_tickers
    SET updated_at = strftime('%s', 'now')
    WHERE ticker = NEW.ticker;
END;

-- ----------------------------------------------------------------------------
-- TRIGGER: track_state_transitions
-- Purpose: Track state changes and increment transition counter
-- ----------------------------------------------------------------------------
CREATE TRIGGER IF NOT EXISTS track_state_transitions
AFTER UPDATE OF state ON watchlist_tickers
FOR EACH ROW
WHEN OLD.state != NEW.state
BEGIN
    UPDATE watchlist_tickers
    SET
        previous_state = OLD.state,
        state_transition_count = state_transition_count + 1,
        last_state_change = strftime('%s', 'now')
    WHERE ticker = NEW.ticker;
END;

-- ----------------------------------------------------------------------------
-- TRIGGER: track_promotions
-- Purpose: Increment promoted_count when ticker returns to HOT state
-- ----------------------------------------------------------------------------
CREATE TRIGGER IF NOT EXISTS track_promotions
AFTER UPDATE OF state ON watchlist_tickers
FOR EACH ROW
WHEN NEW.state = 'HOT' AND OLD.state != 'HOT'
BEGIN
    UPDATE watchlist_tickers
    SET promoted_count = promoted_count + 1
    WHERE ticker = NEW.ticker;
END;

-- ----------------------------------------------------------------------------
-- TRIGGER: update_peak_tracking
-- Purpose: Update max/min price tracking when new snapshot is added
-- Note: This is a basic trigger; application logic should also handle this
--       for better control and to avoid trigger complexity
-- ----------------------------------------------------------------------------
CREATE TRIGGER IF NOT EXISTS update_peak_tracking
AFTER INSERT ON performance_snapshots
FOR EACH ROW
BEGIN
    UPDATE watchlist_tickers
    SET
        max_price_seen = MAX(COALESCE(max_price_seen, NEW.price), NEW.price),
        min_price_seen = MIN(COALESCE(min_price_seen, NEW.price), NEW.price)
    WHERE ticker = NEW.ticker;
END;

-- ============================================================================
-- INITIAL DATA & CONFIGURATION
-- ============================================================================

-- No initial data seeded by default.
-- Application code should handle:
--   1. State configuration (HOT/WARM/COOL durations, check intervals)
--   2. Default monitoring settings
--   3. Catalyst type definitions

-- ============================================================================
-- SCHEMA VERSION & MIGRATION SUPPORT
-- ============================================================================

-- ----------------------------------------------------------------------------
-- TABLE: schema_version
-- Purpose: Track schema version for migrations
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER PRIMARY KEY,
    applied_at INTEGER NOT NULL DEFAULT (strftime('%s', 'now')),
    description TEXT
);

-- Insert current schema version
INSERT OR IGNORE INTO schema_version (version, description)
VALUES (1, 'Initial watchlist performance tracking schema');

-- ============================================================================
-- VACUUM & OPTIMIZATION RECOMMENDATIONS
-- ============================================================================
--
-- Run these commands periodically for optimal performance:
--
--   1. After bulk deletes:
--      VACUUM;
--
--   2. After significant data changes:
--      ANALYZE;
--
--   3. For query optimization:
--      PRAGMA optimize;
--
--   4. Check index usage:
--      SELECT * FROM sqlite_master WHERE type='index';
--
--   5. Check table stats:
--      SELECT name, tbl_name, sql FROM sqlite_master WHERE type='table';
--
-- ============================================================================

-- ============================================================================
-- EXAMPLE QUERIES (For Testing & Documentation)
-- ============================================================================
--
-- 1. Get all HOT tickers:
--    SELECT * FROM v_hot_tickers;
--
-- 2. Get tickers needing check now:
--    SELECT * FROM v_tickers_needing_check;
--
-- 3. Get all snapshots for ticker:
--    SELECT * FROM performance_snapshots
--    WHERE ticker = 'AAPL'
--    ORDER BY snapshot_at DESC;
--
-- 4. Get latest snapshot for ticker:
--    SELECT * FROM performance_snapshots
--    WHERE ticker = 'AAPL'
--    ORDER BY snapshot_at DESC
--    LIMIT 1;
--
-- 5. Get performance summary for all tickers:
--    SELECT * FROM v_ticker_performance_summary;
--
-- 6. Get tickers by catalyst type:
--    SELECT * FROM watchlist_tickers
--    WHERE catalyst_type = 'fda_approval'
--    AND removed_at IS NULL;
--
-- 7. Get tickers that gained > 10%:
--    SELECT * FROM watchlist_tickers
--    WHERE price_change_pct > 10.0
--    AND removed_at IS NULL
--    ORDER BY price_change_pct DESC;
--
-- 8. Count tickers by state:
--    SELECT state, COUNT(*) as count
--    FROM watchlist_tickers
--    WHERE removed_at IS NULL
--    GROUP BY state;
--
-- 9. Get volume surge events:
--    SELECT s.ticker, s.snapshot_at, s.volume, s.rvol, t.catalyst_type
--    FROM performance_snapshots s
--    JOIN watchlist_tickers t ON s.ticker = t.ticker
--    WHERE s.volume_surge = 1
--    ORDER BY s.snapshot_at DESC;
--
-- 10. Get tickers ready to transition from WARM to COOL:
--     SELECT ticker,
--            (strftime('%s', 'now') - last_state_change) / 86400.0 as days_in_warm
--     FROM watchlist_tickers
--     WHERE state = 'WARM'
--     AND (strftime('%s', 'now') - last_state_change) / 86400.0 > ?;  -- e.g., > 7 days
--
-- ============================================================================

-- ============================================================================
-- END OF SCHEMA
-- ============================================================================
