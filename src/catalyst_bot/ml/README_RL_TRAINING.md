# RL Trading Components - Implementation Guide

## Overview

This directory contains comprehensive scaffolding for training reinforcement learning agents on catalyst trading data. The implementation follows the architecture described in the paper trading bot research document.

## Components

### 1. CatalystTradingEnv (`trading_env.py`)
Gymnasium-compatible environment for RL training.

**Features:**
- 33-dimensional state space (price, sentiment, catalysts, market regime, position)
- Continuous action space [-1, 1] for position sizing
- Sharpe-ratio based reward function with transaction costs
- Integration with existing catalyst bot infrastructure

**State Space (33 features):**
```
Price Features (7):
  - last_price, price_change_pct, volatility_20d, volume_ratio
  - rsi_14, macd, bb_position

Sentiment Features (10):
  - vader, llm, ml, sec, earnings, analyst, social, premarket, aftermarket, combined

Catalyst Features (6):
  - keyword_score, category_one_hot (FDA, clinical, partnership, offering, other)

Market Regime (5):
  - vix_level, spy_trend, market_session, time_of_day, day_of_week

Position (5):
  - current_position, unrealized_pnl, time_in_position, portfolio_value, cash
```

**Usage:**
```python
from catalyst_bot.ml import CatalystTradingEnv

# Create environment
env = CatalystTradingEnv(
    data_df=catalyst_data,
    initial_capital=10000.0,
    max_position_size=0.2,
    transaction_cost=0.001,
)

# Standard gym interface
obs, info = env.reset()
action = env.action_space.sample()
obs, reward, terminated, truncated, info = env.step(action)
```

### 2. AgentTrainer (`train_agent.py`)
Comprehensive training pipeline for PPO, SAC, and A2C algorithms.

**Features:**
- Data splitting (train/val/test with temporal ordering)
- Multi-algorithm support (PPO, SAC, A2C from stable-baselines3)
- Hyperparameter optimization (Optuna)
- Walk-forward validation
- Model checkpointing and TensorBoard logging

**Training Example:**
```python
from catalyst_bot.ml import AgentTrainer

# Create trainer
trainer = AgentTrainer(
    data_df=catalyst_data,
    train_ratio=0.7,
    val_ratio=0.15,
    test_ratio=0.15,
)

# Train PPO agent
trainer.train_ppo(
    total_timesteps=100000,
    learning_rate=3e-4,
    n_steps=2048,
    batch_size=64,
)

# Save model
trainer.save_model("checkpoints/ppo_agent.zip")

# Hyperparameter optimization
best_params = trainer.optimize_hyperparameters(
    algorithm="ppo",
    n_trials=50,
    n_timesteps=50000,
)

# Walk-forward validation
results = trainer.walk_forward_validate(
    n_splits=5,
    algorithm="ppo",
    timesteps_per_split=50000,
)
```

**Command-line Interface:**
```bash
python -m catalyst_bot.ml.train_agent \
  --data data/catalyst_history.csv \
  --algorithm ppo \
  --timesteps 100000 \
  --output checkpoints/ppo_agent.zip
```

### 3. EnsembleAgent (`ensemble.py`)
Sharpe-weighted ensemble of multiple trained agents.

**Features:**
- Combine multiple agents (PPO, SAC, A2C)
- Sharpe-ratio weighted predictions
- Dynamic weight adjustment based on rolling performance
- Per-agent performance tracking

**Usage:**
```python
from catalyst_bot.ml import EnsembleAgent

# Create ensemble
ensemble = EnsembleAgent(
    reweight_frequency=1000,
    min_weight=0.1,
    lookback_window=100,
)

# Add agents
ensemble.add_agent("checkpoints/ppo_agent.zip", "ppo", weight=1.0)
ensemble.add_agent("checkpoints/sac_agent.zip", "sac", weight=1.0)
ensemble.add_agent("checkpoints/a2c_agent.zip", "a2c", weight=1.0)

# Predict (weighted average of all agents)
action, info = ensemble.predict(observation)

# Update performance (for reweighting)
ensemble.update_performance(observation, action, reward)

# Get stats
stats = ensemble.get_agent_stats()
for stat in stats:
    print(f"{stat['name']}: weight={stat['weight']:.3f}, sharpe={stat['sharpe']:.3f}")
```

### 4. StrategyEvaluator (`evaluate.py`)
Comprehensive backtesting and performance analysis.

**Features:**
- Backtest agents on historical data
- Calculate performance metrics (Sharpe, Sortino, max drawdown, etc.)
- Generate HTML/JSON reports
- Visualize equity curves, trades, drawdowns
- Compare multiple strategies

**Performance Metrics:**
- Total return, annualized return
- Sharpe ratio, Sortino ratio, Calmar ratio
- Max drawdown, max drawdown duration
- Win rate, profit factor
- Total trades, average trade return

