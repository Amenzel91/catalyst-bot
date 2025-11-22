"""
Migration 002: Create Trading Database Tables

Creates tables for order execution, fills, portfolio tracking, and performance metrics.
Database: data/trading.db

Tables:
- orders: All orders placed (pending, filled, cancelled, rejected)
- fills: Order fill events (partial and complete fills)
- portfolio_snapshots: Daily portfolio value snapshots
- performance_metrics: Daily performance metrics (Sharpe, drawdown, etc.)
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from catalyst_bot.storage import _ensure_dir, init_optimized_connection


TRADING_DB_PATH = "data/trading.db"


def create_orders_table(conn: sqlite3.Connection) -> None:
    """
    Create the orders table for tracking all order submissions.

    Schema Design:
    - order_id: Broker's unique order identifier
    - client_order_id: Our internal order tracking ID
    - ticker: Stock symbol
    - order_type: market, limit, stop, stop_limit
    - side: buy or sell
    - quantity: Number of shares
    - limit_price: Limit price for limit/stop_limit orders
    - stop_price: Stop trigger price for stop/stop_limit orders
    - time_in_force: day, gtc (good-til-cancelled), ioc (immediate-or-cancel)
    - status: pending, filled, partially_filled, cancelled, rejected, expired
    - submitted_at: When order was submitted to broker
    - filled_at: When order was completely filled (NULL if not filled)
    - cancelled_at: When order was cancelled (NULL if not cancelled)
    - filled_quantity: How many shares were filled
    - filled_avg_price: Average fill price
    - position_id: Link to position this order opened/closed
    - strategy: Which strategy generated this order
    - metadata: Additional order context
    """
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS orders (
            order_id TEXT PRIMARY KEY,
            client_order_id TEXT UNIQUE NOT NULL,
            ticker TEXT NOT NULL,
            order_type TEXT NOT NULL CHECK(
                order_type IN ('market', 'limit', 'stop', 'stop_limit', 'trailing_stop')
            ),
            side TEXT NOT NULL CHECK(side IN ('buy', 'sell')),
            quantity INTEGER NOT NULL CHECK(quantity > 0),
            limit_price REAL CHECK(limit_price IS NULL OR limit_price > 0),
            stop_price REAL CHECK(stop_price IS NULL OR stop_price > 0),
            time_in_force TEXT NOT NULL DEFAULT 'day' CHECK(
                time_in_force IN ('day', 'gtc', 'ioc', 'fok', 'opg', 'cls')
            ),
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
            submitted_at INTEGER NOT NULL,
            updated_at INTEGER NOT NULL,
            filled_at INTEGER,
            cancelled_at INTEGER,
            expired_at INTEGER,
            filled_quantity INTEGER DEFAULT 0 CHECK(filled_quantity >= 0),
            filled_avg_price REAL CHECK(filled_avg_price IS NULL OR filled_avg_price > 0),
            commission REAL DEFAULT 0.0,
            position_id TEXT,
            parent_order_id TEXT,
            strategy TEXT,
            signal_score REAL CHECK(signal_score >= 0 AND signal_score <= 1),
            expected_price REAL,
            slippage REAL,
            reject_reason TEXT,
            metadata TEXT,
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
        """
    )

    print("✓ Created 'orders' table")


