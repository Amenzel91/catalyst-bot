# Configuration Migration Guide
## Catalyst-Bot Patch Wave Environment Changes

**Version:** 1.0
**Last Updated:** November 5, 2025
**For:** Patch Wave 2 - Pre-Pump Configuration Optimization

---

## Table of Contents

1. [Overview](#overview)
2. [Quick Migration](#quick-migration)
3. [Detailed Changes](#detailed-changes)
4. [Feature Flags Reference](#feature-flags-reference)
5. [Cycle Timing Recommendations](#cycle-timing-recommendations)
6. [Troubleshooting](#troubleshooting)
7. [Rollback Procedures](#rollback-procedures)

---

## Overview

### What Changed

Patch Wave 2 introduces **9 configuration changes** to the `.env` file designed to:
- Reduce alert latency from 25min-7hr to <5min
- Disable feature multipliers that slow down classification
- Increase scan frequency for faster catalyst detection
- Expand freshness window to capture delayed-publication catalysts

### Migration Strategy

**Recommended Approach:**
1. Backup current `.env` file
2. Apply all 9 changes at once (atomic migration)
3. Restart bot
4. Monitor for 1 hour

**Alternative Approach:**
1. Apply changes incrementally (disable features first, then adjust cycles)
2. Test each change independently
3. Roll back if issues arise

### Impact Summary

| Area | Before | After | Impact |
|------|--------|-------|--------|
| **Latency** | 25min-7hr | <5min | -95-98% |
| **Noise** | 67% | 11-19% | -72-84% |
| **CPU** | ~35% | ~40% | +5% |
| **API Calls** | ~100/hour | ~300/hour | +200% |
| **Alert Coverage** | 100% | ~130% | +30% |

---

## Quick Migration

### Step 1: Backup Current Configuration

```bash
# Navigate to project directory
cd /path/to/catalyst-bot

# Backup current .env
cp .env .env.backup.$(date +%Y%m%d)

# Verify backup
ls -lh .env.backup.*
```

### Step 2: Apply Changes

**Option A: Manual Editing** (recommended for control)

```bash
# Open .env in your preferred editor
nano .env

# Apply all 9 changes (see sections below)
# Save and exit
```

**Option B: Automated Script** (faster but less control)

```bash
# Create migration script
cat > migrate_config.sh << 'EOF'
#!/bin/bash

# Backup
cp .env .env.backup.$(date +%Y%m%d_%H%M%S)

# Apply changes
sed -i 's/^RVOL_MIN_AVG_VOLUME=100000/RVOL_MIN_AVG_VOLUME=50000/' .env
sed -i 's/^FEATURE_RVOL=1/FEATURE_RVOL=0/' .env
sed -i 's/^FEATURE_FUNDAMENTAL_SCORING=1/FEATURE_FUNDAMENTAL_SCORING=0/' .env
sed -i 's/^FEATURE_MARKET_REGIME=1/FEATURE_MARKET_REGIME=0/' .env
sed -i 's/^FEATURE_VOLUME_PRICE_DIVERGENCE=1/FEATURE_VOLUME_PRICE_DIVERGENCE=0/' .env
sed -i 's/^LOOP_SECONDS=60/LOOP_SECONDS=30/' .env
sed -i 's/^FEED_CYCLE=600/FEED_CYCLE=180/' .env
sed -i 's/^SEC_FEED_CYCLE=900/SEC_FEED_CYCLE=300/' .env
sed -i 's/^MAX_ARTICLE_AGE_MINUTES=30/MAX_ARTICLE_AGE_MINUTES=720/' .env

echo "Migration complete. Restart bot to apply changes."
EOF

chmod +x migrate_config.sh
./migrate_config.sh
```

### Step 3: Verify Changes

```bash
# Check all 9 settings
grep -E "RVOL_MIN_AVG_VOLUME|FEATURE_RVOL|FEATURE_FUNDAMENTAL|FEATURE_MARKET_REGIME|FEATURE_VOLUME_PRICE|LOOP_SECONDS|FEED_CYCLE|SEC_FEED_CYCLE|MAX_ARTICLE_AGE" .env

# Expected output:
# RVOL_MIN_AVG_VOLUME=50000
# FEATURE_RVOL=0
# FEATURE_FUNDAMENTAL_SCORING=0
# FEATURE_MARKET_REGIME=0
# FEATURE_VOLUME_PRICE_DIVERGENCE=0
# LOOP_SECONDS=30
# FEED_CYCLE=180
# SEC_FEED_CYCLE=300
# MAX_ARTICLE_AGE_MINUTES=720
```

### Step 4: Restart Bot

```bash
# If using systemd
sudo systemctl restart catalyst-bot

# If running manually
pkill -f "python.*runner.py"
python src/catalyst_bot/runner.py
```

### Step 5: Monitor Logs

```bash
# Watch logs for 1 hour
tail -f data/logs/bot.jsonl | grep -E "cycle_time|rvol|classification"

# Expected behavior:
# - cycle_time ~30 seconds (not 60)
# - No "rvol" calculation messages
# - classification_time <15 seconds (not 45-60)
```

---

## Detailed Changes

### Change 1: Volume Filtering Threshold

**Setting:** `RVOL_MIN_AVG_VOLUME`

```bash
# .env - Line ~472

# OLD VALUE
RVOL_MIN_AVG_VOLUME=100000

# NEW VALUE
RVOL_MIN_AVG_VOLUME=50000

# RATIONALE
# Low-float penny stocks (<$10) often have <100k average daily volume
# but are highly volatile catalysts. Lowering threshold from 100k to 50k
# captures more low-float opportunities without sacrificing quality.

# IMPACT
# - +30% alert coverage (captures more micro-cap stocks)
# - Minimal noise increase (retrospective filter compensates)
# - No latency impact (threshold check is instant)
```

**Verification:**

```bash
# Check setting
grep RVOL_MIN_AVG_VOLUME .env

# Expected: RVOL_MIN_AVG_VOLUME=50000

# Monitor impact
grep "rvol_avg_volume" data/logs/bot.jsonl | tail -20

# Should see more tickers with 50k-100k avg volume passing through
```

---

### Changes 2-5: Feature Flags (DISABLED)

These four features are **disabled** to reduce classification latency. Each feature adds 1-30 seconds per ticker.

#### Change 2: RVol Multiplier

**Setting:** `FEATURE_RVOL`

```bash
# .env - Line ~457

# OLD VALUE
FEATURE_RVOL=1

# NEW VALUE
FEATURE_RVOL=0

# RATIONALE
# RVol (Relative Volume) calculation requires:
# 1. Fetch 20-day historical volume from Tiingo API (5-10 sec)
# 2. Estimate full-day volume based on current time (1 sec)
# 3. Calculate ratio vs 20-day average (instant)
# 4. Apply multiplier: 1.2x-1.4x for high RVol, 0.8x for low RVol
#
# This adds 15-30 seconds PER TICKER during classification.
# For pre-pump alerts, we prioritize SPEED over scoring precision.
# Alert users immediately upon detection, not after RVol calculation.

# IMPACT
# - 15-30 sec latency reduction per ticker
# - No more RVol multipliers (1.2x-1.4x boosts removed)
# - Classification time: 45-60 sec → 10-15 sec (67-83% faster)
# - Trade-off: Less precise scoring, but faster alerts

# WHEN TO RE-ENABLE
# - After market close (for backtesting and analysis)
# - For watchlist-only mode (fewer tickers = manageable latency)
# - If using paid Tiingo plan with lower latency API
```

**Verification:**

```bash
# Check setting
grep FEATURE_RVOL .env

# Expected: FEATURE_RVOL=0

# Verify RVol NOT calculated
grep "rvol_calculation" data/logs/bot.jsonl

# Should return NO RESULTS (feature disabled)

# Check classification time
grep "classification_time" data/logs/bot.jsonl | tail -20

# Should be <15 seconds average (not 45-60)
```

#### Change 3: Fundamental Scoring

**Setting:** `FEATURE_FUNDAMENTAL_SCORING`

```bash
# .env - Line ~371

# OLD VALUE
FEATURE_FUNDAMENTAL_SCORING=1

# NEW VALUE
FEATURE_FUNDAMENTAL_SCORING=0

# RATIONALE
# Fundamental scoring (float + short interest) requires:
# 1. Scrape FinViz for float shares (2-3 sec)
# 2. Fetch yfinance short interest (1-2 sec)
# 3. Apply boosts: <10M float = +0.5, >20% SI = +0.5
#
# This adds 3-5 seconds PER TICKER during classification.
# For pre-pump alerts, we want INSTANT alerts, not refined scores.

# IMPACT
# - 3-5 sec latency reduction per ticker
# - No more float/SI boosts (+0.3-0.5 removed)
# - Trade-off: Less precise scoring for low-float stocks

# WHEN TO RE-ENABLE
# - After implementing cached float data (Wave 3)
# - For watchlist-only mode (pre-fetched fundamental data)
# - If using FinViz Elite API with faster response times
```

**Verification:**

```bash
# Check setting
grep FEATURE_FUNDAMENTAL_SCORING .env

# Expected: FEATURE_FUNDAMENTAL_SCORING=0

# Verify fundamentals NOT fetched
grep "float_shares\|short_interest" data/logs/bot.jsonl

# Should return NO RESULTS (feature disabled)
```

#### Change 4: Market Regime Classification

**Setting:** `FEATURE_MARKET_REGIME`

```bash
# .env - Line ~424

# OLD VALUE
FEATURE_MARKET_REGIME=1

# NEW VALUE
FEATURE_MARKET_REGIME=0

# RATIONALE
# Market regime classification (VIX-based) requires:
# 1. Fetch VIX current price (1-2 sec)
# 2. Classify: BULL (VIX<15), NEUTRAL (15-20), HIGH_VOL (20-30), BEAR (30-40), CRASH (40+)
# 3. Apply multipliers: 0.5x (CRASH) to 1.2x (BULL)
#
# This adds 1-2 seconds PER CYCLE (not per ticker, but still overhead).
# For pre-pump alerts, we want to catch catalysts regardless of market regime.

# IMPACT
# - 1-2 sec latency reduction per cycle
# - No more regime multipliers (0.5x-1.2x removed)
# - Alerts sent in all market conditions (no suppression during crashes)
# - Trade-off: May send more alerts during volatile periods

# WHEN TO RE-ENABLE
# - During extreme volatility (VIX >40) to suppress noise
# - For backtesting to analyze regime-specific performance
# - If user prefers fewer alerts during bear markets
```

**Verification:**

```bash
# Check setting
grep FEATURE_MARKET_REGIME .env

# Expected: FEATURE_MARKET_REGIME=0

# Verify regime NOT calculated
grep "market_regime\|vix" data/logs/bot.jsonl

# Should return NO RESULTS (feature disabled)
```

#### Change 5: Volume-Price Divergence

**Setting:** `FEATURE_VOLUME_PRICE_DIVERGENCE`

```bash
# .env - Line ~536

# OLD VALUE
FEATURE_VOLUME_PRICE_DIVERGENCE=1

# NEW VALUE
FEATURE_VOLUME_PRICE_DIVERGENCE=0

# RATIONALE
# Volume-price divergence detection requires:
# 1. RVol calculation (already disabled, but this adds checks)
# 2. Price change calculation
# 3. Pattern classification (weak rally, strong selloff, etc.)
# 4. Sentiment adjustment (-0.15 to +0.15)
#
# This adds 5-10 seconds PER TICKER if RVol was enabled.
# Since RVol is disabled, divergence has no data and fails gracefully.
# Disabling explicitly prevents any attempted calculations.

# IMPACT
# - 5-10 sec latency reduction (if RVol were enabled)
# - No more divergence signals (-0.15 to +0.15 removed)
# - Trade-off: Less technical confirmation, but faster alerts

# WHEN TO RE-ENABLE
# - After re-enabling RVol (prerequisite)
# - For watchlist-only mode with pre-calculated divergence
# - If using minute-by-minute data for real-time divergence
```

**Verification:**

```bash
# Check setting
grep FEATURE_VOLUME_PRICE_DIVERGENCE .env

# Expected: FEATURE_VOLUME_PRICE_DIVERGENCE=0

# Verify divergence NOT calculated
grep "divergence" data/logs/bot.jsonl

# Should return NO RESULTS (feature disabled)
```

---

### Changes 6-8: Cycle Timing (REDUCED)

These three settings control how frequently the bot scans for new news. Reducing cycle times means faster detection but higher API usage.

#### Change 6: Main Scan Cycle

**Setting:** `LOOP_SECONDS`

```bash
# .env - Line ~199 (in config.py)

# OLD VALUE
LOOP_SECONDS=60

# NEW VALUE
LOOP_SECONDS=30

# RATIONALE
# LOOP_SECONDS controls the main event loop frequency.
# Every LOOP_SECONDS, the bot:
# 1. Checks if feed refresh is due
# 2. Processes any new items from previous fetch
# 3. Runs classification pipeline
# 4. Posts alerts to Discord
#
# With 60-second cycles, breaking news can be missed for up to 60 seconds.
# Reducing to 30 seconds cuts this detection gap in half.

# IMPACT
# - 30 sec worst-case latency reduction
# - 2x more cycles per hour (60/min → 120/min)
# - ~5% CPU increase (more cycles = more processing)
# - Trade-off: Slightly higher resource usage

# WHEN TO INCREASE
# - During non-market hours (use 60-120 sec to save resources)
# - If CPU usage exceeds 60% sustained
# - If bot crashes due to memory pressure
```

**Verification:**

```bash
# Check setting
grep LOOP_SECONDS .env

# Expected: LOOP_SECONDS=30

# Monitor actual cycle time
grep "cycle_complete" data/logs/bot.jsonl | tail -20

# Should see timestamps ~30 seconds apart
# Example:
# 2025-11-05T10:00:00 cycle_complete
# 2025-11-05T10:00:30 cycle_complete
# 2025-11-05T10:01:00 cycle_complete
```

#### Change 7: News Feed Refresh

**Setting:** `FEED_CYCLE`

```bash
# .env - Line ~383 (not in .env.example, defined in config.py)

# OLD VALUE
FEED_CYCLE=600  # 10 minutes

# NEW VALUE
FEED_CYCLE=180  # 3 minutes

# RATIONALE
# FEED_CYCLE controls how often RSS/API feeds are refreshed.
# News sources (GlobeNewswire, Finnhub, etc.) are polled every FEED_CYCLE.
#
# With 10-minute cycles:
# - News published at 10:01 AM won't be fetched until 10:10 AM (9 min delay)
# - Average delay: ~5 minutes
#
# With 3-minute cycles:
# - News published at 10:01 AM fetched by 10:04 AM (3 min delay)
# - Average delay: ~1.5 minutes

# IMPACT
# - 7 min worst-case latency reduction
# - 3.3x more feed refreshes (6/hour → 20/hour)
# - ~200% increase in API calls to news sources
# - Trade-off: Higher API usage (may hit rate limits)

# WHEN TO INCREASE
# - If hitting API rate limits (429 errors)
# - During low-volume periods (after market close)
# - If news sources throttle your IP

# ADD TO .ENV
# This setting is NOT in .env.example by default.
# Add it manually:
echo "FEED_CYCLE=180" >> .env
```

**Verification:**

```bash
# Check setting (may not exist in .env)
grep FEED_CYCLE .env

# If missing, add it:
echo "FEED_CYCLE=180" >> .env

# Monitor feed refresh frequency
grep "feed_refresh" data/logs/bot.jsonl | tail -20

# Should see timestamps ~3 minutes apart
# Example:
# 2025-11-05T10:00:00 feed_refresh source=GlobeNewswire
# 2025-11-05T10:03:00 feed_refresh source=GlobeNewswire
# 2025-11-05T10:06:00 feed_refresh source=GlobeNewswire
```

#### Change 8: SEC Filing Refresh

**Setting:** `SEC_FEED_CYCLE`

```bash
# .env - Line ~383 (not in .env.example, defined in config.py)

# OLD VALUE
SEC_FEED_CYCLE=900  # 15 minutes

# NEW VALUE
SEC_FEED_CYCLE=300  # 5 minutes

# RATIONALE
# SEC_FEED_CYCLE controls how often SEC EDGAR feeds are refreshed.
# SEC filings (8-K, 424B5, FWP, 13D/G) are polled every SEC_FEED_CYCLE.
#
# With 15-minute cycles:
# - Filing posted at 10:01 AM won't be fetched until 10:15 AM (14 min delay)
# - Average delay: ~7.5 minutes
#
# With 5-minute cycles:
# - Filing posted at 10:01 AM fetched by 10:06 AM (5 min delay)
# - Average delay: ~2.5 minutes

# IMPACT
# - 10 min worst-case latency reduction
# - 3x more SEC refreshes (4/hour → 12/hour)
# - ~200% increase in EDGAR API calls
# - Trade-off: Higher API usage (EDGAR is generally permissive)

# WHEN TO INCREASE
# - During non-market hours (filings are rare after 8 PM ET)
# - If EDGAR throttles your User-Agent
# - If SEC filings are not a priority

# ADD TO .ENV
# This setting is NOT in .env.example by default.
# Add it manually:
echo "SEC_FEED_CYCLE=300" >> .env
```

**Verification:**

```bash
# Check setting (may not exist in .env)
grep SEC_FEED_CYCLE .env

# If missing, add it:
echo "SEC_FEED_CYCLE=300" >> .env

# Monitor SEC refresh frequency
grep "sec_feed_refresh" data/logs/bot.jsonl | tail -20

# Should see timestamps ~5 minutes apart
# Example:
# 2025-11-05T10:00:00 sec_feed_refresh
# 2025-11-05T10:05:00 sec_feed_refresh
# 2025-11-05T10:10:00 sec_feed_refresh
```

---

### Change 9: Article Freshness Window

**Setting:** `MAX_ARTICLE_AGE_MINUTES`

```bash
# .env - Line ~59

# OLD VALUE
MAX_ARTICLE_AGE_MINUTES=30

# NEW VALUE
MAX_ARTICLE_AGE_MINUTES=720  # 12 hours

# RATIONALE
# MAX_ARTICLE_AGE_MINUTES controls the maximum age of articles to alert on.
# Articles older than this threshold are rejected as "stale."
#
# OLD LOGIC (30 minutes):
# - Rejected articles published >30 min ago
# - Missed catalysts with delayed timestamps (clinical trials filed at 6 AM,
#   announced at 8 AM)
# - Overly aggressive freshness filter
#
# NEW LOGIC (12 hours):
# - Accept articles published in last 12 hours
# - Rely on RETROSPECTIVE FILTER (Wave 1) to block post-event articles
# - Capture delayed-publication catalysts

# IMPACT
# - NO latency impact (filter relaxation)
# - +10-20% alert coverage (captures delayed catalysts)
# - Noise controlled by retrospective filter (not freshness)
# - Trade-off: Slightly more processing (more articles evaluated)

# WHEN TO DECREASE
# - If retrospective filter is disabled (would cause noise)
# - If you want stricter freshness (e.g., 1-2 hour window)
# - If processing too many stale articles
```

**Verification:**

```bash
# Check setting
grep MAX_ARTICLE_AGE_MINUTES .env

# Expected: MAX_ARTICLE_AGE_MINUTES=720

# Monitor article age distribution
grep "article_age" data/logs/bot.jsonl | tail -50

# Should see articles with age 0-720 minutes
# Should NOT see "rejected_stale" for articles <12 hours old
```

---

## Feature Flags Reference

### Complete Feature Flag List

```bash
# ============================================================================
# FEATURE FLAGS - PATCH WAVE 2 CHANGES
# ============================================================================

# WAVE 2: DISABLED for Pre-Pump Alerts
FEATURE_RVOL=0                        # RVol multiplier (15-30 sec latency)
FEATURE_FUNDAMENTAL_SCORING=0         # Float/SI scoring (3-5 sec latency)
FEATURE_MARKET_REGIME=0               # VIX-based regime (1-2 sec latency)
FEATURE_VOLUME_PRICE_DIVERGENCE=0     # Divergence detection (5-10 sec latency)

# UNCHANGED: Still Enabled
FEATURE_ALERTS=1                      # Core alert system
FEATURE_HEARTBEAT=1                   # Health monitoring
FEATURE_INDICATORS=1                  # Chart indicators
FEATURE_EARNINGS_ALERTS=1             # Earnings alerts
FEATURE_SEC_FILINGS=1                 # SEC filing integration
FEATURE_MULTI_TICKER_SCORING=1        # Multi-ticker handling (Wave 3)
FEATURE_FLOAT_DATA=1                  # Float data collection (Wave 3)
FEATURE_FLASH_LITE=1                  # LLM cost optimization (Wave Alpha)
FEATURE_SEC_LLM_CACHE=1               # SEC LLM caching (Wave Alpha)
FEATURE_LLM_BATCH=1                   # Batch classification (Wave Alpha)

# OPTIONAL: May Be Enabled
FEATURE_GOOGLE_TRENDS=0               # Google Trends sentiment (optional)
FEATURE_SHORT_INTEREST_BOOST=0        # Short interest boost (optional)
FEATURE_PREMARKET_SENTIMENT=0         # Pre-market sentiment (optional)
FEATURE_AFTERMARKET_SENTIMENT=0       # After-market sentiment (optional)
FEATURE_INSIDER_SENTIMENT=0           # Insider trading sentiment (optional)
FEATURE_NEWS_VELOCITY=0               # News velocity tracking (optional)
FEATURE_SEMANTIC_KEYWORDS=0           # KeyBERT keywords (optional)
```

### Feature Flag Priority Matrix

| Feature | Priority | Latency Impact | Recommended for Pre-Pump |
|---------|----------|----------------|--------------------------|
| `FEATURE_RVOL` | Medium | 15-30 sec | DISABLE (Wave 2) |
| `FEATURE_FUNDAMENTAL_SCORING` | Medium | 3-5 sec | DISABLE (Wave 2) |
| `FEATURE_MARKET_REGIME` | Low | 1-2 sec | DISABLE (Wave 2) |
| `FEATURE_VOLUME_PRICE_DIVERGENCE` | Low | 5-10 sec | DISABLE (Wave 2) |
| `FEATURE_ALERTS` | Critical | 0 sec | ENABLE (required) |
| `FEATURE_HEARTBEAT` | High | 0 sec | ENABLE (recommended) |
| `FEATURE_INDICATORS` | High | 1-2 sec | ENABLE (charts) |
| `FEATURE_EARNINGS_ALERTS` | High | 0 sec | ENABLE (catalysts) |
| `FEATURE_SEC_FILINGS` | High | 0 sec | ENABLE (catalysts) |
| `FEATURE_MULTI_TICKER_SCORING` | High | 1 sec | ENABLE (Wave 3) |
| `FEATURE_FLASH_LITE` | Medium | -0.5 sec | ENABLE (cost savings) |
| `FEATURE_LLM_BATCH` | Medium | +2 sec | ENABLE (cost savings) |
| `FEATURE_GOOGLE_TRENDS` | Low | 5-10 sec | OPTIONAL (slow API) |
| `FEATURE_SEMANTIC_KEYWORDS` | Low | 2-3 sec | OPTIONAL (nice-to-have) |

---

## Cycle Timing Recommendations

### Timing Presets

#### Preset 1: AGGRESSIVE (Pre-Pump Focus) - **RECOMMENDED FOR WAVE 2**

```bash
LOOP_SECONDS=30
FEED_CYCLE=180
SEC_FEED_CYCLE=300
MAX_ARTICLE_AGE_MINUTES=720

# Use Case: Day trading, pre-pump alerts, sub-5-minute latency
# Pros: Fastest possible alerts, catch catalysts before pump
# Cons: Higher API usage, ~5% CPU increase
```

#### Preset 2: BALANCED (General Use)

```bash
LOOP_SECONDS=60
FEED_CYCLE=300
SEC_FEED_CYCLE=600
MAX_ARTICLE_AGE_MINUTES=360

# Use Case: General trading, good latency without excessive API calls
# Pros: Good balance of speed and efficiency
# Cons: 5-10 min latency (acceptable for swing trading)
```

#### Preset 3: CONSERVATIVE (Resource Efficient)

```bash
LOOP_SECONDS=120
FEED_CYCLE=600
SEC_FEED_CYCLE=900
MAX_ARTICLE_AGE_MINUTES=180

# Use Case: Backtesting, analysis, overnight monitoring
# Pros: Minimal API usage, low CPU overhead
# Cons: 10-15 min latency (not suitable for day trading)
```

#### Preset 4: MARKET HOURS AWARE (Dynamic Switching)

```bash
# Market Open (9:30 AM - 4:00 PM ET)
MARKET_OPEN_CYCLE_SEC=30
FEED_CYCLE_MARKET_OPEN=180
SEC_FEED_CYCLE_MARKET_OPEN=300

# Extended Hours (4:00-9:30 AM, 4:00-8:00 PM ET)
EXTENDED_HOURS_CYCLE_SEC=60
FEED_CYCLE_EXTENDED=300
SEC_FEED_CYCLE_EXTENDED=600

# Market Closed (8:00 PM - 4:00 AM ET)
MARKET_CLOSED_CYCLE_SEC=180
FEED_CYCLE_CLOSED=600
SEC_FEED_CYCLE_CLOSED=900

# Enable market hours detection
FEATURE_MARKET_HOURS_DETECTION=1

# Use Case: Optimize resource usage based on market status
# Pros: Best of all worlds (fast during market, efficient during closed)
# Cons: Requires market hours detection implementation (Wave 0.0 Phase 2)
```

### Custom Tuning

**For Slow Systems (Limited CPU/RAM):**

```bash
# Increase cycles to reduce load
LOOP_SECONDS=90  # 1.5 minutes
FEED_CYCLE=600   # 10 minutes
SEC_FEED_CYCLE=900  # 15 minutes

# Reduce max alerts per cycle
MAX_ALERTS_PER_CYCLE=20  # Down from 40
```

**For High-Volume Trading (Ultra-Low Latency):**

```bash
# Decrease cycles to absolute minimum
LOOP_SECONDS=15  # 15 seconds
FEED_CYCLE=60    # 1 minute
SEC_FEED_CYCLE=180  # 3 minutes

# Increase max alerts to avoid missing opportunities
MAX_ALERTS_PER_CYCLE=60  # Up from 40

# WARNING: May hit API rate limits, monitor logs
```

**For API Rate Limit Avoidance:**

```bash
# If seeing HTTP 429 errors, increase cycles:
FEED_CYCLE=600  # 10 minutes (from 3)
SEC_FEED_CYCLE=900  # 15 minutes (from 5)

# Enable batching to reduce API calls
FEATURE_LLM_BATCH=1
LLM_BATCH_SIZE=10  # Group 10 items per LLM call
```

---

## Troubleshooting

### Issue 1: Configuration Not Applied

**Symptoms:**
- Logs still show 60-second cycles
- RVol calculations still appearing

**Diagnosis:**

```bash
# Check if .env was modified
stat .env

# Check if bot restarted after changes
systemctl status catalyst-bot

# Check loaded config in logs
grep "config_loaded" data/logs/bot.jsonl | tail -1
```

**Solution:**

```bash
# Force restart
sudo systemctl restart catalyst-bot

# Or if running manually
pkill -f "python.*runner.py"
sleep 5
python src/catalyst_bot/runner.py
```

### Issue 2: API Rate Limit Errors (HTTP 429)

**Symptoms:**
- Logs show "HTTP 429: Too Many Requests"
- Alerts delayed or missing

**Diagnosis:**

```bash
# Count rate limit errors
grep -c "429" data/logs/bot.jsonl

# Identify which API is rate limiting
grep "429" data/logs/bot.jsonl | grep -oE "api=[a-z]+" | sort | uniq -c
```

**Solution:**

```bash
# Option 1: Increase cycle times
# Edit .env:
FEED_CYCLE=600  # 10 min instead of 3 min
SEC_FEED_CYCLE=900  # 15 min instead of 5 min

# Option 2: Enable rate limiting delays
# Edit .env:
API_RATE_LIMIT_DELAY=5  # 5-second delay between API calls

# Option 3: Disable specific API sources
# Edit .env:
SKIP_SOURCES=Finnhub,GlobeNewswire  # Skip problematic sources

# Restart
sudo systemctl restart catalyst-bot
```

### Issue 3: High CPU Usage (>60%)

**Symptoms:**
- Bot process using >60% CPU sustained
- System responsiveness degraded

**Diagnosis:**

```bash
# Check CPU usage
top -p $(pgrep -f "python.*runner.py")

# Profile bottlenecks
python -m cProfile -o profile.out src/catalyst_bot/runner.py
```

**Solution:**

```bash
# Option 1: Increase LOOP_SECONDS
# Edit .env:
LOOP_SECONDS=60  # Back to 1 minute (from 30 sec)

# Option 2: Disable heavy features
# Edit .env:
FEATURE_SEMANTIC_KEYWORDS=0  # Disable KeyBERT
FEATURE_LLM_BATCH=0  # Disable batching

# Option 3: Process priority
# Lower process priority:
renice +10 $(pgrep -f "python.*runner.py")

# Restart
sudo systemctl restart catalyst-bot
```

### Issue 4: Alerts Still Arriving Late

**Symptoms:**
- Average latency still >5 minutes
- News arrives mid-pump

**Diagnosis:**

```bash
# Calculate actual latency
grep "alert_sent" data/logs/bot.jsonl | tail -50 | \
jq -r '.published_at, .alert_sent_at' | \
paste - - | awk '{print ($2 - $1) / 60 " minutes"}'

# Check if cycles are actually faster
grep "cycle_complete" data/logs/bot.jsonl | tail -20 | \
jq -r '.timestamp' | awk 'NR>1 {print ($1 - prev)} {prev=$1}'
```

**Solution:**

```bash
# Option 1: Verify .env changes applied
grep -E "LOOP_SECONDS|FEED_CYCLE" .env

# Option 2: Check for bottlenecks
grep "classification_time" data/logs/bot.jsonl | tail -20

# If classification_time >30 sec, disable more features:
FEATURE_SEMANTIC_KEYWORDS=0

# Option 3: Increase feed refresh frequency
FEED_CYCLE=60  # 1 minute (very aggressive)

# Restart
sudo systemctl restart catalyst-bot
```

### Issue 5: Missing Alerts (Coverage Decreased)

**Symptoms:**
- Fewer alerts than before
- Known catalysts not triggering

**Diagnosis:**

```bash
# Check rejection reasons
grep "rejected_reason" data/logs/bot.jsonl | jq -r '.rejected_reason' | sort | uniq -c

# Common reasons:
# - retrospective (Wave 1 filter)
# - stale (MAX_ARTICLE_AGE_MINUTES too low)
# - low_score (MIN_SCORE too high)
```

**Solution:**

```bash
# Option 1: Lower MIN_SCORE threshold
# Edit .env:
MIN_SCORE=0.1  # Down from 0.2

# Option 2: Expand freshness window
# Edit .env:
MAX_ARTICLE_AGE_MINUTES=1440  # 24 hours (from 12)

# Option 3: Disable retrospective filter temporarily
# Edit feeds.py:
# if False and _is_retrospective_article(...):

# Restart
sudo systemctl restart catalyst-bot
```

---

## Rollback Procedures

### Quick Rollback (All Changes)

```bash
# Restore backup
cp .env.backup.$(ls -t .env.backup.* | head -1) .env

# Or restore specific date
cp .env.backup.20251105 .env

# Verify restoration
grep -E "RVOL_MIN_AVG_VOLUME|FEATURE_RVOL|LOOP_SECONDS" .env

# Restart
sudo systemctl restart catalyst-bot
```

### Partial Rollback (Individual Settings)

```bash
# Rollback RVol only (keep other changes)
# Edit .env:
FEATURE_RVOL=1
RVOL_MIN_AVG_VOLUME=100000

# Rollback cycle times only (keep features disabled)
# Edit .env:
LOOP_SECONDS=60
FEED_CYCLE=600
SEC_FEED_CYCLE=900

# Rollback freshness window only
# Edit .env:
MAX_ARTICLE_AGE_MINUTES=30

# Restart
sudo systemctl restart catalyst-bot
```

### Rollback Verification

```bash
# After rollback, verify settings
grep -E "RVOL_MIN_AVG_VOLUME|FEATURE_RVOL|FEATURE_FUNDAMENTAL|FEATURE_MARKET_REGIME|FEATURE_VOLUME_PRICE|LOOP_SECONDS|FEED_CYCLE|SEC_FEED_CYCLE|MAX_ARTICLE_AGE" .env

# Check logs for expected behavior
tail -f data/logs/bot.jsonl | grep -E "rvol|cycle_time|classification"

# Expected after rollback:
# - rvol_calculation messages (RVol re-enabled)
# - cycle_time ~60 seconds (LOOP_SECONDS restored)
# - classification_time 45-60 seconds (features re-enabled)
```

---

## Summary

### Configuration Checklist

- [ ] Backup current `.env` file
- [ ] Apply all 9 configuration changes
- [ ] Verify changes with `grep` commands
- [ ] Restart bot service
- [ ] Monitor logs for 1 hour
- [ ] Check alert latency (<5 min)
- [ ] Verify no API rate limit errors
- [ ] Confirm CPU usage <60%

### Expected Results

**After Migration:**
- Alert latency: <5 minutes (95-98% improvement)
- Noise rate: 11-19% (72-84% improvement)
- Classification time: <15 seconds (67-83% faster)
- API calls: ~300/hour (200% increase, acceptable)
- CPU usage: ~40% (5% increase, acceptable)

### Support

**Documentation:**
- Main Report: `docs/PATCH_WAVE_IMPLEMENTATION_REPORT.md`
- Retrospective Filter: `docs/RETROSPECTIVE_FILTER_REFERENCE.md`
- Testing Guide: `tests/test_wave_fixes_11_5_2025.py`

**Rollback:**
- See [Rollback Procedures](#rollback-procedures) section above

**Monitoring:**
```bash
# Watch logs
tail -f data/logs/bot.jsonl

# Filter for issues
tail -f data/logs/bot.jsonl | grep -E "ERROR|WARNING|429|timeout"
```

---

**Document Version:** 1.0
**Last Updated:** November 5, 2025
**Next Review:** November 12, 2025 (7 days post-deployment)
