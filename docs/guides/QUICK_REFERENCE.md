# Quick Reference Card - 3 Patch Waves
**One-Page Operations Guide**

---

## TL;DR - What's Changing?

| Change | From | To | Risk | Deploy Time |
|--------|------|-----|------|-------------|
| RVOL feature | ON | OFF | LOW | 1 min |
| Momentum indicators | ON | OFF | LOW | 1 min |
| Pre/After sentiment | ON | OFF | LOW | 1 min |
| RVOL min volume | 100K | 50K | LOW | 1 min |
| Article freshness | 30 min | 60 min | LOW | 1 min |
| **Market cycle time** | **60s** | **20s** | **MEDIUM** | 1 min + 24h monitor |
| **Extended cycle time** | **90s** | **30s** | **MEDIUM** | 1 min + 24h monitor |
| Retrospective filter | Old regex | New regex | LOW | 2 min (BLOCKED) |
| SEC alert format | Current | New format | LOW | 2 min (BLOCKED) |

---

## Critical Actions

### Before Deploying Cycle Time Changes ⚠️

**MUST DO**:
```bash
# Edit .env - ADD THIS LINE
ALERT_CONSECUTIVE_EMPTY_CYCLES=10

# Verify it's there
grep "ALERT_CONSECUTIVE_EMPTY_CYCLES" .env
# Should show: ALERT_CONSECUTIVE_EMPTY_CYCLES=10
```

**Why**: Prevents false network alerts due to faster cycles.

---

## 30-Second Deployment (Wave 1A+1B)

```bash
# 1. Edit .env
nano .env

# 2. Change these lines:
FEATURE_RVOL=0
FEATURE_MOMENTUM_INDICATORS=0
FEATURE_VOLUME_PRICE_DIVERGENCE=0
FEATURE_PREMARKET_SENTIMENT=0
FEATURE_AFTERMARKET_SENTIMENT=0
RVOL_MIN_AVG_VOLUME=50000
MAX_ARTICLE_AGE_MINUTES=60

# 3. Restart
systemctl restart catalyst-bot

# 4. Verify
tail -f data/logs/bot.jsonl | grep "cycle_complete"
```

**Expected**: Bot runs normally, features disabled in logs.

---

## 2-Minute Deployment (Wave 1C - Cycle Times)

**CRITICAL**: Only after Wave 1A+1B is stable!

```bash
# 1. Verify alert threshold is set
grep "ALERT_CONSECUTIVE_EMPTY_CYCLES=10" .env
# If not found, ADD IT FIRST!

# 2. Edit .env
nano .env

# 3. Change cycle times:
MARKET_OPEN_CYCLE_SEC=20
EXTENDED_HOURS_CYCLE_SEC=30

# 4. Restart
systemctl restart catalyst-bot

# 5. Monitor for 1 hour (CRITICAL)
watch -n 60 'grep "rate_limit\|api_error" data/logs/bot.jsonl | tail -10'
```

**Expected**: Cycles every 20s, no rate limit errors.

**If rate limit errors appear**: ROLLBACK IMMEDIATELY (see below).

---

## Emergency Rollback (1 Minute)

```bash
# 1. Edit .env
nano .env

# 2. Revert to these values:
FEATURE_RVOL=1
FEATURE_MOMENTUM_INDICATORS=1
FEATURE_VOLUME_PRICE_DIVERGENCE=1
FEATURE_PREMARKET_SENTIMENT=1
FEATURE_AFTERMARKET_SENTIMENT=1
RVOL_MIN_AVG_VOLUME=100000
MAX_ARTICLE_AGE_MINUTES=30
MARKET_OPEN_CYCLE_SEC=60
EXTENDED_HOURS_CYCLE_SEC=90
ALERT_CONSECUTIVE_EMPTY_CYCLES=5

# 3. Restart
systemctl restart catalyst-bot

# 4. Verify
tail -f data/logs/bot.jsonl | grep "feature_rvol=True"
```

**OR** use backup:
```bash
cp .env.backup .env
systemctl restart catalyst-bot
```

---

## Health Check (30 Seconds)

```bash
# Quick smoke test
pgrep -f "catalyst_bot.runner" && echo "✓ Running" || echo "✗ Dead"

# Recent cycle
grep "cycle_complete" data/logs/bot.jsonl | tail -1

# Recent alert
grep "alert_sent" data/logs/bot.jsonl | tail -1

# Error count (last 100 lines)
grep "ERROR" data/logs/bot.jsonl | tail -100 | wc -l
# Should be <5
```

---

## Monitoring (Every Hour for 24 Hours)

```bash
# 1. Rate limit errors (CRITICAL - should be 0)
grep -c "rate_limit" data/logs/bot.jsonl

# 2. Cycle time (should be ~20s during market hours)
grep "cycle_complete" data/logs/bot.jsonl | tail -1 | grep -oP 'duration=\K[0-9.]+'

# 3. Alert volume (should be within 50% of baseline)
grep -c "alert_sent" data/logs/bot.jsonl

# 4. Errors (should be <10/hour)
grep "ERROR" data/logs/bot.jsonl | grep "$(date -u +%Y-%m-%d)" | tail -100 | wc -l
```

**If any metric out of range**: Investigate or rollback.

---

## When to Rollback

| Symptom | Action |
|---------|--------|
| Runner crashes | ROLLBACK NOW |
| Rate limit errors >5 in 1 hour | ROLLBACK NOW |
| No alerts for 30 minutes | ROLLBACK NOW |
| Error count >20 in 1 hour | ROLLBACK NOW |
| Cycle time stuck at 60s | Restart runner |
| Alert volume drops >50% | Investigate 30 min, then rollback |

---

## Wave 2 & 3 Status

**Wave 2 (Retrospective Filter)**: ⚠️ BLOCKED
- Need: Regex patterns from user
- Deploy: When patterns provided (~2 min)

**Wave 3 (SEC Format)**: ⚠️ BLOCKED
- Need: Format changes from user
- Deploy: When changes provided (~2 min)

---

## Contact

**Issues**: Check `ARCHITECTURE_STABILITY_REPORT.md`
**Details**: Check `DEPLOYMENT_CHECKLIST.md`
**Questions**: Check `VALIDATION_SUMMARY.md`

---

## Deployment Sign-Off

- [ ] Wave 1A+1B deployed: _________ (date/time)
- [ ] Wave 1A+1B verified: _________ (initials)
- [ ] Wave 1C deployed: _________ (date/time)
- [ ] Wave 1C 24h monitoring complete: _________ (date/time)
- [ ] Wave 1C verified stable: _________ (initials)

**Deployment Lead**: _________________
**Date**: _________

---

**Version**: 1.0 | **Generated**: 2025-11-05 | **Agent**: Architecture Stability Validator
