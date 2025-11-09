# Deployment Checklist - 3 Patch Waves
**Quick Reference for Operations Team**

---

## Pre-Deployment (All Waves)

### Backup & Safety
- [ ] Backup current `.env` file to `.env.backup`
- [ ] Create git tag for current production: `git tag pre-patch-waves-$(date +%Y%m%d)`
- [ ] Create deployment branch: `git checkout -b patch-waves-deployment`
- [ ] Verify staging environment is ready
- [ ] Test rollback procedure in staging

### Monitoring Setup
- [ ] Enable detailed logging: `LOG_LEVEL=DEBUG` (temporary)
- [ ] Set up API rate limit monitoring dashboard
- [ ] Configure alerts for:
  - API rate limit errors (threshold: >5/hour)
  - Feed fetch failures (threshold: >10 consecutive)
  - Classification errors (threshold: >5/hour)
  - Database query time (threshold: >1s p95)

---

## Wave 1: Configuration Changes

### Phase 1A: Non-Critical Feature Flags (Low Risk)

**Estimated time**: 5 minutes
**Rollback time**: 1 minute

**Changes**:
```bash
# Edit .env
FEATURE_RVOL=0
FEATURE_MOMENTUM_INDICATORS=0
FEATURE_VOLUME_PRICE_DIVERGENCE=0
FEATURE_PREMARKET_SENTIMENT=0
FEATURE_AFTERMARKET_SENTIMENT=0
RVOL_MIN_AVG_VOLUME=50000
```

**Deployment**:
```bash
# 1. Edit .env file
nano .env

# 2. Verify changes
grep -E "FEATURE_RVOL|FEATURE_MOMENTUM|FEATURE_VOLUME_PRICE|FEATURE_PREMARKET|FEATURE_AFTERMARKET|RVOL_MIN_AVG_VOLUME" .env

# 3. Restart runner
systemctl restart catalyst-bot
# OR
pkill -f "python -m catalyst_bot.runner" && python -m catalyst_bot.runner --loop &

# 4. Verify features disabled
tail -f data/logs/bot.jsonl | grep -E "feature_rvol|feature_momentum"
```

**Verification** (5 minutes):
- [ ] Bot starts successfully
- [ ] No RVOL calculations in logs: `grep "rvol_calculated" data/logs/bot.jsonl`
- [ ] No momentum indicator calculations: `grep "momentum_indicators" data/logs/bot.jsonl`
- [ ] Classification still works: Check for `classified_item` logs
- [ ] Alerts still sent: Check Discord channel

**Success Criteria**:
- ✓ Bot running without errors
- ✓ 0 RVOL calculation logs
- ✓ 0 momentum indicator logs
- ✓ Classification score format unchanged
- ✓ Alerts still flowing

**Rollback if**:
- Classification errors > 5 in 5 minutes
- No alerts sent in 10 minutes
- Runner crashes

---

### Phase 1B: Article Freshness (Low Risk)

**Estimated time**: 2 minutes
**Rollback time**: 1 minute

**Changes**:
```bash
# Edit .env
MAX_ARTICLE_AGE_MINUTES=60
```

**Deployment**:
```bash
# 1. Edit .env
nano .env

# 2. Restart runner
systemctl restart catalyst-bot

# 3. Monitor article acceptance rate
tail -f data/logs/bot.jsonl | grep "article_age_check"
```

**Verification** (10 minutes):
- [ ] Articles up to 60 min old accepted
- [ ] Articles >60 min old rejected
- [ ] No duplicate alerts (SeenStore working)
- [ ] Alert volume increase <50%

**Success Criteria**:
- ✓ Article age threshold at 60 min
- ✓ No duplicate alerts
- ✓ Alert volume within expected range

**Rollback if**:
- Duplicate alerts appearing
- Alert volume >2x baseline

---

### Phase 1C: Cycle Time Changes (MEDIUM RISK ⚠️)

**Estimated time**: 10 minutes
**Rollback time**: 1 minute

**Pre-requisites**:
```bash
# 1. Add Alpha Vantage protection FIRST
nano .env

# Add these lines:
ALERT_CONSECUTIVE_EMPTY_CYCLES=10  # Was 5
# Note: AV caching already handled by existing TTL
```

**Changes**:
```bash
# Edit .env
MARKET_OPEN_CYCLE_SEC=20
EXTENDED_HOURS_CYCLE_SEC=30
```

