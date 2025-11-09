# Catalyst Bot - Wave 1-3 Deployment Guide

**Version:** Wave 1-3 Production Release
**Date:** 2025-10-25
**Deployment Type:** Phased rollout recommended

## Executive Summary

This guide covers the deployment of Waves 1-3 improvements to the Catalyst Bot production environment. These changes include:

- **Wave 1 (Critical Filters):** Age-based filtering, OTC stock blocking, enhanced logging
- **Wave 2 (Alert Layout):** Restructured Discord embeds, badge system, sentiment gauge improvements
- **Wave 3 (Data Quality):** Float data caching, chart gap filling, multi-ticker intelligence, offering sentiment correction

**Impact Level:** Medium (user-visible changes, new features, no breaking changes)
**Downtime Required:** None (rolling restart)
**Rollback Complexity:** Low (environment variables control all features)

---

## Table of Contents

1. [Pre-Deployment Checklist](#pre-deployment-checklist)
2. [Deployment Steps](#deployment-steps)
3. [Feature Validation](#feature-validation)
4. [Rollback Procedure](#rollback-procedure)
5. [Monitoring & Metrics](#monitoring--metrics)
6. [Troubleshooting](#troubleshooting)

---

## Pre-Deployment Checklist

### Required Actions

- [ ] **Backup current configuration**
  ```bash
  cp .env .env.backup.$(date +%Y%m%d)
  ```

- [ ] **Review git status and commit changes**
  ```bash
  git status
  git stash  # if uncommitted changes exist
  ```

- [ ] **Test in staging environment** (if available)
  - Run bot for 1 hour minimum
  - Verify alert appearance
  - Check log output format

- [ ] **Update dependencies** (if needed)
  ```bash
  pip install -r requirements.txt
  ```

- [ ] **Verify Discord webhook connectivity**
  ```bash
  curl -X POST "$DISCORD_WEBHOOK_URL" \
    -H "Content-Type: application/json" \
    -d '{"content":"Deployment test message"}'
  ```

- [ ] **Check disk space** for new cache files
  ```bash
  df -h data/cache/
  ```

- [ ] **Review configuration guide** for new environment variables

---

## Deployment Steps

### Recommended Approach: Phased Rollout

Deploy waves sequentially to isolate potential issues and validate each set of changes independently.

---

### Phase 1: Wave 1 - Critical Filters (30 minutes)

**Goal:** Reduce noise from stale news and OTC stocks

#### 1.1 Update Environment Variables

Add the following to your `.env` file:

```bash
# =============================================================================
# WAVE 1: Critical Filters
# =============================================================================

# Article Age Limits (prevent stale news alerts)
MAX_ARTICLE_AGE_MINUTES=30          # Regular news: 30 min
MAX_SEC_FILING_AGE_MINUTES=240      # SEC filings: 4 hours (slower processing)

# OTC Stock Filter (block illiquid penny stocks)
FILTER_OTC_STOCKS=1                 # 1=enabled, 0=disabled
```

#### 1.2 Restart Bot

```bash
# Stop current process (if using systemd)
sudo systemctl restart catalyst-bot

# OR if running manually
pkill -f "python.*runner.py"
python -m src.catalyst_bot.runner
```

#### 1.3 Validation (15 minutes)

Monitor logs for new rejection reasons:

```bash
tail -f data/logs/bot.jsonl | grep -E "stale_article|otc_exchange"
```

**Expected behavior:**
- Articles older than 30 minutes are logged as `rejection_reason=stale_article`
- OTC stocks are logged as `rejection_reason=otc_exchange`
- Rejection counters appear in logs: `skipped_stale=5 skipped_otc=3`

**Success Criteria:**
- No crashes or errors in logs
- Alerts continue to flow (reduced volume expected)
- Rejection counters incrementing properly

---

### Phase 2: Wave 2 - Alert Layout (1 hour)

**Goal:** Improve alert readability and visual hierarchy

#### 2.1 No Environment Variable Changes Required

Wave 2 changes are **automatic** when the new code is deployed. The alert layout refactoring is built into `discord_interactions.py`.

#### 2.2 Restart Bot (if not done in Phase 1)

```bash
sudo systemctl restart catalyst-bot
```

#### 2.3 Validation (30 minutes)

Check Discord channel for new alert format:

**Before Wave 2 (15-20 fields):**
```
┌─────────────────────────────┐
│ Field 1: Ticker             │
│ Field 2: Price              │
│ Field 3: Change             │
│ Field 4: Volume             │
│ Field 5: Sentiment          │
│ ... (15-20 total fields)    │
└─────────────────────────────┘
```

**After Wave 2 (4-6 fields):**
```
┌─────────────────────────────┐
│ 📊 EARNINGS | Score: 8.5    │ ← Catalyst badge
│                             │
│ Price & Volume (inline)     │ ← Consolidated metrics
│ Sentiment ⚫⚫⚫⚫⚫⚪⚪⚪⚪⚪    │ ← Visual gauge (10 circles)
│ Catalyst Details            │ ← Compact summary
│                             │
│ ⏰ 2 minutes ago            │ ← Footer timestamp
└─────────────────────────────┘
```

**Expected Changes:**
- **Catalyst Badges:** 📊 EARNINGS, 💊 FDA NEWS, 🤝 M&A, etc.
- **Sentiment Gauge:** 10-circle visualization (was 5)
- **Field Count:** 4-6 fields (was 15-20)
- **Footer:** Single line with timestamp (was multi-line)

**Success Criteria:**
- Alerts appear with new compact layout
- Badges display correctly
- Sentiment gauge shows 10 circles
- No formatting errors or broken embeds

---

### Phase 3: Wave 3 - Data Quality (1-2 hours)

**Goal:** Improve float data reliability, chart quality, and multi-ticker handling

#### 3.1 Update Environment Variables

Add to `.env`:

```bash
# =============================================================================
# WAVE 3: Data Quality Improvements
# =============================================================================

# Float Data Caching (reduce API calls, improve reliability)
FLOAT_CACHE_MAX_AGE_HOURS=24        # Cache float data for 24h
FLOAT_DATA_ENABLE_CACHE=1           # Enable caching (default: on)
# Cache file: data/cache/float_cache.json (created automatically)

# Chart Gap Filling (smooth premarket/afterhours charts)
CHART_FILL_EXTENDED_HOURS=1         # Fill data gaps (default: on)
CHART_FILL_METHOD=forward_fill      # Options: forward_fill, interpolate, flat_line
CHART_SHOW_EXTENDED_HOURS_ANNOTATION=1  # Show premarket/AH zones

# Multi-Ticker Article Intelligence
FEATURE_MULTI_TICKER_SCORING=1      # Score ticker relevance (default: on)
MULTI_TICKER_MIN_RELEVANCE_SCORE=40 # Threshold: 40 (moderate relevance)
MULTI_TICKER_MAX_PRIMARY=2          # Max primary tickers per article
MULTI_TICKER_SCORE_DIFF_THRESHOLD=30  # Single vs multi-ticker threshold
```

#### 3.2 Create Cache Directory

```bash
mkdir -p data/cache
chmod 755 data/cache
```

#### 3.3 Restart Bot

```bash
sudo systemctl restart catalyst-bot
```

#### 3.4 Validation (45 minutes)

**Float Data Caching:**

```bash
# Check cache file creation
ls -lh data/cache/float_cache.json

# Monitor cache hits/misses in logs
tail -f data/logs/bot.jsonl | grep "float_cache"
```

**Expected:**
- Cache file created after first float lookup
- Cache hits logged as `float_cache_hit=true`
- Cache misses trigger API calls, then cache update

**Chart Gap Filling:**

Generate a test chart during premarket/afterhours:

```bash
# If market is closed, test manually
python -c "
from src.catalyst_bot.charts_advanced import generate_chart
generate_chart('AAPL', timeframe='1D', show_extended=True)
"
```

**Expected:**
- Gaps in premarket/afterhours filled with dashed lines
- Shaded zones for extended hours
- No sudden drops to zero volume

**Multi-Ticker Intelligence:**

Monitor logs for multi-ticker articles:

```bash
tail -f data/logs/bot.jsonl | grep "multi_ticker"
```

**Expected:**
- Articles with multiple tickers are scored
- Primary tickers receive alerts
- Secondary tickers listed in metadata
- Log entries: `primary_tickers=AAPL secondary_tickers=MSFT,GOOGL`

**Success Criteria:**
- Float cache file created and populated
- Charts display smoothly without gaps
- Multi-ticker articles only alert primary subjects
- No increase in API errors

---

## Feature Validation

### Post-Deployment Testing (2 hours)

Run comprehensive tests to validate all waves:

#### Test 1: Article Age Filter

```bash
# Manually inject an old article (for testing only)
# Expected: Article rejected with reason=stale_article
```

**Pass Criteria:** Old articles do not generate alerts

#### Test 2: OTC Stock Filter

```bash
# Test with known OTC ticker (e.g., MMTXU, RVLY)
# Expected: Ticker rejected with reason=otc_exchange
```

**Pass Criteria:** OTC stocks do not generate alerts

#### Test 3: Alert Layout

**Pass Criteria:**
- Alerts have 4-6 fields (not 15-20)
- Catalyst badge visible in title
- Sentiment gauge shows 10 circles
- Footer shows timestamp only

#### Test 4: Float Data Cache

```bash
# Check cache file
cat data/cache/float_cache.json | jq '.AAPL'
```

**Expected Output:**
```json
{
  "AAPL": {
    "float": 15300000000,
    "timestamp": 1729890000,
    "source": "yfinance"
  }
}
```

**Pass Criteria:** Cache populated and used for subsequent lookups

#### Test 5: Multi-Ticker Articles

Monitor for articles mentioning multiple tickers:

**Pass Criteria:**
- Only primary ticker receives alert
- Secondary tickers listed in metadata: `"Also mentions: MSFT, GOOGL"`

---

## Rollback Procedure

### If Issues Arise

Wave 1-3 changes are **feature-flagged** via environment variables. You can roll back individual waves without redeploying code.

#### Quick Rollback (5 minutes)

**Disable all Wave 1-3 features:**

```bash
# Edit .env
FILTER_OTC_STOCKS=0                    # Disable OTC filter
MAX_ARTICLE_AGE_MINUTES=999999         # Disable age filter
FEATURE_MULTI_TICKER_SCORING=0         # Disable multi-ticker scoring
CHART_FILL_EXTENDED_HOURS=0            # Disable chart gap filling

# Restart bot
sudo systemctl restart catalyst-bot
```

**Result:** Bot reverts to pre-Wave 1-3 behavior immediately.

#### Selective Rollback

Roll back individual waves if needed:

**Rollback Wave 1 only:**
```bash
FILTER_OTC_STOCKS=0
MAX_ARTICLE_AGE_MINUTES=999999
MAX_SEC_FILING_AGE_MINUTES=999999
```

**Rollback Wave 3 only:**
```bash
FEATURE_MULTI_TICKER_SCORING=0
CHART_FILL_EXTENDED_HOURS=0
FLOAT_DATA_ENABLE_CACHE=0
```

**Note:** Wave 2 (alert layout) cannot be rolled back via environment variables. To revert, you must checkout previous code:

```bash
git checkout HEAD~1 src/catalyst_bot/discord_interactions.py
sudo systemctl restart catalyst-bot
```

#### Full Code Rollback (10 minutes)

If environment variable rollback is insufficient:

```bash
# Restore previous commit
git log --oneline -n 5  # Find commit before Wave 1-3
git checkout <commit-hash>

# Restore backup .env
cp .env.backup.YYYYMMDD .env

# Restart bot
sudo systemctl restart catalyst-bot
```

---

## Monitoring & Metrics

### Key Metrics to Watch (First 24 Hours)

#### 1. Alert Volume

**Expected:** 20-40% reduction in alert count due to filters

```bash
# Count alerts per hour
grep "alert_sent" data/logs/bot.jsonl | \
  awk -F'"' '{print $4}' | \
  cut -d'T' -f2 | cut -d':' -f1 | \
  sort | uniq -c
```

**Baseline (pre-Wave 1):** ~40-60 alerts/hour
**Expected (post-Wave 1):** ~25-40 alerts/hour

#### 2. Rejection Reasons

```bash
# Top rejection reasons
grep "rejection_reason" data/logs/bot.jsonl | \
  jq -r '.rejection_reason' | \
  sort | uniq -c | sort -rn
```

**Expected Distribution:**
```
150 stale_article       # Articles older than 30 min
 45 otc_exchange        # OTC stocks
 30 low_relevance       # Multi-ticker secondary mentions
 20 price_ceiling       # Above $10 (existing)
```

#### 3. Cache Performance

```bash
# Float cache hit rate
grep "float_cache" data/logs/bot.jsonl | \
  jq -r '.float_cache_hit' | \
  awk '{hits+=$1; total+=1} END {print hits/total*100 "%"}'
```

**Target:** >70% cache hit rate after 1 hour

#### 4. API Error Rate

```bash
# Check for increased API errors
grep "api_error" data/logs/bot.jsonl | wc -l
```

**Baseline:** <5 errors/hour
**Threshold:** >10 errors/hour (investigate)

#### 5. Discord Delivery Success Rate

```bash
# Check Discord webhook errors
grep "discord_error" data/logs/bot.jsonl | wc -l
```

**Target:** 0 errors/hour
**Threshold:** >1 error/hour (investigate)

### Monitoring Dashboard Commands

**Real-time monitoring (recommended for first 2 hours):**

```bash
# Terminal 1: Alert flow
watch -n 10 'tail -20 data/logs/bot.jsonl | grep "alert_sent" | jq -r ".ticker"'

# Terminal 2: Rejection tracking
watch -n 30 'grep "rejection_reason" data/logs/bot.jsonl | tail -20 | jq -r ".rejection_reason"'

# Terminal 3: Error monitoring
watch -n 60 'grep -E "error|exception" data/logs/bot.jsonl | tail -10'
```

---

## Troubleshooting

### Common Issues & Solutions

#### Issue 1: High Rejection Rate (>80% of articles filtered)

**Symptoms:**
- Very few alerts being sent
- Logs show `skipped_stale=200` or `skipped_otc=150`

**Diagnosis:**
```bash
grep "rejection_reason" data/logs/bot.jsonl | \
  jq -r '.rejection_reason' | \
  sort | uniq -c
```

**Solution:**
```bash
# Relax age filter temporarily
MAX_ARTICLE_AGE_MINUTES=60  # Increase from 30 to 60

# Verify OTC filter isn't too aggressive
FILTER_OTC_STOCKS=0  # Disable temporarily to test
```

#### Issue 2: Float Cache Not Populating

**Symptoms:**
- `data/cache/float_cache.json` is empty or missing
- Logs show `float_cache_hit=false` for all tickers

**Diagnosis:**
```bash
ls -lh data/cache/float_cache.json
cat data/cache/float_cache.json
```

**Solution:**
```bash
# Check directory permissions
chmod 755 data/cache

# Verify cache is enabled
grep FLOAT_DATA_ENABLE_CACHE .env  # Should be 1

# Restart bot
sudo systemctl restart catalyst-bot
```

#### Issue 3: Discord Embeds Not Displaying Correctly

**Symptoms:**
- Badges missing or showing raw text
- Sentiment gauge broken
- Fields misaligned

**Diagnosis:**
Check Discord webhook version and bot code version:

```bash
git log --oneline -n 1 src/catalyst_bot/discord_interactions.py
```

**Solution:**
```bash
# Verify latest code is deployed
git pull origin main
sudo systemctl restart catalyst-bot

# If embeds still broken, check Discord API status
curl -I https://discord.com/api/v10
```

#### Issue 4: Multi-Ticker Articles Still Alerting All Tickers

**Symptoms:**
- Same article alerts multiple tickers
- Logs show `multi_ticker_scoring=false`

**Diagnosis:**
```bash
grep "FEATURE_MULTI_TICKER_SCORING" .env
```

**Solution:**
```bash
# Enable multi-ticker scoring
FEATURE_MULTI_TICKER_SCORING=1

# Restart bot
sudo systemctl restart catalyst-bot
```

#### Issue 5: Chart Gap Filling Causing Visual Artifacts

**Symptoms:**
- Charts show flat lines during market hours
- Gaps not being filled in premarket/afterhours

**Diagnosis:**
Check chart fill method:

```bash
grep CHART_FILL .env
```

**Solution:**
```bash
# Try different fill method
CHART_FILL_METHOD=forward_fill  # Change from interpolate

# Or disable gap filling temporarily
CHART_FILL_EXTENDED_HOURS=0
```

---

## Expected Behavior Changes

### User-Facing Changes

**Before Waves 1-3:**
- Alerts for all articles regardless of age
- OTC stocks included in alerts
- Verbose Discord embeds (15-20 fields)
- Multi-ticker articles alert all mentioned tickers
- Chart gaps during extended hours

**After Waves 1-3:**
- Only fresh articles (< 30 min) generate alerts
- OTC stocks filtered out
- Compact Discord embeds (4-6 fields)
- Multi-ticker articles alert only primary subjects
- Smooth charts during extended hours

### Alert Volume Impact

**Conservative Estimate:**
- Stale article filter: -20% alert volume
- OTC filter: -10% alert volume
- Multi-ticker scoring: -5% alert volume
- **Total reduction: ~30-35% fewer alerts**

**This is a feature, not a bug!** The goal is to improve signal-to-noise ratio.

---

## Success Criteria

### Phase 1 (Wave 1) Success

- [ ] Bot running without crashes for 1 hour
- [ ] Rejection counters appearing in logs
- [ ] Stale articles not generating alerts
- [ ] OTC stocks not generating alerts

### Phase 2 (Wave 2) Success

- [ ] Discord embeds display with new compact layout
- [ ] Catalyst badges visible in titles
- [ ] Sentiment gauge shows 10 circles
- [ ] Footer contains timestamp only

### Phase 3 (Wave 3) Success

- [ ] Float cache file created and populated
- [ ] Cache hit rate >70% after 1 hour
- [ ] Charts display smoothly without gaps
- [ ] Multi-ticker articles only alert primary tickers

### Overall Deployment Success

- [ ] All waves validated independently
- [ ] Alert volume reduced by 20-40%
- [ ] No increase in error rate
- [ ] User feedback positive on new alert layout
- [ ] System stable for 24 hours

---

## Post-Deployment Tasks

### Week 1

- [ ] Monitor alert volume trends daily
- [ ] Review rejection reason distribution
- [ ] Gather user feedback on new alert layout
- [ ] Adjust age thresholds if needed

### Week 2

- [ ] Analyze cache performance metrics
- [ ] Review multi-ticker classification accuracy
- [ ] Optimize chart gap filling parameters
- [ ] Document any configuration tweaks made

### Month 1

- [ ] Compare alert quality pre/post deployment
- [ ] Measure false positive reduction
- [ ] Plan Wave 4+ features based on learnings

---

## Support & Escalation

**For deployment issues:**
1. Check this troubleshooting guide first
2. Review logs: `data/logs/bot.jsonl`
3. Consult CONFIGURATION_GUIDE.md for settings
4. Test rollback procedure if critical

**Emergency Rollback Contact:**
- Create GitHub issue with logs attached
- Tag: `deployment`, `wave-1-3`, `production`

**Non-Critical Issues:**
- Document in GitHub issues
- Continue monitoring for 24 hours
- Adjust configuration as needed

---

## Appendix: Configuration Quick Reference

### Wave 1 Variables
```bash
MAX_ARTICLE_AGE_MINUTES=30
MAX_SEC_FILING_AGE_MINUTES=240
FILTER_OTC_STOCKS=1
```

### Wave 2 Variables
*(No variables - automatic)*

### Wave 3 Variables
```bash
FLOAT_CACHE_MAX_AGE_HOURS=24
CHART_FILL_EXTENDED_HOURS=1
CHART_FILL_METHOD=forward_fill
FEATURE_MULTI_TICKER_SCORING=1
MULTI_TICKER_MIN_RELEVANCE_SCORE=40
```

### Monitoring Commands
```bash
# Alert count
grep "alert_sent" data/logs/bot.jsonl | wc -l

# Rejection reasons
grep "rejection_reason" data/logs/bot.jsonl | jq -r '.rejection_reason' | sort | uniq -c

# Cache performance
ls -lh data/cache/float_cache.json
```

---

**End of Deployment Guide**
