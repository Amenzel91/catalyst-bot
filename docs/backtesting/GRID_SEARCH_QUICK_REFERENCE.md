# Grid Search Quick Reference

## Basic Usage

```python
from catalyst_bot.backtesting.validator import validate_parameter_grid

results = validate_parameter_grid(
    param_ranges={
        'min_score': [0.20, 0.25, 0.30, 0.35],
        'take_profit_pct': [0.15, 0.20, 0.25]
    },
    backtest_days=30
)
```

## Function Signature

```python
validate_parameter_grid(
    param_ranges: Dict[str, List[Any]],
    backtest_days: int = 30,
    initial_capital: float = 10000.0,
    price_data: Optional[Any] = None,
    signal_data: Optional[Any] = None,
) -> Dict
```

## Supported Parameters

| Parameter | Type | Description | Example Values |
|-----------|------|-------------|----------------|
| `min_score` | float | Minimum relevance score (0-1) | `[0.20, 0.25, 0.30]` |
| `min_sentiment` | float | Minimum sentiment (-1 to 1) | `[0.0, 0.1, 0.2]` |
| `take_profit_pct` | float | Take profit threshold | `[0.15, 0.20, 0.25]` |
| `stop_loss_pct` | float | Stop loss threshold | `[0.08, 0.10, 0.12]` |
| `max_hold_hours` | int | Max holding period (hours) | `[12, 18, 24, 36]` |
| `position_size_pct` | float | Position size (% of capital) | `[0.05, 0.10, 0.15]` |

## Return Value

```python
{
    'best_params': {
        'min_score': 0.30,
        'take_profit_pct': 0.20
    },
    'best_metrics': {
        'sharpe_ratio': 2.45,
        'sortino_ratio': 3.12,
        'total_return': 0.18,
        'total_trades': 42,
        'win_rate': 0.67
    },
    'all_results': DataFrame,  # All combinations sorted by Sharpe
    'n_combinations': 12,
    'execution_time_sec': 3.5,
    'speedup_estimate': 34.0
}
```

## Common Use Cases

### 1. Optimize Entry Thresholds
```python
results = validate_parameter_grid(
    param_ranges={
        'min_score': [0.20, 0.25, 0.30, 0.35, 0.40],
        'min_sentiment': [0.0, 0.1, 0.2]
    },
    backtest_days=30
)
# Tests 15 combinations (5 × 3)
```

### 2. Optimize Exit Strategy
```python
results = validate_parameter_grid(
    param_ranges={
        'take_profit_pct': [0.10, 0.15, 0.20, 0.25],
        'stop_loss_pct': [0.05, 0.08, 0.10, 0.12]
    },
    backtest_days=60
)
# Tests 16 combinations (4 × 4)
```

### 3. Full Strategy Optimization
```python
results = validate_parameter_grid(
    param_ranges={
        'min_score': [0.25, 0.30, 0.35],
        'take_profit_pct': [0.15, 0.20, 0.25],
        'stop_loss_pct': [0.08, 0.10],
        'max_hold_hours': [12, 24, 36]
    },
    backtest_days=45
)
# Tests 54 combinations (3 × 3 × 2 × 3)
```

## Accessing Results

### Best Parameters
```python
best = results['best_params']
print(f"Min score: {best['min_score']}")
print(f"Take profit: {best['take_profit_pct']:.0%}")
```

### Best Metrics
```python
metrics = results['best_metrics']
print(f"Sharpe: {metrics['sharpe_ratio']:.2f}")
print(f"Win rate: {metrics['win_rate']:.1%}")
print(f"Total trades: {metrics['total_trades']}")
```

### View All Results
```python
df = results['all_results']
print(df.head(10))  # Top 10 combinations
print(df.tail(10))  # Bottom 10 combinations

# Filter by criteria
good_combos = df[df['sharpe_ratio'] > 2.0]
```

### Performance Stats
```python
print(f"Tested {results['n_combinations']} combinations")
print(f"Time: {results['execution_time_sec']:.2f}s")
print(f"Speedup: ~{results['speedup_estimate']:.0f}x")
```

## Recommended Workflow

### Step 1: Quick Exploration (Grid Search)
```python
# Test many combinations quickly
grid_results = validate_parameter_grid(
    param_ranges={
        'min_score': [0.20, 0.25, 0.30, 0.35],
        'take_profit_pct': [0.15, 0.20, 0.25]
    },
    backtest_days=30
)
```

