# Robust Statistics Quick Reference

## When to Use (Decision Tree)

```
Do you have penny stock backtest data with potential extreme outliers?
│
├─ YES → Use ROBUST statistics (this guide)
│
└─ NO  → Traditional statistics are fine
```

## The Four Essential Functions

### 1. Winsorize - Clip Outliers
```python
from catalyst_bot.backtesting.validator import winsorize

# Clip at 1st/99th percentile (default)
winsorized = winsorize(returns, limits=(0.01, 0.01))

# Use for: means, std devs, correlations
mean = np.mean(winsorized)
std = np.std(winsorized, ddof=1)
```

### 2. Trimmed Mean - Typical Performance
```python
from catalyst_bot.backtesting.validator import trimmed_mean

# Remove top/bottom 5% (default)
typical = trimmed_mean(returns, proportiontocut=0.05)

# Use for: summary statistics, reports
print(f"Typical return: {typical:.2%}")
```

### 3. MAD - Robust Risk
```python
from catalyst_bot.backtesting.validator import median_absolute_deviation

# Calculate robust standard deviation
risk = median_absolute_deviation(returns)

# Use for: risk metrics, Sharpe ratio
robust_sharpe = (np.median(returns) / risk) * np.sqrt(252)
```

### 4. Robust Z-Score - Find Outliers
```python
from catalyst_bot.backtesting.validator import robust_zscore

# Detect outliers
z_scores = robust_zscore(returns)
outliers = np.where(np.abs(z_scores) > 3)[0]

# Use for: flagging suspicious trades
print(f"Found {len(outliers)} outliers")
```

## Complete Workflow (Copy-Paste Template)

```python
import numpy as np
from catalyst_bot.backtesting.validator import (
    winsorize,
    trimmed_mean,
    median_absolute_deviation,
    robust_zscore
)

# Your backtest returns (as decimals: 0.05 = 5%)
returns = np.array([...])  # 500+ trades

# Step 1: Detect outliers
z_scores = robust_zscore(returns)
outliers = np.abs(z_scores) > 3
outlier_count = np.sum(outliers)

if outlier_count > 0:
    print(f"WARNING: {outlier_count} outliers detected ({outlier_count/len(returns):.1%})")
    print("Using robust statistics...")

# Step 2: Calculate robust statistics
typical_return = trimmed_mean(returns, proportiontocut=0.05)
robust_risk = median_absolute_deviation(returns)
robust_sharpe = (np.median(returns) / robust_risk) * np.sqrt(252)

# Step 3: Compare with traditional (for transparency)
traditional_mean = np.mean(returns)
traditional_std = np.std(returns, ddof=1)
traditional_sharpe = (traditional_mean / traditional_std) * np.sqrt(252)

# Step 4: Report results
print("\nTraditional Statistics:")
print(f"  Mean: {traditional_mean:.2%}, Sharpe: {traditional_sharpe:.2f}")
print("\nRobust Statistics (RECOMMENDED):")
print(f"  Typical Return: {typical_return:.2%}")
print(f"  Robust Risk: {robust_risk:.2%}")
print(f"  Robust Sharpe: {robust_sharpe:.2f}")

# Step 5: Robust confidence intervals
from scipy import stats as scipy_stats

winsorized = winsorize(returns, limits=(0.01, 0.01))
ci_result = scipy_stats.bootstrap(
    (winsorized,),
    np.mean,
    n_resamples=10000,
    confidence_level=0.95,
    random_state=42
)

print(f"\nRobust 95% CI: [{ci_result.confidence_interval.low:.2%}, "
      f"{ci_result.confidence_interval.high:.2%}]")
```

## Cheat Sheet

| Statistic | Traditional | Robust Alternative | When to Use Robust |
|-----------|-------------|-------------------|-------------------|
| **Central Tendency** | `np.mean()` | `trimmed_mean()` | Outliers present |
| **Spread/Risk** | `np.std()` | `median_absolute_deviation()` | Outliers present |
| **Sharpe Ratio** | mean/std | median/MAD | Outliers present |
| **Outlier Detection** | (X-mean)/std | `robust_zscore()` | Always for detection |
| **Pre-processing** | None | `winsorize()` | Before calculating stats |

