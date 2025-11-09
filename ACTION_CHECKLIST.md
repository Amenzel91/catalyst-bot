# ACTION CHECKLIST - Catalyst Bot Production Deployment

**Generated:** 2025-10-25
**Priority:** CRITICAL - Fixes required before deployment
**Estimated Total Time:** 2-4 hours (critical path) | 8-12 hours (recommended)

---

## IMMEDIATE ACTIONS (BEFORE NEXT WEEK) - 2-4 HOURS

**These items BLOCK deployment. Fix immediately.**

### CRITICAL FIX #1: Syntax Error in universe.py (2 minutes)
- [ ] Open `src/catalyst_bot/universe.py`
- [ ] Navigate to line 64-70 in the `requests.get()` call
- [ ] Remove EITHER line 64 (`timeout=15,`) OR line 70 (`timeout=timeout,`)
- [ ] Recommended: Keep line 70 (uses parameter) for flexibility
- [ ] Verify fix: `python -m py_compile src/catalyst_bot/universe.py`
- [ ] Expected: No output = success

**Command to verify:**
```bash
python -m py_compile src/catalyst_bot/universe.py
```

---

### CRITICAL FIX #2: UTF-8 BOM in feeds.py (5 minutes)
- [ ] Run the following command to remove BOM:
```bash
python -c "with open('src/catalyst_bot/feeds.py', 'rb') as f: content = f.read(); content = content[3:] if content.startswith(b'\xef\xbb\xbf') else content; open('src/catalyst_bot/feeds.py', 'wb').write(content)"
```
- [ ] Verify fix: `python -m py_compile src/catalyst_bot/feeds.py`
- [ ] Alternative: Re-save file in editor as "UTF-8 without BOM"

**Command to verify:**
```bash
python -m py_compile src/catalyst_bot/feeds.py
```

---

### CRITICAL FIX #3: Ticker Validation CSV Parsing (30 minutes)
- [ ] Locate ticker list CSV file (likely `data/ticker_list.csv` or similar)
- [ ] Open file and inspect format:
  - Check column separator (comma, tab, pipe?)
  - Check number of columns
  - Check if headers are present
- [ ] Open `src/catalyst_bot/ticker_validation.py` line 183
- [ ] Update `pd.read_csv()` parameters to match CSV format:
  - Add `sep='\t'` if tab-separated
  - Add `header=0` if headers present, `header=None` if not
  - Add `names=['ticker']` if no headers and single column expected
- [ ] Run tests: `pytest tests/test_ticker_validation.py -v`
- [ ] Expected: All tests pass (19 tests)

**Example fix:**
```python
# If CSV is tab-separated with no headers:
df = pd.read_csv(csv_path, sep='\t', header=None, names=['ticker'])

# If CSV is comma-separated with headers:
df = pd.read_csv(csv_path, sep=',', header=0)
```

**Command to test:**
```bash
pytest tests/test_ticker_validation.py -v
```

---

### CRITICAL FIX #4: Deduplication Hash Non-Determinism (1-2 hours)
- [ ] Locate deduplication hash generation code (likely in `src/catalyst_bot/dedupe.py`)
- [ ] Review temporal dedup key generation function
- [ ] Ensure all hash inputs are deterministic:
  - Sort dictionary keys before hashing: `json.dumps(data, sort_keys=True)`
  - Sort lists before hashing
  - Normalize whitespace/case if applicable
  - Use `hashlib.sha1(text.encode('utf-8')).hexdigest()` consistently
- [ ] Run test: `pytest tests/test_dedupe.py::test_temporal_dedup_key -v`
- [ ] Expected: Test passes (hash is deterministic)
- [ ] Run full dedup tests: `pytest tests/test_dedupe.py -v`
- [ ] Expected: 5/5 tests pass

**Debugging hint:**
```python
# Print what's being hashed to understand variation
import hashlib
text = json.dumps(data, sort_keys=True)  # Force deterministic ordering
print(f"Hashing: {text}")
hash_value = hashlib.sha1(text.encode('utf-8')).hexdigest()
```

**Command to test:**
```bash
pytest tests/test_dedupe.py::test_temporal_dedup_key -v
pytest tests/test_dedupe.py -v
```

---

### VALIDATION: Run Wave 1 Tests (10 minutes)
- [ ] Run all Wave 1 tests to verify fixes:
```bash
pytest tests/test_dedupe.py tests/test_ticker_validation.py tests/test_article_freshness.py tests/test_non_substantive.py -v
```
- [ ] Expected: >90% pass rate (currently 60.5%)
- [ ] Target: 40+ tests pass out of 43

---

## HIGH PRIORITY (BEFORE DEPLOYMENT) - 2-3 HOURS

**These items strongly recommended before deployment to avoid operational issues.**

