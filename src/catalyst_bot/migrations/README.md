# Database Migrations for Paper Trading Bot

This directory contains database migration scripts for the Catalyst Bot paper trading system.

## Overview

The paper trading bot uses three separate SQLite databases:

1. **`data/positions.db`** - Open and closed trading positions
2. **`data/trading.db`** - Orders, fills, portfolio snapshots, and performance metrics
3. **`data/ml_training.db`** - RL training runs, agent performance, and hyperparameters

## Quick Start

### Run All Migrations

```bash
# From project root
python -m catalyst_bot.migrations.migrate

# Or with explicit upgrade
python -m catalyst_bot.migrations.migrate upgrade
```

### Check Migration Status

```bash
python -m catalyst_bot.migrations.migrate status
```

### Verify Databases

```bash
python -m catalyst_bot.migrations.migrate verify
```

### Run Specific Migration

```bash
python -m catalyst_bot.migrations.migrate upgrade --migration 001
```

### Rollback Migrations

```bash
# Rollback all migrations (requires confirmation)
python -m catalyst_bot.migrations.migrate downgrade

# Rollback specific migration
python -m catalyst_bot.migrations.migrate downgrade --migration 002
```

## Migration Files

### 001_create_positions_tables.py

**Database:** `data/positions.db`

Creates tables for position tracking:

- **`positions`** - Currently open positions
  - position_id, ticker, side, quantity, entry_price, current_price
  - unrealized_pnl, stop_loss_price, take_profit_price
  - opened_at, updated_at, strategy, signal_score
  - metadata (JSON)

- **`closed_positions`** - Historical closed positions
  - All position fields plus:
  - closed_at, exit_price, realized_pnl, holding_period_hours
  - exit_reason, commission, slippage
  - max_favorable_excursion, max_adverse_excursion

**Indexes:**
- ticker, strategy, opened_at, unrealized_pnl
- ticker+side composite index

**Views:**
- `v_position_summary` - Current positions with P&L
- `v_recent_closed_trades` - Last 100 closed trades

### 002_create_trading_tables.py

**Database:** `data/trading.db`

Creates tables for trading execution and performance:

- **`orders`** - All orders placed
  - order_id, ticker, order_type, side, quantity
  - limit_price, stop_price, time_in_force
  - status, filled_quantity, filled_avg_price
  - commission, slippage, position_id

- **`fills`** - Order fill events
  - fill_id, order_id, ticker, side, quantity, price
  - filled_at, liquidity (maker/taker), commission

- **`portfolio_snapshots`** - Daily portfolio values
  - snapshot_date, total_equity, cash_balance
  - long_market_value, short_market_value
  - daily_pnl, cumulative_pnl, positions_count
  - buying_power, leverage, unrealized_pnl

- **`performance_metrics`** - Daily performance statistics
  - sharpe_ratio, sortino_ratio, calmar_ratio
  - max_drawdown, current_drawdown, volatility
  - win_rate, profit_factor, avg_win, avg_loss
  - alpha, beta, correlation_to_benchmark

**Indexes:**
- Order: ticker, status, submitted_at, position_id, strategy
- Fills: order_id, ticker, filled_at, position_id
- Portfolio: snapshot_date, snapshot_time
- Performance: metric_date, strategy

**Views:**
- `v_recent_orders` - Last 100 orders
- `v_order_fill_stats` - Fill statistics per order
- `v_equity_curve` - Portfolio value over time
- `v_performance_summary` - Last 30 days of metrics

### 003_create_ml_training_tables.py

**Database:** `data/ml_training.db`

Creates tables for RL training and agent management:

- **`training_runs`** - RL training session metadata
  - run_id, algorithm (PPO/SAC/A2C/TD3/DQN)
  - start_time, end_time, duration_seconds, total_timesteps
  - train_start_date, train_end_date, val_start_date, val_end_date
  - status, final_reward, model_path

- **`agent_performance`** - Validation results
  - run_id, evaluation_date, data_period_start, data_period_end
  - sharpe_ratio, sortino_ratio, max_drawdown, total_return
  - win_rate, profit_factor, total_trades
  - avg_episode_reward, num_episodes

- **`hyperparameters`** - Hyperparameter configurations
  - run_id, algorithm, learning_rate, batch_size, n_steps, gamma
  - policy_type, net_arch, n_epochs, buffer_size
  - ent_coef, vf_coef, max_grad_norm
  - params_json (all parameters as JSON)

- **`ensemble_weights`** - Ensemble agent weights
  - ensemble_id, run_id, algorithm, weight
  - performance_score, sharpe_ratio, is_active
  - weighting_method, update_time

- **`training_episodes`** - Individual training episodes
  - run_id, episode_number, episode_reward, episode_length
  - mean_action, std_action, mean_value, mean_loss

**Indexes:**
- Training runs: algorithm, status, start_time, model_name
- Performance: run_id, evaluation_type, sharpe_ratio, date
- Hyperparameters: run_id, algorithm
- Ensemble weights: ensemble_id+update_time composite
- Episodes: run_id, run_id+episode_number composite

**Views:**
- `v_agent_leaderboard` - Best agents by Sharpe ratio
- `v_current_ensemble` - Active ensemble composition
- `v_training_summary` - Training runs with performance
- `v_hyperparameter_results` - Hyperparameter optimization results

## Migration Tracking

Migrations are tracked in `data/migrations.db` with the following schema:

```sql
CREATE TABLE migration_history (
    migration_id TEXT PRIMARY KEY,
    migration_name TEXT NOT NULL,
    database_path TEXT NOT NULL,
    applied_at INTEGER NOT NULL,
    applied_date TEXT NOT NULL,
    duration_seconds REAL,
    status TEXT NOT NULL CHECK(status IN ('applied', 'rolled_back', 'failed')),
    error_message TEXT
);
```