**Deployment**:
```bash
# 1. Verify pre-requisites
grep "ALERT_CONSECUTIVE_EMPTY_CYCLES" .env
# Should show: ALERT_CONSECUTIVE_EMPTY_CYCLES=10

# 2. Edit cycle times
nano .env

# 3. Restart runner
systemctl restart catalyst-bot

# 4. Monitor cycle execution
tail -f data/logs/bot.jsonl | grep "cycle_complete"
```

**Verification** (30 minutes - CRITICAL):
- [ ] Cycle time = 20s during market hours (9:30-4pm ET)
- [ ] Cycle time = 30s during extended hours
- [ ] No API rate limit errors: `grep "rate_limit" data/logs/bot.jsonl`
- [ ] Feed fetch latency <2s: `grep "feed_fetch_latency" data/logs/bot.jsonl`
- [ ] No consecutive empty cycles alert
- [ ] Database query time <500ms: `grep "db_query_time" data/logs/bot.jsonl`

**Success Criteria**:
- ✓ Cycles running at 20s/30s intervals
- ✓ 0 API rate limit errors in 30 minutes
- ✓ Feed fetch latency p95 <2s
- ✓ No network failure alerts

**MONITOR CLOSELY FOR 24 HOURS**:
```bash
# Run every hour for 24 hours
watch -n 3600 'grep "rate_limit\|api_error" data/logs/bot.jsonl | tail -20'
```

**Rollback if**:
- API rate limit errors >5 in 30 minutes
- Feed fetch failures >10 consecutive
- Database query time >2s sustained
- Network failure alert triggered

**Rollback procedure**:
```bash
# 1. Revert .env
MARKET_OPEN_CYCLE_SEC=60
EXTENDED_HOURS_CYCLE_SEC=90

# 2. Restart
systemctl restart catalyst-bot

# 3. Verify slower cycles
tail -f data/logs/bot.jsonl | grep "cycle_complete"
```

---

## Wave 2: Retrospective Filter Enhancement

### ⚠️ BLOCKED - Awaiting User Input

**Missing Information**:
- Proposed new regex patterns not provided
- Cannot proceed without pattern specification

**When patterns provided**:

**Estimated time**: 5 minutes
**Rollback time**: 2 minutes

**Pre-deployment**:
- [ ] Review proposed regex patterns
- [ ] Validate regex syntax: `python -c "import re; re.compile(r'PATTERN')"`
- [ ] Run test suite: `pytest tests/test_retrospective_patterns.py -v`
- [ ] Test against real headlines (sample from last 24 hours)

**Deployment**:
```bash
# 1. Update feeds.py with new patterns
git checkout -b wave2-retrospective-filter
nano src/catalyst_bot/feeds.py  # Edit lines 195-203

# 2. Run tests
pytest tests/test_retrospective_patterns.py -v
pytest tests/test_wave_fixes_11_5_2025.py -v

# 3. Commit changes
git add src/catalyst_bot/feeds.py
git commit -m "Wave 2: Update retrospective filter patterns"

# 4. Deploy and restart
systemctl restart catalyst-bot
```

**Verification** (60 minutes):
- [ ] Test suite passes
- [ ] Retrospective rejection rate logged
- [ ] Compare to baseline rejection rate
- [ ] No false negatives (missed real-time catalysts)
- [ ] No false positives (accepted retrospective articles)

**Baseline metrics** (collect before deployment):
```bash
# Get current retrospective rejection rate
grep "retrospective_article_filtered" data/logs/bot.jsonl | wc -l
```

**Success Criteria**:
- ✓ All tests pass
- ✓ Rejection rate within ±30% of baseline
- ✓ No obvious false positives/negatives in logs

**Rollback if**:
- Tests fail
- Rejection rate changes >50%
- False positives/negatives confirmed

**Rollback procedure**:
```bash
# 1. Revert commit
git revert HEAD

# 2. Restart
systemctl restart catalyst-bot

# 3. Verify old patterns active
grep "_is_retrospective_article" src/catalyst_bot/feeds.py
```

---

## Wave 3: SEC Filing Alert Format

### ⚠️ BLOCKED - Awaiting User Input

**Missing Information**:
- Proposed formatting changes not specified
- Cannot proceed without change specification

**When changes provided**:

**Estimated time**: 5 minutes
**Rollback time**: 2 minutes

**Pre-deployment**:
- [ ] Review proposed format changes
- [ ] **CRITICAL**: Verify these fields remain:
  - `filing_section.filing_url` (deduplication)
  - `filing_section.ticker` (routing)
  - `filing_section.filing_type` (classification)
  - `embed.timestamp` (Discord requirement)
- [ ] Test Discord embed rendering in test webhook

