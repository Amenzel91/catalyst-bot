-- ============================================================================
-- TRADING DATABASE SCHEMA
-- Database: data/trading.db
-- Migration: 002_create_trading_tables.py
-- ============================================================================
-- This file contains the complete SQL schema for the trading database.
-- It tracks orders, fills, portfolio snapshots, and performance metrics.
-- ============================================================================

-- ============================================================================
-- TABLE: orders
-- ============================================================================
-- Tracks all orders submitted to the broker (pending, filled, cancelled, rejected).
-- ============================================================================

CREATE TABLE IF NOT EXISTS orders (
    -- Primary keys
    order_id TEXT PRIMARY KEY,
    client_order_id TEXT UNIQUE NOT NULL,

    -- Order details
    ticker TEXT NOT NULL,
    order_type TEXT NOT NULL CHECK(
        order_type IN ('market', 'limit', 'stop', 'stop_limit', 'trailing_stop')
    ),
    side TEXT NOT NULL CHECK(side IN ('buy', 'sell')),
    quantity INTEGER NOT NULL CHECK(quantity > 0),

    -- Price parameters
    limit_price REAL CHECK(limit_price IS NULL OR limit_price > 0),
    stop_price REAL CHECK(stop_price IS NULL OR stop_price > 0),

    -- Order configuration
    time_in_force TEXT NOT NULL DEFAULT 'day' CHECK(
        time_in_force IN ('day', 'gtc', 'ioc', 'fok', 'opg', 'cls')
    ),

    -- Order status
    status TEXT NOT NULL DEFAULT 'pending' CHECK(
        status IN (
            'pending',
            'new',
            'accepted',
            'partially_filled',
            'filled',
            'cancelled',
            'rejected',
            'expired',
            'replaced',
            'pending_cancel',
            'pending_replace'
        )
    ),

    -- Timestamps
    submitted_at INTEGER NOT NULL,
    updated_at INTEGER NOT NULL,
    filled_at INTEGER,
    cancelled_at INTEGER,
    expired_at INTEGER,

    -- Fill information
    filled_quantity INTEGER DEFAULT 0 CHECK(filled_quantity >= 0),
    filled_avg_price REAL CHECK(filled_avg_price IS NULL OR filled_avg_price > 0),
    commission REAL DEFAULT 0.0,

    -- Relationships
    position_id TEXT,
    parent_order_id TEXT,  -- For bracket orders

    -- Strategy metadata
    strategy TEXT,
    signal_score REAL CHECK(signal_score >= 0 AND signal_score <= 1),

    -- Execution quality metrics
    expected_price REAL,
    slippage REAL,
    reject_reason TEXT,

    -- Additional context (JSON)
    metadata TEXT,

    -- Constraints
    CONSTRAINT valid_filled_quantity CHECK(filled_quantity <= quantity),
    CONSTRAINT valid_limit_order CHECK(
        (order_type = 'limit' AND limit_price IS NOT NULL)
        OR (order_type != 'limit')
    ),
    CONSTRAINT valid_stop_order CHECK(
        (order_type IN ('stop', 'stop_limit') AND stop_price IS NOT NULL)
        OR (order_type NOT IN ('stop', 'stop_limit'))
    )
);

-- ============================================================================
-- TABLE: fills
-- ============================================================================
-- Tracks individual fill events (partial and complete fills).
-- ============================================================================

CREATE TABLE IF NOT EXISTS fills (
    -- Primary key
    fill_id TEXT PRIMARY KEY,

    -- Order reference
    order_id TEXT NOT NULL,
    client_order_id TEXT NOT NULL,

    -- Fill details
    ticker TEXT NOT NULL,
    side TEXT NOT NULL CHECK(side IN ('buy', 'sell')),
    quantity INTEGER NOT NULL CHECK(quantity > 0),
    price REAL NOT NULL CHECK(price > 0),
    filled_at INTEGER NOT NULL,

    -- Execution details
    liquidity TEXT CHECK(liquidity IN ('maker', 'taker', 'unknown')),
    commission REAL DEFAULT 0.0,

    -- Relationships
    position_id TEXT,
    exchange TEXT,

    -- Additional context (JSON)
    metadata TEXT,

    -- Foreign keys
    FOREIGN KEY (order_id) REFERENCES orders(order_id)
);

-- ============================================================================
-- TABLE: portfolio_snapshots
-- ============================================================================
-- Daily snapshots of portfolio value and composition.
-- ============================================================================