## Schema Design Principles

### Timestamps
- All timestamps stored as Unix epoch integers (seconds since 1970-01-01)
- Converted to datetime in views for readability
- Uses `datetime(timestamp, 'unixepoch')` in SQL

### Foreign Keys
- Foreign key constraints enable referential integrity
- Use `PRAGMA foreign_keys = ON;` to enforce

### Indexes
- Primary indexes on commonly filtered columns
- Composite indexes for common WHERE clauses
- Descending indexes for time-based sorting

### Views
- Pre-built views for common query patterns
- Include datetime conversions and calculated fields
- Simplify application queries

### Constraints
- CHECK constraints for data validation
- UNIQUE constraints for deduplication
- NOT NULL for required fields

## Database Optimization

All databases use the optimized connection settings from `storage.py`:

```python
PRAGMA journal_mode=WAL         # Write-Ahead Logging for concurrency
PRAGMA synchronous=NORMAL       # Balance safety and speed
PRAGMA cache_size=10000         # ~40MB cache
PRAGMA mmap_size=30000000000    # 30GB memory-mapped I/O
PRAGMA temp_store=MEMORY        # Memory temp tables
```

## Common Queries

### Positions Database

```sql
-- Get all open positions
SELECT * FROM v_position_summary;

-- Get total unrealized P&L
SELECT SUM(unrealized_pnl) FROM positions;

-- Get win rate
SELECT
    COUNT(CASE WHEN realized_pnl > 0 THEN 1 END) * 1.0 / COUNT(*) as win_rate
FROM closed_positions;
```

### Trading Database

```sql
-- Get equity curve
SELECT * FROM v_equity_curve;

-- Get current Sharpe ratio
SELECT sharpe_ratio, max_drawdown_pct
FROM performance_metrics
ORDER BY metric_date DESC
LIMIT 1;

-- Get recent order fills
SELECT * FROM v_recent_orders WHERE status = 'filled';
```

### ML Training Database

```sql
-- Get best agents
SELECT * FROM v_agent_leaderboard LIMIT 10;

-- Get current ensemble
SELECT * FROM v_current_ensemble;

-- Compare algorithms
SELECT
    algorithm,
    AVG(sharpe_ratio) as avg_sharpe,
    COUNT(*) as num_runs
FROM training_runs tr
JOIN agent_performance ap ON tr.run_id = ap.run_id
GROUP BY algorithm;
```

## Backup and Restore

### Backup

```bash
# Backup all databases
cp data/positions.db data/backups/positions_$(date +%Y%m%d_%H%M%S).db
cp data/trading.db data/backups/trading_$(date +%Y%m%d_%H%M%S).db
cp data/ml_training.db data/backups/ml_training_$(date +%Y%m%d_%H%M%S).db
```

### Restore

```bash
# Restore from backup
cp data/backups/positions_20250120_123000.db data/positions.db
```

### Export to SQL

```bash
# Export schema and data
sqlite3 data/positions.db .dump > positions_dump.sql

# Restore from SQL dump
sqlite3 data/positions_new.db < positions_dump.sql
```

## Testing Migrations

```bash
# Test migrations in isolated environment
export DB_PATH_PREFIX="test_"

# Run migrations
python -m catalyst_bot.migrations.migrate

# Verify
python -m catalyst_bot.migrations.migrate verify

# Cleanup
rm -f test_*.db
```

## Troubleshooting

### Migration Fails

```bash
# Check migration status
python -m catalyst_bot.migrations.migrate status

# View error in migration history
sqlite3 data/migrations.db "SELECT * FROM migration_history WHERE status = 'failed';"

# Fix issue and re-run specific migration
python -m catalyst_bot.migrations.migrate upgrade --migration 001
```

### Database Locked

If you get "database is locked" errors:

```bash
# Check WAL mode is enabled
sqlite3 data/positions.db "PRAGMA journal_mode;"
# Should return: wal

# Check for stuck connections
lsof | grep positions.db

# Close all connections and restart
```

### Schema Mismatch

```bash
# Check actual schema
sqlite3 data/positions.db ".schema positions"

# Compare to migration file
# If needed, rollback and re-run
python -m catalyst_bot.migrations.migrate downgrade --migration 001
python -m catalyst_bot.migrations.migrate upgrade --migration 001
```

## Integration with Storage.py

The migrations use the same connection patterns as `storage.py`:

```python
from catalyst_bot.storage import _ensure_dir, init_optimized_connection

# Create database with optimized settings
conn = init_optimized_connection("data/positions.db")

# Run migration
conn.execute("CREATE TABLE IF NOT EXISTS positions (...)")
conn.commit()
conn.close()
```

## Future Migrations

To add a new migration:

1. Create `004_migration_name.py` in this directory
2. Implement `upgrade()` and `downgrade()` functions
3. Follow the existing patterns from 001-003
4. Add to `MIGRATIONS` list in `migrate.py`
5. Test thoroughly before running on production data

## Best Practices

1. **Always backup** before running migrations on production data
2. **Test migrations** on development/staging databases first
3. **Use transactions** - migrations should be atomic
4. **Keep idempotent** - migrations should be safe to run multiple times
5. **Add indexes** for common query patterns
6. **Use views** to simplify complex queries
7. **Document schemas** with clear comments
8. **Validate constraints** to ensure data integrity

## References

- [SQLite Documentation](https://www.sqlite.org/docs.html)
- [SQLite WAL Mode](https://www.sqlite.org/wal.html)
- [Paper Trading Bot Implementation Plan](/home/user/catalyst-bot/docs/paper-trading-bot-implementation-plan.md)
- [Existing Storage Module](/home/user/catalyst-bot/src/catalyst_bot/storage.py)
