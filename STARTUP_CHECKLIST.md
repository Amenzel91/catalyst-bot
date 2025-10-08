# 🚀 Catalyst-Bot Startup Checklist

**Last Updated:** 2025-10-06
**Status:** Production Ready

---

## Pre-Flight Checks ✓

### 1. Environment Setup
- [ ] Virtual environment activated: `.venv\Scripts\activate`
- [ ] All dependencies installed: `pip install -r requirements.txt`
- [ ] `.env` file exists and configured
- [ ] Discord bot token set in `.env`

### 2. External Services
- [ ] **Ollama running** (for LLM sentiment)
  ```bash
  ollama serve
  ```
  Test: `curl http://localhost:11434`

- [ ] **QuickChart running** (for advanced charts - optional)
  ```bash
  start_quickchart.bat
  ```
  Test: `curl http://localhost:3400`

- [ ] **Cloudflare Tunnel running** (for Discord interactions)
  ```bash
  cloudflare-tunnel-windows-amd64.exe tunnel --url http://localhost:8081
  ```
  Copy the URL it gives you!

### 3. Configuration Verification
- [ ] Check critical settings in `.env`:
  ```ini
  DISCORD_BOT_TOKEN=        # Set
  DISCORD_WEBHOOK_URL=      # Set
  DISCORD_APPLICATION_ID=   # Set (for slash commands)
  FEATURE_MARKET_HOURS_DETECTION=1
  FEATURE_FEEDBACK_LOOP=1
  FEATURE_ML_SENTIMENT=1
  ```

---

## Startup Sequence 🎬

### Option A: Quick Test (Single Cycle)
**Use this for testing new features**

1. Start bot in test mode:
   ```bash
   python -m catalyst_bot.runner --once
   ```

2. Check logs:
   ```bash
   type data\logs\bot.jsonl | findstr ERROR
   ```

3. Expected output:
   - Market status detected
   - Databases initialized
   - One cycle completed
   - No critical errors

---

### Option B: Full Production Start
**Use this for live trading alerts**

#### Terminal 1: Interaction Server (Discord Buttons)
```bash
python interaction_server.py
```
**Expected:** Server running on port 8081

#### Terminal 2: Main Bot
```bash
python -m catalyst_bot.runner
```
**Expected:** Continuous cycles every 60-180s based on market hours

---

## First Cycle Verification ✅

Watch for these log messages:

### **1. Initialization**
```
process_priority_set priority=BELOW_NORMAL
ml_sentiment_model_loaded model=finbert
feedback_loop_database_initialized
health_monitor_initialized
```

### **2. Market Hours Detection**
```
market_status status=pre_market cycle=90s features=llm_enabled,breakout_enabled
```
**OR** (during market hours):
```
market_status status=regular cycle=60s features=llm_enabled,charts_enabled,breakout_enabled
```

### **3. Sentiment Aggregation**
```
sentiment_aggregated sources={'vader': '0.650', 'earnings': '0.850', 'ml': '0.700'} final=0.750 confidence=0.850
```

### **4. Alert Posted**
```
alert_posted ticker=AAPL score=5.2 sentiment=0.75
feedback_alert_recorded alert_id=abc123
```

---

## Health Checks 🏥

### Quick Health Check
```bash
curl http://localhost:8080/health/ping
```
**Expected:** `ok`

### Detailed Health
```bash
curl http://localhost:8080/health/detailed
```
**Expected:** JSON with uptime, GPU stats, cycles, alerts

### GPU Check (if using ML sentiment)
```bash
python -c "from catalyst_bot.gpu_monitor import get_gpu_stats; print(get_gpu_stats())"
```
**Expected:** GPU utilization, VRAM usage

---

## Common Issues & Fixes 🔧

### ❌ Import Errors
**Problem:** `ModuleNotFoundError: No module named 'X'`
**Fix:**
```bash
pip install -r requirements.txt
```

### ❌ Database Locked
**Problem:** `database is locked`
**Fix:**
```bash
# Stop all bot instances
# Delete lock files
del data\feedback\*.db-wal
del data\feedback\*.db-shm
```

### ❌ GPU Not Available
**Problem:** `CUDA not available` or `ML model failed to load`
**Fix:** CPU fallback is automatic, but you can disable:
```ini
# .env
FEATURE_ML_SENTIMENT=0
```