CREATE TABLE IF NOT EXISTS portfolio_snapshots (
    -- Primary key
    snapshot_id INTEGER PRIMARY KEY AUTOINCREMENT,

    -- Snapshot timing
    snapshot_date TEXT NOT NULL UNIQUE,
    snapshot_time INTEGER NOT NULL UNIQUE,

    -- Portfolio values
    total_equity REAL NOT NULL,
    cash_balance REAL NOT NULL,
    long_market_value REAL NOT NULL DEFAULT 0.0,
    short_market_value REAL NOT NULL DEFAULT 0.0,
    net_liquidation_value REAL NOT NULL,
    positions_count INTEGER NOT NULL DEFAULT 0,

    -- Daily P&L
    daily_pnl REAL NOT NULL DEFAULT 0.0,
    daily_return_pct REAL NOT NULL DEFAULT 0.0,

    -- Cumulative P&L
    cumulative_pnl REAL NOT NULL DEFAULT 0.0,
    cumulative_return_pct REAL NOT NULL DEFAULT 0.0,

    -- Margin and leverage
    buying_power REAL,
    leverage REAL,
    margin_used REAL,

    -- P&L breakdown
    unrealized_pnl REAL DEFAULT 0.0,
    realized_pnl_today REAL DEFAULT 0.0,

    -- Trading activity
    trades_today INTEGER DEFAULT 0,
    wins_today INTEGER DEFAULT 0,
    losses_today INTEGER DEFAULT 0,

    -- Additional context (JSON)
    metadata TEXT,

    -- Constraints
    CONSTRAINT valid_equity CHECK(total_equity >= 0),
    CONSTRAINT valid_positions_count CHECK(positions_count >= 0)
);

-- ============================================================================
-- TABLE: performance_metrics
-- ============================================================================
-- Daily performance statistics and risk metrics.
-- ============================================================================

CREATE TABLE IF NOT EXISTS performance_metrics (
    -- Primary key
    metric_id INTEGER PRIMARY KEY AUTOINCREMENT,

    -- Timing
    metric_date TEXT NOT NULL UNIQUE,
    metric_time INTEGER NOT NULL UNIQUE,

    -- Risk-adjusted returns
    sharpe_ratio REAL,
    sortino_ratio REAL,
    calmar_ratio REAL,
    omega_ratio REAL,

    -- Drawdown metrics
    max_drawdown REAL,
    max_drawdown_pct REAL,
    current_drawdown REAL,
    current_drawdown_pct REAL,
    days_in_drawdown INTEGER DEFAULT 0,
    recovery_days INTEGER,

    -- Return metrics (rolling windows)
    return_1d REAL,
    return_7d REAL,
    return_30d REAL,
    return_ytd REAL,
    return_inception REAL,

    -- Volatility metrics
    volatility_daily REAL,
    volatility_annualized REAL,
    downside_deviation REAL,

    -- Trade statistics (rolling 30 days)
    total_trades_30d INTEGER DEFAULT 0,
    winning_trades_30d INTEGER DEFAULT 0,
    losing_trades_30d INTEGER DEFAULT 0,
    win_rate_30d REAL,

    -- Profit metrics (rolling 30 days)
    avg_win_30d REAL,
    avg_loss_30d REAL,
    profit_factor_30d REAL,
    expectancy_30d REAL,
    largest_win_30d REAL,
    largest_loss_30d REAL,

    -- Streak tracking
    current_win_streak INTEGER DEFAULT 0,
    current_loss_streak INTEGER DEFAULT 0,
    max_win_streak INTEGER DEFAULT 0,
    max_loss_streak INTEGER DEFAULT 0,

    -- Portfolio metrics
    avg_position_size REAL,
    avg_holding_period_hours REAL,
    turnover_rate REAL,

    -- Benchmark comparison
    benchmark_return REAL,
    alpha REAL,
    beta REAL,
    correlation_to_benchmark REAL,

    -- Strategy-specific
    strategy TEXT,
    metadata TEXT
);

-- ============================================================================
-- INDEXES
-- ============================================================================
-- Indexes for common query patterns and performance optimization.
-- ============================================================================

-- Orders table indexes
CREATE INDEX IF NOT EXISTS idx_orders_ticker ON orders(ticker);
CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(status);
CREATE INDEX IF NOT EXISTS idx_orders_submitted_at ON orders(submitted_at DESC);
CREATE INDEX IF NOT EXISTS idx_orders_position_id ON orders(position_id);
CREATE INDEX IF NOT EXISTS idx_orders_strategy ON orders(strategy);
CREATE INDEX IF NOT EXISTS idx_orders_client_order_id ON orders(client_order_id);

-- Fills table indexes
CREATE INDEX IF NOT EXISTS idx_fills_order_id ON fills(order_id);
CREATE INDEX IF NOT EXISTS idx_fills_ticker ON fills(ticker);
CREATE INDEX IF NOT EXISTS idx_fills_filled_at ON fills(filled_at DESC);
CREATE INDEX IF NOT EXISTS idx_fills_position_id ON fills(position_id);

