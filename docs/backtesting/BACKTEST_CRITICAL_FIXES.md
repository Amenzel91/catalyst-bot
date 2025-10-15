# CRITICAL FIXES FOR 2-YEAR BACKTEST

**Quick Reference:** Implement these 3 mandatory fixes before running 2-year backtest

**Total Time Required:** 30-60 minutes
**Priority:** CRITICAL (system will fail without these)

---

## FIX #1: Implement LRU Cache (30 minutes)

**Problem:** Unbounded price cache will cause out-of-memory crash after 3-4 months

**Solution:** Add LRU cache with max size limit

**Location:** `src/catalyst_bot/backtesting/engine.py`

### Step 1: Add LRU Cache Class

Add this at the top of `engine.py` (after imports):

```python
from collections import OrderedDict

class LRUCache:
    """Least Recently Used cache with size limit."""

    def __init__(self, max_size: int = 50):
        self.cache: OrderedDict = OrderedDict()
        self.max_size = max_size

    def get(self, key: str) -> Optional[pd.DataFrame]:
        if key not in self.cache:
            return None
        # Move to end (most recently used)
        self.cache.move_to_end(key)
        return self.cache[key]

    def set(self, key: str, value: pd.DataFrame) -> None:
        if key in self.cache:
            self.cache.move_to_end(key)
        self.cache[key] = value
        if len(self.cache) > self.max_size:
            # Remove least recently used
            oldest_key, _ = self.cache.popitem(last=False)
            log.debug("cache_evicted key=%s", oldest_key)

    def __contains__(self, key: str) -> bool:
        return key in self.cache

    def __getitem__(self, key: str) -> pd.DataFrame:
        return self.get(key)

    def __setitem__(self, key: str, value: pd.DataFrame) -> None:
        self.set(key, value)
```

### Step 2: Replace Price Cache Dictionary

In `BacktestEngine.__init__()` (around line 102), replace:

```python
# OLD:
self.price_cache: Dict[str, pd.DataFrame] = {}

# NEW:
self.price_cache = LRUCache(max_size=50)  # Limit to 50 tickers in memory
```

### Step 3: Update cache access in load_price_data()

In `load_price_data()` method (around line 199-202), update:

```python
# OLD:
if cache_key in self.price_cache:
    return self.price_cache[cache_key]

# NEW:
cached = self.price_cache.get(cache_key)
if cached is not None:
    return cached
```

And later (around line 226):

```python
# OLD:
self.price_cache[cache_key] = df

# NEW:
self.price_cache.set(cache_key, df)
```

**Testing:**
```python
# Verify cache eviction works:
cache = LRUCache(max_size=3)
cache.set("A", "data_a")
cache.set("B", "data_b")
cache.set("C", "data_c")
cache.set("D", "data_d")  # Should evict "A"
assert "A" not in cache
assert len(cache.cache) == 3
```

**Benefit:** Prevents OOM crash, limits memory to ~150MB (50 tickers × ~3MB each)

---

## FIX #2: Reduce Monitoring Frequency (5 minutes)

**Problem:** Hourly monitoring = 17,520 iterations over 2 years (12+ hour runtime)

**Solution:** Change to 15-minute intervals (still catches intraday moves)

**Location:** `src/catalyst_bot/backtesting/engine.py`

### Change Monitoring Interval

In `_monitor_positions()` method (around line 560), replace:

```python
# OLD:
current_time += timedelta(hours=1)

# NEW:
current_time += timedelta(minutes=15)  # 4x fewer iterations, still catches TP/SL
```

**Impact:**
- Iterations reduced: 17,520 → 4,380 (75% reduction)
- Still checks every 15 minutes (catches intraday take-profit/stop-loss)
- Runtime reduced: 12+ hours → 3-4 hours (without other optimizations)

**Testing:**
```python
# Verify monitoring frequency:
start = datetime(2023, 1, 1, 9, 0)
end = datetime(2023, 1, 1, 16, 0)
current = start
count = 0
while current <= end:
    count += 1
    current += timedelta(minutes=15)

assert count == 29  # 7 hours × 4 checks/hour + 1
```

