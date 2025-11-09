# Catalyst-Bot Pipeline - Quick Reference Guide

## Key Entry Points

| Component | File | Function | Entry Point |
|-----------|------|----------|------------|
| Main CLI | `main.py` | - | `python -m catalyst_bot run --loop` |
| Bot Runner | `runner.py` | `runner_main()` | Line 2952+ |
| Core Cycle | `runner.py` | `_cycle()` | Line 985+ |
| Feed Fetching | `feeds.py` | `fetch_pr_feeds()` | Line 1099 |
| Deduplication | `feeds.py` | `dedupe()` | Line 2608 |
| Classification | `classify.py` | `classify()` / `fast_classify()` | - |
| Alert Sending | `alerts.py` | `send_alert_safe()` | Line 740 |
| Enrichment | `enrichment_worker.py` | `enqueue_for_enrichment()` | - |

---

## Timing Hierarchy

```
Main Loop (every LOOP_SECONDS = 30s)
├─ Check Market Hours (optional)
├─ Execute _cycle() [40-120 seconds typical]
│  ├─ Fetch feeds (3-8s)
│  ├─ Deduplicate (1s)
│  ├─ Batch price fetch (3-10s if price_ceiling set)
│  ├─ SEC LLM batch (5-15s if SEC items)
│  └─ Process items in loop:
│     ├─ Classification (0.5-2s per item)
│     ├─ Filtering (1-2 filters per item, <1ms each)
│     ├─ Enrichment enqueue (async, non-blocking)
│     └─ Alert POST (1-3s per alert with retries)
├─ Sleep remainder of LOOP_SECONDS
└─ Heartbeat every HEARTBEAT_INTERVAL_MIN (60 min default)
```

---

## Bottleneck Analysis

### Highest Impact (Use These to Optimize)

1. **Feed Polling Interval** - ~15s average latency
   - Current: 30 seconds default
   - Optimization: Reduce to 15 seconds
   - Savings: 15 seconds per cycle
   - Config: `LOOP_SECONDS=15`

2. **Classification per Item** - ~0.5-2s per item
   - Current: Runs for every deduped article
   - Optimization: Disable unused sentiment sources
   - Savings: 0.5-1s per item
   - Configs: `FEATURE_NEWS_SENTIMENT=0`, `FEATURE_LOCAL_SENTIMENT=0`

3. **Chart Generation** - ~1-3s per alert (optional)
   - Current: Sequential per alert
   - Optimization: Cache daily charts, use QuickChart API
   - Savings: 1-2s per chart
   - Config: `FEATURE_RICH_ALERTS=0` or `FEATURE_QUICKCHART=1`

4. **Price Batch Fetching** - ~3-10s
   - Current: Called once per cycle if PRICE_CEILING set
   - Optimization: Cache longer, reduce frequency
   - Savings: 3-5s
   - Config: Increase price cache TTL from 60s

5. **SEC LLM Processing** - ~5-15s if SEC items present
   - Current: Batch process all SEC filings
   - Optimization: Use flash LLM, reduce batch size
   - Savings: 5-10s
   - Config: `FEATURE_SEC_DIGESTER=0` or use cheaper LLM

---

## Critical Path (Determines Minimum Cycle Time)

```
Feed Fetch (3-8s) 
  → Dedup (1s) 
  → Item Loop (0.5-2s per item × N items)
    → Classify (0.5-1s)
    → Filter (1ms per check)
    → Enrich & Alert (1-3s per alert)
  → Sleep remaining time until next cycle
```

**To minimize latency:**
1. Reduce polling interval (`LOOP_SECONDS`)
2. Use fast classification (disable sentiment sources)
3. Batch Discord posts instead of sequential POSTs

---

## End-to-End Latency Estimates

### From News Publication to Discord Alert

| Scenario | Latency |
|----------|---------|
| **Fast Path** | 20-25 seconds |
| (Fast classify, no charts, no enrichment wait) | |
| | |
| **Typical Path** | 45-60 seconds |
| (With classification + filters) | |
| | |
| **Slow Path** | 90+ seconds |
| (With charts + enrichment wait + retries) | |
| | |
| **Average** | 50-70 seconds |
| (Most common scenario) | |

### Components Contributing to Latency

| Component | Range | Notes |
|-----------|-------|-------|
| Feed polling | 15s avg | Worst case: 30s (LOOP_SECONDS) |
| Feed fetch | 3-8s | Async concurrent, all sources parallel |
| Dedup | <1s | In-memory + SQLite seen store |
| Price batch | 3-10s | Only if PRICE_CEILING set |
| SEC LLM | 5-15s | Only if SEC items present |
| Classification | 0.5-2s/item | Depends on sentiment sources |
| Charts | 1-3s/chart | Only if FEATURE_RICH_ALERTS=1 |
| Enrichment | 0-5s | Async background, non-blocking |
| Discord POST | 1-3s/alert | With retries (429, 5xx) |

---

## Configuration Quick Wins

### Reduce Latency (In Priority Order)