### Step 2: Statistical Validation
```python
from catalyst_bot.backtesting.validator import validate_parameter_change

# Validate best candidate with rigorous testing
validation = validate_parameter_change(
    param='min_score',
    old_value=0.25,
    new_value=grid_results['best_params']['min_score'],
    backtest_days=60
)

if validation['recommendation'] == 'APPROVE':
    print(f"Deploy new value: {validation['new_value']}")
```

## Performance Guide

### Execution Time Estimates

| Combinations | Time | Speedup |
|--------------|------|---------|
| 10 | 1-2s | ~10x |
| 25 | 2-3s | ~20x |
| 50 | 3-5s | ~30x |
| 100 | 5-10s | ~40x |
| 200 | 10-20s | ~50x |

### Scaling Behavior
- Sub-linear: 100 combos ~2-3x slower than 10 (not 10x)
- Memory efficient: Shared price data across all combinations
- Parallel execution: All combinations tested simultaneously

## Best Practices

### 1. Start Broad, Refine Narrow
```python
# Round 1: Wide range
results1 = validate_parameter_grid(
    param_ranges={'min_score': [0.15, 0.20, 0.25, 0.30, 0.35, 0.40]},
    backtest_days=30
)

# Round 2: Narrow around best
best_score = results1['best_params']['min_score']
results2 = validate_parameter_grid(
    param_ranges={
        'min_score': [best_score - 0.02, best_score, best_score + 0.02]
    },
    backtest_days=60
)
```

### 2. Use Adequate Backtest Period
- **7-14 days:** Quick exploration only
- **30 days:** Standard minimum
- **60+ days:** Production validation

### 3. Check Sample Size
```python
# Ensure enough trades for reliable results
if results['best_metrics']['total_trades'] < 30:
    print("Warning: Sample size too small!")
    print("Consider longer backtest period or wider parameters")
```

### 4. Validate Top Candidates
```python
# Don't just use the best - validate statistically
df = results['all_results']
top_5 = df.head(5)

for idx, row in top_5.iterrows():
    print(f"Validating combination {idx}...")
    # Run validate_parameter_change() for each
```

## Common Pitfalls

### 1. Overfitting
**Problem:** Too many parameters or fine-grained ranges
**Solution:** Limit to 3-4 key parameters, use reasonable step sizes

```python
# Bad: Too fine-grained
param_ranges={'min_score': [0.20, 0.21, 0.22, 0.23, ...]}  # Too many!

# Good: Reasonable steps
param_ranges={'min_score': [0.20, 0.25, 0.30, 0.35]}  # Good spacing
```

### 2. Insufficient Data
**Problem:** Short backtest period with few trades
**Solution:** Use longer periods or check trade count

```python
if results['best_metrics']['total_trades'] < 30:
    # Extend backtest period
    results = validate_parameter_grid(..., backtest_days=60)
```

### 3. Ignoring Statistical Validation
**Problem:** Deploying based on grid search alone
**Solution:** Always validate top candidates

```python
# Don't do this:
best_params = results['best_params']  # Deploy immediately

# Do this:
best_params = results['best_params']
validation = validate_parameter_change(...)  # Validate first
if validation['recommendation'] == 'APPROVE':
    # Then deploy
```

## Troubleshooting

### ImportError: VectorBT not available
```bash
pip install vectorbt
```

### No data available warning
- Check `data/events.jsonl` exists
- Verify date range has events
- Ensure tickers are present

### Grid search takes too long
- Reduce parameter combinations
- Shorten backtest period
- Check for data loading issues

## Integration with Existing Tools

### With validate_parameter_change()
```python
# Grid search for exploration
grid = validate_parameter_grid(...)

# Statistical validation for confirmation
validation = validate_parameter_change(
    param='min_score',
    old_value=0.25,
    new_value=grid['best_params']['min_score'],
    backtest_days=60
)
```

### With BacktestEngine
```python
# Find best params with grid search
results = validate_parameter_grid(...)
best_params = results['best_params']

# Run detailed backtest with best params
from catalyst_bot.backtesting.engine import BacktestEngine
engine = BacktestEngine(
    start_date='2024-01-01',
    end_date='2024-12-31',
    strategy_params=best_params
)
detailed_results = engine.run_backtest()
```

## Additional Resources

- Full documentation: `GRID_SEARCH_INTEGRATION_SUMMARY.md`
- Examples: `examples/grid_search_example.py`
- Tests: `tests/test_parameter_grid_search.py`
- Module docstring: See `validator.py` header
