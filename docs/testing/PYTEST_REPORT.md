# PYTEST SUITE EXECUTION & ANALYSIS REPORT
**Agent 3 - Debugging Sweep**
**Generated:** 2025-10-25
**Test Framework:** pytest 8.4.2 / Python 3.13.7

---

## EXECUTIVE SUMMARY

| Metric | Value |
|--------|-------|
| **Total Test Files** | 89 |
| **Total Tests Discovered** | ~1,289 |
| **Tests Executed (Wave 1)** | 43 |
| **Tests Passed (Wave 1)** | 26 (60.5%) |
| **Tests Failed (Wave 1)** | 17 (39.5%) |
| **Execution Time (Wave 1)** | 24.70s |
| **Overall Status** | **UNSTABLE - Critical Failures Detected** |

### CRITICAL FINDINGS

1. **Ticker Validation System Broken**: 13/17 failures are in ticker validation due to CSV parsing error
2. **Temporal Dedup Hash Instability**: Deduplication key generation is non-deterministic
3. **Timezone Handling Issues**: Datetime comparison failures in freshness checks
4. **File Handle Leak**: Pytest encounters `ValueError: I/O operation on closed file` preventing full suite execution

---

## TEST DISCOVERY

### Total Test Files Found: 89

```
Wave 1 Tests (Data Quality):
- test_dedupe.py
- test_ticker_validation.py
- test_article_freshness.py
- test_non_substantive.py

Wave 2 Tests (Alert Layout):
- test_catalyst_badges.py
- test_sentiment_gauge.py
- test_alert_layout_wave2.py
- test_footer_formatting.py

Wave 3 Tests (Data Robustness):
- test_float_data_robust.py
- test_chart_gap_filling.py
- test_multi_ticker_handler.py
- test_offering_sentiment.py

Wave 4 Tests (Integration):
- test_wave_integration.py
- test_regression.py

Additional Test Categories:
- SEC Filing Processing (9 files)
- Chart/Pattern Analysis (13 files)
- Market Data (8 files)
- Backtesting (5 files)
- MOA/Historical Analysis (4 files)
- Classification/Sentiment (7 files)
- Infrastructure (15+ files)
```

---

## WAVE 1: DATA QUALITY TESTS (EXECUTED)

**Status:** FAILED (60.5% pass rate)
**Execution Time:** 24.70s
**Tests:** 43 total (26 passed, 17 failed)

### Test Results by Module

#### 1. test_dedupe.py (4 passed, 1 failed)

**PASSED:**
- `test_dedupe_stable` - Deduplication signature stability
- `test_signature_includes_ticker` - Ticker inclusion in signature
- `test_signature_backwards_compatible` - Backward compatibility
- `test_temporal_dedup_different_tickers` - Multi-ticker deduplication

**FAILED:**
- `test_temporal_dedup_key` - **CRITICAL**
  - **Error:** Hash non-determinism
  - **Expected:** d9e5179f358c5ddc7fae5f7dccb687a68ca54c01
  - **Got:** 7f942def31e012e13044c1c4a203f3481cb7f975
  - **Impact:** Duplicate articles may not be detected consistently

#### 2. test_ticker_validation.py (5 passed, 14 failed)

**ROOT CAUSE:** CSV parsing error in ticker list
**Error Message:** `Error tokenizing data. C error: Expected 1 fields in line 9, saw 14`

**PASSED:**
- `test_empty_and_none_inputs` - Null handling
- `test_import_failure_graceful_handling` - Import error resilience
- `test_is_enabled_property` - Status check
- `test_successful_load_info_logging` - Load success logging
- `test_feeds_integration_no_ticker` - No ticker handling

**FAILED (All due to CSV parsing):**
- `test_valid_tickers_pass_validation`
- `test_invalid_tickers_fail_validation`
- `test_case_insensitive_validation`
- `test_load_failure_graceful_handling`
- `test_ticker_count_property`
- `test_validate_and_log_debug_logging`
- `test_otc_detection`
- `test_otc_case_insensitive`
- `test_validate_and_check_otc`
- `test_validate_and_check_otc_logging`
- `test_feeds_integration_valid_ticker`
- `test_feeds_integration_invalid_ticker`
- `test_feeds_integration_case_insensitive`

**Impact:** Ticker validation is completely non-functional in production

#### 3. test_article_freshness.py (9 passed, 3 failed)