**Usage:**
```python
from catalyst_bot.ml import StrategyEvaluator

# Create evaluator
evaluator = StrategyEvaluator(
    initial_capital=10000.0,
    risk_free_rate=0.02,
    output_dir="evaluation/",
)

# Backtest single agent
results = evaluator.backtest_agent(
    model_path="checkpoints/ppo_agent.zip",
    model_type="ppo",
    test_data=test_df,
)

# Print report
evaluator.print_report(results)

# Save report
evaluator.save_report(results, "evaluation/ppo_report.json")

# Plot equity curve
evaluator.plot_equity_curve(results, output_path="evaluation/equity_curve.png")

# Compare multiple strategies
results_list = [
    evaluator.backtest_agent("checkpoints/ppo_agent.zip", "ppo", test_df),
    evaluator.backtest_agent("checkpoints/sac_agent.zip", "sac", test_df),
]
comparison = evaluator.compare_strategies(results_list, output_path="evaluation/comparison.csv")
print(comparison)
```

**Command-line Interface:**
```bash
python -m catalyst_bot.ml.evaluate \
  --model checkpoints/ppo_agent.zip \
  --type ppo \
  --data data/test.csv \
  --output-dir evaluation/
```

## Installation

### Dependencies

Add to `requirements.txt`:
```
# RL Training (NEW)
gymnasium>=0.29.0
stable-baselines3>=2.0.0
optuna>=3.0.0  # For hyperparameter optimization

# Visualization
matplotlib>=3.5.0
plotly>=5.0.0  # Optional, for interactive plots
```

Install:
```bash
pip install gymnasium stable-baselines3 optuna matplotlib plotly
```

## Integration with Existing Catalyst Bot

### Data Preparation

The RL components expect a DataFrame with the following columns:

```python
Required Columns:
- ts_utc: Timestamp (datetime or ISO string)
- ticker: Stock ticker symbol
- last_price: Current price

Sentiment Columns (from classify.py):
- sentiment_local: VADER sentiment
- sentiment_llm: LLM sentiment
- sentiment_ml: ML sentiment (FinBERT)
- sentiment_sec: SEC filing sentiment
- sentiment_earnings: Earnings sentiment
- sentiment_analyst: Analyst sentiment
- sentiment_social: Social sentiment
- sentiment_premarket: Pre-market sentiment
- sentiment_aftermarket: After-market sentiment
- sentiment_combined: Combined sentiment

Catalyst Columns:
- keyword_score: Keyword match score
- catalyst_category: Category (fda, clinical, partnership, offering, other)
```

### Extracting Training Data

Use existing catalyst bot infrastructure:

```python
from catalyst_bot.storage import connect, migrate
from catalyst_bot.classify import classify
from catalyst_bot.market import get_last_price_snapshot
import pandas as pd

# Connect to database
conn = connect()
migrate(conn)

# Load historical events
query = """
SELECT
    ts_utc,
    ticker,
    title,
    sentiment_local,
    sentiment_llm,
    sentiment_ml,
    sentiment_sec,
    sentiment_earnings,
    sentiment_analyst,
    sentiment_social,
    sentiment_premarket,
    sentiment_aftermarket,
    sentiment_combined,
    keyword_score,
    catalyst_category
FROM alerts
WHERE ts_utc >= date('now', '-12 months')
ORDER BY ts_utc
"""

df = pd.read_sql_query(query, conn)

# Enrich with price data (if not in DB)
for idx, row in df.iterrows():
    last_price, prev_close = get_last_price_snapshot(row['ticker'])
    df.at[idx, 'last_price'] = last_price

# Save for training
df.to_csv('data/catalyst_training_data.csv', index=False)
```

### Production Integration

Once trained, integrate RL agent into live trading flow:

```python
from catalyst_bot.ml import EnsembleAgent
from catalyst_bot.classify import classify
import numpy as np

# Load ensemble at startup
ensemble = EnsembleAgent()
ensemble.add_agent("checkpoints/ppo_best.zip", "ppo")
ensemble.add_agent("checkpoints/sac_best.zip", "sac")

# In main trading loop (after classify)
def process_catalyst_event(event):
    # Classify event (existing)
    scored = classify(event)

    # Extract features for RL agent
    features = extract_features_for_rl(scored)  # 33-dim vector

    # Get RL agent recommendation
    action, info = ensemble.predict(features)

    # Convert action to position size (-1 to 1)
    position_size = action[0]

    # Execute trade if confidence high enough
    if abs(position_size) > 0.3:
        execute_paper_trade(
            ticker=scored.ticker,
            position_size=position_size,
            event=scored,
        )
```

## Training Workflow

### 1. Data Collection (12+ months)
```bash
# Run catalyst bot to collect data
python main.py

# Export to CSV
python scripts/export_training_data.py --output data/catalyst_12mo.csv
```