```bash
# 1. Fastest impact: Reduce polling interval
LOOP_SECONDS=15  # From 30s, saves 15s

# 2. Disable rich features
FEATURE_RICH_ALERTS=0  # Disable charts
FEATURE_QUICKCHART=0   # Disable QuickChart API charts

# 3. Disable expensive sentiment sources
FEATURE_NEWS_SENTIMENT=0       # External news sentiment
FEATURE_LOCAL_SENTIMENT=0      # VADER sentiment (fast but still time)

# 4. Skip SEC processing if not needed
FEATURE_SEC_DIGESTER=0  # Skip LLM analysis of SEC filings

# 5. Reduce enrichment timeout
ENRICHMENT_BATCH_TIMEOUT=1.0  # From 2.0, results faster

# 6. Disable chart generation features
FEATURE_MOMENTUM_INDICATORS=0  # MACD, EMA, VWAP
FEATURE_INDICATORS=0           # General indicators
```

**Combined savings: 30-50 seconds per cycle**

---

## Feature Flags Impact

### Performance-Critical Features

| Flag | Impact | Enable If |
|------|--------|-----------|
| `FEATURE_RICH_ALERTS` | +1-3s per alert | Need visual chart context |
| `FEATURE_QUICKCHART` | +1-2s per chart (better than local) | Have API credits |
| `FEATURE_NEWS_SENTIMENT` | +1-2s per item | Need external sentiment |
| `FEATURE_LOCAL_SENTIMENT` | +0.5s per item | Want free sentiment |
| `FEATURE_SEC_DIGESTER` | +5-15s if SEC items | Want SEC insight |
| `FEATURE_MOMENTUM_INDICATORS` | +1-2s per alert | Need momentum context |
| `FEATURE_MARKET_HOURS_DETECTION` | <1s check | Want market-aware cycles |
| `FEATURE_WATCHLIST_CASCADE` | <1s per cycle | Using watchlist tiers |
| `FEATURE_52W_LOW_SCANNER` | +2-5s per cycle | Want 52w low alerts |
| `FEATURE_LLM_BATCH` | Cost reducer | Want cheaper LLM calls |

---

## Recommended Configurations

### For Minimal Latency (Speed Optimized)
```env
LOOP_SECONDS=15
FEATURE_RICH_ALERTS=0
FEATURE_QUICKCHART=0
FEATURE_NEWS_SENTIMENT=0
FEATURE_LOCAL_SENTIMENT=0
FEATURE_SEC_DIGESTER=0
FEATURE_MOMENTUM_INDICATORS=0
ENRICHMENT_BATCH_TIMEOUT=1.0
MAX_ALERTS_PER_CYCLE=20
MIN_SCORE=0.5  # Filter aggressively
```
**Expected Cycle Time: 20-40 seconds**

### For Balanced Performance (Recommended)
```env
LOOP_SECONDS=30
FEATURE_RICH_ALERTS=0
FEATURE_QUICKCHART=1  # Charts don't block
FEATURE_NEWS_SENTIMENT=1
FEATURE_LOCAL_SENTIMENT=0
FEATURE_SEC_DIGESTER=0
FEATURE_MOMENTUM_INDICATORS=0
ENRICHMENT_BATCH_SIZE=10
MAX_ALERTS_PER_CYCLE=40
```
**Expected Cycle Time: 40-60 seconds**

### For Maximum Intelligence (Quality Optimized)
```env
LOOP_SECONDS=60
FEATURE_RICH_ALERTS=1
FEATURE_QUICKCHART=1
FEATURE_NEWS_SENTIMENT=1
FEATURE_LOCAL_SENTIMENT=1
FEATURE_SEC_DIGESTER=1
FEATURE_MOMENTUM_INDICATORS=1
FEATURE_ANALYST_SENTIMENT=1
ENRICHMENT_BATCH_SIZE=10
MAX_ALERTS_PER_CYCLE=40
```
**Expected Cycle Time: 90-120 seconds**

---

## Key Files to Monitor

### Real-Time Metrics
- `CYCLE_DONE` logs: Shows actual cycle execution time
- `batch_price_fetch`: Price data fetch time
- `sec_batch_processing_complete`: SEC LLM processing time
- `enrichment_batch_processed`: Enrichment processing time
- `discord_post_target`: Alert posting success/failure

### Debugging
- Check `LAST_CYCLE_STATS` in heartbeat for per-cycle metrics
- Monitor `feed_http` errors for connectivity issues
- Look for `async_feed_fetch_error` for source-specific failures
- Check `enrichment_queue` metrics for backlog issues

---

## Potential Bottlenecks to Watch

| Issue | Signal | Fix |
|-------|--------|-----|
| Feed outage | No items fetched for N cycles | Check feed API keys, network |
| High latency | CYCLE_DONE takes >120s | Reduce features, increase hardware |
| Enrichment queue growing | enrichment_queue_size increasing | Reduce batch timeout, increase workers |
| LLM rate limiting | LLM API errors | Reduce LLM_BATCH_SIZE, add delay |
| Price fetch timeout | batch_price_fetch_failed | Increase timeout, reduce price ceiling |
| Memory leak | Process memory growing | Clear ML batch scorer, check enrichment |

---

## Testing & Validation

### Quick Test Run
```bash
# Single cycle
python -m catalyst_bot run --once

# Timed loop (5 cycles)
timeout 300 python -m catalyst_bot run --loop

# Check cycle time
grep "CYCLE_DONE" logs/*.log
```

### Performance Testing
```bash
# Check average cycle time
grep "CYCLE_DONE" logs/*.log | awk '{print $NF}' | sort -n | tail -20

# Monitor in real-time
tail -f logs/runner.log | grep -E "CYCLE_DONE|batch_price_fetch|discord_post"
```