### Install Pre-commit Tools (5 minutes)
- [ ] Install pre-commit and linting tools:
```bash
pip install pre-commit black isort autoflake flake8
```
- [ ] Install pre-commit hooks:
```bash
pre-commit install
```
- [ ] Test pre-commit on all files:
```bash
pre-commit run --all-files
```
- [ ] Expected: May show formatting issues, but no errors

---

### Fix Timezone Handling (1 hour)
- [ ] Open `src/catalyst_bot/` files handling article freshness
- [ ] Find datetime comparison logic (search for `is_fresh` or `publish_time`)
- [ ] Default timezone-naive datetimes to UTC:
```python
if dt.tzinfo is None:
    dt = dt.replace(tzinfo=timezone.utc)
```
- [ ] Fix boundary condition: Use `>=` instead of `>` for threshold checks
- [ ] Run tests: `pytest tests/test_article_freshness.py -v`
- [ ] Expected: 12/12 tests pass (currently 9/12)

**Command to test:**
```bash
pytest tests/test_article_freshness.py -v
```

---

### Configure Line Ending Consistency (10 minutes)
- [ ] Create `.gitattributes` file in project root:
```bash
echo "* text=auto" > .gitattributes
echo "*.py text eol=lf" >> .gitattributes
echo "*.md text eol=lf" >> .gitattributes
echo "*.json text eol=lf" >> .gitattributes
echo "*.bat text eol=crlf" >> .gitattributes
```
- [ ] Commit the file: `git add .gitattributes && git commit -m "Add .gitattributes for line ending consistency"`
- [ ] Normalize existing files: `git add --renormalize .`

---

### Pytest Infrastructure Bug Workaround (5 minutes)
- [ ] Document pytest batching workaround in test documentation
- [ ] Run tests in batches of 4-5 files at a time
- [ ] Alternative: Update pytest version: `pip install --upgrade pytest`
- [ ] Test if bug is resolved: `pytest tests/ --collect-only`

**Note:** This is non-blocking if you run tests in batches (as Agent 3 did).

---

## MEDIUM PRIORITY (FIX NEXT SPRINT) - 2-4 HOURS

**These items improve code quality but don't block deployment.**

### Run Black Formatter (5 minutes)
- [ ] Format all Python files:
```bash
black src/ tests/
```
- [ ] Review changes: `git diff`
- [ ] Commit: `git add . && git commit -m "Apply black formatter to fix 181 line length violations"`
- [ ] Expected: Fixes 181 line length violations automatically

---

### Convert Print Statements to Logging (2-4 hours)
- [ ] Priority files: `runner.py`, `classify.py`, `alerts.py`
- [ ] Replace `print(...)` with:
  - `logger.info(...)` for informational messages
  - `logger.debug(...)` for debug messages
  - `logger.warning(...)` for warnings
  - `logger.error(...)` for errors
- [ ] Test after changes to ensure logging works
- [ ] Expected: Better log control and production debugging

**Example:**
```python
# Before:
print(f"Processing ticker: {ticker}")

# After:
logger.info(f"Processing ticker: {ticker}")
```

---

### Review Global Variables (4-8 hours)
- [ ] Identify 50 global variables across codebase
- [ ] Refactor high-risk globals to:
  - Configuration objects
  - Function parameters
  - Dependency injection
- [ ] Focus on critical paths first (runner.py, alerts.py)
- [ ] Expected: Better testability and thread safety

---

## MANUAL UPDATES (USER MUST DO) - 5-10 MINUTES

**These require API keys that only you have access to.**

### Optional API Keys (Add if features needed)

#### If Using Benzinga News:
- [ ] Add to `.env`: `BENZINGA_API_KEY=your_key_here`

#### If Using OpenAI LLM:
- [ ] Add to `.env`: `OPENAI_API_KEY=sk-your_key_here`

#### If Using Reddit Sentiment:
- [ ] Add to `.env`:
```bash
REDDIT_CLIENT_ID=your_client_id
REDDIT_CLIENT_SECRET=your_client_secret
REDDIT_USER_AGENT=CatalystBot/1.0
```
- [ ] Enable feature: `FEATURE_REDDIT_SENTIMENT=1`

#### If Using StockTwits Sentiment:
- [ ] Add to `.env`: `STOCKTWITS_ACCESS_TOKEN=your_token_here`
- [ ] Enable feature: `FEATURE_STOCKTWITS_SENTIMENT=1`

#### If Using Discord Slash Commands:
- [ ] Add to `.env`:
```bash
DISCORD_APPLICATION_ID=your_app_id
DISCORD_GUILD_ID=your_server_id
```

---

## OPTIONAL (NICE TO HAVE) - 4-8 HOURS

