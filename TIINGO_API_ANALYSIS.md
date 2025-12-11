# Tiingo API Rate Limit Analysis & Solutions

## Current Problem

**Error Count**: 1,937 `tiingo_invalid_json` errors in 9 hours
**Impact**: 77% of Tiingo API calls failing, slowing down cycle times
**Fallback**: yfinance working but slower and less reliable

## Data Flow Architecture

### Current Pipeline (Per Cycle):

```
1. Feed Aggregation (feeds.py)
   └─> Fetch RSS feeds from all sources
   └─> Extract ~70 items per cycle
   └─> Deduplicate via SeenStore
   └─> Extract tickers (CIK, patterns, etc.)

2. Ticker Validation (runner.py)
   └─> Filter to unique tickers (~30-40 per cycle)
   └─> Batch price fetch via market.py

3. Price Fetch (market.py) ⚠️ BOTTLENECK HERE
   └─> PRIMARY: Tiingo API (failing ~77%)
   │   ├─> Batch endpoint: /tiingo/daily/prices
   │   ├─> Individual fallback: /tiingo/daily/{ticker}/prices
   │   └─> Intraday: /iex/{ticker}/prices
   │
   └─> FALLBACK: yfinance (slower, succeeds ~90%)
       └─> Sequential ticker fetches

4. Classification & Scoring
   └─> Score items with prices
   └─> Apply filters (price ceiling, volume, etc.)
   └─> Generate alerts for qualifying items
```

### Rate Limit Analysis

**Tiingo API Limits** (typical):
- Free tier: 1,000 requests/day (~42/hour, 0.7/minute)
- Paid tier: 10,000 requests/day (~417/hour, 7/minute)

**Current Bot Usage**:
- 414 cycles in 9 hours = 46 cycles/hour
- ~30 tickers per cycle
- **Estimated**: ~1,380 API calls/hour (if no batching)
- **Result**: Exceeding even paid tier limits!

**Why So Many Calls?**
1. Not using batch endpoint effectively
2. Cache misses (TTL too short?)
3. Market closed but still fetching
4. OTC ticker retries (3-4 attempts per ticker)
5. No rate limit detection/backoff

---

## Solution Options

### **Option A: Aggressive Caching** ⭐ (Quick Win)

**Implementation:**
```python
# In market.py
PRICE_CACHE_TTL = {
    "market_open": 60,      # 1 min during trading hours
    "market_closed": 3600,  # 1 hour after hours (currently 5min)
    "weekend": 86400,       # 24 hours on weekends
}
```

**Pros:**
- Immediate reduction in API calls
- No code changes to call sites
- Works with existing cache system

**Cons:**
- Stale prices during high volatility
- May miss rapid price movements

**Expected Impact:** 60-80% reduction in API calls

---

### **Option B: Batch API Optimization** ⭐⭐ (Best ROI)

**Current Issue:**
- Batch endpoint exists but may not be used effectively
- Falls back to individual calls on batch failure
- No retry logic with exponential backoff

**Implementation:**
```python
# In market.py batch_fetch_prices()

1. Group tickers by exchange/type (NYSE, NASDAQ, OTC)
2. Use batch endpoint for non-OTC tickers
3. Add retry with exponential backoff
4. Cache entire batch response
5. Only fallback to individual for OTC/failed tickers

# Rate limit handling
if "rate limit" in error_message:
    sleep_time = min(2 ** retry_count, 300)  # Max 5min
    log.warning(f"tiingo_rate_limited backoff={sleep_time}s")
    time.sleep(sleep_time)
```

**Pros:**
- Respects API design (batch = fewer requests)
- Reduces calls by 10-20x for valid tickers
- Better error handling

**Cons:**
- Requires testing batch endpoint behavior
- More complex error handling

**Expected Impact:** 80-90% reduction in API calls

---

### **Option C: Smart Fallback Strategy** (Safety Net)

**Current**: Tiingo → yfinance (only on total failure)

**Improved**:
```python
# Priority-based provider selection

def get_price(ticker):
    # 1. Try cache first (always)
    if cached := price_cache.get(ticker):
        return cached

    # 2. Check ticker type
    if is_otc(ticker):
        return yfinance_fetch(ticker)  # Skip Tiingo for OTC

    # 3. Check rate limit status
    if tiingo_rate_limited():
        if time_until_reset() < 60:
            sleep_until_reset()
        else:
            return yfinance_fetch(ticker)

    # 4. Try Tiingo with circuit breaker
    if tiingo_error_rate < 0.5:  # <50% errors
        try:
            return tiingo_fetch(ticker)
        except RateLimitError:
            tiingo_set_rate_limited(ttl=300)  # 5min cooldown
            return yfinance_fetch(ticker)

    # 5. Fallback
    return yfinance_fetch(ticker)
```

**Pros:**
- Graceful degradation
- Reduces wasted API calls on known-bad tickers
- Self-healing with circuit breaker

