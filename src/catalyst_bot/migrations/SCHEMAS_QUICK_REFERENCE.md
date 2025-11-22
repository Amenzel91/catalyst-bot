# Database Schemas Quick Reference

## Overview

Three databases for paper trading bot:
- **positions.db** - Position tracking
- **trading.db** - Order execution and performance
- **ml_training.db** - RL training and agent management

---

## positions.db

### Tables

#### `positions` - Open Positions
```
position_id, ticker, side, quantity, entry_price, current_price,
unrealized_pnl, unrealized_pnl_pct, stop_loss_price, take_profit_price,
opened_at, updated_at, strategy, signal_score, atr_at_entry, rvol_at_entry,
market_regime, metadata
```

#### `closed_positions` - Historical Positions
```
position_id, ticker, side, quantity, entry_price, exit_price,
realized_pnl, realized_pnl_pct, stop_loss_price, take_profit_price,
opened_at, closed_at, updated_at, holding_period_hours, exit_reason,
strategy, signal_score, atr_at_entry, rvol_at_entry, market_regime,
commission, slippage, max_favorable_excursion, max_adverse_excursion, metadata
```

### Views
- `v_position_summary` - Current positions with P&L
- `v_recent_closed_trades` - Last 100 closed trades

### Key Queries
```sql
-- Total unrealized P&L
SELECT SUM(unrealized_pnl) FROM positions;

-- Win rate
SELECT COUNT(CASE WHEN realized_pnl > 0 THEN 1 END) * 1.0 / COUNT(*) FROM closed_positions;
```

---

## trading.db

### Tables

#### `orders` - All Orders
```
order_id, client_order_id, ticker, order_type, side, quantity,
limit_price, stop_price, time_in_force, status, submitted_at, updated_at,
filled_at, cancelled_at, expired_at, filled_quantity, filled_avg_price,
commission, position_id, parent_order_id, strategy, signal_score,
expected_price, slippage, reject_reason, metadata
```

#### `fills` - Fill Events
```
fill_id, order_id, client_order_id, ticker, side, quantity, price,
filled_at, liquidity, commission, position_id, exchange, metadata
```

#### `portfolio_snapshots` - Daily Portfolio Values
```
snapshot_id, snapshot_date, snapshot_time, total_equity, cash_balance,
long_market_value, short_market_value, net_liquidation_value, positions_count,
daily_pnl, daily_return_pct, cumulative_pnl, cumulative_return_pct,
buying_power, leverage, margin_used, unrealized_pnl, realized_pnl_today,
trades_today, wins_today, losses_today, metadata
```

#### `performance_metrics` - Daily Performance Stats
```
metric_id, metric_date, metric_time, sharpe_ratio, sortino_ratio, calmar_ratio,
omega_ratio, max_drawdown, max_drawdown_pct, current_drawdown, current_drawdown_pct,
days_in_drawdown, recovery_days, return_1d, return_7d, return_30d, return_ytd,
return_inception, volatility_daily, volatility_annualized, downside_deviation,
total_trades_30d, winning_trades_30d, losing_trades_30d, win_rate_30d,
avg_win_30d, avg_loss_30d, profit_factor_30d, expectancy_30d, largest_win_30d,
largest_loss_30d, current_win_streak, current_loss_streak, max_win_streak,
max_loss_streak, avg_position_size, avg_holding_period_hours, turnover_rate,
benchmark_return, alpha, beta, correlation_to_benchmark, strategy, metadata
```

### Views
- `v_recent_orders` - Last 100 orders
- `v_order_fill_stats` - Fill statistics per order
- `v_equity_curve` - Portfolio value over time
- `v_performance_summary` - Last 30 days of metrics

### Key Queries
```sql
-- Equity curve
SELECT snapshot_date, total_equity, cumulative_return_pct FROM portfolio_snapshots;

-- Current Sharpe ratio
SELECT sharpe_ratio, max_drawdown_pct FROM performance_metrics ORDER BY metric_date DESC LIMIT 1;
```

---

## ml_training.db

### Tables

#### `training_runs` - Training Sessions
```
run_id, algorithm, model_name, start_time, end_time, duration_seconds,
total_timesteps, train_start_date, train_end_date, val_start_date, val_end_date,
status, final_reward, best_reward, final_loss, convergence_achieved, early_stopped,
model_path, tensorboard_log_dir, python_version, stable_baselines_version,
random_seed, device, num_envs, notes, metadata
```