-- Portfolio snapshots indexes
CREATE INDEX IF NOT EXISTS idx_portfolio_snapshots_date ON portfolio_snapshots(snapshot_date DESC);
CREATE INDEX IF NOT EXISTS idx_portfolio_snapshots_time ON portfolio_snapshots(snapshot_time DESC);

-- Performance metrics indexes
CREATE INDEX IF NOT EXISTS idx_performance_metrics_date ON performance_metrics(metric_date DESC);
CREATE INDEX IF NOT EXISTS idx_performance_metrics_strategy ON performance_metrics(strategy);

-- ============================================================================
-- VIEWS
-- ============================================================================
-- Pre-built views for common queries with calculated fields.
-- ============================================================================

-- View: Recent order activity
CREATE VIEW IF NOT EXISTS v_recent_orders AS
SELECT
    order_id,
    client_order_id,
    ticker,
    order_type,
    side,
    quantity,
    filled_quantity,
    status,
    filled_avg_price,
    datetime(submitted_at, 'unixepoch') AS submitted_datetime,
    datetime(filled_at, 'unixepoch') AS filled_datetime,
    strategy,
    slippage
FROM orders
ORDER BY submitted_at DESC
LIMIT 100;

-- View: Order fill statistics
CREATE VIEW IF NOT EXISTS v_order_fill_stats AS
SELECT
    o.order_id,
    o.ticker,
    o.side,
    o.quantity AS order_quantity,
    o.filled_quantity,
    COUNT(f.fill_id) AS num_fills,
    AVG(f.price) AS avg_fill_price,
    MIN(f.price) AS best_fill_price,
    MAX(f.price) AS worst_fill_price
FROM orders o
LEFT JOIN fills f ON o.order_id = f.order_id
WHERE o.status IN ('filled', 'partially_filled')
GROUP BY o.order_id;

-- View: Equity curve
CREATE VIEW IF NOT EXISTS v_equity_curve AS
SELECT
    snapshot_date,
    total_equity,
    cumulative_pnl,
    cumulative_return_pct,
    daily_return_pct,
    positions_count,
    trades_today
FROM portfolio_snapshots
ORDER BY snapshot_date ASC;

-- View: Performance summary
CREATE VIEW IF NOT EXISTS v_performance_summary AS
SELECT
    metric_date,
    sharpe_ratio,
    max_drawdown_pct,
    win_rate_30d,
    profit_factor_30d,
    return_30d,
    total_trades_30d,
    avg_win_30d,
    avg_loss_30d
FROM performance_metrics
ORDER BY metric_date DESC
LIMIT 30;

-- ============================================================================
-- SAMPLE QUERIES
-- ============================================================================

/*
-- Get all pending orders
SELECT * FROM orders WHERE status = 'pending' ORDER BY submitted_at DESC;

-- Get fill rate today
SELECT
    COUNT(CASE WHEN status = 'filled' THEN 1 END) * 1.0 / COUNT(*) as fill_rate,
    COUNT(*) as total_orders
FROM orders
WHERE DATE(submitted_at, 'unixepoch') = DATE('now');

-- Get recent fills with slippage
SELECT
    o.ticker,
    o.side,
    o.expected_price,
    f.price as actual_price,
    (f.price - o.expected_price) as slippage_dollars,
    datetime(f.filled_at, 'unixepoch') as filled_time
FROM fills f
JOIN orders o ON f.order_id = o.order_id
ORDER BY f.filled_at DESC
LIMIT 20;

-- Get portfolio equity curve
SELECT * FROM v_equity_curve;

-- Get current Sharpe ratio and drawdown
SELECT
    sharpe_ratio,
    max_drawdown_pct,
    current_drawdown_pct,
    days_in_drawdown
FROM performance_metrics
ORDER BY metric_date DESC
LIMIT 1;

-- Get win rate by strategy
SELECT
    o.strategy,
    COUNT(*) as total_orders,
    AVG(CASE WHEN o.side = 'sell' THEN 1 ELSE 0 END) as close_rate
FROM orders o
WHERE o.status = 'filled'
GROUP BY o.strategy;

-- Get average slippage by order type
SELECT
    order_type,
    AVG(slippage) as avg_slippage,
    COUNT(*) as count
FROM orders
WHERE slippage IS NOT NULL
GROUP BY order_type;

-- Get daily trading activity
SELECT
    DATE(submitted_at, 'unixepoch') as trade_date,
    COUNT(*) as orders_placed,
    COUNT(CASE WHEN status = 'filled' THEN 1 END) as orders_filled,
    SUM(quantity * filled_avg_price) as total_volume
FROM orders
GROUP BY trade_date
ORDER BY trade_date DESC
LIMIT 30;

-- Use pre-built views
SELECT * FROM v_recent_orders;
SELECT * FROM v_performance_summary;
*/
