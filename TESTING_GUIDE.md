# Catalyst Bot - Testing Guide (Waves 1-3)

**Version:** Wave 1-3 Release
**Last Updated:** 2025-10-25

## Table of Contents

1. [Overview](#overview)
2. [Test Environment Setup](#test-environment-setup)
3. [Wave 1 Testing](#wave-1-testing)
4. [Wave 2 Testing](#wave-2-testing)
5. [Wave 3 Testing](#wave-3-testing)
6. [Integration Testing](#integration-testing)
7. [Validation Checklist](#validation-checklist)

---

## Overview

This guide provides comprehensive testing procedures for validating Waves 1-3 changes before and after deployment.

### Testing Philosophy

- **Test each wave independently** before integration testing
- **Use real data** when possible (live RSS feeds)
- **Document results** for troubleshooting
- **Automate** where feasible (regression prevention)

---

## Test Environment Setup

### Prerequisites

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Create test .env
cp .env .env.test
```

### Test Configuration

**`.env.test` contents:**
```bash
# Use test webhook (avoid spamming production)
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/TEST_ID/TEST_TOKEN

# Enable all Wave 1-3 features
MAX_ARTICLE_AGE_MINUTES=30
MAX_SEC_FILING_AGE_MINUTES=240
FILTER_OTC_STOCKS=1
FLOAT_CACHE_MAX_AGE_HOURS=24
CHART_FILL_EXTENDED_HOURS=1
FEATURE_MULTI_TICKER_SCORING=1
MULTI_TICKER_MIN_RELEVANCE_SCORE=40

# Enable verbose logging
LOG_PLAIN=1
LOG_LEVEL=DEBUG
```

### Test Discord Channel

Create a dedicated testing channel to avoid spamming production:
1. Create #bot-testing channel in Discord
2. Create new webhook for testing
3. Use test webhook URL in `.env.test`

---

## Wave 1 Testing

### Test 1.1: Article Age Filter

**Objective:** Verify old articles are rejected

**Setup:**
```bash
# Set strict threshold
MAX_ARTICLE_AGE_MINUTES=5
```

**Test Procedure:**
```bash
# Run bot and monitor rejections
python -m src.catalyst_bot.runner

# In separate terminal, watch logs
tail -f data/logs/bot.jsonl | grep "stale_article"
```

**Expected Results:**
```json
{
  "rejection_reason": "stale_article",
  "article_age_minutes": 45,
  "threshold": 5,
  "ticker": "AAPL",
  "title": "AAPL Reports Q3 Earnings..."
}
```

**Success Criteria:**
- ✅ Articles older than 5 minutes are rejected
- ✅ Rejection logged with `stale_article` reason
- ✅ `skipped_stale` counter increments
- ✅ No crashes or exceptions

**Failure Modes:**
- ❌ Old articles still generating alerts
- ❌ Rejection reason not logged
- ❌ Counter not incrementing

---

### Test 1.2: OTC Stock Filter

**Objective:** Verify OTC stocks are blocked

**Test Data:**
```python
# Known OTC tickers for testing
OTC_TICKERS = ['MMTXU', 'RVLY', 'GTII', 'TLSS']
# Known non-OTC tickers (control group)
VALID_TICKERS = ['AAPL', 'TSLA', 'SPY', 'QQQ']
```

**Test Procedure:**
```bash
# Test OTC detection manually
python -c "
from src.catalyst_bot.ticker_validation import is_otc_stock
print('MMTXU:', is_otc_stock('MMTXU'))  # Should be True
print('AAPL:', is_otc_stock('AAPL'))    # Should be False
"
```

**Expected Output:**
```
MMTXU: True  ✅
AAPL: False  ✅
```

**Live Test:**
```bash
# Monitor OTC rejections in production
tail -f data/logs/bot.jsonl | grep "otc_exchange"
```

**Expected Results:**
```json
{
  "rejection_reason": "otc_exchange",
  "ticker": "MMTXU",
  "exchange": "OTCMKTS",
  "skipped_otc": 3
}
```

**Success Criteria:**
- ✅ OTC tickers detected correctly
- ✅ Non-OTC tickers pass through
- ✅ Rejection logged with exchange info
- ✅ `skipped_otc` counter increments

---

### Test 1.3: Rejection Logging

**Objective:** Verify all rejection reasons are logged

**Test Procedure:**
```bash
# Run bot for 1 hour, collect rejection stats
python -m src.catalyst_bot.runner &
sleep 3600
pkill -f runner.py

# Analyze rejection distribution
cat data/logs/bot.jsonl | \
  jq -r 'select(.rejection_reason) | .rejection_reason' | \
  sort | uniq -c | sort -rn
```

**Expected Output:**
```
150 stale_article
 45 otc_exchange
 30 low_relevance
 20 price_ceiling
 15 low_score
```

**Success Criteria:**
- ✅ All rejection reasons logged
- ✅ Structured JSON format
- ✅ No missing fields
- ✅ Counters match log counts

---

## Wave 2 Testing

### Test 2.1: Alert Layout

**Objective:** Verify Discord embeds have new compact format

**Visual Inspection Test:**
```bash
# Send test alert
python -c "
from src.catalyst_bot.discord_interactions import send_alert
from src.catalyst_bot.config import SETTINGS

test_item = {
    'ticker': 'AAPL',
    'title': 'Apple Reports Record Q3 Earnings Beat',
    'score': 8.5,
    'sentiment': 0.65,
    'price': 175.43,
    'change_pct': 2.34,
    'volume': 45300000,
    'classification': {'tags': ['earnings', 'guidance']}
}

send_alert(test_item, SETTINGS.discord_webhook_url)
"
```

**Manual Verification:**
1. Open Discord testing channel
2. Inspect alert embed
3. Compare to checklist below

**Checklist:**
- ✅ Title contains catalyst badge (e.g., "📊 EARNINGS")
- ✅ Title contains score (e.g., "Score: 8.5")
- ✅ Fields reduced to 4-6 (not 15-20)
- ✅ Price and volume on single line
- ✅ Sentiment gauge shows 10 circles
- ✅ Footer is single line with timestamp
- ✅ No broken formatting

**Before/After Comparison:**

**Before (Wave 1):**
```
┌────────────────────────────────┐
│ AAPL - Catalyst Alert          │
│                                │
│ Ticker: AAPL                   │
│ Price: $175.43                 │
│ Change: +2.34%                 │
│ Volume: 45.3M                  │
│ Avg Volume: 50.2M              │
│ Sentiment: Bullish             │
│ Sentiment Score: 0.65          │
│ Float: 15.3B                   │
│ Source: BusinessWire           │
│ Category: Earnings             │
│ Keywords: earnings, beat       │
│ Score: 8.5                     │
│ (15 total fields)              │
└────────────────────────────────┘
```

**After (Wave 2):**
```
┌────────────────────────────────┐
│ 📊 EARNINGS | Score: 8.5       │
│                                │
│ $175.43 (+2.3%) | Vol 45M      │
│ ⚫⚫⚫⚫⚫⚫⚪⚪⚪⚪              │
│ Strong Q3 earnings beat...     │
│                                │
│ ⏰ 2m ago | BusinessWire       │
│ (4-6 total fields)             │
└────────────────────────────────┘
```

---

### Test 2.2: Catalyst Badges

**Objective:** Verify badge detection for all 12 catalyst types

**Test Script:**
```python
# tests/test_catalyst_badges.py
from src.catalyst_bot.catalyst_badges import extract_catalyst_badges

test_cases = [
    {
        "title": "Apple Reports Q3 Earnings Beat",
        "expected": ["📊 EARNINGS"]
    },
    {
        "title": "FDA Approves New Cancer Drug",
        "expected": ["💊 FDA NEWS"]
    },
    {
        "title": "Microsoft Acquires Activision",
        "expected": ["🤝 M&A"]
    },
    {
        "title": "Tesla Raises Guidance",
        "expected": ["📈 GUIDANCE"]
    },
    {
        "title": "Company Files 8-K SEC Form",
        "expected": ["📄 SEC FILING"]
    },
    # ... 7 more test cases
]

for test in test_cases:
    result = extract_catalyst_badges(None, test["title"], "")
    assert result == test["expected"], f"Expected {test['expected']}, got {result}"
    print(f"✅ {test['title']} → {result}")
```

**Success Criteria:**
- ✅ All 12 badge types detected
- ✅ Priority order respected (FDA > Earnings > M&A > ...)
- ✅ Max 3 badges per alert
- ✅ No false positives

---

### Test 2.3: Sentiment Gauge

**Objective:** Verify 10-circle gauge displays correctly

**Test Script:**
```python
from src.catalyst_bot.sentiment_gauge import render_sentiment_gauge

test_cases = [
    (-1.0, "⚪⚪⚪⚪⚪⚪⚪⚪⚪⚪"),  # Very bearish
    (-0.5, "⚫⚫⚪⚪⚪⚪⚪⚪⚪⚪"),  # Bearish
    (0.0, "⚫⚫⚫⚫⚫⚪⚪⚪⚪⚪"),   # Neutral
    (0.5, "⚫⚫⚫⚫⚫⚫⚫⚪⚪⚪"),   # Bullish
    (1.0, "⚫⚫⚫⚫⚫⚫⚫⚫⚫⚫"),   # Very bullish
]

for sentiment, expected in test_cases:
    result = render_sentiment_gauge(sentiment)
    assert result == expected, f"Sentiment {sentiment}: expected {expected}, got {result}"
    assert len(result) == 10, f"Expected 10 circles, got {len(result)}"
    print(f"✅ {sentiment:+.1f} → {result}")
```

**Success Criteria:**
- ✅ 10 circles total (not 5)
- ✅ Correct number filled for each sentiment
- ✅ Handles edge cases (-1.0, 1.0)
- ✅ Visual display in Discord is correct

---

## Wave 3 Testing

### Test 3.1: Float Data Caching

**Objective:** Verify float cache works with multi-source fallback

**Test Setup:**
```bash
# Clear cache
rm -f data/cache/float_cache.json

# Enable caching
FLOAT_DATA_ENABLE_CACHE=1
FLOAT_CACHE_MAX_AGE_HOURS=24
```

**Test Procedure:**
```python
# Test float fetch with cache
from src.catalyst_bot.float_data import get_float_data
import time

# First call: Cache miss (should fetch from API)
print("First call (cache miss):")
start = time.time()
float1 = get_float_data('AAPL')
elapsed1 = time.time() - start
print(f"Float: {float1}, Time: {elapsed1:.3f}s")

# Second call: Cache hit (should be instant)
print("Second call (cache hit):")
start = time.time()
float2 = get_float_data('AAPL')
elapsed2 = time.time() - start
print(f"Float: {float2}, Time: {elapsed2:.3f}s")

# Verify
assert float1 == float2, "Cache returned different value"
assert elapsed2 < elapsed1 / 10, "Cache not faster than API call"
print("✅ Cache working correctly")
```

**Expected Output:**
```
First call (cache miss):
Float: 15300000000, Time: 0.450s

Second call (cache hit):
Float: 15300000000, Time: 0.002s

✅ Cache working correctly
```

**Cache File Inspection:**
```bash
# Check cache file
cat data/cache/float_cache.json | jq '.'
```

**Expected Structure:**
```json
{
  "AAPL": {
    "float": 15300000000,
    "timestamp": 1729890000,
    "source": "yfinance",
    "expires_at": 1729976400
  }
}
```

**Success Criteria:**
- ✅ Cache file created automatically
- ✅ First call fetches from API (slow)
- ✅ Second call uses cache (fast)
- ✅ Cache expires after TTL
- ✅ Fallback works if primary source fails

---

### Test 3.2: Chart Gap Filling

**Objective:** Verify gaps are filled during extended hours

**Test Setup:**
```bash
CHART_FILL_EXTENDED_HOURS=1
CHART_FILL_METHOD=forward_fill
CHART_SHOW_EXTENDED_HOURS_ANNOTATION=1
```

**Test Procedure (Manual):**
```python
from src.catalyst_bot.charts_advanced import generate_chart
import matplotlib.pyplot as plt

# Generate test chart
chart_path = generate_chart('AAPL', timeframe='1D', show_extended=True)
print(f"Chart saved to: {chart_path}")

# Open chart for visual inspection
plt.show()
```

**Visual Inspection Checklist:**
- ✅ No sudden drops to zero during premarket
- ✅ Gaps filled with dashed lines
- ✅ Premarket zone shaded differently
- ✅ Regular hours zone normal
- ✅ Afterhours zone shaded
- ✅ Price continuity maintained

**Automated Test:**
```python
# Test gap filling logic
from src.catalyst_bot.charts_advanced import fill_extended_hours_gaps
import pandas as pd

# Create test data with gap
df = pd.DataFrame({
    'timestamp': pd.date_range('2025-01-15 09:00', periods=5, freq='1min'),
    'close': [10.0, 10.0, None, None, 10.05],  # Gap at minutes 3-4
    'volume': [1000, 500, 0, 0, 2000]
})

# Fill gaps
df_filled = fill_extended_hours_gaps(df, method='forward_fill')

# Verify gaps filled
assert df_filled.iloc[2]['close'] == 10.0, "Gap 1 not filled"
assert df_filled.iloc[3]['close'] == 10.0, "Gap 2 not filled"
assert df_filled.iloc[2]['filled'] == True, "Gap not marked"
print("✅ Gap filling working correctly")
```

---

### Test 3.3: Multi-Ticker Scoring

**Objective:** Verify primary ticker selection logic

**Test Cases:**
```python
from src.catalyst_bot.multi_ticker_handler import analyze_multi_ticker_article

# Test Case 1: Single-ticker story (large score gap)
article1 = {
    "title": "AAPL Reports Record Q3 Earnings",
    "summary": "Apple Inc (AAPL) announced today... AAPL stock up 5%..."
}
primary, secondary, scores = analyze_multi_ticker_article(
    ['AAPL', 'MSFT'], article1
)
assert primary == ['AAPL'], f"Expected ['AAPL'], got {primary}"
assert 'MSFT' in secondary, f"Expected MSFT in secondary"
assert scores['AAPL'] > 80, "AAPL score too low"
assert scores['MSFT'] < 40, "MSFT score too high"
print("✅ Test 1 passed: Single-ticker story")

# Test Case 2: True multi-ticker story (close scores)
article2 = {
    "title": "AAPL and GOOGL Announce AI Partnership",
    "summary": "Apple (AAPL) and Google (GOOGL) will collaborate..."
}
primary, secondary, scores = analyze_multi_ticker_article(
    ['AAPL', 'GOOGL'], article2
)
assert len(primary) == 2, f"Expected 2 primary tickers, got {len(primary)}"
assert 'AAPL' in primary and 'GOOGL' in primary
assert abs(scores['AAPL'] - scores['GOOGL']) < 30, "Scores should be close"
print("✅ Test 2 passed: Multi-ticker partnership")

# Test Case 3: Comparison article (one primary)
article3 = {
    "title": "Market Update: AAPL Down, MSFT Up",
    "summary": "Stocks moved mixed. Apple fell 5% while Microsoft..."
}
primary, secondary, scores = analyze_multi_ticker_article(
    ['AAPL', 'MSFT'], article3
)
assert len(primary) == 1, f"Expected 1 primary, got {len(primary)}"
assert scores['AAPL'] > scores['MSFT'], "AAPL should score higher"
print("✅ Test 3 passed: Comparison article")
```

**Success Criteria:**
- ✅ Single-ticker stories alert one ticker only
- ✅ Partnerships alert both tickers
- ✅ Comparisons alert primary subject only
- ✅ Scores reflect relevance accurately

---

### Test 3.4: Offering Sentiment

**Objective:** Verify offering stage detection and sentiment correction

**Test Cases:**
```python
from src.catalyst_bot.offering_sentiment import detect_offering_stage, apply_offering_sentiment_correction

# Test Case 1: Offering closing (should be slightly bullish)
title1 = "ACME Corp Closes $25M Public Offering"
stage, conf = detect_offering_stage(title1, "")
assert stage == "closing", f"Expected 'closing', got {stage}"
sentiment, _, corrected = apply_offering_sentiment_correction(title1, "", -0.6)
assert sentiment == 0.2, f"Expected +0.2, got {sentiment}"
assert corrected == True, "Should have corrected sentiment"
print("✅ Test 1: Offering closing detected, sentiment corrected")

# Test Case 2: Offering upsize (should be very bearish)
title2 = "ACME Corp Upsizes Offering to $50M"
stage, conf = detect_offering_stage(title2, "")
assert stage == "upsize", f"Expected 'upsize', got {stage}"
sentiment, _, corrected = apply_offering_sentiment_correction(title2, "", -0.5)
assert sentiment == -0.7, f"Expected -0.7, got {sentiment}"
print("✅ Test 2: Offering upsize detected, sentiment corrected")

# Test Case 3: Offering announcement (should be bearish)
title3 = "ACME Corp Announces $25M Offering"
stage, conf = detect_offering_stage(title3, "")
assert stage == "announcement", f"Expected 'announcement', got {stage}"
sentiment, _, corrected = apply_offering_sentiment_correction(title3, "", 0.0)
assert sentiment == -0.6, f"Expected -0.6, got {sentiment}"
print("✅ Test 3: Offering announcement detected, sentiment corrected")
```

---

## Integration Testing

### Full Pipeline Test

**Objective:** Verify all waves work together end-to-end

**Test Procedure:**
```bash
# 1. Clear all caches
rm -rf data/cache/*

# 2. Start bot with full config
python -m src.catalyst_bot.runner

# 3. Monitor for 1 hour
# 4. Verify all features working:
#    - Articles filtered by age ✅
#    - OTC stocks blocked ✅
#    - Alerts have compact layout ✅
#    - Badges display correctly ✅
#    - Float cache populated ✅
#    - Multi-ticker scoring active ✅
```

**Monitoring Commands:**
```bash
# Terminal 1: Alert flow
watch -n 10 'tail -20 data/logs/bot.jsonl | grep "alert_sent"'

# Terminal 2: Rejections
watch -n 30 'grep "rejection_reason" data/logs/bot.jsonl | tail -20'

# Terminal 3: Cache stats
watch -n 60 'ls -lh data/cache/ && cat data/cache/float_cache.json | jq "keys | length"'
```

---

## Validation Checklist

### Pre-Deployment Checklist

- [ ] All unit tests pass (`pytest tests/`)
- [ ] Manual testing completed for each wave
- [ ] Integration testing passed
- [ ] No regressions in existing features
- [ ] Cache files created successfully
- [ ] Discord webhooks working
- [ ] Logs structured correctly
- [ ] No memory leaks (run for 24h)

### Post-Deployment Checklist

- [ ] Alert volume reduced by 20-40% (expected)
- [ ] No crashes or errors in production logs
- [ ] Discord alerts display correctly
- [ ] Float cache hit rate >70% after 1 hour
- [ ] Multi-ticker scoring active in logs
- [ ] Rejection reasons logged properly
- [ ] User feedback positive

---

## Sample Test Commands

### Quick Validation Suite

```bash
# Run all Wave 1-3 tests
pytest tests/ -v -k "wave1 or wave2 or wave3"

# Test specific wave
pytest tests/ -v -k "wave1"
pytest tests/ -v -k "wave2"
pytest tests/ -v -k "wave3"

# Integration tests only
pytest tests/ -v -k "integration"

# Coverage report
pytest tests/ --cov=src.catalyst_bot --cov-report=html
```

### Manual Smoke Test

```bash
# 1. Clear state
rm -rf data/cache/* data/logs/bot.jsonl

# 2. Run bot for 10 minutes
timeout 600 python -m src.catalyst_bot.runner

# 3. Check results
echo "Alert count:"
grep -c "alert_sent" data/logs/bot.jsonl

echo "Rejection breakdown:"
grep "rejection_reason" data/logs/bot.jsonl | \
  jq -r '.rejection_reason' | sort | uniq -c

echo "Cache status:"
ls -lh data/cache/float_cache.json
cat data/cache/float_cache.json | jq 'keys | length'
```

---

**End of Testing Guide**