### 2. Train Multiple Agents
```bash
# Train PPO
python -m catalyst_bot.ml.train_agent \
  --data data/catalyst_12mo.csv \
  --algorithm ppo \
  --timesteps 200000 \
  --output checkpoints/ppo_agent.zip

# Train SAC
python -m catalyst_bot.ml.train_agent \
  --data data/catalyst_12mo.csv \
  --algorithm sac \
  --timesteps 200000 \
  --output checkpoints/sac_agent.zip

# Train A2C
python -m catalyst_bot.ml.train_agent \
  --data data/catalyst_12mo.csv \
  --algorithm a2c \
  --timesteps 200000 \
  --output checkpoints/a2c_agent.zip
```

### 3. Hyperparameter Optimization (Optional)
```python
from catalyst_bot.ml import AgentTrainer
import pandas as pd

data = pd.read_csv('data/catalyst_12mo.csv')
trainer = AgentTrainer(data)

# Optimize PPO
best_ppo_params = trainer.optimize_hyperparameters(
    algorithm="ppo",
    n_trials=50,
    n_timesteps=50000,
)

# Retrain with best params
trainer.train_ppo(total_timesteps=200000, **best_ppo_params)
trainer.save_model("checkpoints/ppo_optimized.zip")
```

### 4. Walk-Forward Validation
```python
results = trainer.walk_forward_validate(
    n_splits=5,
    algorithm="ppo",
    timesteps_per_split=50000,
)

# Analyze results
import json
print(json.dumps(results, indent=2))
```

### 5. Evaluation
```bash
python -m catalyst_bot.ml.evaluate \
  --model checkpoints/ppo_agent.zip \
  --type ppo \
  --data data/test.csv \
  --output-dir evaluation/ppo/
```

### 6. Create Ensemble
```python
from catalyst_bot.ml import EnsembleAgent

ensemble = EnsembleAgent()
ensemble.add_agent("checkpoints/ppo_agent.zip", "ppo")
ensemble.add_agent("checkpoints/sac_agent.zip", "sac")
ensemble.add_agent("checkpoints/a2c_agent.zip", "a2c")

# Test ensemble
from catalyst_bot.ml import StrategyEvaluator
evaluator = StrategyEvaluator()

# Backtest ensemble (TODO: implement ensemble backtesting in evaluator)
```

## TODO: Implementation Priorities

### Critical (Week 1)
1. ✅ Create scaffolding (DONE)
2. ⬜ Complete feature extraction in `_extract_features()` (integrate market.py indicators)
3. ⬜ Implement data validation in `_validate_data()`
4. ⬜ Test environment on sample data
5. ⬜ Train baseline PPO agent

### Important (Week 2)
6. ⬜ Implement walk-forward validation properly
7. ⬜ Add comprehensive logging/tensorboard integration
8. ⬜ Test SAC and A2C training
9. ⬜ Implement ensemble backtesting
10. ⬜ Create data export script from catalyst DB

### Nice-to-Have (Week 3+)
11. ⬜ Add Monte Carlo simulation for robustness testing
12. ⬜ Implement custom network architectures (LSTM for sequences)
13. ⬜ Add multi-asset portfolio optimization
14. ⬜ Create web dashboard for monitoring training
15. ⬜ Integrate with live paper trading API

## Monitoring Training

### TensorBoard
```bash
tensorboard --logdir logs/
```

View at http://localhost:6006

### Checkpoints
Models are saved periodically to `checkpoints/`:
- `checkpoints/ppo/ppo_model_10000_steps.zip`
- `checkpoints/ppo_best/best_model.zip`

### Evaluation
```bash
# Monitor validation performance
tail -f logs/ppo_eval/evaluations.npz

# Check training logs
tail -f logs/ppo/ppo_run_1/events.out.tfevents.*
```

## Troubleshooting

### Issue: Environment step fails with missing features
**Solution:** Ensure all required columns exist in data_df. Check `_validate_data()` warnings.

### Issue: Training is slow
**Solution:**
- Use more parallel environments (`n_envs=4`)
- Reduce `n_steps` for more frequent updates
- Use SubprocVecEnv instead of DummyVecEnv

### Issue: Agent learns poorly (low Sharpe)
**Solution:**
- Increase training timesteps (100k → 500k+)
- Tune hyperparameters (learning rate, reward function)
- Check reward function design (may need scaling)
- Verify feature normalization

### Issue: Ensemble weights don't change
**Solution:**
- Reduce `reweight_frequency` (1000 → 500)
- Increase `lookback_window` for more stable Sharpe estimates
- Check that agents are producing different actions

## References

- [Stable-Baselines3 Docs](https://stable-baselines3.readthedocs.io/)
- [Gymnasium Docs](https://gymnasium.farama.org/)
- [RL Trading Paper](https://arxiv.org/abs/2011.09607)
- Catalyst Bot Research Doc: `/home/user/catalyst-bot/docs/paper_trading_bot_research.md`

## Contact

For questions or issues, see main project README.
