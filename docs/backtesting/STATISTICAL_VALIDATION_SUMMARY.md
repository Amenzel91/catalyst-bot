# Statistical Significance Testing - Implementation Summary

## Overview
Added rigorous statistical significance testing to the validator module to ensure backtest improvements are real and not due to random chance.

## Changes Made

### 1. New Statistical Functions

#### `calculate_bootstrap_ci(data, statistic_func, confidence_level=0.95)`
- Uses `scipy.stats.bootstrap()` with 10,000 samples
- Calculates 95% confidence intervals for any statistic
- Returns: (point_estimate, lower_bound, upper_bound)

#### `calculate_sharpe_bootstrap_ci(returns, confidence_level=0.95)`
- Specialized bootstrap CI for Sharpe ratio
- Handles annualization correctly
- Returns: (sharpe_ratio, lower_bound, upper_bound)

#### `test_strategy_significance(old_returns, new_returns, old_win_rate, new_win_rate, old_trades, new_trades)`
- Independent t-test for returns comparison (`scipy.stats.ttest_ind`)
- Proportion z-test for win rate comparison
- Sample size validation (minimum 30 trades)
- Returns dictionary with:
  - `returns_pvalue`: p-value for returns difference
  - `returns_significant`: True if p < 0.05
  - `win_rate_pvalue`: p-value for win rate difference
  - `win_rate_significant`: True if p < 0.05
  - `sample_size_adequate`: True if >= 30 trades
  - `warning`: Warning message if issues detected

#### `extract_returns_from_results(results)`
- Helper function to extract individual trade returns from backtest results
- Converts percentage returns to decimals for statistical analysis

#### `_calculate_confidence_intervals(returns, win_rate_pct)`
- Calculates bootstrap CIs for win rate, average return, and Sharpe ratio
- Returns structured dictionary with estimates and confidence bounds

### 2. Updated Validation Functions

#### `validate_parameter_change()`
**New Fields in Results:**
```python
{
    # ... existing fields ...
    'statistical_tests': {
        'returns_pvalue': float,
        'returns_significant': bool,
        'win_rate_pvalue': float,
        'win_rate_significant': bool,
        'sample_size_adequate': bool,
        'warning': str or None
    },
    'confidence_intervals': {
        'win_rate': {'estimate': float, 'ci_lower': float, 'ci_upper': float},
        'avg_return': {'estimate': float, 'ci_lower': float, 'ci_upper': float},
        'sharpe_ratio': {'estimate': float, 'ci_lower': float, 'ci_upper': float}
    }
}
```

#### `validate_multiple_parameters()`
- Now includes same statistical tests and confidence intervals as single parameter validation

#### `_evaluate_change()`
**Enhanced Decision Logic:**
- **Strong improvements**: Confidence boosted 10% if statistically significant
- **Good improvements**: Confidence boosted 10% if statistically significant
- **Moderate improvements**: REQUIRES statistical significance if sample size adequate
  - Downgraded to NEUTRAL if p >= 0.05
- **Degradations**: Confidence boosted 15% if statistically significant
- Warnings appended to reason string when sample size insufficient

### 3. Statistical Constants

```python
MIN_SAMPLE_SIZE = 30        # Minimum trades for reliable t-test
BOOTSTRAP_SAMPLES = 10000   # Number of bootstrap samples
CONFIDENCE_LEVEL = 0.95     # 95% confidence interval
SIGNIFICANCE_THRESHOLD = 0.05  # p < 0.05 for significance
```

## How to Interpret Results

### Bootstrap Confidence Intervals

**Example:**
```python
'win_rate': {
    'estimate': 65.0,
    'ci_lower': 58.3,
    'ci_upper': 71.2
}
```

**Interpretation:**
- Point estimate: 65% win rate
- 95% confident true win rate is between 58.3% and 71.2%
- Narrower intervals = more confidence in estimate
- If CI for returns includes 0, profitability uncertain

### P-Values

**Example:**
```python
'returns_pvalue': 0.023,        # Significant!
'returns_significant': True,
'win_rate_pvalue': 0.087,       # Not significant
'win_rate_significant': False
```

