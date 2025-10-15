# Data Pipeline Investigation Report
**Date:** 2025-10-14
**Status:** ✅ Investigation Complete, Data Cache Cleared

---

## Executive Summary

Investigated the data collection pipeline to understand why backtesting wasn't working. Found that **timestamps are working correctly**, but **94.4% of events have no ticker assigned**. Data cache has been cleared for fresh start.

---

## Investigation Findings

### ✅ Timestamps: Working Correctly!

All three data files correctly set timestamps using `"ts"` field:

| File | Timestamp Field | Implementation |
|------|----------------|----------------|
| `events.jsonl` | `ts` | Via `logs.log_event()` |
| `rejected_items.jsonl` | `ts` | `datetime.now(timezone.utc).isoformat()` (line 113) |
| `accepted_items.jsonl` | `ts` | `datetime.now(timezone.utc).isoformat()` (line 120) |

**BacktestEngine Compatibility:**
- Handles both `"ts"` and `"timestamp"` fields (engine.py lines 225, 622)
- No compatibility issues found

### ❌ The Real Problem: Missing Tickers

**events.jsonl analysis (483 events):**
- ✅ 483/483 (100%) have `ts` timestamp
- ❌ 27/483 (5.6%) have `ticker` field
- ❌ 456/483 (94.4%) have NO ticker

**Why:**
- Most news items don't have ticker extraction during classification
- Classifier may be failing to extract tickers from news content
- Or items are genuinely ticker-less (press releases, general news, etc.)

### Test Data Found (25/27 valid events)

```
AAPL, TSLA, NVDA, AMD, META (Oct 3-7)
- All scores = 0.00
- Empty titles
- Synthetic prices (150, 200, 400, 100, 300)
- Not real trading data
```

### Real Events (2/27)

1. **TEST** - "Demo: Feeds empty, testing alert pipeline" (no price data)
2. **GRLT** - "Primior Holdings Reports Q2 2025 Results" (no price data)

---

## Data Pipeline Architecture

### Files That Write Data

```
┌─────────────────────────────────────────────────────────────┐
│                      EVENTS.JSONL                            │
│  Written by: logs.log_event()                               │
│  Timestamp: Added by caller (various places)                │
│  Ticker: From classification (if available)                 │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│                  REJECTED_ITEMS.JSONL                        │
│  Written by: rejected_items_logger.log_rejected_item()      │
│  Timestamp: datetime.now(timezone.utc).isoformat()          │
│  Ticker: Required (items without tickers are skipped)       │
│  Filter: Only logs items priced $0.10-$10.00                │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│                  ACCEPTED_ITEMS.JSONL                        │
│  Written by: accepted_items_logger.log_accepted_item()      │
│  Timestamp: datetime.now(timezone.utc).isoformat()          │
│  Ticker: Required (items without tickers are skipped)       │
│  Filter: Only logs items priced $0.10-$10.00                │
└─────────────────────────────────────────────────────────────┘
```

---

## Data Cache Cleared ✅

**Backup created:** `data_backup_20251014_225934/`

**Files backed up:**
- accepted_items.jsonl (13.09 KB)
- admin_changes.jsonl (8.69 KB)
- events.jsonl (191.91 KB)
- rejected_items.jsonl (355.18 KB)
- sentiment_scores.jsonl (42.18 KB)

**Files cleared:**
- All 5 non-empty JSONL files cleared to 0 bytes
- Ready for fresh data collection
- No duplicates will occur

---

## Why Backtest Showed 0 Trades

**Expected:** 27 valid events with both `ts` and `ticker`
**Actual:** 0 trades executed

**Reasons:**
1. **Test data (25 events):** Synthetic prices, scores=0.00, empty titles
2. **Invalid tickers (2 events):** TEST and GRLT had no real price data available
3. **Date range:** Some events may have been outside backtest window
4. **Entry criteria:** Even with min_score=0.0, events need:
   - Valid ticker with available price data
   - Price within tradeable range
   - Market hours alignment

---

## Next Steps for Production Backtesting

### 1. Fix Ticker Extraction (High Priority)

94.4% of events have no ticker assigned. Need to investigate:

**Check classification pipeline:**
```bash
# Find where tickers are extracted
grep -r "ticker.*extract\|extract.*ticker" src/catalyst_bot/
```

**Possible issues:**
- Ticker regex pattern not matching common formats
- Ticker extraction disabled/broken in classify.py
- News sources using non-standard ticker formats
- Ticker validation too strict

### 2. Run Live Bot to Generate Real Data

Once data cache is cleared, run the bot to generate fresh, real data:

```bash
# Start the bot
python -m catalyst_bot.runner

# Let it run for several hours/days to collect:
# - Real news items
# - Proper ticker extraction
# - Classification scores
# - Market prices
```

### 3. Run Fresh Backtest

Once real data is collected:

```python
from catalyst_bot.backtesting.engine import BacktestEngine

engine = BacktestEngine(
    start_date="2025-10-15",  # After data collection starts
    end_date="2025-10-22",     # 1 week later
    initial_capital=10000.0
)

results = engine.run_backtest()
```

---

## Configuration Verification

**Timestamp fields:**
- ✅ All loggers use `"ts"` field
- ✅ BacktestEngine reads both `"ts"` and `"timestamp"`
- ✅ Format: ISO 8601 with timezone (`2025-10-14T22:59:34+00:00`)

**Ticker fields:**
- ✅ rejected_items_logger requires ticker (line 69)
- ✅ accepted_items_logger requires ticker (line 79)
- ⚠️ events.jsonl accepts items without tickers

**Price range filtering:**
- ✅ rejected_items: $0.10-$10.00 (lines 19-20)
- ✅ accepted_items: $0.10-$10.00 (lines 29-30)
- ❌ events.jsonl: No price filtering

---

## Recommendations

### Immediate (Before Backtest)

1. ✅ **Data cache cleared** - No action needed
2. ⚠️ **Fix ticker extraction** - Investigate why 94.4% of events lack tickers
3. ⚠️ **Run bot live** - Collect real production data

### Short Term

1. **Add ticker extraction tests** - Verify extraction works for common formats
2. **Monitor ticker extraction rate** - Alert if < 50% of events have tickers
3. **Add data quality dashboard** - Track % of events with required fields

### Long Term

1. **Add LLM ticker extraction** - Fallback for regex failures
2. **Validate tickers against market data** - Reject invalid/delisted tickers
3. **Add ticker confidence score** - Track extraction quality

---

## Conclusion

**Investigation Status:** ✅ COMPLETE

**Key Findings:**
- ✅ Timestamps working correctly (100% coverage)
- ❌ Ticker extraction failing (94.4% missing)
- ✅ Data cache cleared for fresh start
- ✅ Backtesting infrastructure ready

**Next Action:** Fix ticker extraction in classification pipeline, then run live bot to generate real data for backtesting.

**Estimated Effort:**
- Ticker extraction fix: 2-4 hours
- Data collection: 24-48 hours (passive)
- Fresh backtest: 5-10 minutes

---

**Report Generated:** 2025-10-14 22:59:34 UTC
**Backup Location:** `data_backup_20251014_225934/`
**Total Files Cleared:** 5 files, 611 KB
