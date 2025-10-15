# Backtest Examples

Real-world examples and use cases for the Catalyst Bot backtesting engine.

---

## Example 1: Basic 30-Day Performance Check

**Scenario:** You want to see how the bot would have performed over the last month with current settings.

**Command:**
```bash
python run_backtest.py --days 30
```

**Sample Output:**
```
Running backtest...
Date range: 2025-09-06 to 2025-10-06
Initial capital: $10,000.00

=== Backtest Results ===

Total Return: 18.75%
Sharpe Ratio: 2.15
Win Rate: 62.0%
Max Drawdown: 6.30%
Profit Factor: 2.45
Total Trades: 45
Winning Trades: 28
Losing Trades: 17
Avg Hold Time: 16.2 hours
```

**Analysis:**
- ✅ Positive 18.75% return
- ✅ Excellent Sharpe ratio (2.15 > 2.0)
- ✅ Good win rate (62%)
- ✅ Low drawdown (6.3% < 10%)
- **Conclusion:** Strategy is performing well

---

## Example 2: Testing Higher Quality Filter

**Scenario:** You think the bot is sending too many low-quality alerts. Test what happens if you increase MIN_SCORE from 0.25 to 0.35.

**Command:**
```bash
python run_backtest.py --validate min_score --old 0.25 --new 0.35 --days 30
```

**Sample Output:**
```
Validating parameter change: min_score
Old value: 0.25
New value: 0.35
Backtest period: 30 days

=== Validation Results ===

Recommendation: APPROVE
Confidence: 88%
Reason: Strong improvement: Sharpe +28.5%, Return +3.2%, Win Rate +8.0%

| Metric | Old Value | New Value | Change |
|--------|-----------|-----------|--------|
| Sharpe Ratio | 1.65 | 2.12 | +0.47 |
| Return % | 18.75% | 21.95% | +3.20% |
| Win Rate | 62.0% | 70.0% | +8.0% |
| Max Drawdown | 6.30% | 4.80% | -1.50% |
| Total Trades | 45 | 28 | -17 |
```

**Analysis:**
- ✅ Higher score threshold = fewer but higher quality trades
- ✅ Win rate jumped from 62% to 70%
- ✅ Better risk-adjusted returns (Sharpe +28.5%)
- ✅ Lower drawdown
- ⚠️ Fewer trades (45 → 28) means less opportunity
- **Conclusion:** APPROVE change, quality > quantity

---

## Example 3: Optimizing Take Profit Target

**Scenario:** Current take profit is 20%. Test if 15% or 25% would perform better.

**Command:**
```bash
python run_backtest.py --sweep take_profit_pct --values 0.15,0.20,0.25,0.30 --simulations 20 --days 60
```

**Sample Output:**
```
Running parameter sweep: take_profit_pct
Values: [0.15, 0.2, 0.25, 0.3]
Simulations per value: 20
Date range: 2025-08-07 to 2025-10-06

=== Parameter Sweep Results ===

Parameter: take_profit_pct
Optimal Value: 0.25
Confidence: 82%

| Value | Avg Sharpe | Avg Return | Avg Win Rate | Std Dev |
|-------|------------|------------|--------------|---------|
| 0.15 | 1.55 | 22.30% | 68.5% | 4.2 |
| 0.20 | 1.78 | 18.75% | 62.0% | 3.5 |
| 0.25 | 1.92 | 19.20% | 58.5% | 3.1 |  ← OPTIMAL
| 0.30 | 1.65 | 16.40% | 54.0% | 3.8 |
```

**Analysis:**
- 0.15 (15%): Highest return but lower Sharpe (more variance)
- 0.20 (20%): Current setting - balanced
- 0.25 (25%): **Optimal** - Best Sharpe ratio (most consistent)
- 0.30 (30%): Too conservative, missing opportunities
- **Conclusion:** Change to 25% take profit for better risk-adjusted returns

---

## Example 4: Comparing Strategies by Catalyst Type

**Scenario:** Generate a report showing which catalyst types perform best.

**Command:**
```bash
python run_backtest.py --days 60 --format markdown --output catalyst_analysis.md
```

**Report Excerpt:**
```markdown
## Performance by Catalyst Type

| Catalyst | Trades | Win Rate | Avg Return | Profit Factor | Avg Hold (hrs) |
|----------|--------|----------|------------|---------------|----------------|
| fda_approval | 22 | 81.8% | +24.5% | 4.2 | 14.5 |
| clinical_trial | 18 | 72.2% | +18.3% | 3.1 | 16.8 |
| earnings | 35 | 51.4% | +11.2% | 1.6 | 22.1 |
| partnership | 15 | 60.0% | +14.7% | 2.0 | 19.3 |
| sec_filing | 28 | 46.4% | +8.5% | 1.3 | 18.7 |
```

**Analysis:**
- **FDA approvals:** Best performer (82% win rate, 4.2 profit factor)
- **Clinical trials:** Second best (72% win rate)
- **Earnings:** Mediocre (51% win rate, barely profitable)
- **SEC filings:** Worst performer (46% win rate)