**Deployment**:
```bash
# 1. Update sec_filing_alerts.py
git checkout -b wave3-sec-format
nano src/catalyst_bot/sec_filing_alerts.py

# 2. Test embed structure
python -c "from catalyst_bot.sec_filing_alerts import create_sec_filing_embed; print('OK')"

# 3. Commit changes
git add src/catalyst_bot/sec_filing_alerts.py
git commit -m "Wave 3: Update SEC filing alert format"

# 4. Deploy and restart
systemctl restart catalyst-bot
```

**Verification** (30 minutes):
- [ ] SEC filing alert sent successfully
- [ ] Discord embed renders correctly
- [ ] All buttons functional (View Filing, Dig Deeper, Chart)
- [ ] No deduplication errors: `grep "duplicate_sec_filing" data/logs/bot.jsonl`
- [ ] Ticker routing works correctly

**Success Criteria**:
- ✓ SEC alerts display correctly in Discord
- ✓ All interactive buttons work
- ✓ No deduplication errors
- ✓ Critical fields present

**Rollback if**:
- Discord embed rendering broken
- Deduplication errors appear
- Buttons non-functional
- Critical fields missing

**Rollback procedure**:
```bash
# 1. Revert commit
git revert HEAD

# 2. Restart
systemctl restart catalyst-bot

# 3. Verify old format active
tail -f data/logs/bot.jsonl | grep "sec_filing_alert_sent"
```

---

## Post-Deployment Monitoring (24 Hours)

### Critical Metrics Dashboard

**Every Hour** (automated):
```bash
#!/bin/bash
# Save as: monitor_patch_waves.sh

echo "=== Patch Waves Monitoring $(date) ==="

echo "1. API Rate Limits:"
grep -c "rate_limit" data/logs/bot.jsonl | tail -1

echo "2. Cycle Time (last 10):"
grep "cycle_complete" data/logs/bot.jsonl | tail -10 | grep -oP 'duration=\K[0-9.]+'

echo "3. Feed Fetch Latency (last 10):"
grep "feed_fetch" data/logs/bot.jsonl | tail -10 | grep -oP 'latency=\K[0-9.]+'

echo "4. Classification Errors (last hour):"
grep "classification_error" data/logs/bot.jsonl | grep "$(date -u +%Y-%m-%d)" | wc -l

echo "5. Retrospective Filter (last hour):"
grep "retrospective_article_filtered" data/logs/bot.jsonl | grep "$(date -u +%Y-%m-%d)" | wc -l

echo "6. Alert Volume (last hour):"
grep "alert_sent" data/logs/bot.jsonl | grep "$(date -u +%Y-%m-%d)" | wc -l

echo "7. Database Query Time (p95):"
grep "db_query_time" data/logs/bot.jsonl | tail -100 | grep -oP 'time=\K[0-9.]+' | sort -n | tail -5

echo "========================================"
```

**Run every hour**:
```bash
chmod +x monitor_patch_waves.sh
watch -n 3600 ./monitor_patch_waves.sh
```

### Alert Thresholds

**Immediate rollback if**:
- API rate limit errors >10 in 1 hour
- Classification errors >20 in 1 hour
- Feed fetch failures >20 consecutive
- Database query time >3s sustained
- Alert volume drops >50% for >2 hours
- Runner crashes >3 times in 1 hour

**Investigate if**:
- API rate limit errors >5 in 1 hour
- Classification errors >10 in 1 hour
- Feed fetch latency >2s p95
- Database query time >1s sustained
- Alert volume changes >30%

---

## Health Checks

### Quick Smoke Test (Run after each wave)
```bash
#!/bin/bash
# Save as: smoke_test.sh

echo "Running smoke test..."

# 1. Check runner is alive
pgrep -f "catalyst_bot.runner" > /dev/null && echo "✓ Runner alive" || echo "✗ Runner dead"

# 2. Check recent cycle
LAST_CYCLE=$(grep "cycle_complete" data/logs/bot.jsonl | tail -1)
if [ -n "$LAST_CYCLE" ]; then
    echo "✓ Last cycle: $LAST_CYCLE"
else
    echo "✗ No recent cycles"
fi

# 3. Check recent alert
LAST_ALERT=$(grep "alert_sent" data/logs/bot.jsonl | tail -1)
if [ -n "$LAST_ALERT" ]; then
    echo "✓ Last alert: $LAST_ALERT"
else
    echo "⚠ No recent alerts (may be normal)"
fi

# 4. Check errors in last 5 minutes
ERROR_COUNT=$(grep "ERROR" data/logs/bot.jsonl | grep "$(date -u +%Y-%m-%d)" | tail -100 | wc -l)
if [ "$ERROR_COUNT" -lt 5 ]; then
    echo "✓ Error count: $ERROR_COUNT (<5)"
else
    echo "✗ Error count: $ERROR_COUNT (>=5)"
fi

# 5. Check database connectivity
sqlite3 data/seen_store.db "SELECT COUNT(*) FROM seen_urls LIMIT 1" > /dev/null && echo "✓ Database accessible" || echo "✗ Database error"

echo "Smoke test complete."
```

