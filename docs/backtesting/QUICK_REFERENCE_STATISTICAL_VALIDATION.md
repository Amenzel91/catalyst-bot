# Statistical Validation Quick Reference

## At a Glance

### What Changed?
The validator now includes **statistical significance testing** to ensure improvements are real, not random chance.

### Key Additions
1. **Bootstrap Confidence Intervals** (95% CI)
2. **P-value Tests** (t-test for returns, z-test for win rates)
3. **Sample Size Validation** (minimum 30 trades recommended)

---

## Quick Decision Guide

### When to APPROVE?
- ✅ Strong improvement (Sharpe +20%) - approved regardless
- ✅ Good improvement (Sharpe +10%) + statistically significant (p < 0.05)
- ✅ Moderate improvement (Sharpe +5%) + statistically significant

### When to REJECT?
- ❌ Degradation + statistically significant (high confidence)
- ❌ Fewer than 10 trades
- ❌ Sample size < 30 and no improvement

### When NEUTRAL?
- ⚠️ Moderate improvement but NOT statistically significant (p > 0.05)
- ⚠️ Minimal change (within ±3% score)

---

## Reading the Results

### Confidence Intervals
```python
'win_rate': {
    'estimate': 65.0,      # Your point estimate
    'ci_lower': 58.3,      # 95% confident it's >= this
    'ci_upper': 71.2       # 95% confident it's <= this
}
```

**What it means:**
- Narrow range (< 10%) = confident in estimate
- Wide range (> 20%) = need more data
- If CI includes 0 for returns = profitability uncertain

### P-Values
```python
'returns_pvalue': 0.023,           # p = 0.023
'returns_significant': True,       # p < 0.05 → significant!
```

**What it means:**
- **p < 0.05**: Statistically significant (95% confidence it's real)
- **p < 0.01**: Highly significant (99% confidence)
- **p > 0.05**: Not significant (could be random chance)

### Sample Size Warning
```python
'sample_size_adequate': False,
'warning': 'Sample size too small (old=15, new=18). Need >=30 trades.'
```

**What to do:**
- ⚠️ Results unreliable with < 30 trades
- 🔧 Solution: Increase `backtest_days` parameter
- 🎯 Target: 30+ trades per strategy

---

## Common Scenarios

### Scenario 1: Strong Improvement
```
Sharpe: +25%, Return: +8%, p = 0.018
→ APPROVE (confidence 0.95)
   "Strong improvement (statistically significant)"
```

### Scenario 2: Marginal Improvement, Not Significant
```
Sharpe: +7%, Return: +2%, p = 0.12
→ NEUTRAL (confidence 0.5)
   "Improvement not statistically significant (p > 0.05)"
```

### Scenario 3: Good Improvement, Significant
```
Sharpe: +15%, Return: +5%, p = 0.031
→ APPROVE (confidence 0.92)
   "Good improvement (statistically significant)"
```

### Scenario 4: Small Sample Size
```
Trades: 18, Sharpe: +10%
→ Warning: "Sample size too small... Need >=30 trades"
   Lower confidence, p-values unreliable
```

---

## Usage Pattern

```python
from src.catalyst_bot.backtesting.validator import validate_parameter_change

# 1. Run validation
result = validate_parameter_change(
    param='take_profit_pct',
    old_value=0.15,
    new_value=0.20,
    backtest_days=60,      # ← Use 60+ days for 30+ trades
    initial_capital=10000.0
)

# 2. Check recommendation
if result['recommendation'] == 'APPROVE':
    print(f"✓ APPROVED (confidence: {result['confidence']:.0%})")
elif result['recommendation'] == 'REJECT':
    print(f"✗ REJECTED: {result['reason']}")
else:
    print(f"⚠ NEUTRAL: Need more data or bigger effect")

# 3. Check statistical significance
stats = result['statistical_tests']
if stats['sample_size_adequate']:
    if stats['returns_significant']:
        print("→ Statistically significant improvement!")
    else:
        print("→ Not significant, could be chance")
else:
    print(f"⚠ Warning: {stats['warning']}")

# 4. Review confidence intervals
ci = result['confidence_intervals']
sharpe = ci['sharpe_ratio']
print(f"Sharpe: {sharpe['estimate']:.2f} "
      f"[{sharpe['ci_lower']:.2f}, {sharpe['ci_upper']:.2f}]")
```

---

## Troubleshooting

### Problem: "Sample size too small"
**Cause:** Fewer than 30 trades per strategy
**Solution:**
- Increase `backtest_days` (try 60 or 90 days)
- Or lower `min_score` threshold to get more trades

### Problem: "Insufficient variance for t-test"
**Cause:** All returns are very similar
**Solution:**
- This is rare, check data quality
- May need different parameter or longer period

### Problem: Wide confidence intervals
**Cause:** High variance in returns or small sample
**Solution:**
- Need more trades for tighter CIs
- Consider if strategy is too volatile

### Problem: p-value close to 0.05 (e.g., 0.048 or 0.052)
**Cause:** Borderline significance
**Solution:**
- Collect more data (longer backtest)
- If critical decision, be conservative
- Consider practical significance vs statistical

---

## Best Practices Checklist

- [ ] Use `backtest_days=60` or more for adequate sample
- [ ] Check `sample_size_adequate` before trusting p-values
- [ ] Look at confidence intervals, not just point estimates
- [ ] Require statistical significance for moderate improvements
- [ ] If p-value near 0.05, collect more data
- [ ] Read warnings carefully
- [ ] Consider both statistical AND practical significance

---

## Statistical Thresholds

| Metric | Threshold | Meaning |
|--------|-----------|---------|
| Minimum trades | 30 | Required for reliable t-test |
| Bootstrap samples | 10,000 | For accurate CI estimation |
| Confidence level | 95% | Standard in finance/trading |
| Significance level | p < 0.05 | 95% confidence it's real |
| Highly significant | p < 0.01 | 99% confidence it's real |

---

## When to Trust Results

✅ **High Confidence**
- Sample size >= 30
- p < 0.05
- Narrow confidence intervals
- Consistent across metrics

⚠️ **Medium Confidence**
- Sample size 20-30
- p between 0.05-0.10
- Moderate CI width

❌ **Low Confidence**
- Sample size < 20
- p > 0.10
- Very wide CIs
- Warnings present

---

## Additional Resources

- Full documentation: `STATISTICAL_VALIDATION_SUMMARY.md`
- Test examples: `test_statistical_validation.py`
- Source code: `src/catalyst_bot/backtesting/validator.py`