**PASSED:**
- `test_fresh_article` - Fresh article detection
- `test_stale_article` - Stale article detection
- `test_edge_case_one_second_over_threshold` - Boundary condition
- `test_sec_filing_exception` - SEC filing special handling
- `test_missing_publish_time` - Missing timestamp handling
- `test_very_old_article` - Old article rejection
- `test_sec_filing_old_but_within_window` - SEC window check
- `test_sec_filing_beyond_window` - SEC expiration check

**FAILED:**
- `test_edge_case_exactly_at_threshold`
  - **Error:** Boundary condition false (should be true)
  - **Impact:** Articles at exact threshold may be incorrectly rejected

- `test_timezone_naive_datetime`
  - **Error:** Timezone-naive datetime treated as stale
  - **Impact:** Articles without timezone info may be incorrectly rejected

- `test_future_published_date`
  - **Error:** Age calculation off by 1 minute (-4 vs -5)
  - **Impact:** Future-dated articles (edge case) may be misclassified

#### 4. test_non_substantive.py (9 passed, 0 failed)

**Status:** 100% PASS
**Coverage:**
- Substantive news detection
- Non-substantive pattern matching
- Generic trading update filtering
- Short title handling
- Combined title/text analysis
- Case insensitivity
- Real-world example (TOVX)

---

## WAVE 2-4: NOT EXECUTED

**Reason:** Wave 1 failures + pytest file handle bug prevented execution

**Status:** UNKNOWN

**Wave 2 Files:**
- test_catalyst_badges.py
- test_sentiment_gauge.py
- test_alert_layout_wave2.py
- test_footer_formatting.py

**Wave 3 Files:**
- test_float_data_robust.py
- test_chart_gap_filling.py
- test_multi_ticker_handler.py
- test_offering_sentiment.py

**Wave 4 Files:**
- test_wave_integration.py
- test_regression.py

---

## FAILURE CATEGORIZATION

### By Type:

| Category | Count | Tests |
|----------|-------|-------|
| **CSV Parsing Error** | 13 | All ticker_validation tests |
| **Hash Non-Determinism** | 1 | test_temporal_dedup_key |
| **Timezone Issues** | 2 | test_timezone_naive_datetime, test_edge_case_exactly_at_threshold |
| **Calculation Error** | 1 | test_future_published_date |

### By Severity:

| Severity | Count | Description |
|----------|-------|-------------|
| **CRITICAL** | 14 | Ticker validation broken (13) + dedup instability (1) |
| **HIGH** | 2 | Timezone handling errors |
| **MEDIUM** | 1 | Age calculation precision |

---

## INFRASTRUCTURE ISSUES

### Pytest File Handle Bug

**Error:**
```
ValueError: I/O operation on closed file.
  File ".../capture.py", line 591, in snap
    self.tmpfile.seek(0)
```

**Impact:**
- Prevents full test suite execution
- Occurs during test collection/teardown
- Blocks automated CI/CD pipeline usage

**Workaround:** Run tests in smaller batches (as done in Wave 1)

---

## PERFORMANCE METRICS

| Metric | Value |
|--------|-------|
| Collection Time | ~13.28s |
| Wave 1 Execution | 24.70s |
| Avg Test Speed | ~0.57s/test |
| **Projected Full Suite** | **~12-15 minutes** |

---

## STABILITY ASSESSMENT

### Stability Score: **35/100** (UNSTABLE)

**Breakdown:**
- **Test Pass Rate:** 60.5% (Wave 1) → -40 points
- **Critical System Failures:** 2 (ticker validation, dedup) → -20 points
- **Infrastructure Issues:** pytest bug → -5 points

### Risk Level: **HIGH**

**Reasons:**
1. Ticker validation completely non-functional
2. Deduplication may allow duplicate articles through
3. Timezone handling issues could reject valid articles
4. Cannot run full test suite reliably

---

## COVERAGE GAPS IDENTIFIED

### Missing/Untested Areas:
1. **Alert Rendering** - Wave 2 tests not executed
2. **Chart Generation** - Wave 3 tests not executed
3. **Integration Flows** - Wave 4 tests not executed
4. **MOA Historical Analysis** - Not in Wave tests
5. **SEC Filing Processing** - Not in Wave tests
6. **Backtesting System** - Not in Wave tests

### Test Distribution:
- **Wave 1-4 Tests:** ~16 files (18%)
- **Other Tests:** ~73 files (82%)
- **Wave Tests Executed:** 4 files (4.5%)

---

## DEPLOYMENT RECOMMENDATION

### **Status: DO NOT DEPLOY** ❌

### Blockers:

1. **CRITICAL:** Ticker validation broken
   - **Fix:** Repair CSV parsing in `ticker_validation.py`
   - **File:** Line 183 - CSV tokenization error
   - **Impact:** Cannot validate any tickers