**Run after each deployment**:
```bash
chmod +x smoke_test.sh
./smoke_test.sh
```

---

## Rollback Decision Matrix

| Symptom | Severity | Action | Time |
|---------|----------|--------|------|
| Runner crashes | CRITICAL | Rollback immediately | 1 min |
| API rate limits >10/hr | CRITICAL | Rollback Wave 1C | 1 min |
| Classification errors >20/hr | CRITICAL | Rollback all waves | 2 min |
| Feed failures >20 consecutive | CRITICAL | Rollback Wave 1C | 1 min |
| Alert volume drop >50% | HIGH | Investigate, rollback if not resolved in 30 min | 30 min |
| Duplicate SEC alerts | HIGH | Rollback Wave 3 | 2 min |
| DB query time >3s | HIGH | Rollback Wave 1C | 1 min |
| API rate limits 5-10/hr | MEDIUM | Monitor, may rollback if increasing | 1 hour |
| Alert volume change ±30% | MEDIUM | Monitor, investigate | 2 hours |
| Retrospective rejection rate change >50% | MEDIUM | Rollback Wave 2 | 2 min |

---

## Complete Rollback Procedure (All Waves)

**If critical failure occurs**:

```bash
#!/bin/bash
# Save as: emergency_rollback.sh

echo "=== EMERGENCY ROLLBACK ==="

# 1. Stop runner
systemctl stop catalyst-bot
# OR
pkill -9 -f "catalyst_bot.runner"

# 2. Restore .env
cp .env.backup .env
echo "✓ .env restored"

# 3. Revert code changes
git reset --hard pre-patch-waves-$(date +%Y%m%d)
echo "✓ Code reverted"

# 4. Restart runner
systemctl start catalyst-bot
# OR
python -m catalyst_bot.runner --loop &

# 5. Wait for startup
sleep 10

# 6. Verify
./smoke_test.sh

echo "=== ROLLBACK COMPLETE ==="
```

**Verify rollback**:
- [ ] Runner started successfully
- [ ] Smoke test passes
- [ ] Cycle time back to 60s/90s
- [ ] Features re-enabled (RVOL, momentum, etc.)
- [ ] Alert volume returns to baseline

---

## Sign-Off Checklist

### Wave 1 Phase 1A (Feature Flags)
- [ ] Deployed by: _________________ Date: _________
- [ ] Verified by: _________________ Date: _________
- [ ] Rollback tested: Yes / No
- [ ] Monitoring: Active / Not Active
- [ ] Status: ✓ Success / ✗ Rolled Back

### Wave 1 Phase 1B (Article Age)
- [ ] Deployed by: _________________ Date: _________
- [ ] Verified by: _________________ Date: _________
- [ ] Status: ✓ Success / ✗ Rolled Back

### Wave 1 Phase 1C (Cycle Times)
- [ ] Deployed by: _________________ Date: _________
- [ ] Verified by: _________________ Date: _________
- [ ] 24-hour monitoring complete: Yes / No
- [ ] API rate limits acceptable: Yes / No
- [ ] Status: ✓ Success / ✗ Rolled Back

### Wave 2 (Retrospective Filter)
- [ ] Blocked pending user input: Yes
- [ ] User provided patterns: Yes / No
- [ ] Deployed by: _________________ Date: _________
- [ ] Test suite passed: Yes / No
- [ ] Status: ✓ Success / ✗ Rolled Back

### Wave 3 (SEC Format)
- [ ] Blocked pending user input: Yes
- [ ] User provided changes: Yes / No
- [ ] Deployed by: _________________ Date: _________
- [ ] Discord embeds verified: Yes / No
- [ ] Status: ✓ Success / ✗ Rolled Back

### Final Sign-Off
- [ ] All waves deployed: Yes / No
- [ ] 24-hour monitoring complete: Yes / No
- [ ] No critical issues: Yes / No
- [ ] Production stable: Yes / No
- [ ] Deployment complete: ✓ / ✗

**Deployment Lead**: _________________
**Date**: _________
**Signature**: _________________

---

**Checklist Version**: 1.0
**Generated**: 2025-11-05
**Agent**: Architecture Stability Validator
