# Admin Controls Testing - Quick Start Guide

## 🚀 Quick Test Commands

### Run All Tests (Recommended First)
```bash
# Interactive visual test (best for first-time validation)
python test_admin_interactive.py

# Automated test suite
pytest test_admin_workflow.py -v

# Extended unit tests
pytest tests/test_admin_controls.py -v
```

---

## 📋 Pre-Flight Checklist

Before running tests, ensure:
- [ ] Python environment is activated
- [ ] All dependencies installed (`pip install -r requirements.txt`)
- [ ] You're in the project root directory

Optional (for full testing):
- [ ] `.env` file exists (for parameter application tests)
- [ ] `data/` directory exists
- [ ] Discord bot token configured (for Discord API tests)

---

## 🎯 Test Scenarios

### Scenario 1: First-Time Setup Validation
**Goal:** Verify admin controls work end-to-end

```bash
# Step 1: Run interactive tests
python test_admin_interactive.py

# Expected output: All 10 tests pass with ✅ indicators
# Time: ~30 seconds
```

**What it tests:**
- Report generation
- Discord embed building
- Button interactions
- Parameter validation
- Rollback functionality

---

### Scenario 2: Pre-Deployment Validation
**Goal:** Ensure all components work before deploying

```bash
# Step 1: Run full automated suite
pytest test_admin_workflow.py -v

# Step 2: Run extended unit tests
pytest tests/test_admin_controls.py -v

# Step 3: Check coverage
pytest test_admin_workflow.py --cov=src.catalyst_bot.admin_controls --cov-report=html
```

**Expected Results:**
- All tests pass (59+ tests)
- Coverage > 90%
- No errors or warnings

---

### Scenario 3: Button Handler Testing
**Goal:** Test Discord button interactions specifically

```bash
# Run button handler tests only
pytest tests/test_admin_controls.py::TestButtonHandlers -v

# Run edge case tests
pytest tests/test_admin_controls.py::TestButtonHandlerEdgeCases -v
```

**What it tests:**
- View Details button
- Approve Changes button
- Reject Changes button
- Custom Adjust modal
- Error handling for invalid inputs

---

### Scenario 4: Debugging Failed Tests
**Goal:** Get detailed error information

```bash
# Run with full traceback
pytest test_admin_workflow.py -v --tb=long

# Run specific failing test
pytest test_admin_workflow.py::TestButtonInteractionWorkflow::test_approve_button -v -s

# Enable logging
pytest test_admin_workflow.py -v --log-cli-level=DEBUG
```

---

## 🔍 Understanding Test Output

### Interactive Test Output
```
✅ = Test passed
❌ = Test failed
⚠️  = Test skipped (expected in some environments)
ℹ️  = Informational message
```

### Pytest Output
```
PASSED = Test succeeded ✅
FAILED = Test failed - needs attention ❌
SKIPPED = Test skipped (conditional) ⚠️
ERROR = Test setup/teardown error ❌
```

---

## 🐛 Common Issues & Solutions

### Issue 1: "No .env file found"
**Symptom:** Tests skip with warning about missing .env
**Solution:** This is expected in test environments. Tests that require .env will be skipped.
**Action:** No action needed unless testing parameter application specifically.

### Issue 2: "ModuleNotFoundError"
**Symptom:** Python can't find catalyst_bot modules
**Solution:**
```bash
# Ensure you're in project root
cd C:\Users\menza\OneDrive\Desktop\Catalyst-Bot\catalyst-bot

# Add src to Python path
export PYTHONPATH="${PYTHONPATH}:$(pwd)/src"  # Linux/Mac
set PYTHONPATH=%PYTHONPATH%;%CD%\src         # Windows
```

### Issue 3: "Permission denied" on backup files
**Symptom:** Can't create backups in data/config_backups/
**Solution:**
```bash
# Create directory with proper permissions
mkdir -p data/config_backups
chmod 755 data/config_backups
```

### Issue 4: Tests pass but no visual output
**Symptom:** Pytest runs but you want more detail
**Solution:** Use interactive test script instead:
```bash
python test_admin_interactive.py
```

---

## 📊 Test Coverage Report

### Generate HTML Coverage Report
```bash
pytest test_admin_workflow.py --cov=src.catalyst_bot --cov-report=html
```

View report:
```bash
# Open in browser
open htmlcov/index.html  # Mac
start htmlcov\index.html # Windows
```

---

## 🎨 Interactive Test Examples

### Example: Successful Test Run
```
================================================================================
  TEST 1: Report Generation & Persistence
================================================================================

Created report for date: 2025-10-06
Total alerts: 75
Backtest trades: 75
Win rate: 60.0%
Recommendations: 3

✅ Report saved to: out\admin_reports\report_2025-10-06.json
✅ Report loaded successfully
   Verified date: 2025-10-06
   Verified alerts: 75
```

### Example: Test with Skip Warning
```
================================================================================
  TEST 5: Approve Changes (SKIPPED)
================================================================================

⚠️  No .env file found - skipping approve test
```

---

## 🔧 Advanced Testing

### Run Specific Test Class
```bash
pytest test_admin_workflow.py::TestButtonInteractionWorkflow -v
```

### Run Tests Matching Pattern
```bash
pytest -k "button" -v  # All tests with "button" in name
pytest -k "modal" -v   # All tests with "modal" in name
```

### Run Tests in Parallel (faster)
```bash
pip install pytest-xdist
pytest test_admin_workflow.py -n auto
```

### Generate JUnit XML Report
```bash
pytest test_admin_workflow.py --junit-xml=test-results.xml
```

---

## 📝 Test Maintenance

### Adding New Tests
1. Add test function to appropriate test class
2. Follow naming convention: `test_<description>`
3. Include docstring explaining what's tested
4. Run locally before committing

### Updating Existing Tests
1. Run tests before changes: `pytest -v`
2. Make your changes
3. Run tests after: `pytest -v`
4. Ensure no regressions

---

## 🚨 CI/CD Integration

### GitHub Actions Example
```yaml
name: Admin Controls Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - name: Set up Python
        uses: actions/setup-python@v2
        with:
          python-version: 3.11

      - name: Install dependencies
        run: pip install -r requirements.txt

      - name: Run tests
        run: pytest test_admin_workflow.py -v

      - name: Generate coverage
        run: pytest test_admin_workflow.py --cov=src.catalyst_bot --cov-report=xml
```

---

## 📞 Getting Help

If tests fail unexpectedly:
1. Check this guide for common issues
2. Review test output for specific error
3. Run interactive tests for detailed feedback
4. Check `WAVE_BETA_1_ADMIN_TESTING_SUMMARY.md` for detailed documentation

---

**Happy Testing! 🎉**