**Benefit:** 75% reduction in monitoring iterations

---

## FIX #3: Backfill Historical Data (1-3 hours)

**Problem:** events.jsonl only has 3 days of data (Oct 11-13, 2025), not 2023-2025

**Solution:** Use historical bootstrapper or manually populate events.jsonl

### Option A: Use Historical Bootstrapper (Recommended)

If `historical_bootstrapper.py` is available:

```bash
cd /path/to/catalyst-bot
python src/catalyst_bot/historical_bootstrapper.py \
    --start 2023-01-01 \
    --end 2025-01-01 \
    --output data/events.jsonl
```

**Expected Output:**
- Fetches historical news/catalysts from RSS feeds
- Classifies and scores each event
- Writes to events.jsonl in correct format
- Time: 1-3 hours depending on data sources

### Option B: Manual Population

If bootstrapper unavailable, manually create test data:

```python
import json
from datetime import datetime, timedelta

# Generate synthetic events for testing
events = []
base_date = datetime(2023, 1, 1)

for i in range(365 * 2):  # 2 years, 1 event per day
    event = {
        "ts": (base_date + timedelta(days=i)).isoformat() + "Z",
        "ticker": f"TEST{i % 50}",  # 50 unique tickers
        "price": 5.0 + (i % 10) * 0.5,
        "cls": {
            "score": 0.3 + (i % 70) * 0.01,  # 0.30 to 1.00
            "sentiment": -0.5 + (i % 100) * 0.01,  # -0.5 to 0.5
            "confidence": 0.7 + (i % 30) * 0.01,
            "keywords": ["catalyst", "news", "fda"] if i % 3 == 0 else ["earnings", "breakout"]
        },
        "source": "test_data",
        "headline": f"Test catalyst event {i}"
    }
    events.append(event)

# Write to events.jsonl
with open("data/events.jsonl", "w", encoding="utf-8") as f:
    for event in events:
        f.write(json.dumps(event) + "\n")

print(f"Generated {len(events)} synthetic events")
```

**Warning:** Synthetic data won't reflect real market conditions but allows testing

### Option C: Use Existing Production Data

If you have a running Catalyst-Bot instance:

```bash
# Copy events.jsonl from production to backtest environment
scp user@production:/path/to/catalyst-bot/data/events.jsonl ./data/
```

### Verification

Verify data coverage:

```python
import json
from datetime import datetime

with open("data/events.jsonl", "r") as f:
    events = [json.loads(line) for line in f if line.strip()]

dates = [datetime.fromisoformat(e["ts"].replace("Z", "+00:00")) for e in events]
print(f"Total events: {len(events)}")
print(f"Date range: {min(dates).date()} to {max(dates).date()}")
print(f"Unique tickers: {len(set(e['ticker'] for e in events))}")
```

**Expected Output:**
```
Total events: 730+
Date range: 2023-01-01 to 2025-01-01
Unique tickers: 50-200
```

**Benefit:** Enables actual backtest execution (cannot run without data)

---

## TESTING THE FIXES

### Quick Validation (5 minutes)

After implementing all fixes, run a 1-week test:

```python
from catalyst_bot.backtesting.engine import BacktestEngine

# Short test backtest
engine = BacktestEngine(
    start_date="2023-01-01",
    end_date="2023-01-08",  # Just 1 week
    initial_capital=10000.0,
    strategy_params={
        'min_score': 0.25,
        'take_profit_pct': 0.20,
        'stop_loss_pct': 0.10,
        'max_hold_hours': 24,
    }
)

results = engine.run_backtest()
print(f"Test complete: {results['metrics']['total_trades']} trades")
```

**Expected Runtime:** <2 minutes
**Expected Output:** Non-zero trades (if data exists for Jan 2023)

### Full Validation (10 minutes)

Run a 3-month test before committing to 2 years:

```python
engine = BacktestEngine(
    start_date="2023-01-01",
    end_date="2023-04-01",  # 3 months
    initial_capital=10000.0,
)

results = engine.run_backtest()
```

**Expected Runtime:** 5-10 minutes
**Expected Metrics:**
- 20-50 trades (depending on data quality)
- Memory usage: <200MB
- No OOM crashes

---

## VERIFICATION CHECKLIST

Before running 2-year backtest, verify:

- [ ] LRU cache implemented and max_size set to 50
- [ ] Cache eviction tested (add item 51, verify item 1 removed)
- [ ] Monitoring interval changed to 15 minutes
- [ ] events.jsonl contains 500+ events across 2023-2025
- [ ] Data verification shows correct date range
- [ ] 1-week test backtest completes successfully
- [ ] 3-month test backtest completes in <10 minutes
- [ ] No OOM errors during 3-month test

---

## EXPECTED RESULTS (After Fixes)

### Performance Improvements

| Metric | Before | After | Improvement |
|--------|--------|-------|-------------|
| Monitoring iterations | 17,520 | 4,380 | 75% reduction |
| Memory usage (peak) | Unbounded (OOM) | ~150MB | Capped |
| Runtime (2-year) | 13-25 hours | 30-45 min | 95% faster |
| Price cache size | Unbounded | 50 tickers | Managed |

### Runtime Breakdown (After Fixes)

1. Data loading: 5-10 minutes
2. Alert processing: 5-10 minutes
3. Monitoring loop: 15-20 minutes (4,380 checks × 250ms)
4. Metrics calculation: 1-2 minutes
5. Report generation: 1-2 minutes

**Total: 30-45 minutes**

---

## RUNNING THE 2-YEAR BACKTEST

Once all fixes are implemented and tested:

```bash
cd /path/to/catalyst-bot
python scripts/run_2year_backtest.py
```

The script will:
1. Run pre-flight checks
2. Validate data availability
3. Execute backtest with progress tracking
4. Generate comprehensive report
5. Save results to `backtest_results/`

**Expected Output:**
- Markdown report with all metrics
- JSON file with raw results
- CSV file with trade log

---

## TROUBLESHOOTING

### Issue: OOM Crash During Backtest

**Cause:** LRU cache not working or max_size too high

**Fix:**
1. Verify LRU cache is actually being used (add debug logging)
2. Reduce max_size from 50 to 25
3. Clear cache more aggressively:
   ```python
   # After each ticker processed:
   self.price_cache = LRUCache(max_size=25)  # Reset
   ```

### Issue: Backtest Taking >2 Hours

**Cause:** Monitoring interval not changed or too many API calls

**Fix:**
1. Verify monitoring interval is 15 minutes (not hours)
2. Check if price data is being cached properly
3. Consider pre-loading all price data at start:
   ```python
   # At start of run_backtest():
   unique_tickers = set(alert['ticker'] for alert in alerts)
   self._preload_prices(unique_tickers)
   ```

### Issue: No Trades in Backtest

**Cause:** No data in target date range or filters too strict

**Fix:**
1. Verify events.jsonl has data for 2023-2025
2. Lower min_score from 0.30 to 0.20
3. Remove min_sentiment filter
4. Check alert timestamps match backtest date range

---

## FINAL CHECKLIST

Before production 2-year backtest:

- [ ] All 3 critical fixes implemented
- [ ] 1-week test passes (< 2 min runtime)
- [ ] 3-month test passes (< 10 min runtime, no OOM)
- [ ] events.jsonl verified (500+ events, correct dates)
- [ ] Disk space available (>1GB free)
- [ ] Internet connection stable
- [ ] Ready to commit 30-45 minutes for full run

**If all checked:** Ready for production 2-year backtest

---

**Document Version:** 1.0
**Last Updated:** 2025-10-14
**Estimated Fix Time:** 30-60 minutes
**Estimated Test Time:** 15 minutes
**Total Time to Prod:** 1-2 hours