**These are optimizations and enhancements, not blockers.**

### Optimize Slow Imports (2-3 hours)
- [ ] Refactor `runner.py` to lazy-load heavy modules
- [ ] Defer ML model loading in `classify.py` until first use
- [ ] Move chart library imports to function scope
- [ ] Target: Reduce startup time from 8.8s to <3s

---

### Install Optional Dependencies (5 minutes)
- [ ] If using Discord embeds:
```bash
pip install discord.py>=2.0,<3
```
- [ ] If using advanced technical analysis:
```bash
pip install pandas-ta
```
- [ ] If using OpenAI:
```bash
pip install openai
```

---

### Refactor Large Files (16-40 hours)
- [ ] Extract modules from `alerts.py` (135 KB)
- [ ] Extract modules from `runner.py` (118 KB)
- [ ] Extract modules from `feeds.py` (115 KB)
- [ ] Create separate files for logical concerns
- [ ] Expected: Easier maintenance and testing

---

## PRE-DEPLOYMENT VALIDATION CHECKLIST

**Run this checklist before deploying to production.**

### Code Validation (15 minutes)
- [ ] All syntax errors fixed (verify with py_compile)
- [ ] Wave 1 tests pass at >90% (currently 60.5%)
- [ ] No import errors (run: `python -c "import src.catalyst_bot.runner"`)
- [ ] No critical warnings in logs

### Configuration Validation (5 minutes)
- [ ] `.env` contains all required variables (checked by Agent 1)
- [ ] Discord webhook URL is valid
- [ ] API keys are active and not expired
- [ ] Feature flags set correctly for production

### Smoke Test (10 minutes)
- [ ] Run bot in dry-run mode:
```bash
python src/catalyst_bot/runner.py --dry-run --once
```
- [ ] Expected: No crashes, processes at least one article
- [ ] Check logs: `tail -100 data/logs/bot.jsonl`
- [ ] Expected: No ERROR level messages

### Manual QA (30 minutes)
- [ ] Run bot for one full cycle (30 min)
- [ ] Verify alerts posted to Discord
- [ ] Verify charts generated correctly
- [ ] Verify no duplicate alerts
- [ ] Verify ticker validation working
- [ ] Check log files for errors

---

## POST-DEPLOYMENT MONITORING

**Monitor these metrics in first 24 hours after deployment.**

### Health Checks (First 24 hours)
- [ ] Monitor Discord for alert quality
- [ ] Check `data/logs/bot.jsonl` for errors every 4 hours
- [ ] Verify no duplicate alerts appearing
- [ ] Verify ticker validation rejecting invalid symbols
- [ ] Monitor LLM usage costs (check `data/logs/llm_usage.jsonl`)

### Success Metrics
- [ ] Alerts posted successfully
- [ ] No crash/restart cycles
- [ ] Deduplication working (no duplicates)
- [ ] Ticker validation working (no invalid tickers)
- [ ] Log file size growing normally (not exploding)

---

## EMERGENCY ROLLBACK PLAN

**If critical issues arise after deployment:**

### Immediate Rollback (5 minutes)
1. Stop the bot process
2. Revert to last known good commit: `git checkout <previous-commit-hash>`
3. Restart bot
4. Check logs to confirm stability

### Post-Rollback Analysis
1. Review `data/logs/bot.jsonl` for error patterns
2. Reproduce issue in development environment
3. Fix issue
4. Re-test thoroughly
5. Re-deploy

---

## SUMMARY TIMELINE

| Phase | Time Required | Status |
|-------|---------------|--------|
| **Critical Fixes** | 2-4 hours | BLOCKING |
| **High Priority** | 2-3 hours | STRONGLY RECOMMENDED |
| **Validation** | 1 hour | REQUIRED |
| **Medium Priority** | 2-4 hours | RECOMMENDED |
| **Manual Updates** | 5-10 min | AS NEEDED |
| **Total (Minimum)** | 5-8 hours | |
| **Total (Recommended)** | 8-12 hours | |

---

## QUICK REFERENCE: BLOCKING ISSUES

| Issue | Location | Time | Command |
|-------|----------|------|---------|
| Duplicate timeout | universe.py:70 | 2 min | Remove line 64 or 70 |
| UTF-8 BOM | feeds.py:1 | 5 min | Run Python BOM removal script |
| Ticker CSV parsing | ticker_validation.py:183 | 30 min | Fix pd.read_csv() params |
| Dedup hash | dedupe.py | 1-2 hrs | Add sort_keys=True to JSON |

**Deployment Status After Fixes:** READY FOR PRODUCTION

---

**Last Updated:** 2025-10-25
**Next Review:** After critical fixes (2-4 hours from now)
**Deployment Target:** 2025-10-26 (pending fixes)