**Cons:**
- More complex logic
- Need to track error rates

**Expected Impact:** 50-70% reduction in failed calls

---

### **Option D: Rate Limit Monitoring** (Observability)

**Add Metrics:**
```python
# Track per-provider metrics
metrics = {
    "tiingo": {
        "calls": 0,
        "success": 0,
        "rate_limited": 0,
        "invalid_json": 0,
        "avg_latency_ms": 0,
    },
    "yfinance": {...},
    "alpha_vantage": {...},
}

# Log every hour
log.info(
    "market_data_metrics",
    tiingo_success_rate=metrics["tiingo"]["success"] / metrics["tiingo"]["calls"],
    tiingo_calls_per_hour=metrics["tiingo"]["calls"],
    yfinance_success_rate=...,
)

# Alert if degraded
if success_rate < 0.5:
    log.warning("market_data_provider_degraded provider=tiingo rate={:.1%}".format(success_rate))
```

**Pros:**
- Visibility into API health
- Can detect issues early
- Helps tune cache TTLs

**Cons:**
- Doesn't fix root cause
- Adds logging overhead

**Expected Impact:** 0% reduction (but enables data-driven tuning)

---

### **Option E: Market Hours Awareness** (Efficiency)

**Current Issue**: Fetching prices when market is closed wastes calls

**Implementation:**
```python
# In runner.py main loop

if market_is_closed():
    # Use longer cache, skip intraday endpoints
    cache_ttl = 3600  # 1 hour
    skip_intraday = True
    cycle_interval = 300  # 5 min (less frequent)
else:
    cache_ttl = 60    # 1 min
    skip_intraday = False
    cycle_interval = 60   # 1 min (more frequent)
```

**Pros:**
- Saves API calls when prices won't change
- Reduces server load
- Better resource utilization

**Cons:**
- Need accurate market hours calendar
- After-hours trading still happens

**Expected Impact:** 30-40% reduction during off-hours

---

## Recommended Solution: **Combined Approach**

### **Phase 1: Immediate (Today)** - Option A + Option D
1. ✅ **Increase cache TTL** to 1 hour during market close
2. ✅ **Add rate limit monitoring** to understand usage patterns
3. ✅ **Skip Tiingo for known-OTC tickers** (go straight to yfinance)

**Expected**: 60% reduction in API calls, visibility into patterns

### **Phase 2: Short-term (This Week)** - Option B + Option C
1. ✅ **Optimize batch API usage** with better error handling
2. ✅ **Implement circuit breaker** for Tiingo failures
3. ✅ **Add exponential backoff** for rate limit errors

**Expected**: 80-90% reduction in API calls, graceful degradation

### **Phase 3: Long-term (Optional)** - Option E
1. ✅ **Market hours awareness** for dynamic caching
2. ✅ **Pre-fetch during market open** for known tickers
3. ✅ **Webhooks for price updates** (if available from provider)

**Expected**: Further optimization, real-time price updates

---

## Quick Win Implementation

### Immediate 3-Line Fix (Option A):

**File**: `src/catalyst_bot/market.py`

**Change**:
```python
# Find the PRICE_CACHE_TTL or cache TTL setting
# Change from:
PRICE_CACHE_TTL = 300  # 5 minutes

# To:
def get_cache_ttl():
    if market_is_closed():
        return 3600  # 1 hour when closed
    return 300      # 5 min when open
```

This alone should reduce calls by 60% during off-hours.

---

## Monitoring Commands

### Check Current API Usage:
```bash
# Count Tiingo errors by type
grep tiingo_invalid_json data/logs/bot.jsonl | wc -l

# Check success rate
python << EOF
import json
logs = [json.loads(line) for line in open("data/logs/bot.jsonl")]
tiingo_logs = [l for l in logs if "tiingo" in l.get("name", "").lower()]
success = len([l for l in tiingo_logs if l.get("level") == "INFO"])
total = len(tiingo_logs)
print(f"Tiingo success rate: {success/total*100:.1f}%")
EOF
```

### Track Rate Limits:
```bash
# Add to runner.py or market.py
log.info("api_usage_summary",
    tiingo_calls=tiingo_call_count,
    yf_calls=yf_call_count,
    cache_hits=cache_hit_count,
    cache_hit_rate=cache_hit_count / total_requests
)
```

---

## Additional Considerations

### Is Tiingo Worth It?

**Tiingo Pros:**
- More reliable than yfinance (when working)
- Better data quality
- Batch endpoints
- Professional API

**yfinance Pros:**
- Free, no rate limits
- Works for OTC stocks
- Simpler API
- Currently higher success rate (90% vs 23%)

**Recommendation**: Keep Tiingo but fix the rate limit issues. If issues persist after fixes, consider:
1. Upgrading Tiingo tier (paid plan)
2. Making yfinance primary for small-cap/OTC
3. Adding Alpha Vantage as third option

---

**Created**: 2025-12-11
**Analysis By**: Claude Code