**Interpretation:**
- p < 0.05: Statistically significant difference (95% confidence)
- p >= 0.05: Cannot conclude significant difference exists
- In example: Returns improved significantly, win rate did not

### Sample Size Warnings

**Example:**
```python
'sample_size_adequate': False,
'warning': 'Sample size too small (old=15, new=18). Need >=30 trades.'
```

**Interpretation:**
- Need at least 30 trades per strategy for reliable t-test
- With fewer trades, p-values may be unreliable
- Solution: Use longer backtest period to get more trades

## Usage Example

```python
from src.catalyst_bot.backtesting.validator import validate_parameter_change

# Validate parameter change
result = validate_parameter_change(
    param='take_profit_pct',
    old_value=0.15,
    new_value=0.20,
    backtest_days=60,  # Longer period for more trades
    initial_capital=10000.0
)

# Check recommendation
print(f"Recommendation: {result['recommendation']}")
print(f"Confidence: {result['confidence']:.2%}")

# Check statistical significance
stats = result['statistical_tests']
if stats['returns_significant']:
    print(f"✓ Statistically significant (p={stats['returns_pvalue']:.4f})")
else:
    print(f"✗ Not significant (p={stats['returns_pvalue']:.4f})")

# Check confidence intervals
ci = result['confidence_intervals']
sharpe_ci = ci['sharpe_ratio']
print(f"Sharpe: {sharpe_ci['estimate']:.2f} "
      f"[{sharpe_ci['ci_lower']:.2f}, {sharpe_ci['ci_upper']:.2f}]")
```

## Decision Making Framework

### APPROVE with High Confidence
- Strong/Good improvement + statistically significant
- Confidence automatically boosted when p < 0.05
- Example: Sharpe +25%, p = 0.018 → Confidence 0.95

### NEUTRAL (Downgrade)
- Moderate improvement but NOT statistically significant
- Sample size adequate but p >= 0.05
- Example: Sharpe +8%, p = 0.12 → NEUTRAL instead of APPROVE

### REJECT with High Confidence
- Performance degradation + statistically significant
- Strong evidence change hurts performance
- Example: Return -5%, p = 0.008 → High confidence REJECT

## Best Practices

1. **Use 60+ day backtests** to get adequate sample size (30+ trades)
2. **Pay attention to confidence intervals**, not just point estimates
3. **Require statistical significance** for moderate improvements
4. **If p-value near 0.05**, collect more data before deciding
5. **Wide confidence intervals** = need more data
6. **Always check warnings** about sample size or variance

## Testing

Run the test script to see examples:
```bash
python test_statistical_validation.py
```

This demonstrates:
- Single parameter validation
- Multiple parameter validation
- How to interpret statistical results
- Decision making with statistical tests

## Dependencies

No new dependencies needed! Already in requirements.txt:
- `numpy>=1.26,<2`
- `scipy>=1.11,<2`

## Files Modified

1. `src/catalyst_bot/backtesting/validator.py` - Main implementation
2. `test_statistical_validation.py` - Test script with examples

## Technical Details

### T-Test for Returns
- Uses `scipy.stats.ttest_ind()` for independent samples
- Two-tailed test (detects both improvements and degradations)
- Assumes normal distribution (valid for 30+ samples by CLT)
- Checks for sufficient variance before running test

### Z-Test for Win Rates
- Proportion z-test for comparing two proportions
- Formula: z = (p1 - p2) / SE where SE uses pooled proportion
- Two-tailed p-value from standard normal distribution

### Bootstrap Method
- Percentile method (non-parametric, no distribution assumptions)
- 10,000 resamples with replacement
- Handles small samples better than normal approximation
- Works for any statistic (mean, Sharpe, etc.)

## Future Enhancements

Potential improvements:
1. Effect size calculation (Cohen's d)
2. Multiple testing correction (Bonferroni)
3. Bayesian A/B testing
4. Sequential testing for early stopping
5. Power analysis for sample size planning
