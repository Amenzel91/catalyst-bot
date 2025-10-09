# 📈 7-Day Production Data Collection Plan

**Start Date:** October 6, 2025
**End Date:** October 13, 2025
**Objective:** Collect quality alert data to enable admin controls and backtesting features

---

## 🎯 **Goals**

By the end of 7 days, you should have:
- ✅ **100+ quality alerts** posted to Discord
- ✅ **Performance tracking data** for all alerts (15m, 1h, 4h, 1d)
- ✅ **Keyword statistics** with win rates
- ✅ **Catalyst type breakdowns** (earnings, SEC filings, news)
- ✅ **Backtest-ready historical data** in events.jsonl
- ✅ **Admin report with real recommendations**

---

## 🚀 **Day 0 (Today): Launch Production**

### **Checklist Before Starting**

- [x] All services running (Ollama, QuickChart, Health Monitor)
- [x] Feedback loop enabled in .env (FEATURE_FEEDBACK_LOOP=1)
- [x] Admin webhook configured
- [x] Virtual environment activated
- [ ] Cloudflare tunnel running (if using slash commands)
- [ ] Interaction server running (if using Discord buttons)

### **Start Production**

**Option 1: Quick Start (Recommended)**
```bash
# Double-click this shortcut
Catalyst Bot - Start All (desktop shortcut)
```

**Option 2: Manual Start**
```bash
# Terminal 1: Interaction Server (optional, for buttons)
python interaction_server.py

# Terminal 2: Main Bot
python -m catalyst_bot.runner
```

### **What to Expect**

**First Cycle (~8 minutes):**
- ✅ FinBERT model will download (438MB) - **one time only**
- ✅ Market hours detected (currently: pre-market)
- ✅ Feeds fetched (Finnhub, SEC, GlobeNewswire)
- ✅ Sentiment aggregation using all 4 sources
- ✅ Alerts posted to Discord (if any meet criteria)
- ✅ Feedback tracker starts monitoring prices

**Subsequent Cycles:**
- ⚡ 60-second cycles during market hours (9:30am-4pm ET)
- ⏱️ 90-second cycles during extended hours (4am-9:30am, 4pm-8pm ET)
- 🌙 180-second cycles when market closed (8pm-4am ET)

---

## 📅 **Day 1-2: Initial Data Collection**

### **Monitoring**

**Check these every 4-6 hours:**

1. **Discord Alert Channel**
   - Are alerts posting?
   - Are charts generating correctly?
   - Is sentiment displaying all 4 sources?

2. **Feedback Database**
   ```bash
   # Check if feedback is being tracked
   sqlite3 data/feedback/alert_performance.db "SELECT COUNT(*) FROM alert_performance"
   ```
   Expected: 10+ alerts tracked

3. **Events Log**
   ```bash
   # Check event count
   type data\events.jsonl | find /c /v ""
   ```
   Expected: Growing steadily

4. **Bot Logs**
   ```bash
   # Check for errors
   type data\logs\bot.jsonl | findstr ERROR
   ```
   Expected: No critical errors

### **What You Should See**

- **Day 1 Target:** 10-15 alerts posted
- **Day 2 Target:** 20-30 total alerts
- **Feedback Tracking:** Price updates every 60 seconds for open positions
- **Keyword Stats:** data/analyzer/keyword_stats.json updating

### **Common Issues**

| Issue | Cause | Fix |
|-------|-------|-----|
| No alerts posting | MIN_SCORE too high | Lower to 0.20 temporarily |
| Charts not showing | QuickChart not running | Run start_quickchart.bat |
| ML sentiment missing | PyTorch not installed | pip install torch transformers |
| Mistral timeouts | Ollama not running | Run start_ollama.bat |

---

## 📊 **Day 3-4: Data Quality Check**

### **Quality Metrics to Check**

**Run these commands:**

```bash
# 1. Alert count
type data\events.jsonl | find /c /v ""

# 2. Feedback database stats
sqlite3 data/feedback/alert_performance.db "SELECT
  COUNT(*) as total_alerts,
  SUM(CASE WHEN price_1h IS NOT NULL THEN 1 ELSE 0 END) as tracked_1h,
  SUM(CASE WHEN price_4h IS NOT NULL THEN 1 ELSE 0 END) as tracked_4h,
  SUM(CASE WHEN price_1d IS NOT NULL THEN 1 ELSE 0 END) as tracked_1d
FROM alert_performance"

# 3. Check keyword performance
python -c "import json; data=json.load(open('data/analyzer/keyword_stats.json')); print('Keywords tracked:', len(data)); print('Top 5:', list(data.items())[:5])"
```

