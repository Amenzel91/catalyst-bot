"""
Migration 001: Create Positions Database Tables

Creates tables for tracking open positions and historical closed positions.
Database: data/positions.db

Tables:
- positions: Currently open trading positions
- closed_positions: Historical positions with realized P&L
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from catalyst_bot.storage import _ensure_dir, init_optimized_connection


POSITIONS_DB_PATH = "data/positions.db"


def create_positions_table(conn: sqlite3.Connection) -> None:
    """
    Create the positions table for tracking open positions.

    Schema Design:
    - position_id: Unique identifier (UUID recommended)
    - ticker: Stock symbol (e.g., 'AAPL', 'TSLA')
    - side: Position direction ('long' or 'short')
    - quantity: Number of shares held
    - entry_price: Average entry price per share
    - current_price: Last known market price
    - unrealized_pnl: Current profit/loss (not realized until closed)
    - stop_loss_price: Automatic exit price if market moves against position
    - take_profit_price: Automatic exit price at target profit level
    - opened_at: Unix timestamp when position was opened
    - updated_at: Unix timestamp of last update (price/quantity change)
    - strategy: Which trading strategy/agent opened this position
    - signal_score: Original catalyst alert score (0.0-1.0)
    - metadata: JSON field for additional context (catalyst type, entry reason, etc.)
    """
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS positions (
            position_id TEXT PRIMARY KEY,
            ticker TEXT NOT NULL,
            side TEXT NOT NULL CHECK(side IN ('long', 'short')),
            quantity INTEGER NOT NULL CHECK(quantity > 0),
            entry_price REAL NOT NULL CHECK(entry_price > 0),
            current_price REAL NOT NULL CHECK(current_price > 0),
            unrealized_pnl REAL NOT NULL DEFAULT 0.0,
            unrealized_pnl_pct REAL NOT NULL DEFAULT 0.0,
            stop_loss_price REAL,
            take_profit_price REAL,
            opened_at INTEGER NOT NULL,
            updated_at INTEGER NOT NULL,
            strategy TEXT,
            signal_score REAL CHECK(signal_score >= 0 AND signal_score <= 1),
            atr_at_entry REAL,
            rvol_at_entry REAL,
            market_regime TEXT,
            metadata TEXT,
            CONSTRAINT valid_stop_loss CHECK(
                (side = 'long' AND (stop_loss_price IS NULL OR stop_loss_price < entry_price))
                OR (side = 'short' AND (stop_loss_price IS NULL OR stop_loss_price > entry_price))
            ),
            CONSTRAINT valid_take_profit CHECK(
                (side = 'long' AND (take_profit_price IS NULL OR take_profit_price > entry_price))
                OR (side = 'short' AND (take_profit_price IS NULL OR take_profit_price < entry_price))
            )
        );
        """
    )

    print("✓ Created 'positions' table")


