# Wave 1-3 Integration Testing Quick Reference

## Quick Start

### Run All Wave Integration Tests
```bash
cd C:\Users\menza\OneDrive\Desktop\Catalyst-Bot\catalyst-bot
python -m pytest tests/test_wave_integration.py -v
```

### Run All Regression Tests
```bash
python -m pytest tests/test_regression.py -v
```

### Run Both Test Suites
```bash
python -m pytest tests/test_wave_integration.py tests/test_regression.py -v
```

## Test Organization

### Integration Tests (test_wave_integration.py)
- **TestWave1CriticalFilters** - OTC filtering, freshness, non-substantive, dedup
- **TestWave2AlertLayout** - Field restructure, badges, sentiment gauge
- **TestWave3DataQuality** - Float data, chart gaps, multi-ticker, offering sentiment
- **TestInterWaveIntegration** - Cross-wave validation

### Regression Tests (test_regression.py)
- **TestConfigBackwardCompatibility** - Config changes don't break existing setups
- **TestClassificationOutputUnchanged** - API contracts preserved
- **TestAlertEmbedFieldsRequired** - Critical embed fields still present
- **TestExistingIndicatorsUnaffected** - RSI, MACD, VWAP still work

## Running Specific Tests

### Run Single Test Class
```bash
# Wave 1 filters only
python -m pytest tests/test_wave_integration.py::TestWave1CriticalFilters -v

# Wave 2 layout only
python -m pytest tests/test_wave_integration.py::TestWave2AlertLayout -v

# Backward compatibility only
python -m pytest tests/test_regression.py::TestConfigBackwardCompatibility -v
```

### Run Single Test Function
```bash
# OTC filtering test only
python -m pytest tests/test_wave_integration.py::TestWave1CriticalFilters::test_otc_stock_rejected_early -v

# Embed structure test only
python -m pytest tests/test_regression.py::TestAlertEmbedFieldsRequired::test_critical_fields_present_in_embed -v
```

## Test Output Options

### Verbose Output
```bash
python -m pytest tests/test_wave_integration.py -v
```

### Show Print Statements
```bash
python -m pytest tests/test_wave_integration.py -v -s
```

### Show Full Traceback
```bash
python -m pytest tests/test_wave_integration.py -v --tb=long
```

### Short Traceback (Recommended)
```bash
python -m pytest tests/test_wave_integration.py -v --tb=short
```

### Stop on First Failure
```bash
python -m pytest tests/test_wave_integration.py -v -x
```

## Coverage Reports

### Generate HTML Coverage Report
```bash
python -m pytest tests/test_wave_integration.py tests/test_regression.py \
  --cov=catalyst_bot \
  --cov-report=html

# Open htmlcov/index.html in browser
```

### Terminal Coverage Report
```bash
python -m pytest tests/test_wave_integration.py tests/test_regression.py \
  --cov=catalyst_bot \
  --cov-report=term-missing
```

## Test Statistics

| Metric | Value |
|--------|-------|
| Total Tests | 32 |
| Integration Tests | 17 |
| Regression Tests | 15 |
| Test Classes | 7 |
| Lines of Test Code | 1,101 |

## Test Execution Time

Expected execution times (approximate):
- Integration tests: ~5-10 seconds
- Regression tests: ~3-5 seconds
- Full suite: ~10-15 seconds

## Common Issues

### Import Errors
If you see import errors, ensure you're in the correct directory:
```bash
cd C:\Users\menza\OneDrive\Desktop\Catalyst-Bot\catalyst-bot
```

### Module Not Found
Add src to Python path:
```bash
$env:PYTHONPATH = "$PWD\src"
python -m pytest tests/test_wave_integration.py -v
```

### Slow Test Execution
Tests import catalyst_bot modules which may trigger dependency loading. This is normal and only happens once per session.

## Pre-Deployment Checklist

Before deploying Waves 1-3 to production:

- [ ] Run integration tests: `pytest tests/test_wave_integration.py -v`
- [ ] Run regression tests: `pytest tests/test_regression.py -v`
- [ ] All tests pass (32/32)
- [ ] Review INTEGRATION_TEST_REPORT.md
- [ ] Check risk assessment (should be LOW)
- [ ] Enable monitoring for medium-risk items
- [ ] Prepare rollback plan

## Continuous Integration

Add to CI/CD pipeline:
```yaml
# Example GitHub Actions
- name: Run Wave Integration Tests
  run: python -m pytest tests/test_wave_integration.py tests/test_regression.py -v --tb=short

- name: Check Coverage
  run: python -m pytest tests/test_wave_integration.py tests/test_regression.py --cov=catalyst_bot --cov-fail-under=80
```

## Monitoring Post-Deployment

After deploying, monitor these metrics:
1. Dedup rate (should remain ~20-30%)
2. OTC rejection rate (new metric)
3. Stale article rate (should be low)
4. Non-substantive rate (~10-15%)
5. API call reduction (~60% for rejected items)

Check logs:
```bash
# Dedup behavior
grep "dedup" data/logs/bot.jsonl | tail -100

# OTC filtering
grep "otc_check" data/logs/bot.jsonl | tail -50

# Gap filling
grep "gap_filled" data/logs/bot.jsonl | jq '.gap_count' | sort | uniq -c

# Multi-ticker selections
grep "multi_ticker" data/logs/bot.jsonl | jq '{title, primary_ticker}'
```

## Support

For issues or questions:
1. Review INTEGRATION_TEST_REPORT.md for detailed analysis
2. Check test failure messages for specific errors
3. Enable verbose logging: `-v -s --tb=long`
4. Review risk mitigation plans in the report

---

**Created:** October 25, 2025
**Agent:** 4.1 (Integration Testing & Regression Validation)
**Status:** Ready for deployment testing
