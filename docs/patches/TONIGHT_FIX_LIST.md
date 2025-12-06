# Tonight's Fix List - Priority Ordered

**Date:** 2025-10-23 9:02 AM CST
**Status:** Bot running in production, monitoring all day
**Next Work Session:** Tonight after work

---

## 🔴 **CRITICAL FIXES (Do These First)**

### 1. Enable SEC Filing Integration
**Priority:** HIGH
**Time:** 5 minutes
**Impact:** Enables the entire SEC filing pipeline we just built

**Steps:**
```bash
# Add to .env file:
SEC_MONITOR_USER_EMAIL=your-email@example.com
FEATURE_SEC_FILINGS=1

# Optional - set watchlist for SEC filings:
WATCHLIST=SOFI,PLTR,AMD  # Use tickers < $10 for testing

# Restart bot to apply changes
```

**Why:** Without this, all SEC filing code is dormant. This is the switch to activate it.

**Expected Result:** Bot will start fetching SEC filings and sending alerts with full metrics + SEC data

---

### 2. Fix Ticker CSV Formatting Issue
**Priority:** MEDIUM-HIGH
**Time:** 10 minutes
**Impact:** Enables ticker validation, improves test pass rate

**Problem:**
```
Failed to load ticker list (Error tokenizing data. C error: Expected 1 fields in line 9, saw 14)
```

**Root Cause:** `data/tickers.csv` has malformed line 9

**Steps:**
```bash
# 1. Open data/tickers.csv
# 2. Go to line 9
# 3. Check for:
#    - Extra commas
#    - Unquoted fields with commas inside
#    - Inconsistent column count
# 4. Fix or delete line 9
# 5. Re-test: python -c "import pandas as pd; pd.read_csv('data/tickers.csv')"
```

**Expected Result:** Ticker validation will work, 3 failing tests in `test_sec_filtering.py` should pass

---

## 🟡 **IMPORTANT ENHANCEMENTS (Do Tonight)**

### 3. Install Optional Dependencies for Better Performance
**Priority:** MEDIUM
**Time:** 5 minutes
**Impact:** Better sentiment analysis, semantic keyword extraction

**Steps:**
```bash
# Install FinBERT for better sentiment (currently falling back to VADER):
pip install transformers torch

# Install KeyBERT for semantic keyword extraction:
pip install keybert

# Restart bot
```

**Why:**
- FinBERT is 30-40% more accurate for financial sentiment vs VADER
- KeyBERT finds semantically similar keywords (e.g., "merger" → "acquisition")

**Expected Result:**
- Logs will show "model=finbert" instead of "Falling back to VADER"
- Better sentiment scoring on SEC filings

---

### 4. Fix Deprecated datetime.utcnow() in Tests
**Priority:** LOW-MEDIUM
**Time:** 10 minutes
**Impact:** Removes 10 deprecation warnings, future-proofs for Python 3.13+

**Steps:**
```bash
# Find all occurrences:
grep -r "datetime.utcnow()" tests/

# Replace with:
datetime.now(timezone.utc)

# Files affected:
# - tests/test_classify.py (10 instances)
# - tests/test_*.py (check others)
```

**Example:**
```python
# Old (deprecated):
ts_utc=datetime.utcnow()

# New (recommended):
from datetime import timezone
ts_utc=datetime.now(timezone.utc)
```

**Expected Result:** No more deprecation warnings in test output

---

### 5. Fix test_sec_filtering.py Mocking Issues
**Priority:** MEDIUM
**Time:** 15 minutes
**Impact:** 100% test pass rate (currently 92%)

**Problem:** 3 tests fail due to mock ticker data not matching production tickers

**Steps:**
```python
# In tests/test_sec_filtering.py, add fixture:

@pytest.fixture
def mock_ticker_db():
    """Mock ticker database with test tickers."""
    return {
        "SOFI": {"exchange": "NASDAQ", "price": 8.50, "valid": True},
        "PLTR": {"exchange": "NYSE", "price": 9.25, "valid": True},
        "AAPL": {"exchange": "NASDAQ", "price": 180.00, "valid": True},
        "TSLA": {"exchange": "NASDAQ", "price": 250.00, "valid": True},
        # Add all test tickers here
    }

# Update test setup to use mock_ticker_db
# OR use real tickers.db in tests
```

**Expected Result:** All 84/84 tests passing (100% pass rate)

---

## 🟢 **OPTIONAL IMPROVEMENTS (If Time Permits)**

### 6. Add Pre-commit Hooks
**Priority:** LOW
**Time:** 5 minutes
**Impact:** Automated code quality checks

**Steps:**
```bash
pip install pre-commit
pre-commit install
pre-commit run --all-files
```

**Expected Result:** Git commits will auto-check code formatting, linting, etc.