**Recommendations:**
1. Increase position size on FDA approval alerts
2. Consider filtering out SEC filing alerts (unless high score)
3. Add keyword weighting to favor biotech catalysts

---

## Example 5: Testing Aggressive vs Conservative Strategy

### Conservative Strategy
```bash
python run_backtest.py \
  --days 60 \
  --min-score 0.40 \
  --take-profit-pct 0.15 \
  --stop-loss-pct 0.08 \
  --max-hold-hours 12
```

**Results:**
- Total Trades: 18
- Win Rate: 77.8%
- Total Return: 12.3%
- Sharpe Ratio: 2.35
- Max Drawdown: 3.2%

**Profile:** Low risk, high win rate, fewer opportunities

### Aggressive Strategy
```bash
python run_backtest.py \
  --days 60 \
  --min-score 0.20 \
  --take-profit-pct 0.30 \
  --stop-loss-pct 0.15 \
  --max-hold-hours 48
```

**Results:**
- Total Trades: 68
- Win Rate: 48.5%
- Total Return: 24.8%
- Sharpe Ratio: 1.45
- Max Drawdown: 14.5%

**Profile:** Higher risk, higher returns, more volatility

**Comparison:**
| Metric | Conservative | Aggressive | Winner |
|--------|-------------|------------|--------|
| Total Return | 12.3% | 24.8% | Aggressive |
| Sharpe Ratio | 2.35 | 1.45 | Conservative |
| Win Rate | 77.8% | 48.5% | Conservative |
| Max Drawdown | 3.2% | 14.5% | Conservative |
| Total Trades | 18 | 68 | Aggressive |

**Conclusion:** Choose based on risk tolerance. Conservative = better risk-adjusted. Aggressive = higher absolute returns.

---

## Example 6: Walk-Forward Validation

**Scenario:** Avoid overfitting by validating strategy on different time periods.

### Step 1: Optimize on August Data
```bash
python run_backtest.py \
  --start-date 2025-08-01 \
  --end-date 2025-08-31 \
  --sweep min_score \
  --values 0.20,0.25,0.30,0.35,0.40 \
  --simulations 50
```

**Result:** Optimal MIN_SCORE = 0.30 (Sharpe: 1.95)

### Step 2: Validate on September Data
```bash
python run_backtest.py \
  --start-date 2025-09-01 \
  --end-date 2025-09-30 \
  --min-score 0.30
```

**Result:** Sharpe: 1.82 (within 10% of training period)

### Step 3: Validate on October Data
```bash
python run_backtest.py \
  --start-date 2025-10-01 \
  --end-date 2025-10-06 \
  --min-score 0.30
```

**Result:** Sharpe: 1.76 (consistent)

**Conclusion:** MIN_SCORE = 0.30 is robust across different market conditions (not overfit).

---

## Example 7: Export and Analyze Trades in Python

```bash
python run_backtest.py --days 60 --export trades.csv
```

**Python Analysis:**
```python
import pandas as pd
import matplotlib.pyplot as plt

# Load trades
trades = pd.read_csv("trades.csv")

# Best tickers
best_tickers = trades.groupby("ticker")["profit_pct"].mean().sort_values(ascending=False).head(10)
print("Best Performing Tickers:")
print(best_tickers)

# Profit by hour of day
trades["entry_hour"] = pd.to_datetime(trades["entry_time"]).dt.hour
hourly_profit = trades.groupby("entry_hour")["profit_pct"].mean()

plt.figure(figsize=(10, 6))
hourly_profit.plot(kind="bar")
plt.title("Average Profit % by Entry Hour")
plt.xlabel("Hour of Day (UTC)")
plt.ylabel("Avg Profit %")
plt.grid(True)
plt.savefig("profit_by_hour.png")
print("Chart saved to profit_by_hour.png")

# Win rate by catalyst
catalyst_stats = trades.groupby("catalyst_type").agg({
    "profit_pct": ["mean", "count"],
    "ticker": lambda x: (trades.loc[x.index, "profit"] > 0).sum()
})
catalyst_stats.columns = ["avg_profit_pct", "total_trades", "wins"]
catalyst_stats["win_rate"] = catalyst_stats["wins"] / catalyst_stats["total_trades"]
print("\nCatalyst Performance:")
print(catalyst_stats)
```

**Output:**
```
Best Performing Tickers:
ABCD    +48.2%
EFGH    +35.7%
IJKL    +28.3%
...

Catalyst Performance:
                avg_profit_pct  total_trades  wins  win_rate
fda_approval          24.5            22      18     0.818
clinical_trial        18.3            18      13     0.722
earnings              11.2            35      18     0.514
...
```

---

## Example 8: Multi-Parameter Optimization

**Scenario:** Optimize multiple parameters simultaneously to find best combination.