def create_fills_table(conn: sqlite3.Connection) -> None:
    """
    Create the fills table for tracking order fill events.

    This table records every fill event, including partial fills.
    Multiple fill records may exist for a single order if filled incrementally.

    Schema Design:
    - fill_id: Unique fill event identifier
    - order_id: Reference to the order that was filled
    - ticker: Stock symbol
    - side: buy or sell
    - quantity: Number of shares filled in this event
    - price: Actual fill price
    - filled_at: Timestamp of fill
    - liquidity: Whether this fill added or removed liquidity (maker/taker)
    - commission: Commission charged for this fill
    """
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS fills (
            fill_id TEXT PRIMARY KEY,
            order_id TEXT NOT NULL,
            client_order_id TEXT NOT NULL,
            ticker TEXT NOT NULL,
            side TEXT NOT NULL CHECK(side IN ('buy', 'sell')),
            quantity INTEGER NOT NULL CHECK(quantity > 0),
            price REAL NOT NULL CHECK(price > 0),
            filled_at INTEGER NOT NULL,
            liquidity TEXT CHECK(liquidity IN ('maker', 'taker', 'unknown')),
            commission REAL DEFAULT 0.0,
            position_id TEXT,
            exchange TEXT,
            metadata TEXT,
            FOREIGN KEY (order_id) REFERENCES orders(order_id)
        );
        """
    )

    print("✓ Created 'fills' table")


def create_portfolio_snapshots_table(conn: sqlite3.Connection) -> None:
    """
    Create the portfolio_snapshots table for daily portfolio value tracking.

    Takes a snapshot of portfolio state at market close each day.
    Used for performance tracking and equity curve generation.

    Schema Design:
    - snapshot_id: Auto-incrementing ID
    - snapshot_date: Date of snapshot (YYYY-MM-DD)
    - snapshot_time: Unix timestamp
    - total_equity: Total portfolio value (cash + positions)
    - cash_balance: Available cash
    - long_market_value: Total value of long positions
    - short_market_value: Total value of short positions
    - positions_count: Number of open positions
    - daily_pnl: P&L for this day
    - cumulative_pnl: Total P&L since inception
    - buying_power: Available buying power (includes margin)
    """
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS portfolio_snapshots (
            snapshot_id INTEGER PRIMARY KEY AUTOINCREMENT,
            snapshot_date TEXT NOT NULL UNIQUE,
            snapshot_time INTEGER NOT NULL UNIQUE,
            total_equity REAL NOT NULL,
            cash_balance REAL NOT NULL,
            long_market_value REAL NOT NULL DEFAULT 0.0,
            short_market_value REAL NOT NULL DEFAULT 0.0,
            net_liquidation_value REAL NOT NULL,
            positions_count INTEGER NOT NULL DEFAULT 0,
            daily_pnl REAL NOT NULL DEFAULT 0.0,
            daily_return_pct REAL NOT NULL DEFAULT 0.0,
            cumulative_pnl REAL NOT NULL DEFAULT 0.0,
            cumulative_return_pct REAL NOT NULL DEFAULT 0.0,
            buying_power REAL,
            leverage REAL,
            margin_used REAL,
            unrealized_pnl REAL DEFAULT 0.0,
            realized_pnl_today REAL DEFAULT 0.0,
            trades_today INTEGER DEFAULT 0,
            wins_today INTEGER DEFAULT 0,
            losses_today INTEGER DEFAULT 0,
            metadata TEXT,
            CONSTRAINT valid_equity CHECK(total_equity >= 0),
            CONSTRAINT valid_positions_count CHECK(positions_count >= 0)
        );
        """
    )

    print("✓ Created 'portfolio_snapshots' table")


