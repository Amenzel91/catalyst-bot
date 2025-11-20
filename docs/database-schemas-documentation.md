# Paper Trading Bot Database Schemas Documentation

**Project:** Catalyst Bot Paper Trading Enhancement
**Created:** 2025-11-20
**Version:** 1.0.0

---

## Table of Contents

1. [Overview](#overview)
2. [Database Architecture](#database-architecture)
3. [Positions Database](#positions-database)
4. [Trading Database](#trading-database)
5. [ML Training Database](#ml-training-database)
6. [Migration System](#migration-system)
7. [Usage Examples](#usage-examples)
8. [Performance Optimization](#performance-optimization)
9. [Backup and Recovery](#backup-and-recovery)
10. [Integration Guide](#integration-guide)

---

## Overview

The paper trading bot uses **three separate SQLite databases** to organize data by functional domain:

| Database | Purpose | Tables | Size (Approx) |
|----------|---------|--------|---------------|
| **positions.db** | Position tracking | 2 | Small (MB) |
| **trading.db** | Order execution & performance | 4 | Medium (10s of MB) |
| **ml_training.db** | RL training & agents | 5 | Large (100s of MB) |

All databases use **WAL mode** for concurrent access and are optimized for high-performance trading operations.

### Design Principles

1. **Separation of Concerns** - Each database has a specific domain
2. **Idempotent Migrations** - Safe to run multiple times
3. **Performance First** - Indexes on all common queries
4. **Rich Metadata** - JSON fields for extensibility
5. **Time-Series Ready** - Unix timestamps for all temporal data
6. **View-Based Queries** - Pre-built views for common patterns

---

## Database Architecture

### Connection Pattern

All databases use the same optimized connection pattern from `storage.py`:

```python
from catalyst_bot.storage import init_optimized_connection

conn = init_optimized_connection("data/positions.db")
# PRAGMA journal_mode=WAL
# PRAGMA synchronous=NORMAL
# PRAGMA cache_size=10000  # ~40MB
# PRAGMA mmap_size=30GB
# PRAGMA temp_store=MEMORY
```

### Schema Versioning

Migrations are tracked in `data/migrations.db`:

```sql
CREATE TABLE migration_history (
    migration_id TEXT PRIMARY KEY,
    migration_name TEXT NOT NULL,
    database_path TEXT NOT NULL,
    applied_at INTEGER NOT NULL,
    applied_date TEXT NOT NULL,
    duration_seconds REAL,
    status TEXT CHECK(status IN ('applied', 'rolled_back', 'failed'))
);
```

---

## Positions Database

**File:** `data/positions.db`
**Migration:** `001_create_positions_tables.py`
**Purpose:** Track open and closed trading positions

### Tables

#### positions

Tracks currently open positions with real-time P&L.

**Key Fields:**
- `position_id` (TEXT, PK) - Unique position identifier
- `ticker` (TEXT) - Stock symbol (e.g., 'AAPL')
- `side` (TEXT) - 'long' or 'short'
- `quantity` (INTEGER) - Number of shares
- `entry_price` (REAL) - Average entry price
- `current_price` (REAL) - Last market price
- `unrealized_pnl` (REAL) - Current P&L (not realized)
- `unrealized_pnl_pct` (REAL) - Current P&L percentage
- `stop_loss_price` (REAL) - Stop loss level
- `take_profit_price` (REAL) - Take profit level
- `opened_at` (INTEGER) - Unix timestamp
- `strategy` (TEXT) - Strategy that opened position
- `signal_score` (REAL) - Original alert score (0-1)
- `metadata` (TEXT) - JSON for additional context

**Constraints:**
- `side` must be 'long' or 'short'
- `quantity` > 0
- `entry_price`, `current_price` > 0
- Stop loss must be < entry_price (for longs)
- Take profit must be > entry_price (for longs)

**Indexes:**
- `idx_positions_ticker` - Query by ticker
- `idx_positions_strategy` - Query by strategy
- `idx_positions_opened_at` - Time-based sorting
- `idx_positions_unrealized_pnl` - Sort by P&L
- `idx_positions_ticker_side` - Composite for position lookup

#### closed_positions

Historical record of all closed positions.

**Additional Fields (vs positions):**
- `exit_price` (REAL) - Exit price
- `realized_pnl` (REAL) - Actual profit/loss
- `realized_pnl_pct` (REAL) - Actual P&L percentage
- `closed_at` (INTEGER) - When position was closed
- `holding_period_hours` (REAL) - Duration held
- `exit_reason` (TEXT) - Why position was closed
- `commission` (REAL) - Total commission paid
- `slippage` (REAL) - Price slippage
- `max_favorable_excursion` (REAL) - Best price achieved
- `max_adverse_excursion` (REAL) - Worst price experienced

**Exit Reasons:**
- `stop_loss` - Hit stop loss level
- `take_profit` - Hit take profit target
- `trailing_stop` - Trailing stop triggered
- `time_exit` - Time-based exit (e.g., EOD)
- `manual` - Manual close by operator
- `risk_limit` - Risk management system closed
- `circuit_breaker` - Emergency stop
- `market_close` - Market closing forced exit

**Indexes:**
- Similar to positions table
- Plus `idx_closed_positions_exit_reason`
- Plus `idx_closed_positions_holding_period`

### Views

#### v_position_summary

Current positions with calculated fields:

```sql
SELECT * FROM v_position_summary;
-- Returns: ticker, side, quantity, entry_price, current_price,
--          unrealized_pnl, pnl_dollars, strategy,
--          opened_datetime, hours_held
```

#### v_recent_closed_trades

Last 100 closed trades with outcome classification:

```sql
SELECT * FROM v_recent_closed_trades;
-- Returns: ticker, side, entry_price, exit_price, realized_pnl,
--          exit_reason, holding_period_hours, outcome (WIN/LOSS/BREAKEVEN)
```

### Common Queries

```sql
-- Total unrealized P&L
SELECT SUM(unrealized_pnl) as total_pnl FROM positions;

-- Win rate
SELECT
    COUNT(CASE WHEN realized_pnl > 0 THEN 1 END) * 1.0 / COUNT(*) as win_rate
FROM closed_positions;

-- Average holding period by exit reason
SELECT exit_reason, AVG(holding_period_hours) as avg_hours
FROM closed_positions
GROUP BY exit_reason;

-- Best performers
SELECT ticker, realized_pnl, realized_pnl_pct
FROM closed_positions
ORDER BY realized_pnl DESC
LIMIT 10;
```

---

## Trading Database

**File:** `data/trading.db`
**Migration:** `002_create_trading_tables.py`
**Purpose:** Order execution, fills, portfolio tracking, and performance metrics

### Tables

#### orders

All orders submitted to broker.

**Key Fields:**
- `order_id` (TEXT, PK) - Broker's order ID
- `client_order_id` (TEXT, UNIQUE) - Our internal order ID
- `ticker` (TEXT) - Stock symbol
- `order_type` (TEXT) - market, limit, stop, stop_limit, trailing_stop
- `side` (TEXT) - buy or sell
- `quantity` (INTEGER) - Shares to trade
- `limit_price` (REAL) - For limit orders
- `stop_price` (REAL) - For stop orders
- `time_in_force` (TEXT) - day, gtc, ioc, fok, opg, cls
- `status` (TEXT) - Order status
- `submitted_at` (INTEGER) - Submission timestamp
- `filled_at` (INTEGER) - Fill timestamp
- `filled_quantity` (INTEGER) - Shares filled
- `filled_avg_price` (REAL) - Average fill price
- `commission` (REAL) - Commission paid
- `slippage` (REAL) - Price slippage
- `position_id` (TEXT) - Related position

**Order Status Values:**
- `pending` - Waiting to submit
- `new` - Submitted to broker
- `accepted` - Accepted by broker
- `partially_filled` - Partial fill
- `filled` - Completely filled
- `cancelled` - Cancelled
- `rejected` - Rejected by broker
- `expired` - Order expired

**Indexes:**
- By ticker, status, submission time
- By position_id, strategy
- By client_order_id for lookup

#### fills

Individual fill events (may be multiple per order).

**Key Fields:**
- `fill_id` (TEXT, PK) - Unique fill identifier
- `order_id` (TEXT, FK) - Parent order
- `ticker` (TEXT) - Stock symbol
- `side` (TEXT) - buy or sell
- `quantity` (INTEGER) - Shares filled
- `price` (REAL) - Fill price
- `filled_at` (INTEGER) - Fill timestamp
- `liquidity` (TEXT) - maker, taker, unknown
- `commission` (REAL) - Commission for this fill

**Indexes:**
- By order_id for order fill history
- By ticker, filled_at for fill analysis

#### portfolio_snapshots

Daily snapshots of portfolio value.

**Key Fields:**
- `snapshot_id` (INTEGER, PK AUTO)
- `snapshot_date` (TEXT, UNIQUE) - YYYY-MM-DD
- `snapshot_time` (INTEGER, UNIQUE) - Unix timestamp
- `total_equity` (REAL) - Total portfolio value
- `cash_balance` (REAL) - Available cash
- `long_market_value` (REAL) - Long position value
- `short_market_value` (REAL) - Short position value
- `positions_count` (INTEGER) - Number of positions
- `daily_pnl` (REAL) - P&L for day
- `daily_return_pct` (REAL) - Daily return %
- `cumulative_pnl` (REAL) - Total P&L since start
- `cumulative_return_pct` (REAL) - Total return %
- `buying_power` (REAL) - Available buying power
- `leverage` (REAL) - Current leverage ratio
- `unrealized_pnl` (REAL) - Open position P&L
- `realized_pnl_today` (REAL) - Realized P&L today
- `trades_today` (INTEGER) - Trades executed today
- `wins_today` (INTEGER) - Winning trades today
- `losses_today` (INTEGER) - Losing trades today

**Indexes:**
- By snapshot_date, snapshot_time (DESC)

#### performance_metrics

Daily performance statistics and risk metrics.

**Key Fields:**

*Risk-Adjusted Returns:*
- `sharpe_ratio` (REAL) - Risk-adjusted return
- `sortino_ratio` (REAL) - Downside risk-adjusted
- `calmar_ratio` (REAL) - Return / max drawdown
- `omega_ratio` (REAL) - Probability-weighted ratio

*Drawdown Metrics:*
- `max_drawdown` (REAL) - Largest decline ($)
- `max_drawdown_pct` (REAL) - Largest decline (%)
- `current_drawdown` (REAL) - Current decline ($)
- `current_drawdown_pct` (REAL) - Current decline (%)
- `days_in_drawdown` (INTEGER) - Days underwater

*Return Metrics (Rolling):*
- `return_1d`, `return_7d`, `return_30d` (REAL)
- `return_ytd`, `return_inception` (REAL)

*Volatility:*
- `volatility_daily` (REAL) - Daily volatility
- `volatility_annualized` (REAL) - Annualized volatility
- `downside_deviation` (REAL) - Downside vol

*Trade Statistics (30-day rolling):*
- `total_trades_30d` (INTEGER) - Total trades
- `winning_trades_30d` (INTEGER) - Winning trades
- `win_rate_30d` (REAL) - Win rate
- `avg_win_30d` (REAL) - Average win
- `avg_loss_30d` (REAL) - Average loss
- `profit_factor_30d` (REAL) - Gross profit / gross loss
- `expectancy_30d` (REAL) - Expected value per trade

*Benchmark Comparison:*
- `benchmark_return` (REAL) - SPY/benchmark return
- `alpha` (REAL) - Excess return vs benchmark
- `beta` (REAL) - Correlation to benchmark
- `correlation_to_benchmark` (REAL) - Correlation coeff

**Indexes:**
- By metric_date (DESC)
- By strategy for multi-strategy comparison

### Views

#### v_recent_orders

Last 100 orders with formatted timestamps:

```sql
SELECT * FROM v_recent_orders;
```

#### v_order_fill_stats

Fill statistics per order:

```sql
SELECT * FROM v_order_fill_stats;
-- Returns: num_fills, avg_fill_price, best/worst fill price
```

#### v_equity_curve

Portfolio value over time:

```sql
SELECT * FROM v_equity_curve;
-- Returns: snapshot_date, total_equity, cumulative_return_pct
```

#### v_performance_summary

Last 30 days of performance metrics:

```sql
SELECT * FROM v_performance_summary;
-- Returns: sharpe, drawdown, win_rate, profit_factor, etc.
```

### Common Queries

```sql
-- Current Sharpe ratio and drawdown
SELECT sharpe_ratio, max_drawdown_pct, current_drawdown_pct
FROM performance_metrics
ORDER BY metric_date DESC LIMIT 1;

-- Daily fill rate
SELECT
    DATE(submitted_at, 'unixepoch') as date,
    COUNT(*) as orders,
    COUNT(CASE WHEN status = 'filled' THEN 1 END) as filled,
    COUNT(CASE WHEN status = 'filled' THEN 1 END) * 1.0 / COUNT(*) as fill_rate
FROM orders
GROUP BY date
ORDER BY date DESC;

-- Average slippage by order type
SELECT order_type, AVG(slippage) as avg_slippage
FROM orders
WHERE slippage IS NOT NULL
GROUP BY order_type;
```

---

## ML Training Database

**File:** `data/ml_training.db`
**Migration:** `003_create_ml_training_tables.py`
**Purpose:** RL training runs, agent performance, hyperparameters, and ensemble management

### Tables

#### training_runs

Metadata for each RL training session.

**Key Fields:**
- `run_id` (TEXT, PK) - Unique run identifier
- `algorithm` (TEXT) - PPO, SAC, A2C, TD3, DQN, DDPG, Ensemble
- `model_name` (TEXT) - Descriptive model name
- `start_time` (INTEGER) - Training start
- `end_time` (INTEGER) - Training end
- `duration_seconds` (REAL) - Total training time
- `total_timesteps` (INTEGER) - Environment steps
- `train_start_date` (TEXT) - Training data start
- `train_end_date` (TEXT) - Training data end
- `val_start_date` (TEXT) - Validation data start
- `val_end_date` (TEXT) - Validation data end
- `status` (TEXT) - running, completed, failed, stopped, aborted
- `final_reward` (REAL) - Final episode reward
- `best_reward` (REAL) - Best reward achieved
- `convergence_achieved` (INTEGER) - 1 if converged
- `model_path` (TEXT) - Saved model location
- `tensorboard_log_dir` (TEXT) - TensorBoard logs
- `random_seed` (INTEGER) - Random seed used
- `device` (TEXT) - cpu or cuda

**Indexes:**
- By algorithm, status, start_time
- By model_name for lookup

#### agent_performance

Performance metrics for trained agents.

**Key Fields:**
- `performance_id` (INTEGER, PK AUTO)
- `run_id` (TEXT, FK) - Parent training run
- `evaluation_date` (TEXT) - Evaluation date
- `evaluation_type` (TEXT) - train, validation, test, live_paper, backtest
- `data_period_start` (TEXT) - Evaluation data start
- `data_period_end` (TEXT) - Evaluation data end

*Return Metrics:*
- `total_return` (REAL) - Total return ($)
- `total_return_pct` (REAL) - Total return (%)
- `annualized_return` (REAL) - Annualized return
- `cumulative_reward` (REAL) - RL cumulative reward
- `avg_episode_reward` (REAL) - Avg episode reward

*Risk Metrics:*
- `sharpe_ratio`, `sortino_ratio`, `calmar_ratio` (REAL)
- `max_drawdown`, `max_drawdown_pct` (REAL)
- `volatility`, `downside_deviation` (REAL)

*Trade Statistics:*
- `total_trades`, `winning_trades`, `losing_trades` (INTEGER)
- `win_rate`, `avg_win`, `avg_loss` (REAL)
- `profit_factor`, `expectancy` (REAL)
- `largest_win`, `largest_loss` (REAL)

*Benchmark Comparison:*
- `buy_and_hold_return` (REAL) - B&H performance
- `excess_return` (REAL) - Alpha over B&H
- `information_ratio` (REAL) - Risk-adjusted alpha

*Model Confidence:*
- `avg_action_entropy` (REAL) - Action uncertainty
- `avg_value_estimate` (REAL) - Value function estimate
- `policy_stability` (REAL) - Policy consistency

**Indexes:**
- By run_id for run performance history
- By evaluation_type for filtering
- By sharpe_ratio (DESC) for leaderboard
- By evaluation_date for time series

#### hyperparameters

Hyperparameter configurations.

**Key Fields:**
- `hyperparameter_id` (INTEGER, PK AUTO)
- `run_id` (TEXT, UNIQUE FK) - Parent run
- `algorithm` (TEXT) - Algorithm type

*Common Hyperparameters:*
- `learning_rate` (REAL) - Learning rate
- `batch_size` (INTEGER) - Batch size
- `n_steps` (INTEGER) - Steps per update
- `gamma` (REAL) - Discount factor

*Policy Network:*
- `policy_type` (TEXT) - MlpPolicy, CnnPolicy, etc.
- `net_arch` (TEXT) - Network architecture (JSON)
- `activation_fn` (TEXT) - relu, tanh, etc.

*Training Parameters:*
- `n_epochs` (INTEGER) - Epochs per update
- `buffer_size` (INTEGER) - Replay buffer size
- `tau` (REAL) - Soft update coefficient
- `ent_coef` (REAL) - Entropy coefficient
- `vf_coef` (REAL) - Value function coefficient

*Environment Parameters:*
- `reward_function` (TEXT) - Reward function used
- `reward_scaling` (REAL) - Reward scaling factor
- `transaction_cost_pct` (REAL) - Transaction costs
- `slippage_pct` (REAL) - Slippage simulation

*All Parameters:*
- `params_json` (TEXT) - Complete JSON dump

**Indexes:**
- By run_id for quick lookup
- By algorithm for algorithm comparison

#### ensemble_weights

Weights for ensemble agent configurations.

**Key Fields:**
- `weight_id` (INTEGER, PK AUTO)
- `ensemble_id` (TEXT) - Ensemble identifier
- `update_time` (INTEGER) - When weights updated
- `update_date` (TEXT) - Date updated
- `run_id` (TEXT, FK) - Agent's training run
- `algorithm` (TEXT) - Agent algorithm
- `weight` (REAL) - Weight in ensemble (0-1)
- `performance_score` (REAL) - Performance metric
- `sharpe_ratio` (REAL) - Agent's Sharpe
- `win_rate` (REAL) - Agent's win rate
- `is_active` (INTEGER) - 1 if active
- `weighting_method` (TEXT) - equal, sharpe_weighted, performance_weighted, adaptive, manual
- `lookback_days` (INTEGER) - Performance lookback period

**Indexes:**
- Composite on (ensemble_id, update_time DESC)

#### training_episodes

Individual episode metrics during training.

**Key Fields:**
- `episode_id` (INTEGER, PK AUTO)
- `run_id` (TEXT, FK) - Parent training run
- `episode_number` (INTEGER) - Episode sequence number
- `episode_reward` (REAL) - Episode total reward
- `episode_length` (INTEGER) - Steps in episode
- `episode_time` (INTEGER) - Timestamp
- `mean_action` (REAL) - Average action taken
- `std_action` (REAL) - Action variance
- `mean_value` (REAL) - Average value estimate
- `mean_loss` (REAL) - Average loss
- `learning_rate` (REAL) - Learning rate at episode
- `exploration_rate` (REAL) - Exploration rate

**Indexes:**
- By run_id for episode history
- Composite on (run_id, episode_number) for lookup

### Views

#### v_agent_leaderboard

Best performing agents by Sharpe ratio:

```sql
SELECT * FROM v_agent_leaderboard LIMIT 10;
-- Returns: algorithm, model_name, sharpe_ratio, total_return_pct,
--          max_drawdown_pct, win_rate, total_trades
```

#### v_current_ensemble

Active ensemble composition:

```sql
SELECT * FROM v_current_ensemble;
-- Returns: ensemble_id, algorithm, model_name, weight,
--          performance_score, sharpe_ratio, last_updated
```

#### v_training_summary

Training runs with performance:

```sql
SELECT * FROM v_training_summary;
-- Returns: run_id, algorithm, model_name, status, duration_hours,
--          sharpe_ratio, win_rate, total_return_pct, learning_rate
```

#### v_hyperparameter_results

Hyperparameter optimization results:

```sql
SELECT * FROM v_hyperparameter_results LIMIT 10;
-- Returns: algorithm, learning_rate, batch_size, n_steps, gamma,
--          sharpe_ratio, win_rate, total_return_pct
```

### Common Queries

```sql
-- Best performing agents
SELECT * FROM v_agent_leaderboard LIMIT 10;

-- Compare algorithms
SELECT
    algorithm,
    COUNT(*) as runs,
    AVG(sharpe_ratio) as avg_sharpe,
    MAX(sharpe_ratio) as best_sharpe
FROM training_runs tr
JOIN agent_performance ap ON tr.run_id = ap.run_id
WHERE tr.status = 'completed' AND ap.evaluation_type = 'validation'
GROUP BY algorithm
ORDER BY avg_sharpe DESC;

-- Best hyperparameters for PPO
SELECT learning_rate, batch_size, n_steps, AVG(sharpe_ratio) as avg_sharpe
FROM hyperparameters hp
JOIN agent_performance ap ON hp.run_id = ap.run_id
WHERE hp.algorithm = 'PPO' AND ap.evaluation_type = 'validation'
GROUP BY learning_rate, batch_size, n_steps
ORDER BY avg_sharpe DESC
LIMIT 5;

-- Ensemble weight history
SELECT update_date, algorithm, weight, sharpe_ratio
FROM ensemble_weights
WHERE ensemble_id = 'production'
ORDER BY update_time DESC
LIMIT 20;
```

---

## Migration System

### Running Migrations

All migrations are managed via `migrate.py`:

```bash
# Run all pending migrations
python -m catalyst_bot.migrations.migrate

# Check migration status
python -m catalyst_bot.migrations.migrate status

# Verify databases
python -m catalyst_bot.migrations.migrate verify

# Run specific migration
python -m catalyst_bot.migrations.migrate upgrade --migration 001

# Rollback all (requires confirmation)
python -m catalyst_bot.migrations.migrate downgrade

# Rollback specific migration
python -m catalyst_bot.migrations.migrate downgrade --migration 002
```

### Migration Files

Located in `/home/user/catalyst-bot/src/catalyst_bot/migrations/`:

- `001_create_positions_tables.py` - Positions database
- `002_create_trading_tables.py` - Trading database
- `003_create_ml_training_tables.py` - ML training database
- `migrate.py` - Migration runner
- `README.md` - Migration documentation
- `schemas/` - Standalone SQL schemas

### Migration Tracking

Migrations tracked in `data/migrations.db`:

```sql
SELECT * FROM migration_history ORDER BY applied_at DESC;
```

---

## Usage Examples

### Opening a Position

```python
import time
import sqlite3
from catalyst_bot.storage import init_optimized_connection

conn = init_optimized_connection("data/positions.db")

# Insert new position
position_id = "pos_123456"
conn.execute("""
    INSERT INTO positions (
        position_id, ticker, side, quantity, entry_price, current_price,
        unrealized_pnl, opened_at, updated_at, strategy, signal_score
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
""", (
    position_id, 'AAPL', 'long', 100, 150.00, 150.00,
    0.0, int(time.time()), int(time.time()), 'ppo_agent', 0.85
))

conn.commit()
conn.close()
```

### Updating Position Price

```python
# Update current price and P&L
conn.execute("""
    UPDATE positions
    SET current_price = ?,
        unrealized_pnl = (? - entry_price) * quantity,
        unrealized_pnl_pct = ((? - entry_price) / entry_price) * 100,
        updated_at = ?
    WHERE position_id = ?
""", (155.50, 155.50, 155.50, int(time.time()), position_id))

conn.commit()
```

### Closing a Position

```python
# Move to closed_positions
cursor = conn.execute("SELECT * FROM positions WHERE position_id = ?", (position_id,))
position = cursor.fetchone()

exit_price = 160.00
closed_at = int(time.time())
holding_period_hours = (closed_at - position['opened_at']) / 3600
realized_pnl = (exit_price - position['entry_price']) * position['quantity']

conn.execute("""
    INSERT INTO closed_positions (
        position_id, ticker, side, quantity, entry_price, exit_price,
        realized_pnl, realized_pnl_pct, opened_at, closed_at, updated_at,
        holding_period_hours, exit_reason, strategy
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
""", (
    position_id, position['ticker'], position['side'], position['quantity'],
    position['entry_price'], exit_price, realized_pnl,
    (realized_pnl / (position['entry_price'] * position['quantity'])) * 100,
    position['opened_at'], closed_at, closed_at,
    holding_period_hours, 'take_profit', position['strategy']
))

conn.execute("DELETE FROM positions WHERE position_id = ?", (position_id,))
conn.commit()
```

### Recording an Order

```python
import uuid
conn = init_optimized_connection("data/trading.db")

order_id = f"order_{uuid.uuid4().hex[:8]}"
client_order_id = f"client_{uuid.uuid4().hex[:8]}"

conn.execute("""
    INSERT INTO orders (
        order_id, client_order_id, ticker, order_type, side, quantity,
        limit_price, time_in_force, status, submitted_at, updated_at,
        strategy
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
""", (
    order_id, client_order_id, 'TSLA', 'limit', 'buy', 50,
    250.00, 'day', 'pending', int(time.time()), int(time.time()),
    'sac_agent'
))

conn.commit()
```

### Recording Training Run

```python
conn = init_optimized_connection("data/ml_training.db")

run_id = f"run_{uuid.uuid4().hex[:8]}"

conn.execute("""
    INSERT INTO training_runs (
        run_id, algorithm, model_name, start_time, total_timesteps,
        train_start_date, train_end_date, status, random_seed
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
""", (
    run_id, 'PPO', 'ppo_catalyst_v1', int(time.time()), 200000,
    '2020-01-01', '2023-12-31', 'running', 42
))

conn.commit()
```

---

## Performance Optimization

### Index Strategy

All tables have indexes on:
- **Primary keys** - Fast lookups
- **Foreign keys** - Join performance
- **Time fields** - Time-series queries
- **Status/type fields** - Filtering
- **Composite keys** - Common WHERE clauses

### Query Optimization

```sql
-- Use EXPLAIN QUERY PLAN to verify index usage
EXPLAIN QUERY PLAN
SELECT * FROM positions WHERE ticker = 'AAPL';

-- Should show: SEARCH positions USING INDEX idx_positions_ticker
```

### WAL Mode Benefits

- **Concurrent reads** - Multiple readers don't block
- **Better performance** - Reduced disk I/O
- **Crash safety** - Atomic commits

Check WAL mode:
```sql
PRAGMA journal_mode;  -- Should return: wal
```

### Cache Tuning

Default cache: 10,000 pages (~40MB)

Increase for large queries:
```python
conn.execute("PRAGMA cache_size=20000")  # ~80MB
```

---

## Backup and Recovery

### Backup Strategy

```bash
#!/bin/bash
# Daily backup script

BACKUP_DIR="data/backups"
DATE=$(date +%Y%m%d_%H%M%S)

mkdir -p $BACKUP_DIR

# Backup all databases
cp data/positions.db "$BACKUP_DIR/positions_$DATE.db"
cp data/trading.db "$BACKUP_DIR/trading_$DATE.db"
cp data/ml_training.db "$BACKUP_DIR/ml_training_$DATE.db"
cp data/migrations.db "$BACKUP_DIR/migrations_$DATE.db"

# Compress old backups (older than 7 days)
find $BACKUP_DIR -name "*.db" -mtime +7 -exec gzip {} \;

# Delete backups older than 30 days
find $BACKUP_DIR -name "*.db.gz" -mtime +30 -delete

echo "Backup completed: $DATE"
```

### Export to SQL

```bash
# Export schema and data
sqlite3 data/positions.db .dump > positions_backup.sql

# Restore from SQL
sqlite3 data/positions_new.db < positions_backup.sql
```

### Point-in-Time Recovery

WAL mode provides point-in-time recovery:

```bash
# Backup WAL files along with database
cp data/positions.db data/backups/
cp data/positions.db-wal data/backups/  # If exists
cp data/positions.db-shm data/backups/  # If exists
```

---

## Integration Guide

### Position Manager Integration

```python
# src/catalyst_bot/portfolio/position_manager.py

from catalyst_bot.storage import init_optimized_connection
import time

class PositionManager:
    def __init__(self):
        self.conn = init_optimized_connection("data/positions.db")

    def open_position(self, ticker, side, quantity, entry_price, strategy, signal_score):
        position_id = f"pos_{int(time.time())}_{ticker}"

        self.conn.execute("""
            INSERT INTO positions (
                position_id, ticker, side, quantity, entry_price,
                current_price, unrealized_pnl, opened_at, updated_at,
                strategy, signal_score
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            position_id, ticker, side, quantity, entry_price,
            entry_price, 0.0, int(time.time()), int(time.time()),
            strategy, signal_score
        ))

        self.conn.commit()
        return position_id

    def update_prices(self, prices):
        """Update all positions with current prices"""
        for ticker, price in prices.items():
            self.conn.execute("""
                UPDATE positions
                SET current_price = ?,
                    unrealized_pnl = (? - entry_price) * quantity,
                    unrealized_pnl_pct = ((? - entry_price) / entry_price) * 100,
                    updated_at = ?
                WHERE ticker = ?
            """, (price, price, price, int(time.time()), ticker))

        self.conn.commit()
```

### Order Execution Integration

```python
# src/catalyst_bot/execution/order_executor.py

class OrderExecutor:
    def __init__(self):
        self.conn = init_optimized_connection("data/trading.db")

    def submit_order(self, ticker, side, quantity, order_type, limit_price=None):
        order_id = f"ord_{uuid.uuid4().hex[:8]}"
        client_order_id = f"cli_{uuid.uuid4().hex[:8]}"

        self.conn.execute("""
            INSERT INTO orders (
                order_id, client_order_id, ticker, order_type, side,
                quantity, limit_price, time_in_force, status,
                submitted_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            order_id, client_order_id, ticker, order_type, side,
            quantity, limit_price, 'day', 'pending',
            int(time.time()), int(time.time())
        ))

        self.conn.commit()
        return order_id
```

### Performance Tracking Integration

```python
# src/catalyst_bot/portfolio/performance_tracker.py

class PerformanceTracker:
    def __init__(self):
        self.trading_conn = init_optimized_connection("data/trading.db")
        self.positions_conn = init_optimized_connection("data/positions.db")

    def record_daily_snapshot(self, account_data):
        snapshot_date = time.strftime("%Y-%m-%d")

        self.trading_conn.execute("""
            INSERT OR REPLACE INTO portfolio_snapshots (
                snapshot_date, snapshot_time, total_equity, cash_balance,
                long_market_value, positions_count, daily_pnl,
                cumulative_pnl
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            snapshot_date, int(time.time()), account_data['equity'],
            account_data['cash'], account_data['long_value'],
            account_data['positions_count'], account_data['daily_pnl'],
            account_data['cumulative_pnl']
        ))

        self.trading_conn.commit()
```

---

## File Locations

```
catalyst-bot/
├── src/catalyst_bot/
│   └── migrations/
│       ├── __init__.py
│       ├── migrate.py                          # Migration runner
│       ├── 001_create_positions_tables.py      # Positions migration
│       ├── 002_create_trading_tables.py        # Trading migration
│       ├── 003_create_ml_training_tables.py    # ML training migration
│       ├── README.md                           # Migration docs
│       ├── SCHEMAS_QUICK_REFERENCE.md          # Quick reference
│       └── schemas/
│           ├── positions_schema.sql            # Positions SQL
│           ├── trading_schema.sql              # Trading SQL
│           └── ml_training_schema.sql          # ML training SQL
├── data/
│   ├── positions.db                            # Positions database
│   ├── trading.db                              # Trading database
│   ├── ml_training.db                          # ML training database
│   └── migrations.db                           # Migration tracker
└── docs/
    └── database-schemas-documentation.md       # This file
```

---

## Summary

The paper trading bot database architecture provides:

1. **Comprehensive tracking** - All positions, orders, fills, and performance
2. **ML integration** - Complete training run and agent management
3. **High performance** - Optimized indexes and WAL mode
4. **Easy querying** - Pre-built views for common patterns
5. **Safe migrations** - Idempotent, tracked migrations
6. **Extensibility** - JSON metadata fields for future needs

For questions or issues, refer to:
- Migration README: `/home/user/catalyst-bot/src/catalyst_bot/migrations/README.md`
- Quick Reference: `/home/user/catalyst-bot/src/catalyst_bot/migrations/SCHEMAS_QUICK_REFERENCE.md`
- Implementation Plan: `/home/user/catalyst-bot/docs/paper-trading-bot-implementation-plan.md`