def create_closed_positions_table(conn: sqlite3.Connection) -> None:
    """
    Create the closed_positions table for historical trades.

    This table extends the positions schema with exit information:
    - closed_at: When the position was exited
    - exit_price: Price at which shares were sold
    - realized_pnl: Actual profit/loss after closing
    - exit_reason: Why the position was closed
    - holding_period_hours: Duration the position was held
    - commission: Total commission paid (entry + exit)
    - slippage: Price slippage from expected to actual fills
    """
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS closed_positions (
            position_id TEXT PRIMARY KEY,
            ticker TEXT NOT NULL,
            side TEXT NOT NULL CHECK(side IN ('long', 'short')),
            quantity INTEGER NOT NULL CHECK(quantity > 0),
            entry_price REAL NOT NULL CHECK(entry_price > 0),
            exit_price REAL NOT NULL CHECK(exit_price > 0),
            realized_pnl REAL NOT NULL,
            realized_pnl_pct REAL NOT NULL,
            stop_loss_price REAL,
            take_profit_price REAL,
            opened_at INTEGER NOT NULL,
            closed_at INTEGER NOT NULL,
            updated_at INTEGER NOT NULL,
            holding_period_hours REAL NOT NULL,
            exit_reason TEXT NOT NULL,
            strategy TEXT,
            signal_score REAL CHECK(signal_score >= 0 AND signal_score <= 1),
            atr_at_entry REAL,
            rvol_at_entry REAL,
            market_regime TEXT,
            commission REAL DEFAULT 0.0,
            slippage REAL DEFAULT 0.0,
            max_favorable_excursion REAL,
            max_adverse_excursion REAL,
            metadata TEXT,
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
        """
    )

    print("✓ Created 'closed_positions' table")


def create_indexes(conn: sqlite3.Connection) -> None:
    """
    Create indexes for common query patterns.

    Indexes improve query performance for:
    - Looking up positions by ticker
    - Finding positions by strategy
    - Sorting by entry/exit dates
    - Analyzing performance by exit reason
    - Time-based queries
    """
    indexes = [
        # Positions table indexes
        (
            "idx_positions_ticker",
            "CREATE INDEX IF NOT EXISTS idx_positions_ticker ON positions(ticker);"
        ),
        (
            "idx_positions_strategy",
            "CREATE INDEX IF NOT EXISTS idx_positions_strategy ON positions(strategy);"
        ),
        (
            "idx_positions_opened_at",
            "CREATE INDEX IF NOT EXISTS idx_positions_opened_at ON positions(opened_at DESC);"
        ),
        (
            "idx_positions_unrealized_pnl",
            "CREATE INDEX IF NOT EXISTS idx_positions_unrealized_pnl ON positions(unrealized_pnl DESC);"
        ),
        (
            "idx_positions_ticker_side",
            "CREATE INDEX IF NOT EXISTS idx_positions_ticker_side ON positions(ticker, side);"
        ),

        # Closed positions table indexes
        (
            "idx_closed_positions_ticker",
            "CREATE INDEX IF NOT EXISTS idx_closed_positions_ticker ON closed_positions(ticker);"
        ),
        (
            "idx_closed_positions_closed_at",
            "CREATE INDEX IF NOT EXISTS idx_closed_positions_closed_at ON closed_positions(closed_at DESC);"
        ),
        (
            "idx_closed_positions_exit_reason",
            "CREATE INDEX IF NOT EXISTS idx_closed_positions_exit_reason ON closed_positions(exit_reason);"
        ),
        (
            "idx_closed_positions_strategy",
            "CREATE INDEX IF NOT EXISTS idx_closed_positions_strategy ON closed_positions(strategy);"
        ),
        (
            "idx_closed_positions_realized_pnl",
            "CREATE INDEX IF NOT EXISTS idx_closed_positions_realized_pnl ON closed_positions(realized_pnl DESC);"
        ),
        (
            "idx_closed_positions_holding_period",
            "CREATE INDEX IF NOT EXISTS idx_closed_positions_holding_period ON closed_positions(holding_period_hours);"
        ),
    ]

    for idx_name, sql in indexes:
        try:
            conn.execute(sql)
            print(f"✓ Created index '{idx_name}'")
        except sqlite3.OperationalError as e:
            print(f"⚠ Warning: Could not create index '{idx_name}': {e}")


def create_sample_queries_view(conn: sqlite3.Connection) -> None:
    """
    Create helpful views for common queries.
    """
    # View for position summary with current P&L
    conn.execute(
        """
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
        """
    )

    # View for recent closed positions with performance metrics
    conn.execute(
        """
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
        """
    )

    print("✓ Created helpful query views")


def upgrade(db_path: str = POSITIONS_DB_PATH) -> None:
    """
    Run the migration to create positions tables.

    This migration is idempotent - safe to run multiple times.
    """
    print(f"\n=== Running Migration 001: Create Positions Tables ===")
    print(f"Database: {db_path}\n")

    _ensure_dir(db_path)
    conn = init_optimized_connection(db_path)

    try:
        create_positions_table(conn)
        create_closed_positions_table(conn)
        create_indexes(conn)
        create_sample_queries_view(conn)

        conn.commit()
        print("\n✅ Migration 001 completed successfully!")

        # Print sample queries
        print("\n" + "="*60)
        print("SAMPLE QUERIES")
        print("="*60)
        print("""
# 1. Get all open positions
SELECT * FROM positions ORDER BY opened_at DESC;

# 2. Get total unrealized P&L
SELECT SUM(unrealized_pnl) as total_unrealized_pnl FROM positions;

# 3. Get positions for a specific ticker
SELECT * FROM positions WHERE ticker = 'AAPL';

# 4. Get win rate for closed positions
SELECT
    COUNT(CASE WHEN realized_pnl > 0 THEN 1 END) * 1.0 / COUNT(*) as win_rate,
    COUNT(*) as total_trades,
    SUM(realized_pnl) as total_realized_pnl
FROM closed_positions;

# 5. Get average holding period by exit reason
SELECT
    exit_reason,
    COUNT(*) as count,
    AVG(holding_period_hours) as avg_hours,
    AVG(realized_pnl) as avg_pnl
FROM closed_positions
GROUP BY exit_reason
ORDER BY count DESC;

# 6. Get best and worst trades
SELECT ticker, realized_pnl, realized_pnl_pct, exit_reason
FROM closed_positions
ORDER BY realized_pnl DESC
LIMIT 10;

# 7. Get positions by strategy performance
SELECT
    strategy,
    COUNT(*) as trades,
    AVG(realized_pnl) as avg_pnl,
    SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END) * 1.0 / COUNT(*) as win_rate
FROM closed_positions
GROUP BY strategy
ORDER BY avg_pnl DESC;

# 8. Get positions that hit stop loss
SELECT ticker, entry_price, exit_price, realized_pnl
FROM closed_positions
WHERE exit_reason = 'stop_loss'
ORDER BY closed_at DESC;

# 9. Use the pre-built views
SELECT * FROM v_position_summary;
SELECT * FROM v_recent_closed_trades;
        """)

    except Exception as e:
        conn.rollback()
        print(f"\n❌ Migration 001 failed: {e}")
        raise
    finally:
        conn.close()


def downgrade(db_path: str = POSITIONS_DB_PATH) -> None:
    """
    Rollback migration (drop tables).

    WARNING: This will delete all position data!
    """
    print(f"\n=== Rolling Back Migration 001 ===")
    print(f"Database: {db_path}\n")

    conn = init_optimized_connection(db_path)

    try:
        conn.execute("DROP VIEW IF EXISTS v_recent_closed_trades;")
        conn.execute("DROP VIEW IF EXISTS v_position_summary;")
        conn.execute("DROP TABLE IF EXISTS closed_positions;")
        conn.execute("DROP TABLE IF EXISTS positions;")

        conn.commit()
        print("\n✅ Migration 001 rolled back successfully!")

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