def create_performance_metrics_table(conn: sqlite3.Connection) -> None:
    """
    Create the performance_metrics table for daily performance statistics.

    Stores calculated metrics like Sharpe ratio, drawdown, volatility, etc.
    Used for monitoring strategy performance over time.

    Schema Design:
    - metric_date: Date for these metrics
    - sharpe_ratio: Risk-adjusted return (rolling 30-day)
    - sortino_ratio: Downside risk-adjusted return
    - max_drawdown: Maximum peak-to-trough decline
    - current_drawdown: Current drawdown from peak
    - volatility: Standard deviation of returns (annualized)
    - win_rate: Percentage of winning trades
    - profit_factor: Gross profit / Gross loss
    - average_win: Average profit on winning trades
    - average_loss: Average loss on losing trades
    """
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS performance_metrics (
            metric_id INTEGER PRIMARY KEY AUTOINCREMENT,
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
        """
    )

    print("✓ Created 'performance_metrics' table")


def create_indexes(conn: sqlite3.Connection) -> None:
    """
    Create indexes for common query patterns.
    """
    indexes = [
        # Orders table indexes
        (
            "idx_orders_ticker",
            "CREATE INDEX IF NOT EXISTS idx_orders_ticker ON orders(ticker);"
        ),
        (
            "idx_orders_status",
            "CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(status);"
        ),
        (
            "idx_orders_submitted_at",
            "CREATE INDEX IF NOT EXISTS idx_orders_submitted_at ON orders(submitted_at DESC);"
        ),
        (
            "idx_orders_position_id",
            "CREATE INDEX IF NOT EXISTS idx_orders_position_id ON orders(position_id);"
        ),
        (
            "idx_orders_strategy",
            "CREATE INDEX IF NOT EXISTS idx_orders_strategy ON orders(strategy);"
        ),
        (
            "idx_orders_client_order_id",
            "CREATE INDEX IF NOT EXISTS idx_orders_client_order_id ON orders(client_order_id);"
        ),

        # Fills table indexes
        (
            "idx_fills_order_id",
            "CREATE INDEX IF NOT EXISTS idx_fills_order_id ON fills(order_id);"
        ),
        (
            "idx_fills_ticker",
            "CREATE INDEX IF NOT EXISTS idx_fills_ticker ON fills(ticker);"
        ),
        (
            "idx_fills_filled_at",
            "CREATE INDEX IF NOT EXISTS idx_fills_filled_at ON fills(filled_at DESC);"
        ),
        (
            "idx_fills_position_id",
            "CREATE INDEX IF NOT EXISTS idx_fills_position_id ON fills(position_id);"
        ),

        # Portfolio snapshots indexes
        (
            "idx_portfolio_snapshots_date",
            "CREATE INDEX IF NOT EXISTS idx_portfolio_snapshots_date ON portfolio_snapshots(snapshot_date DESC);"
        ),
        (
            "idx_portfolio_snapshots_time",
            "CREATE INDEX IF NOT EXISTS idx_portfolio_snapshots_time ON portfolio_snapshots(snapshot_time DESC);"
        ),

        # Performance metrics indexes
        (
            "idx_performance_metrics_date",
            "CREATE INDEX IF NOT EXISTS idx_performance_metrics_date ON performance_metrics(metric_date DESC);"
        ),
        (
            "idx_performance_metrics_strategy",
            "CREATE INDEX IF NOT EXISTS idx_performance_metrics_strategy ON performance_metrics(strategy);"
        ),
    ]

    for idx_name, sql in indexes:
        try:
            conn.execute(sql)
            print(f"✓ Created index '{idx_name}'")
        except sqlite3.OperationalError as e:
            print(f"⚠ Warning: Could not create index '{idx_name}': {e}")


def create_views(conn: sqlite3.Connection) -> None:
    """
    Create helpful views for common queries.
    """
    # View for recent order activity
    conn.execute(
        """
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
        """
    )

    # View for order fill statistics
    conn.execute(
        """
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
        """
    )

    # View for equity curve
    conn.execute(
        """
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
        """
    )

    # View for performance summary
    conn.execute(
        """
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
        """
    )

    print("✓ Created helpful query views")


def upgrade(db_path: str = TRADING_DB_PATH) -> None:
    """
    Run the migration to create trading tables.

    This migration is idempotent - safe to run multiple times.
    """
    print(f"\n=== Running Migration 002: Create Trading Tables ===")
    print(f"Database: {db_path}\n")

    _ensure_dir(db_path)
    conn = init_optimized_connection(db_path)

    try:
        create_orders_table(conn)
        create_fills_table(conn)
        create_portfolio_snapshots_table(conn)
        create_performance_metrics_table(conn)
        create_indexes(conn)
        create_views(conn)

        conn.commit()
        print("\n✅ Migration 002 completed successfully!")

        # Print sample queries
        print("\n" + "="*60)
        print("SAMPLE QUERIES")
        print("="*60)
        print("""
# 1. Get all pending orders
SELECT * FROM orders WHERE status = 'pending' ORDER BY submitted_at DESC;

# 2. Get fill rate today
SELECT
    COUNT(CASE WHEN status = 'filled' THEN 1 END) * 1.0 / COUNT(*) as fill_rate,
    COUNT(*) as total_orders
FROM orders
WHERE DATE(submitted_at, 'unixepoch') = DATE('now');

# 3. Get recent fills with slippage
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

# 4. Get portfolio equity curve
SELECT * FROM v_equity_curve;

# 5. Get current Sharpe ratio and drawdown
SELECT
    sharpe_ratio,
    max_drawdown_pct,
    current_drawdown_pct,
    days_in_drawdown
FROM performance_metrics
ORDER BY metric_date DESC
LIMIT 1;

# 6. Get win rate by strategy
SELECT
    o.strategy,
    COUNT(*) as total_orders,
    AVG(CASE WHEN o.side = 'sell' THEN 1 ELSE 0 END) as close_rate
FROM orders o
WHERE o.status = 'filled'
GROUP BY o.strategy;

# 7. Get average slippage by order type
SELECT
    order_type,
    AVG(slippage) as avg_slippage,
    COUNT(*) as count
FROM orders
WHERE slippage IS NOT NULL
GROUP BY order_type;

# 8. Get daily trading activity
SELECT
    DATE(submitted_at, 'unixepoch') as trade_date,
    COUNT(*) as orders_placed,
    COUNT(CASE WHEN status = 'filled' THEN 1 END) as orders_filled,
    SUM(quantity * filled_avg_price) as total_volume
FROM orders
GROUP BY trade_date
ORDER BY trade_date DESC
LIMIT 30;

# 9. Use pre-built views
SELECT * FROM v_recent_orders;
SELECT * FROM v_performance_summary;
        """)

    except Exception as e:
        conn.rollback()
        print(f"\n❌ Migration 002 failed: {e}")
        raise
    finally:
        conn.close()


def downgrade(db_path: str = TRADING_DB_PATH) -> None:
    """
    Rollback migration (drop tables).

    WARNING: This will delete all trading data!
    """
    print(f"\n=== Rolling Back Migration 002 ===")
    print(f"Database: {db_path}\n")

    conn = init_optimized_connection(db_path)

    try:
        conn.execute("DROP VIEW IF EXISTS v_performance_summary;")
        conn.execute("DROP VIEW IF EXISTS v_equity_curve;")
        conn.execute("DROP VIEW IF EXISTS v_order_fill_stats;")
        conn.execute("DROP VIEW IF EXISTS v_recent_orders;")
        conn.execute("DROP TABLE IF EXISTS performance_metrics;")
        conn.execute("DROP TABLE IF EXISTS portfolio_snapshots;")
        conn.execute("DROP TABLE IF EXISTS fills;")
        conn.execute("DROP TABLE IF EXISTS orders;")

        conn.commit()
        print("\n✅ Migration 002 rolled back successfully!")

    except Exception as e:
        conn.rollback()
        print(f"\n❌ Rollback failed: {e}")
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "downgrade":
        downgrade()
    else:
        upgrade()
