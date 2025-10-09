# 🚀 LAUNCH NOW - Quick Start Guide

**You're ready to deploy! Here's what to do right now:**

---

## ✅ **Pre-Flight Complete**

All checks passed:
- ✅ Ollama (Mistral LLM) - Running
- ✅ QuickChart (Charts) - Running
- ✅ Feedback loop enabled
- ✅ Admin webhook configured
- ✅ All dependencies installed

---

## 🎯 **Launch in 3 Steps**

### **Step 1: Start the Bot (Choose One)**

**Option A: Desktop Shortcut (Easiest)**
```
Double-click: "Catalyst Bot - Start All"
```

**Option B: Manual Command**
```bash
python -m catalyst_bot.runner
```

### **Step 2: Verify First Cycle (8-10 minutes)**

Watch for these log messages:
```
✅ process_priority_set
✅ market_status detected
✅ feedback_loop_database_initialized
✅ ml_sentiment_model_loaded
✅ feeds_summary (sources fetched)
✅ CYCLE_DONE
```

### **Step 3: Check Discord**

- Go to your alerts channel
- Look for first alert (may take 1-2 cycles)
- Verify chart, sentiment, and interactive buttons

---

## 📊 **First Hour Expectations**

**Cycles:**
- ~8 minutes for first cycle (model download)
- ~3-5 minutes for subsequent cycles
- ~1-2 alerts per cycle (market dependent)

**What You'll See:**
- Discord alerts with charts
- All 4 sentiment sources (VADER, FinBERT, Earnings, Mistral)
- Feedback database updating every 60s
- No critical errors

**If No Alerts:**
- Normal during pre-market or low volume
- Wait for market hours (9:30am-4pm ET)
- Or lower MIN_SCORE to 0.20 in .env

---

## 🛑 **If Something Goes Wrong**

**Bot crashes immediately:**
```bash
# Check logs
type data\logs\bot.jsonl | findstr ERROR

# Common fixes:
# 1. Virtual environment not activated
.venv\Scripts\activate

# 2. Missing packages
pip install -r requirements.txt

# 3. Port conflict
netstat -ano | findstr 8080
```

**Alerts not posting:**
- Check Discord webhook in .env
- Verify MIN_SCORE not too high (try 0.20)
- Wait for market hours

**Charts not showing:**
```bash
# Restart QuickChart
docker-compose restart quickchart

# Or
start_quickchart.bat
```

---

## 📅 **What's Next**

### **Today (Day 0):**
- ✅ Bot running
- ✅ First few alerts posted
- ✅ No critical errors

### **Tomorrow (Day 1):**
- Check: 10-15 alerts total
- Check: Feedback database growing
- Check: No errors overnight

### **Day 7:**
- ✅ 60-100 quality alerts
- ✅ Admin report with recommendations
- ✅ Backtest results available
- ✅ **Self-learning bot active!**

---

## 📖 **Helpful Commands**

**Check if bot is running:**
```bash
tasklist | findstr python
```

**Check recent logs:**
```bash
powershell "Get-Content data\logs\bot.jsonl -Tail 20"
```

**Count alerts:**
```bash
type data\events.jsonl | find /c /v ""
```

**Check feedback database:**
```bash
sqlite3 data/feedback/alert_performance.db "SELECT COUNT(*) FROM alert_performance"
```

**Stop bot:**
```
Ctrl+C (in terminal)
```

**Restart bot:**
```bash
python -m catalyst_bot.runner
```

---

## 📚 **Full Documentation**

- **7_DAY_PRODUCTION_PLAN.md** - Detailed week plan
- **STARTUP_CHECKLIST.md** - Pre-flight checks
- **ADMIN_CONTROLS_GUIDE.md** - Using admin features
- **BACKTESTING_GUIDE.md** - Running backtests

---

## 🎉 **Ready?**

**Just run:**
```bash
python -m catalyst_bot.runner
```

**Or double-click:**
```
Catalyst Bot - Start All
```

**And watch the magic happen! 🚀**

---

**See you in 7 days with:**
- ✅ Fully trained self-learning bot
- ✅ Actionable admin recommendations
- ✅ Validated backtesting strategies
- ✅ 60-100+ quality alerts analyzed

**Good luck! 🍀**