### **Expected Metrics (Day 3-4)**

- **Total Alerts:** 30-50
- **1h Tracking:** 90%+ of alerts
- **4h Tracking:** 70%+ of alerts
- **1d Tracking:** 50%+ of alerts (need 24 hours)
- **Keywords Tracked:** 50-100 unique keywords

### **Mid-Week Tuning**

**If getting too many alerts (>15/day):**
```ini
# In .env
MIN_SCORE=0.30  # Increase from 0.25
```

**If getting too few alerts (<5/day):**
```ini
# In .env
MIN_SCORE=0.20  # Decrease from 0.25
PRICE_CEILING=15  # Increase from 10
```

**If sentiment seems off:**
- Check `data/logs/bot.jsonl` for sentiment_aggregated logs
- Verify all 4 sources appearing (vader, earnings, ml, llm)
- Adjust weights in .env if needed

---

## 🎯 **Day 5-6: Feature Validation**

### **Test Admin Report**

**Manually trigger admin report:**
```bash
python -c "from catalyst_bot.admin_controls import generate_admin_report; r=generate_admin_report(); print('Total Alerts:', r.total_alerts); print('Recommendations:', len(r.parameter_recommendations))"
```

**Expected Output:**
```
Total Alerts: 40-60
Recommendations: 1-3 parameter suggestions
Backtest Summary: Real win rate data
Keyword Performance: Top/bottom keywords identified
```

### **Test Backtesting**

**Run your first backtest:**
```bash
python run_backtest.py --days 5
```

**Expected Output:**
```
Total Return: X.X%
Sharpe Ratio: X.XX
Win Rate: XX.X%
Max Drawdown: X.X%
Total Trades: 20-40
```

**If backtest fails:**
- Not enough alerts with tickers yet
- Wait until day 7
- Ensure alerts have valid price data

### **Test Parameter Validation**

```bash
# Test a parameter change
python run_backtest.py --validate MIN_SCORE --old 0.25 --new 0.30 --days 5
```

**Expected:** APPROVE/REJECT/NEUTRAL recommendation with confidence

---

## 🏁 **Day 7: Full Feature Unlock**

### **Final Validation**

**1. Check Data Quality**
```bash
# Should have 50-100+ quality alerts
type data\events.jsonl | find /c /v ""

# Should have comprehensive feedback data
sqlite3 data/feedback/alert_performance.db "SELECT COUNT(*) FROM alert_performance WHERE price_1d IS NOT NULL"
```

**2. Generate Full Admin Report**
```bash
python -c "from catalyst_bot.admin_controls import generate_admin_report, build_admin_embed; r=generate_admin_report(); print(build_admin_embed(r))"
```

**3. Run Comprehensive Backtest**
```bash
# 7-day backtest with full metrics
python run_backtest.py --days 7 --format markdown --output backtest_week1.md --export trades_week1.csv
```

**4. Test Parameter Optimization**
```bash
# Find optimal MIN_SCORE
python run_backtest.py --sweep MIN_SCORE --values 0.20,0.25,0.30,0.35,0.40 --simulations 50
```

### **Success Criteria**

By Day 7, you should have:
- ✅ **60-100 quality alerts** logged
- ✅ **Admin reports** with real recommendations
- ✅ **Backtest results** with positive Sharpe ratio
- ✅ **Win rate data** across multiple timeframes
- ✅ **Keyword performance** rankings
- ✅ **Parameter validation** ready for changes

---

## 📈 **What Happens After Day 7**

### **Automated Operations Begin**

**Nightly (23:00 UTC / 6:00pm CT):**
- 📊 Admin report generated automatically
- 💬 Posted to Discord admin channel
- 📋 Parameter recommendations calculated
- ✅ Awaiting your approval via buttons

**Weekly (Sunday 23:00 UTC):**
- 📈 Weekly performance report
- 🏆 Best/worst catalyst types
- 📊 Parameter change impact analysis

### **Ongoing Monitoring**

**Daily Tasks (5 minutes):**
- Check Discord for alerts
- Review any errors in logs
- Approve/reject parameter recommendations

**Weekly Tasks (15 minutes):**
- Review weekly report
- Analyze backtest results
- Apply approved parameter changes
- Check feedback database growth

**Monthly Tasks (30 minutes):**
- Run comprehensive backtest
- Review parameter change history
- Export data for external analysis
- Update strategy based on results

---

## 🛠️ **Troubleshooting During 7 Days**

### **Bot Crashes or Freezes**

**Symptoms:** Bot stops posting alerts, no logs updating

