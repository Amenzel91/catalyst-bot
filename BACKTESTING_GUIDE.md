# Backtesting Engine Guide

**Wave 1.3: Production-Grade Backtesting for Catalyst Trading Bot**

This guide explains how to use the backtesting engine to validate trading strategies with historical data before deploying them live.

---

## Table of Contents

1. [Overview](#overview)
2. [Quick Start](#quick-start)
3. [Components](#components)
4. [Usage Examples](#usage-examples)
5. [Configuration](#configuration)
6. [Understanding Reports](#understanding-reports)
7. [Parameter Optimization](#parameter-optimization)
8. [Best Practices](#best-practices)
9. [Troubleshooting](#troubleshooting)

---

## Overview

The backtesting engine allows you to:

- **Replay historical alerts** from `events.jsonl` with realistic penny stock trading simulation
- **Model slippage and fees** accurately for penny stocks (2-15% slippage based on liquidity)
- **Track performance metrics** including Sharpe ratio, win rate, max drawdown, profit factor
- **Validate parameter changes** before applying them to production
- **Optimize strategy parameters** using Monte Carlo simulations
- **Generate comprehensive reports** in multiple formats (Markdown, HTML, JSON, Discord)

---

## Quick Start

### 1. Run a Basic Backtest

Test the last 30 days of alerts with default parameters:

```bash
python run_backtest.py --days 30
```

**Output:**
```
=== Backtest Results ===

Total Return: 15.50%
Sharpe Ratio: 1.80
Win Rate: 58.0%
Max Drawdown: 8.50%
Profit Factor: 2.10
Total Trades: 50
Winning Trades: 29
Losing Trades: 21
Avg Hold Time: 18.5 hours
```

### 2. Generate a Full Report

```bash
python run_backtest.py --days 30 --format markdown --output backtest_report.md
```

This creates a detailed Markdown report with:
- Executive summary
- Trade statistics
- Performance by catalyst type
- Best/worst trades
- Recommendations

### 3. Validate a Parameter Change

Before changing `MIN_SCORE` from 0.25 to 0.30:

```bash
python run_backtest.py --validate min_score --old 0.25 --new 0.30 --days 30
```

**Output:**
```
=== Validation Results ===

Recommendation: APPROVE
Confidence: 85%
Reason: Good improvement: Sharpe +15.2%, Return +2.3%, Win Rate +4.0%

| Metric | Old Value | New Value | Change |
|--------|-----------|-----------|--------|
| Sharpe Ratio | 1.50 | 1.73 | +0.23 |
| Return % | 14.20% | 16.50% | +2.30% |
| Win Rate | 54.0% | 58.0% | +4.0% |
```

---

## Components

### 1. Trade Simulator (`trade_simulator.py`)

Simulates realistic penny stock trading with:

- **Adaptive slippage model**: 2-15% based on price level, volume, and volatility
  - Sub-$1 stocks: ~5% slippage
  - $1-$2 stocks: ~4% slippage
  - $2-$5 stocks: ~3% slippage
  - $5+ stocks: ~2% slippage

- **Volume constraints**: Cannot trade more than 5% of daily volume (configurable)
- **Market impact**: Larger orders = higher slippage
- **Commission fees**: Configurable (default: $0 for modern brokers)

**Example:**
```python
from catalyst_bot.backtesting import PennyStockTradeSimulator

simulator = PennyStockTradeSimulator(
    initial_capital=10000.0,
    position_size_pct=0.10,  # 10% per trade
    max_daily_volume_pct=0.05,  # Max 5% of daily volume
    slippage_model="adaptive"
)

# Execute a trade
result = simulator.execute_trade(
    ticker="AAPL",
    action="buy",
    price=2.50,
    volume=100000,
    timestamp=1234567890,
    available_capital=10000.0
)

print(f"Executed: {result.executed}")
print(f"Shares: {result.shares}")
print(f"Fill Price: ${result.fill_price:.2f}")
print(f"Slippage: {result.slippage_pct:.2f}%")
```

### 2. Portfolio Manager (`portfolio.py`)

Tracks positions, P&L, and equity curve:

```python
from catalyst_bot.backtesting import Portfolio

portfolio = Portfolio(initial_capital=10000.0)

# Open position
portfolio.open_position(
    ticker="AAPL",
    shares=100,
    entry_price=2.50,
    entry_time=1234567890,
    alert_data={"score": 0.5, "catalyst_type": "fda_approval"}
)

# Close position
trade = portfolio.close_position(
    ticker="AAPL",
    exit_price=3.00,
    exit_time=1234600000,
    exit_reason="take_profit"
)

print(f"Profit: ${trade.profit:.2f}")
print(f"Profit %: {trade.profit_pct:.2f}%")
print(f"Hold Time: {trade.hold_time_hours:.1f} hours")

# Get performance metrics
metrics = portfolio.get_performance_metrics()
print(f"Total Return: {metrics['total_return_pct']:.2f}%")
print(f"Win Rate: {metrics['win_rate']:.1f}%")
```

### 3. Backtest Engine (`engine.py`)

Main engine that replays historical alerts:

```python
from catalyst_bot.backtesting import BacktestEngine

engine = BacktestEngine(
    start_date="2025-08-01",
    end_date="2025-09-01",
    initial_capital=10000.0,
    strategy_params={
        "min_score": 0.30,
        "take_profit_pct": 0.20,
        "stop_loss_pct": 0.10,
        "max_hold_hours": 24
    }
)

results = engine.run_backtest()

print(f"Sharpe Ratio: {results['metrics']['sharpe_ratio']:.2f}")
print(f"Win Rate: {results['metrics']['win_rate']:.1f}%")
print(f"Total Trades: {results['metrics']['total_trades']}")
```

### 4. Analytics (`analytics.py`)

Performance metric calculations:

```python
from catalyst_bot.backtesting import (
    calculate_sharpe_ratio,
    calculate_max_drawdown,
    calculate_win_rate,
    calculate_profit_factor
)

# Sharpe ratio
returns = [0.01, 0.02, -0.01, 0.03, 0.01]
sharpe = calculate_sharpe_ratio(returns)
print(f"Sharpe Ratio: {sharpe:.2f}")

# Max drawdown
equity_curve = [(1000, 10000), (2000, 12000), (3000, 9000)]
dd = calculate_max_drawdown(equity_curve)
print(f"Max Drawdown: {dd['max_drawdown_pct']:.2f}%")
```

### 5. Monte Carlo Simulator (`monte_carlo.py`)

Parameter sensitivity analysis:

```python
from catalyst_bot.backtesting.monte_carlo import MonteCarloSimulator

simulator = MonteCarloSimulator(
    start_date="2025-08-01",
    end_date="2025-09-01",
    initial_capital=10000.0
)

# Test different MIN_SCORE values
results = simulator.run_parameter_sweep(
    parameter="min_score",
    values=[0.20, 0.25, 0.30, 0.35, 0.40],
    num_simulations=100
)

print(f"Optimal Value: {results['optimal_value']}")
print(f"Confidence: {results['confidence']:.2%}")
```

---

## Usage Examples

### Example 1: Custom Date Range Backtest

```bash
python run_backtest.py \
  --start-date 2025-07-01 \
  --end-date 2025-08-31 \
  --capital 25000 \
  --min-score 0.35
```

### Example 2: Aggressive Strategy

```bash
python run_backtest.py \
  --days 60 \
  --take-profit-pct 0.30 \
  --stop-loss-pct 0.15 \
  --max-hold-hours 48
```

### Example 3: Parameter Sweep

Test multiple MIN_SCORE values:

```bash
python run_backtest.py \
  --sweep min_score \
  --values 0.20,0.25,0.30,0.35,0.40 \
  --simulations 50 \
  --days 30
```

### Example 4: Export Trades for Analysis

```bash
python run_backtest.py \
  --days 30 \
  --export trades.csv \
  --output report.md
```

Then analyze in Excel/Python:
```python
import pandas as pd

trades = pd.read_csv("trades.csv")
print(trades.groupby("catalyst_type")["profit_pct"].mean())
```

---

## Configuration

### Environment Variables (.env)

Add to `.env`:

```ini
# Backtesting Configuration (WAVE 1.3)
BACKTEST_INITIAL_CAPITAL=10000.0
BACKTEST_POSITION_SIZE_PCT=0.10
BACKTEST_MAX_VOLUME_PCT=0.05
BACKTEST_SLIPPAGE_MODEL=adaptive  # fixed, adaptive, volume_based
BACKTEST_TAKE_PROFIT_PCT=0.20
BACKTEST_STOP_LOSS_PCT=0.10
BACKTEST_MAX_HOLD_HOURS=24
BACKTEST_RISK_FREE_RATE=0.02
```

### Python API Configuration

```python
from catalyst_bot.config import get_settings

settings = get_settings()

# Access backtest settings
print(settings.backtest_initial_capital)
print(settings.backtest_position_size_pct)
print(settings.backtest_slippage_model)
```

---

## Understanding Reports

### Executive Summary

```markdown
## Executive Summary

- **Total Return:** 15.50%
- **Sharpe Ratio:** 1.80
- **Win Rate:** 58.0%
- **Max Drawdown:** 8.50%
- **Profit Factor:** 2.10
- **Total Trades:** 50
```

**Interpretation:**
- **Total Return:** Portfolio grew by 15.5% over backtest period
- **Sharpe Ratio:** 1.8 = Good risk-adjusted returns (>1.0 is good, >2.0 is excellent)
- **Win Rate:** 58% of trades were profitable
- **Max Drawdown:** Portfolio fell at most 8.5% from peak
- **Profit Factor:** 2.1 = Gross profits are 2.1x gross losses (>2.0 is very good)

### Performance by Catalyst

```markdown
| Catalyst | Trades | Win Rate | Avg Return | Profit Factor |
|----------|--------|----------|------------|---------------|
| fda_approval | 15 | 73.3% | +18.5% | 3.2 |
| earnings | 20 | 55.0% | +12.2% | 1.8 |
| partnership | 10 | 40.0% | +5.1% | 1.1 |
| sec_filing | 5 | 60.0% | +8.3% | 2.0 |
```

**Interpretation:**
- FDA approvals have highest win rate (73%) and best returns
- Partnerships are weakest performer (40% win rate)
- Consider increasing weight on FDA alerts, reducing partnership alerts

### Recommendations

The report auto-generates actionable recommendations:

**Example:**
```markdown
## Recommendations

- **Low Profit Factor:** Average wins are not significantly larger than average losses.
  Consider adjusting `take_profit_pct` to 0.25 and `stop_loss_pct` to 0.08 to improve win/loss ratio.

- **High Win Rate:** Good signal quality. Consider increasing position size from 10% to 12%
  or reducing `min_score` to 0.23 to capture more opportunities.
```

---

## Parameter Optimization

### 1. Single Parameter Optimization

Find optimal MIN_SCORE:

```bash
python run_backtest.py \
  --sweep min_score \
  --values 0.15,0.20,0.25,0.30,0.35,0.40 \
  --simulations 100 \
  --days 60
```

**Output:**
```
| Value | Avg Sharpe | Avg Return | Avg Win Rate | Std Dev |
|-------|------------|------------|--------------|---------|
| 0.15 | 1.20 | 18.50% | 48.0% | 5.2 |
| 0.20 | 1.45 | 16.20% | 52.0% | 4.1 |
| 0.25 | 1.65 | 14.80% | 56.0% | 3.5 |
| 0.30 | 1.80 | 15.20% | 58.0% | 3.2 |  ← OPTIMAL
| 0.35 | 1.70 | 13.50% | 62.0% | 2.8 |
| 0.40 | 1.50 | 11.20% | 65.0% | 2.5 |
```

**Insight:** 0.30 maximizes Sharpe ratio (best risk-adjusted return)

### 2. Multi-Parameter Optimization

Optimize multiple parameters simultaneously:

```python
from catalyst_bot.backtesting.monte_carlo import MonteCarloSimulator

simulator = MonteCarloSimulator(
    start_date="2025-08-01",
    end_date="2025-09-01"
)

results = simulator.optimize_multi_parameter(
    parameters={
        "min_score": [0.25, 0.30, 0.35],
        "take_profit_pct": [0.15, 0.20, 0.25],
        "stop_loss_pct": [0.08, 0.10, 0.12]
    },
    num_iterations=100,
    optimization_metric="sharpe_ratio"
)

print(f"Optimal Params: {results['optimal_params']}")
print(f"Optimal Sharpe: {results['optimal_metric_value']:.2f}")
```

### 3. Walk-Forward Optimization

Test on different time periods to avoid overfitting:

```bash
# Train on Aug data
python run_backtest.py \
  --start-date 2025-08-01 \
  --end-date 2025-08-31 \
  --sweep min_score \
  --values 0.20,0.25,0.30,0.35

# Validate on Sep data
python run_backtest.py \
  --start-date 2025-09-01 \
  --end-date 2025-09-30 \
  --min-score 0.30  # Use optimal from Aug
```

If performance degrades significantly in Sep, the parameter is overfit to Aug.

---

## Best Practices

### 1. Realistic Expectations

- Penny stocks are volatile: 40-60% win rate is realistic
- Sharpe ratio > 1.5 is good for this asset class
- Expect 10-25% max drawdown
- Don't overfit to historical data

### 2. Sufficient Sample Size

- Minimum 30 trades for reliable statistics
- Minimum 60 days for strategy validation
- Run 100+ simulations for parameter sweeps

### 3. Out-of-Sample Testing

- Train on 70% of data, test on 30%
- Use walk-forward analysis
- Validate on most recent data (more relevant)

### 4. Transaction Costs

- Always include slippage (2-5% minimum for penny stocks)
- Model volume constraints realistically
- Account for bid-ask spread

### 5. Parameter Validation Workflow

1. **Propose Change:** Admin suggests new MIN_SCORE value
2. **Run Validation:** `python run_backtest.py --validate min_score --old 0.25 --new 0.30`
3. **Review Results:** Check recommendation and confidence
4. **Approve/Reject:** Apply change if confidence > 70% and recommendation = APPROVE
5. **Monitor Live:** Track performance after deployment

---

## Troubleshooting

### Issue: "No alerts found"

**Cause:** `events.jsonl` is empty or doesn't exist

**Solution:**
```bash
# Check if file exists
ls data/events.jsonl

# Check if it has data
wc -l data/events.jsonl

# If empty, run bot to generate alerts first
python src/catalyst_bot/runner.py
```

### Issue: "No price data available"

**Cause:** yfinance can't fetch historical data for ticker

**Solutions:**
- Check internet connection
- Verify ticker symbols are correct
- Some delisted stocks won't have data
- Try different date range

### Issue: "Insufficient trades for validation"

**Cause:** Strategy is too restrictive (e.g., min_score too high)

**Solution:**
- Lower min_score threshold
- Increase backtest period (`--days 60`)
- Check alert quality in `events.jsonl`

### Issue: Backtest takes too long

**Causes:**
- Large date range
- Many API calls for price data

**Solutions:**
```bash
# Use shorter periods for testing
python run_backtest.py --days 7

# Reduce simulation count
python run_backtest.py --sweep min_score --values 0.25,0.30 --simulations 10
```

### Issue: Validation confidence is low

**Cause:** High variance in results, insufficient data

**Solutions:**
- Increase backtest period
- Run more simulations
- Check if strategy is stable across different market conditions

---

## Advanced Topics

### Custom Slippage Models

Implement your own slippage function:

```python
from catalyst_bot.backtesting import PennyStockTradeSimulator

class CustomSimulator(PennyStockTradeSimulator):
    def calculate_slippage(self, ticker, price, volume, order_size, direction, volatility_pct=None):
        # Your custom slippage logic
        base_slippage = 0.03  # 3%
        if volume and order_size / volume > 0.10:
            base_slippage *= 2  # Double slippage for large orders

        if direction == "buy":
            return price * (1 + base_slippage)
        else:
            return price * (1 - base_slippage)
```

### Integration with Admin Controls

Automatically validate parameter changes from admin channel:

```python
from catalyst_bot.backtesting.validator import validate_parameter_change

def on_admin_parameter_change(param, old_value, new_value):
    """Auto-validate before applying changes."""

    result = validate_parameter_change(
        param=param,
        old_value=old_value,
        new_value=new_value,
        backtest_days=30
    )

    if result["recommendation"] == "APPROVE" and result["confidence"] > 0.75:
        # Apply change
        apply_config_change(param, new_value)
        send_admin_message(f"✅ {param} changed to {new_value}. Confidence: {result['confidence']:.1%}")
    else:
        send_admin_message(
            f"❌ Change rejected. Recommendation: {result['recommendation']}. "
            f"Reason: {result['reason']}"
        )
```

### Equity Curve Analysis

```python
import matplotlib.pyplot as plt
from datetime import datetime

# Extract equity curve from results
equity_curve = results["equity_curve"]

timestamps = [datetime.fromtimestamp(ts) for ts, _ in equity_curve]
values = [val for _, val in equity_curve]

plt.figure(figsize=(12, 6))
plt.plot(timestamps, values)
plt.title("Portfolio Equity Curve")
plt.xlabel("Date")
plt.ylabel("Portfolio Value ($)")
plt.grid(True)
plt.savefig("equity_curve.png")
```

---

## Next Steps

1. **Run your first backtest** on last 30 days
2. **Review the report** and understand metrics
3. **Validate a parameter change** before going live
4. **Optimize parameters** using parameter sweeps
5. **Integrate with admin controls** for production use

For questions or issues, check the main project README or create an issue on GitHub.