#### `agent_performance` - Validation Results
```
performance_id, run_id, evaluation_date, evaluation_time, data_period_start,
data_period_end, evaluation_type, total_return, total_return_pct, annualized_return,
cumulative_reward, avg_episode_reward, sharpe_ratio, sortino_ratio, calmar_ratio,
max_drawdown, max_drawdown_pct, volatility, downside_deviation, total_trades,
winning_trades, losing_trades, win_rate, avg_win, avg_loss, profit_factor,
expectancy, largest_win, largest_loss, avg_holding_period_hours,
buy_and_hold_return, excess_return, information_ratio, num_episodes,
avg_episode_length, successful_episodes, avg_action_entropy, avg_value_estimate,
policy_stability, notes, metadata
```

#### `hyperparameters` - Hyperparameter Configs
```
hyperparameter_id, run_id, algorithm, learning_rate, batch_size, n_steps, gamma,
policy_type, net_arch, activation_fn, n_epochs, buffer_size, learning_starts,
tau, gradient_steps, ent_coef, vf_coef, max_grad_norm, target_kl,
normalize_observations, normalize_rewards, clip_range, clip_range_vf,
optimizer, epsilon, weight_decay, reward_function, reward_scaling,
transaction_cost_pct, slippage_pct, params_json, created_at
```

#### `ensemble_weights` - Ensemble Agent Weights
```
weight_id, ensemble_id, update_time, update_date, run_id, algorithm,
weight, performance_score, sharpe_ratio, win_rate, is_active,
weighting_method, lookback_days, notes, metadata
```

#### `training_episodes` - Training Episodes
```
episode_id, run_id, episode_number, episode_reward, episode_length,
episode_time, mean_action, std_action, mean_value, mean_loss,
learning_rate, exploration_rate, metadata
```

### Views
- `v_agent_leaderboard` - Best agents by Sharpe ratio
- `v_current_ensemble` - Active ensemble composition
- `v_training_summary` - Training runs with performance
- `v_hyperparameter_results` - Hyperparameter optimization results

### Key Queries
```sql
-- Best agents
SELECT * FROM v_agent_leaderboard LIMIT 10;

-- Current ensemble
SELECT * FROM v_current_ensemble;

-- Algorithm comparison
SELECT algorithm, AVG(sharpe_ratio) as avg_sharpe, COUNT(*) as runs
FROM training_runs tr
JOIN agent_performance ap ON tr.run_id = ap.run_id
WHERE tr.status = 'completed' AND ap.evaluation_type = 'validation'
GROUP BY algorithm;
```

---

## Common Patterns

### Timestamps
All timestamps are Unix epoch (seconds since 1970-01-01).
Convert to datetime: `datetime(timestamp, 'unixepoch')`

### Foreign Keys
Enable foreign key constraints:
```sql
PRAGMA foreign_keys = ON;
```

### Metadata Fields
JSON fields for additional context:
```python
import json
metadata = json.dumps({"key": "value"})
```

### Indexes
All common queries have supporting indexes for performance.

---

## Migration Commands

```bash
# Run all migrations
python -m catalyst_bot.migrations.migrate

# Check status
python -m catalyst_bot.migrations.migrate status

# Verify databases
python -m catalyst_bot.migrations.migrate verify

# Run specific migration
python -m catalyst_bot.migrations.migrate upgrade --migration 001

# Rollback (requires confirmation)
python -m catalyst_bot.migrations.migrate downgrade
```

---

## File Locations

- Migration scripts: `/home/user/catalyst-bot/src/catalyst_bot/migrations/`
- SQL schemas: `/home/user/catalyst-bot/src/catalyst_bot/migrations/schemas/`
- Databases: `/home/user/catalyst-bot/data/`
- Migration tracker: `/home/user/catalyst-bot/data/migrations.db`

---

## Database Optimization

All databases use:
- **WAL mode** for concurrency
- **40MB cache** for performance
- **Memory-mapped I/O** for speed
- **NORMAL synchronous mode** for balance

Check optimization:
```sql
PRAGMA journal_mode;  -- Should return: wal
PRAGMA cache_size;    -- Should return: 10000
```
