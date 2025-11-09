"""
Historical Backtest Database Schema

SQLite database for storing backtest results, trades, and validation metrics.
This will eventually migrate to PostgreSQL + TimescaleDB for production scale.

Schema based on MOA_DESIGN_V2.md Phase 0 requirements.

Author: Claude Code (MOA Phase 0)
Date: 2025-10-10
"""

import sqlite3
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Any
import pandas as pd


class BacktestDatabase:
    """
    Manages historical backtest data storage and retrieval.

    Database Tables:
    - backtests: Metadata about each backtest run
    - backtest_results: Performance metrics per backtest
    - backtest_trades: Individual trades from backtests
    - backtest_parameters: Parameter configurations tested
    - walkforward_windows: Walk-forward optimization windows
    - bootstrap_results: Bootstrap validation results
    """

    def __init__(self, db_path: str = "data/backtest_history.db"):
        """
        Initialize database connection.

        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = db_path

        # Ensure data directory exists
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)

        # Initialize schema
        self._init_schema()

    def _get_connection(self) -> sqlite3.Connection:
        """Get database connection with row factory and optimized pragmas."""
        from ..storage import init_optimized_connection

        conn = init_optimized_connection(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self):
        """Create database tables if they don't exist."""
        conn = self._get_connection()
        cursor = conn.cursor()

        # Table 1: Backtests metadata
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS backtests (
                backtest_id INTEGER PRIMARY KEY AUTOINCREMENT,
                strategy_name TEXT NOT NULL,
                symbol TEXT,
                start_date DATE NOT NULL,
                end_date DATE NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                backtest_type TEXT CHECK(backtest_type IN ('in_sample', 'out_of_sample', 'walk_forward')),
                notes TEXT,
                duration_seconds REAL,
                total_trades INTEGER DEFAULT 0,
                status TEXT DEFAULT 'pending' CHECK(status IN ('pending', 'running', 'completed', 'failed'))
            )
        """)

        # Table 2: Backtest results (performance metrics)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS backtest_results (
                result_id INTEGER PRIMARY KEY AUTOINCREMENT,
                backtest_id INTEGER NOT NULL,

                -- Core metrics
                total_return REAL,
                total_trades INTEGER,
                win_rate REAL,

                -- Risk-adjusted metrics
                sharpe_ratio REAL,
                sortino_ratio REAL,
                calmar_ratio REAL,
                omega_ratio REAL,

                -- Advanced metrics
                profit_factor REAL,
                expectancy REAL,
                f1_score REAL,
                information_coefficient REAL,
                roc_auc REAL,

                -- Risk metrics
                max_drawdown REAL,
                avg_drawdown REAL,
                volatility REAL,

                -- Trade statistics
                avg_win REAL,
                avg_loss REAL,
                largest_win REAL,
                largest_loss REAL,
                avg_hold_time_hours REAL,

                -- Validation metrics
                walk_forward_efficiency REAL,
                parameter_robustness_score REAL,
                bootstrap_prob_positive REAL,

                -- Metadata
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

                FOREIGN KEY (backtest_id) REFERENCES backtests(backtest_id)
            )
        """)

        # Table 3: Individual trades from backtests
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS backtest_trades (
                trade_id INTEGER PRIMARY KEY AUTOINCREMENT,
                backtest_id INTEGER NOT NULL,

                -- Trade details
                ticker TEXT NOT NULL,
                entry_time TIMESTAMP NOT NULL,
                exit_time TIMESTAMP NOT NULL,

                -- Entry
                entry_price REAL NOT NULL,
                entry_signal_score REAL,
                entry_reason TEXT,

                -- Exit
                exit_price REAL NOT NULL,
                exit_reason TEXT CHECK(exit_reason IN ('take_profit', 'stop_loss', 'timeout', 'manual')),

                -- Performance
                pnl REAL NOT NULL,
                pnl_pct REAL NOT NULL,
                hold_time_hours REAL,

                -- Position sizing
                shares INTEGER,
                position_value REAL,

                -- Outcome classification
                outcome INTEGER CHECK(outcome IN (-1, 0, 1)),  -- loss, neutral, win

                FOREIGN KEY (backtest_id) REFERENCES backtests(backtest_id)
            )
        """)

        # Table 4: Parameter configurations
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS backtest_parameters (
                param_id INTEGER PRIMARY KEY AUTOINCREMENT,
                backtest_id INTEGER NOT NULL,

                -- Parameter values (JSON serialized)
                parameters TEXT NOT NULL,  -- JSON: {"min_score": 0.25, "take_profit_pct": 0.20, ...}

                -- Parameter hash for deduplication
                param_hash TEXT NOT NULL,

                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

                FOREIGN KEY (backtest_id) REFERENCES backtests(backtest_id)
            )
        """)

        # Table 5: Walk-forward optimization windows
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS walkforward_windows (
                window_id INTEGER PRIMARY KEY AUTOINCREMENT,

                -- Window dates
                train_start DATE NOT NULL,
                train_end DATE NOT NULL,
                test_start DATE NOT NULL,
                test_end DATE NOT NULL,

                -- Linked backtests
                train_backtest_id INTEGER,
                test_backtest_id INTEGER,

                -- Optimal parameters found during training
                optimal_params TEXT,  -- JSON

                -- Performance
                in_sample_sharpe REAL,
                out_of_sample_sharpe REAL,
                efficiency REAL,  -- OOS Sharpe / IS Sharpe

                -- Validation
                is_valid BOOLEAN DEFAULT 1,
                rejection_reason TEXT,

                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

                FOREIGN KEY (train_backtest_id) REFERENCES backtests(backtest_id),
                FOREIGN KEY (test_backtest_id) REFERENCES backtests(backtest_id)
            )
        """)

        # Table 6: Bootstrap validation results
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS bootstrap_results (
                bootstrap_id INTEGER PRIMARY KEY AUTOINCREMENT,
                backtest_id INTEGER NOT NULL,

                -- Bootstrap parameters
                n_iterations INTEGER DEFAULT 10000,
                confidence_level REAL DEFAULT 0.95,

                -- Results
                prob_positive REAL,
                mean_return REAL,
                median_return REAL,
                ci_lower REAL,  -- Lower confidence interval
                ci_upper REAL,  -- Upper confidence interval

                -- Sharpe distribution
                mean_sharpe REAL,
                median_sharpe REAL,
                sharpe_ci_lower REAL,
                sharpe_ci_upper REAL,

                is_valid BOOLEAN DEFAULT 1,
                rejection_reason TEXT,

                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

                FOREIGN KEY (backtest_id) REFERENCES backtests(backtest_id)
            )
        """)

        # Create indexes for common queries
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_backtests_dates
            ON backtests(start_date, end_date)
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_backtests_strategy
            ON backtests(strategy_name, backtest_type)
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_trades_ticker
            ON backtest_trades(ticker, entry_time)
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_trades_backtest
            ON backtest_trades(backtest_id)
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_params_hash
            ON backtest_parameters(param_hash)
        """)

        conn.commit()
        conn.close()

    def create_backtest(
        self,
        strategy_name: str,
        start_date: str,
        end_date: str,
        symbol: Optional[str] = None,
        backtest_type: str = "in_sample",
        notes: Optional[str] = None
    ) -> int:
        """
        Create a new backtest record.

        Args:
            strategy_name: Name of the strategy being tested
            start_date: Start date (YYYY-MM-DD)
            end_date: End date (YYYY-MM-DD)
            symbol: Optional ticker symbol (None for multi-symbol)
            backtest_type: 'in_sample', 'out_of_sample', or 'walk_forward'
            notes: Optional notes

        Returns:
            backtest_id: Primary key of created record
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO backtests (strategy_name, symbol, start_date, end_date, backtest_type, notes, status)
            VALUES (?, ?, ?, ?, ?, ?, 'pending')
        """, (strategy_name, symbol, start_date, end_date, backtest_type, notes))

        backtest_id = cursor.lastrowid
        conn.commit()
        conn.close()

        return backtest_id

    def save_backtest_results(
        self,
        backtest_id: int,
        metrics: Dict[str, float]
    ):
        """
        Save performance metrics for a backtest.

        Args:
            backtest_id: Backtest ID
            metrics: Dict of performance metrics
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO backtest_results (
                backtest_id, total_return, total_trades, win_rate,
                sharpe_ratio, sortino_ratio, calmar_ratio, omega_ratio,
                profit_factor, expectancy, f1_score,
                information_coefficient, roc_auc,
                max_drawdown, avg_win, avg_loss
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            backtest_id,
            metrics.get('total_return', 0.0),
            metrics.get('total_trades', 0),
            metrics.get('win_rate', 0.0),
            metrics.get('sharpe_ratio', 0.0),
            metrics.get('sortino_ratio', 0.0),
            metrics.get('calmar_ratio', 0.0),
            metrics.get('omega_ratio', 0.0),
            metrics.get('profit_factor', 0.0),
            metrics.get('expectancy', 0.0),
            metrics.get('f1_score', 0.0),
            metrics.get('information_coefficient', 0.0),
            metrics.get('roc_auc', 0.0),
            metrics.get('max_drawdown', 0.0),
            metrics.get('avg_win', 0.0),
            metrics.get('avg_loss', 0.0)
        ))

        # Update backtest status
        cursor.execute("""
            UPDATE backtests SET status = 'completed', total_trades = ?
            WHERE backtest_id = ?
        """, (metrics.get('total_trades', 0), backtest_id))

        conn.commit()
        conn.close()

    def save_trades(
        self,
        backtest_id: int,
        trades: List[Dict[str, Any]]
    ):
        """
        Save individual trades from a backtest.

        Args:
            backtest_id: Backtest ID
            trades: List of trade dicts
        """
        if not trades:
            return

        conn = self._get_connection()
        cursor = conn.cursor()

        for trade in trades:
            # Convert timestamps to strings if they are pandas Timestamp objects
            entry_time = trade['entry_time']
            exit_time = trade['exit_time']

            if hasattr(entry_time, 'isoformat'):
                entry_time = entry_time.isoformat()
            if hasattr(exit_time, 'isoformat'):
                exit_time = exit_time.isoformat()

            cursor.execute("""
                INSERT INTO backtest_trades (
                    backtest_id, ticker, entry_time, exit_time,
                    entry_price, entry_signal_score, entry_reason,
                    exit_price, exit_reason,
                    pnl, pnl_pct, hold_time_hours,
                    shares, position_value, outcome
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                backtest_id,
                trade['ticker'],
                entry_time,
                exit_time,
                trade['entry_price'],
                trade.get('entry_signal_score', 0.0),
                trade.get('entry_reason', ''),
                trade['exit_price'],
                trade.get('exit_reason', 'timeout'),
                trade['pnl'],
                trade['pnl_pct'],
                trade.get('hold_time_hours', 0.0),
                trade.get('shares', 0),
                trade.get('position_value', 0.0),
                trade.get('outcome', 0)
            ))

        conn.commit()
        conn.close()

    def save_parameters(
        self,
        backtest_id: int,
        parameters: Dict[str, Any]
    ):
        """
        Save parameter configuration for a backtest.

        Args:
            backtest_id: Backtest ID
            parameters: Dict of parameters
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        # Serialize parameters to JSON
        params_json = json.dumps(parameters, sort_keys=True)

        # Create hash for deduplication
        param_hash = str(hash(params_json))

        cursor.execute("""
            INSERT INTO backtest_parameters (backtest_id, parameters, param_hash)
            VALUES (?, ?, ?)
        """, (backtest_id, params_json, param_hash))

        conn.commit()
        conn.close()

    def get_backtest_summary(
        self,
        limit: int = 20
    ) -> pd.DataFrame:
        """
        Get summary of recent backtests.

        Args:
            limit: Number of recent backtests to return

        Returns:
            DataFrame with backtest summaries
        """
        conn = self._get_connection()

        query = """
            SELECT
                b.backtest_id,
                b.strategy_name,
                b.symbol,
                b.start_date,
                b.end_date,
                b.backtest_type,
                b.status,
                r.total_trades,
                r.sharpe_ratio,
                r.sortino_ratio,
                r.f1_score,
                r.profit_factor,
                r.max_drawdown,
                b.created_at
            FROM backtests b
            LEFT JOIN backtest_results r ON b.backtest_id = r.backtest_id
            ORDER BY b.created_at DESC
            LIMIT ?
        """

        df = pd.read_sql_query(query, conn, params=(limit,))
        conn.close()

        return df

    def get_best_parameters(
        self,
        strategy_name: str,
        metric: str = 'sharpe_ratio',
        min_trades: int = 30
    ) -> Optional[Dict[str, Any]]:
        """
        Get best performing parameter set for a strategy.

        Args:
            strategy_name: Strategy name
            metric: Metric to optimize ('sharpe_ratio', 'sortino_ratio', etc.)
            min_trades: Minimum trades required

        Returns:
            Dict of best parameters, or None if not found
        """
        conn = self._get_connection()

        query = f"""
            SELECT
                p.parameters,
                r.{metric},
                r.total_trades,
                b.backtest_id
            FROM backtest_parameters p
            JOIN backtests b ON p.backtest_id = b.backtest_id
            JOIN backtest_results r ON b.backtest_id = r.backtest_id
            WHERE b.strategy_name = ?
                AND r.total_trades >= ?
                AND b.status = 'completed'
            ORDER BY r.{metric} DESC
            LIMIT 1
        """

        cursor = conn.cursor()
        cursor.execute(query, (strategy_name, min_trades))
        row = cursor.fetchone()
        conn.close()

        if row:
            return {
                'parameters': json.loads(row['parameters']),
                'metric_value': row[metric],
                'total_trades': row['total_trades'],
                'backtest_id': row['backtest_id']
            }

        return None

    def close(self):
        """Close database connection (cleanup)."""
        pass  # sqlite3 connections are per-call, no persistent connection


# Convenience function for global access
_db_instance: Optional[BacktestDatabase] = None


def get_database(db_path: str = "data/backtest_history.db") -> BacktestDatabase:
    """
    Get singleton database instance.

    Args:
        db_path: Path to database file

    Returns:
        BacktestDatabase instance
    """
    global _db_instance

    if _db_instance is None:
        _db_instance = BacktestDatabase(db_path)

    return _db_instance