### ❌ QuickChart Not Responding
**Problem:** Charts fail to generate
**Fix:**
```bash
# Restart QuickChart container
docker-compose restart quickchart

# OR fallback to Tiingo charts
FEATURE_QUICKCHART=0
```

### ❌ Market Hours Wrong
**Problem:** Bot thinks market is closed when it's open
**Fix:** Check your system timezone:
```bash
# Windows
tzutil /g
# Should be in US timezone or UTC
```

---

## Performance Monitoring 📊

### Check Cycle Times
```bash
# View last 10 cycles
type data\logs\bot.jsonl | findstr "CYCLE_DONE" | more +10
```
**Expected:** 2-5 seconds per cycle

### Check Memory Usage
```bash
# Windows Task Manager
tasklist | findstr python
```
**Expected:** 200-500MB RAM, <50% GPU during cycles

### Check Alert Rate
```bash
# Count alerts posted today
type data\logs\bot.jsonl | findstr "alert_posted" | find /c /v ""
```

---

## Shutdown Sequence 🛑

### Graceful Shutdown
1. Stop interaction server (Ctrl+C in Terminal 1)
2. Stop bot (Ctrl+C in Terminal 2)
3. Wait for "shutting down" message
4. **DO NOT** force kill (data may be lost)

### Emergency Stop
```bash
# Windows
taskkill /IM python.exe /F
```
**Warning:** May corrupt databases. Only use if frozen.

---

## Post-Run Checks ✓

### Verify Data Saved
```bash
# Check recent alerts
dir data\events.jsonl

# Check feedback database
dir data\feedback\alert_performance.db
```

### Review Logs
```bash
# Check for errors
type data\logs\errors.log

# Check sentiment breakdown
type data\logs\bot.jsonl | findstr "sentiment_aggregated"
```

### Generate Report (Optional)
```bash
# Run analyzer on last cycle
python -m catalyst_bot.analyzer
```

---

## Daily Maintenance 🧹

### Every Day:
- [ ] Check error logs: `type data\logs\errors.log`
- [ ] Verify alerts posting to Discord
- [ ] Review feedback loop stats (if enabled)

### Every Week:
- [ ] Check feedback weekly report (Sunday 23:00 UTC)
- [ ] Review keyword performance
- [ ] Update API keys if needed

### Every Month:
- [ ] Review and clean old logs (>30 days)
- [ ] Backup `.env` file
- [ ] Update dependencies: `pip install -r requirements.txt --upgrade`

---

## Troubleshooting Commands 🔍

### Get Bot Status
```bash
# If running as service
nssm status CatalystBot

# Check processes
tasklist | findstr python
```

### Test Individual Components
```bash
# Test market hours
python test_market_hours.py

# Test sentiment aggregation
python test_sentiment_aggregation.py

# Test earnings scorer
python -m catalyst_bot.earnings_scorer
```

### View Live Logs
```bash
# Real-time log monitoring
powershell "Get-Content data\logs\bot.jsonl -Wait -Tail 20"
```

---

## Success Criteria ✅

Your bot is running successfully if:

- ✅ No errors in `data\logs\errors.log`
- ✅ Market status detected correctly
- ✅ Cycles completing in <10 seconds
- ✅ Alerts posting to Discord
- ✅ Sentiment showing all sources (vader, ml, earnings, llm)
- ✅ GPU usage <50% during cycles
- ✅ Memory usage stable (<500MB)
- ✅ Feedback database growing (if enabled)

---

## Emergency Contacts 📞

- **Discord Webhook Issues:** Check `DISCORD_WEBHOOK_URL` in `.env`
- **API Rate Limits:** Check Tiingo, Finnhub quotas
- **Database Corruption:** Restore from `backups/` directory
- **Config Issues:** Restore `.env.backup`

---

## Next Steps After Successful Start 🎯

1. **Monitor First Hour**
   - Watch logs for errors
   - Verify alerts are relevant
   - Check sentiment scores make sense

2. **Enable Feedback Loop** (if not already)
   - Set `FEATURE_FEEDBACK_LOOP=1`
   - Wait 24 hours for first performance data

3. **Tune Parameters**
   - Adjust sentiment weights based on results
   - Modify `MIN_SCORE` threshold if too many/few alerts
   - Enable/disable features as needed

4. **Set Up Monitoring**
   - Configure UptimeRobot (see `UPTIMEROBOT_SETUP.md`)
   - Set up admin webhooks for critical errors
   - Schedule weekly backups

---

**Good luck! 🚀**