**Check:**
```bash
# Is Python still running?
tasklist | findstr python

# Check last log entry
powershell "Get-Content data\logs\bot.jsonl -Tail 5"
```

**Fix:**
```bash
# Restart bot
Ctrl+C (if still responding)
# Or force kill
taskkill /IM python.exe /F
# Restart
python -m catalyst_bot.runner
```

### **Feedback Tracking Not Working**

**Symptoms:** price_15m, price_1h, price_4h, price_1d all NULL in database

**Check:**
```bash
# Is feedback loop enabled?
findstr FEATURE_FEEDBACK_LOOP .env

# Check tracker thread
type data\logs\bot.jsonl | findstr feedback_tracker
```

**Fix:**
- Verify `FEATURE_FEEDBACK_LOOP=1` in .env
- Restart bot to start tracker thread
- Check for error logs in feedback module

### **Admin Reports Empty**

**Symptoms:** Admin report shows 0 alerts, no recommendations

**Cause:** Not enough data yet

**Timeline:**
- Day 1-2: Reports will be empty (normal)
- Day 3-4: Basic stats appear
- Day 5+: Real recommendations appear

**Workaround:** Generate report manually to check:
```bash
python -c "from catalyst_bot.admin_controls import generate_admin_report; print(generate_admin_report().total_alerts)"
```

### **Backtesting Fails**

**Error:** "Not enough trades to backtest"

**Cause:** Need minimum 10 alerts with tickers and price data

**Fix:**
- Wait until day 5-7
- Lower MIN_SCORE to generate more alerts
- Check that alerts have tickers (not just news)

---

## 📋 **Daily Checklist Template**

Copy this for each day:

```
[ ] Day X - Date: ___________

Morning Check (9am):
[ ] Bot running (check process)
[ ] Market hours detected correctly
[ ] No errors in logs

Afternoon Check (3pm):
[ ] Alerts posting to Discord
[ ] Charts generating
[ ] Sentiment showing all sources

Evening Check (8pm):
[ ] Count today's alerts: _____
[ ] Check feedback database
[ ] Review any errors
[ ] Bot still running

Notes:
_________________________________
_________________________________
```

---

## 🎯 **End-of-Week Report Card**

After 7 days, grade yourself:

| Metric | Target | Actual | Grade |
|--------|--------|--------|-------|
| Total Alerts | 60-100 | ____ | ☐ A ☐ B ☐ C |
| Uptime % | >95% | ____% | ☐ A ☐ B ☐ C |
| Errors/Day | <5 | ____ | ☐ A ☐ B ☐ C |
| Win Rate (1h) | >50% | ____% | ☐ A ☐ B ☐ C |
| Admin Reports | 7 | ____ | ☐ A ☐ B ☐ C |

**Overall Grade:** _____ / 5

**If you scored:**
- **A (4-5):** Excellent! Admin controls and backtesting fully functional
- **B (3):** Good! Minor tuning needed, but ready to use features
- **C (<3):** Needs troubleshooting - review logs and adjust parameters

---

## 🚀 **Ready to Start?**

### **Final Pre-Launch Checklist**

- [x] Services running (Ollama, QuickChart)
- [x] Feedback loop enabled (FEATURE_FEEDBACK_LOOP=1)
- [x] Admin webhook configured
- [x] Virtual environment activated
- [ ] Discord channel ready to receive alerts
- [ ] Monitoring plan understood
- [ ] Troubleshooting guide reviewed

### **Launch Command**

```bash
# Use the desktop shortcut
Catalyst Bot - Start All

# Or manually
python -m catalyst_bot.runner
```

### **What to Watch**

**First Hour:**
- ✅ First cycle completes without errors
- ✅ Market hours detected correctly
- ✅ At least 1 alert posts (if market is open)
- ✅ Feedback tracker starts

**First Day:**
- ✅ 5-15 alerts posted
- ✅ No critical errors
- ✅ Bot runs continuously
- ✅ Feedback database populating

**First Week:**
- ✅ 60+ quality alerts
- ✅ Admin report with recommendations
- ✅ Backtest results available
- ✅ Self-learning system active

---

**Good luck! 🚀 See you in 7 days with a fully self-learning bot!**

**Next Steps After Day 7:**
- Review ADMIN_CONTROLS_GUIDE.md for managing recommendations
- Review BACKTESTING_GUIDE.md for strategy optimization
- Continue to Tier 2 or Tier 3 features while bot learns

---

**Questions During the Week?**
- Check TROUBLESHOOTING_GUIDE.md
- Review logs in data/logs/bot.jsonl
- Check health endpoint: http://localhost:8080/health/detailed