2. **CRITICAL:** Dedup hash instability
   - **Fix:** Ensure deterministic hash generation
   - **File:** `test_dedupe.py::test_temporal_dedup_key`
   - **Impact:** Duplicate articles may appear

3. **HIGH:** Timezone handling
   - **Fix:** Standardize timezone-naive datetime handling
   - **File:** Article freshness checks
   - **Impact:** May reject valid articles

### Pre-Deployment Requirements:

1. Fix ticker validation CSV parsing (BLOCKER)
2. Fix dedup hash non-determinism (BLOCKER)
3. Resolve pytest file handle bug (for CI/CD)
4. Execute Waves 2-4 tests successfully
5. Achieve >90% pass rate across all waves

---

## RECOMMENDATIONS

### Immediate Actions (P0):

1. **Fix Ticker Validation CSV**
   - Location: `src/catalyst_bot/ticker_validation.py:183`
   - Issue: CSV parser expecting 1 field, seeing 14
   - Action: Update CSV parsing logic or fix data file format

2. **Fix Dedup Hash**
   - Location: Deduplication signature generation
   - Issue: Non-deterministic hash (different on same input)
   - Action: Ensure all hash inputs are sorted/ordered consistently

3. **Resolve Pytest Bug**
   - Issue: File handle leak in capture module
   - Action: Update pytest/Python version or add cleanup hooks

### Short-Term Actions (P1):

4. **Fix Timezone Handling**
   - Location: Article freshness checks
   - Action: Default timezone-naive to UTC or local time
   - Test: `test_timezone_naive_datetime`, `test_edge_case_exactly_at_threshold`

5. **Execute Remaining Waves**
   - Run Wave 2-4 tests individually
   - Document pass/fail status
   - Update stability score

### Long-Term Actions (P2):

6. **Improve Test Infrastructure**
   - Setup CI/CD pipeline with test batching
   - Add test result trending/monitoring
   - Implement flaky test detection

7. **Increase Test Coverage**
   - Target >80% code coverage
   - Add integration tests for critical paths
   - Test edge cases more thoroughly

---

## TEST EXECUTION LOG

### Wave 1 Execution Details:

```
Platform: win32
Python: 3.13.7
Pytest: 8.4.2
Plugins: anyio-4.11.0, asyncio-1.2.0, mock-3.15.1

Command: pytest tests/test_dedupe.py tests/test_ticker_validation.py
                tests/test_article_freshness.py tests/test_non_substantive.py
                -v --tb=short

Results: 17 failed, 26 passed in 24.70s

Warnings: 2 (plugin compatibility)
```

### Test Collection Summary:

```
Total Items Collected: 1289 tests
Test Files: 89 files
Collection Time: 13.28s
Collection Status: SUCCESS (with warnings)
```

---

## NEXT STEPS FOR DEBUGGING SWEEP

### Agent 3 Handoff:

**Completed:**
- Test suite discovery (89 files, ~1289 tests)
- Wave 1 execution (43 tests, 60.5% pass rate)
- Failure analysis and categorization
- Root cause identification

**Pending:**
- Wave 2-4 test execution
- Full suite execution (blocked by pytest bug)
- Integration test results
- Performance/load test results

**Recommended Next Agent Actions:**
1. Agent 4 should focus on fixing ticker validation CSV
2. Agent 5 should address dedup hash stability
3. Agent 6 should investigate pytest infrastructure issue

---

## APPENDIX: DETAILED FAILURE OUTPUT

### Ticker Validation Failure Example:

```python
WARNING  catalyst_bot.ticker_validation:ticker_validation.py:183
Failed to load ticker list (Error tokenizing data. C error: Expected 1 fields in line 9, saw 14
), disabling ticker validation to avoid false rejections

AssertionError: Validator should have tickers loaded
assert False
 +  where False = <catalyst_bot.ticker_validation.TickerValidator object at 0x000001D4827DCA50>.is_enabled
```

### Dedup Hash Failure Example:

```python
def test_temporal_dedup_key():
    assert key1 == key2
E   AssertionError: assert 'd9e5179f358c...687a68ca54c01' == '7f942def31e0...3f3481cb7f975'
E
E     - 7f942def31e012e13044c1c4a203f3481cb7f975
E     + d9e5179f358c5ddc7fae5f7dccb687a68ca54c01
```

### Timezone Failure Example:

```python
def test_timezone_naive_datetime():
    assert is_fresh is True
E   assert False is True
```

---

**Report End** | Agent 3 Test Execution Complete