**Python Script (`optimize.py`):**
```python
from catalyst_bot.backtesting.monte_carlo import MonteCarloSimulator

simulator = MonteCarloSimulator(
    start_date="2025-08-01",
    end_date="2025-10-06",
    initial_capital=10000.0
)

results = simulator.optimize_multi_parameter(
    parameters={
        "min_score": [0.25, 0.30, 0.35],
        "take_profit_pct": [0.15, 0.20, 0.25],
        "stop_loss_pct": [0.08, 0.10, 0.12],
        "max_hold_hours": [12, 24, 36]
    },
    num_iterations=81,  # 3^4 = 81 combinations
    optimization_metric="sharpe_ratio"
)

print(f"Optimal Parameters: {results['optimal_params']}")
print(f"Optimal Sharpe Ratio: {results['optimal_metric_value']:.2f}")

# Show top 5 combinations
sorted_results = sorted(results["all_results"], key=lambda x: x["metric_value"], reverse=True)[:5]
print("\nTop 5 Combinations:")
for i, r in enumerate(sorted_results, 1):
    print(f"{i}. {r['params']} → Sharpe: {r['sharpe_ratio']:.2f}, Return: {r['total_return_pct']:.2f}%")
```

**Output:**
```
Optimal Parameters: {'min_score': 0.30, 'take_profit_pct': 0.25, 'stop_loss_pct': 0.10, 'max_hold_hours': 24}
Optimal Sharpe Ratio: 2.18

Top 5 Combinations:
1. {'min_score': 0.30, 'take_profit_pct': 0.25, 'stop_loss_pct': 0.10, 'max_hold_hours': 24} → Sharpe: 2.18, Return: 21.3%
2. {'min_score': 0.35, 'take_profit_pct': 0.20, 'stop_loss_pct': 0.08, 'max_hold_hours': 24} → Sharpe: 2.12, Return: 18.7%
3. {'min_score': 0.30, 'take_profit_pct': 0.20, 'stop_loss_pct': 0.10, 'max_hold_hours': 24} → Sharpe: 2.05, Return: 19.5%
4. {'min_score': 0.25, 'take_profit_pct': 0.25, 'stop_loss_pct': 0.10, 'max_hold_hours': 36} → Sharpe: 1.98, Return: 22.8%
5. {'min_score': 0.35, 'take_profit_pct': 0.25, 'stop_loss_pct': 0.08, 'max_hold_hours': 12} → Sharpe: 1.95, Return: 16.2%
```

---

## Example 9: Seasonal Performance Analysis

**Scenario:** Check if strategy performs better in certain months.

**Commands:**
```bash
# January
python run_backtest.py --start-date 2025-01-01 --end-date 2025-01-31 --export jan.csv

# February
python run_backtest.py --start-date 2025-02-01 --end-date 2025-02-28 --export feb.csv

# ... repeat for other months
```

**Python Analysis:**
```python
import pandas as pd

months = ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep"]
monthly_returns = []

for month in months:
    df = pd.read_csv(f"{month}.csv")
    total_return = df["profit"].sum() / 10000  # Assuming $10k capital
    monthly_returns.append((month.upper(), total_return * 100))

monthly_df = pd.DataFrame(monthly_returns, columns=["Month", "Return %"])
print(monthly_df)
print(f"\nBest Month: {monthly_df.loc[monthly_df['Return %'].idxmax(), 'Month']}")
print(f"Worst Month: {monthly_df.loc[monthly_df['Return %'].idxmin(), 'Month']}")
```

---

## Example 10: Real-Time Validation Before Live Deployment

**Scenario:** Before deploying a new MIN_SCORE of 0.35, validate with 90 days of data.

**Step 1: Full Validation**
```bash
python run_backtest.py \
  --validate min_score \
  --old 0.25 \
  --new 0.35 \
  --days 90 \
  --output validation_report.json
```

**Step 2: Review JSON Report**
```python
import json

with open("validation_report.json") as f:
    result = json.load(f)

if result["recommendation"] == "APPROVE" and result["confidence"] > 0.80:
    print("✅ APPROVED: Safe to deploy")
    print(f"Confidence: {result['confidence']:.1%}")
    print(f"Expected improvement: {result['new_sharpe'] - result['old_sharpe']:+.2f} Sharpe")

    # Apply to production config
    update_config("MIN_SCORE", 0.35)
else:
    print("❌ REJECTED: Do not deploy")
    print(f"Reason: {result['reason']}")
```

---

## Pro Tips

1. **Always validate before deploying**: Don't change parameters blindly
2. **Use 60+ days of data**: 30 days can be noisy, 60+ is more reliable
3. **Check multiple metrics**: Don't optimize for Sharpe alone (also check drawdown, trades count)
4. **Walk-forward validate**: Test on out-of-sample data to avoid overfitting
5. **Monitor post-deployment**: Even validated changes can underperform in new market conditions
6. **Keep a backtest log**: Track what you've tested and the results

---

## Next Steps

- Run your own backtests with the examples above
- Customize parameters for your risk tolerance
- Set up automated validation before parameter changes
- Integrate backtest results into admin dashboard

For more details, see [BACKTESTING_GUIDE.md](BACKTESTING_GUIDE.md).