---

### 7. Create .env.example Template
**Priority:** LOW
**Time:** 5 minutes
**Impact:** Easier deployment/configuration

**Steps:**
```bash
# Add to .env.example (if not already there):

# SEC Filing Integration
FEATURE_SEC_FILINGS=0  # Set to 1 to enable
SEC_MONITOR_USER_EMAIL=your-email@example.com  # Required for SEC API

# Price Filters
PRICE_CEILING=10  # Max price for alerts
PRICE_FLOOR=0.1  # Min price for alerts

# Watchlist (comma-separated tickers)
WATCHLIST=SOFI,PLTR,AMD
```

---

## 📊 **TESTING CHECKLIST (After Fixes)**

After implementing fixes, run these tests:

```bash
# 1. SEC filing integration tests:
pytest tests/test_sec_*.py -v

# 2. Classification tests (datetime fixes):
pytest tests/test_classify.py -v

# 3. Filtering tests (ticker CSV fix):
pytest tests/test_sec_filtering.py -v

# 4. Full test suite:
pytest tests/ -v --tb=short

# 5. Launch bot and check logs:
python -B -m catalyst_bot.runner
# Watch for:
# - "sec_filings_added raw=X unique=Y"
# - No "sec_email_missing" errors
# - "model=finbert" instead of "Falling back to VADER"
```

---

## 🎯 **EXPECTED OUTCOMES TONIGHT**

After all fixes:

✅ **SEC Filing Integration Active**
- Bot fetching SEC filings every cycle
- SEC alerts showing up with full metrics
- Price ceiling blocking expensive tickers
- OTC filtering working

✅ **Test Pass Rate: 100%**
- 84/84 tests passing (up from 80/84)
- No deprecation warnings
- All mocking issues resolved

✅ **Better Performance**
- FinBERT sentiment (more accurate)
- KeyBERT semantic extraction
- Ticker validation working

---

## 📝 **QUICK REFERENCE**

### Files to Edit:
1. `.env` - Add SEC_MONITOR_USER_EMAIL, FEATURE_SEC_FILINGS
2. `data/tickers.csv` - Fix line 9
3. `tests/test_classify.py` - Replace datetime.utcnow()
4. `tests/test_sec_filtering.py` - Add mock ticker fixture

### Commands to Run:
```bash
# Install dependencies:
pip install transformers torch keybert pre-commit

# Fix CSV:
nano data/tickers.csv  # Or your preferred editor

# Run tests:
pytest tests/ -v --tb=short

# Launch bot:
python -B -m catalyst_bot.runner
```

---

## ⏱️ **TIME ESTIMATES**

- Fix #1 (SEC integration): **5 min** ⭐ DO FIRST
- Fix #2 (Ticker CSV): **10 min** ⭐ HIGH PRIORITY
- Fix #3 (Dependencies): **5 min**
- Fix #4 (Datetime): **10 min**
- Fix #5 (Test mocking): **15 min**
- Fix #6 (Pre-commit): **5 min** (optional)
- Fix #7 (.env template): **5 min** (optional)

**Total Core Fixes: ~30-40 minutes**
**Total with Optional: ~50-60 minutes**

---

## 🚨 **WHAT TO WATCH FOR TODAY**

While you're at work, the bot is running. Check Discord occasionally for:

✅ **Good Signs:**
- Alerts appearing in Discord (news/PR)
- No crash messages
- Health endpoint responding (http://localhost:8080/health)

⚠️ **Warning Signs:**
- No alerts all day (could mean filters too strict)
- Bot stopped/crashed
- Errors flooding logs

**Note:** SEC filing integration is OFF until tonight, so you won't see SEC alerts yet. That's expected!

---

## 📞 **IF ISSUES ARISE**

**Bot Crashed:**
```bash
# Check last 50 lines of logs:
tail -50 data/logs/bot.jsonl

# Restart:
python -B -m catalyst_bot.runner
```

**No Alerts:**
```bash
# Check if filters too strict:
grep "skip_" data/logs/bot.jsonl | tail -20

# Might need to adjust:
# - PRICE_CEILING (currently $10)
# - MIN_SCORE (currently 0.20)
# - MIN_SENT_ABS (sentiment threshold)
```

**Health Check:**
```bash
# Should return JSON:
curl http://localhost:8080/health
```

---

**Good luck at work! Bot is stable and monitoring. Fixes are straightforward and will take less than an hour tonight.** 🚀

**Priority Order Tonight:**
1. Enable SEC filing integration (5 min)
2. Fix ticker CSV (10 min)
3. Install dependencies (5 min)
4. Fix datetime deprecations (10 min)
5. Fix test mocking (15 min)

**Total: ~45 minutes to get everything to 100%** ✅