## Common Thresholds

### Winsorization
- **Conservative**: `limits=(0.01, 0.01)` - clips 1% from each tail
- **Moderate**: `limits=(0.05, 0.05)` - clips 5% from each tail
- **Aggressive**: `limits=(0.10, 0.10)` - clips 10% from each tail

### Trimmed Mean
- **Light trim**: `proportiontocut=0.05` - removes 5% from each tail (10% total)
- **Moderate trim**: `proportiontocut=0.10` - removes 10% from each tail (20% total)
- **Heavy trim**: `proportiontocut=0.20` - removes 20% from each tail (40% total)

### Outlier Detection
- **|z_robust| > 3**: Strong outlier (flag for review)
- **|z_robust| > 4**: Very strong outlier (investigate)
- **|z_robust| > 5**: Extreme outlier (data quality issue?)

### Outlier Indicator
- **MAD/StdDev < 0.67**: Significant outliers present, use robust stats
- **MAD/StdDev ≈ 1.0**: Data approximately normal, traditional stats OK

## One-Liners

```python
# Robust mean
robust_mean = trimmed_mean(returns, 0.05)

# Robust std dev
robust_std = median_absolute_deviation(returns)

# Robust Sharpe
robust_sharpe = (np.median(returns) / median_absolute_deviation(returns)) * np.sqrt(252)

# Count outliers
outlier_count = np.sum(np.abs(robust_zscore(returns)) > 3)

# Winsorized mean
winsorized_mean = np.mean(winsorize(returns, (0.01, 0.01)))
```

## Real-World Example

```python
# 2-year penny stock backtest: 520 trades
returns = [0.03, 0.05, ..., 3.5, ...]  # includes 350% gain outlier

# ❌ WRONG: Traditional statistics
mean = np.mean(returns)  # 8.2% (way too high!)
std = np.std(returns)    # 42% (meaningless!)

# ✅ RIGHT: Robust statistics
typical = trimmed_mean(returns, 0.05)  # 2.8% (realistic)
risk = median_absolute_deviation(returns)  # 12% (stable)
```

## FAQs

**Q: When should I use robust statistics?**
A: Whenever your data has outliers. For penny stocks, always use robust stats.

**Q: Which is better: winsorize or trimmed_mean?**
A: Winsorize preserves sample size (better for small samples). Trimmed mean completely removes outliers (better for reports).

**Q: Can I use robust stats for intraday trading?**
A: Yes! They work for any data with outliers, regardless of timeframe.

**Q: What if I have no outliers?**
A: Robust stats still work fine, they'll give similar results to traditional stats.

**Q: Should I report both traditional and robust?**
A: Yes, for transparency. Show both, but emphasize robust as more reliable.

## File Locations

- **Implementation**: `C:\Users\menza\OneDrive\Desktop\Catalyst-Bot\catalyst-bot\src\catalyst_bot\backtesting\validator.py`
- **Tests**: `C:\Users\menza\OneDrive\Desktop\Catalyst-Bot\catalyst-bot\tests\test_robust_statistics.py`
- **Demo**: `C:\Users\menza\OneDrive\Desktop\Catalyst-Bot\catalyst-bot\examples\robust_statistics_demo.py`
- **Full Docs**: `C:\Users\menza\OneDrive\Desktop\Catalyst-Bot\catalyst-bot\ROBUST_STATISTICS_IMPLEMENTATION.md`

## Run Tests

```bash
cd C:\Users\menza\OneDrive\Desktop\Catalyst-Bot\catalyst-bot
python -m pytest tests/test_robust_statistics.py -v
```

## Run Demo

```bash
cd C:\Users\menza\OneDrive\Desktop\Catalyst-Bot\catalyst-bot
python examples/robust_statistics_demo.py
```

---

**Remember**: Outliers in penny stocks are REAL trades, not errors. Robust statistics help you understand *typical* performance while acknowledging occasional extreme outcomes.
