# Catalyst-Bot Codebase Health Report

**Generated:** December 14, 2025
**Codebase Size:** 253 Python modules | ~122,581 lines of code
**Test Files:** 213 total | 2,130+ test functions

---

## Executive Summary

| Category | Health | Critical Issues | High Issues | Medium Issues |
|----------|--------|-----------------|-------------|---------------|
| **Architecture** | 🔴 Poor | 6 | 9 | 7 |
| **Bugs & Errors** | 🟡 Fair | 8 | 6 | 2 |
| **Security** | 🟡 Fair | 1 | 2 | 4 |
| **Code Quality** | 🟡 Fair | 2 | 5 | 8 |
| **Testing** | 🟡 Fair | 5 | 5 | 5 |
| **Dependencies** | 🟡 Fair | 1 | 2 | 4 |

**Overall Health Score: 45/100** - Significant technical debt requiring attention

---

## 🔴 CRITICAL ISSUES

### 1. God Modules - Massive Files Violating Single Responsibility

| File | Lines | Functions | Problem |
|------|-------|-----------|---------|
| `runner.py` | 4,617 | 47 | Main loop does everything |
| `alerts.py` | 3,816 | 26 | Alert logic scattered |
| `feeds.py` | 3,402 | 33 | 7+ data sources in one file |
| `classify.py` | 2,649 | 38 | Multiple responsibilities |

**Solutions:**
1. **Extract Service Classes** - Break `runner.py` into `FeedProcessor`, `ClassificationPipeline`, `AlertManager`, `StatsTracker` classes
2. **Create Subsystem Directories** - Move related code into `alerts/`, `feeds/`, `classification/` subdirectories with focused modules

---

### 2. Hardcoded API Key in Source Code

**File:** `src/catalyst_bot/historical_bootstrapper.py:68`
```python
_finnhub_api_key = os.getenv("FINNHUB_API_KEY", "d26q8dhr01qvrairld20d26q8dhr01qvrairld2g")
```

**Solutions:**
1. **Remove Default** - Change to `os.getenv("FINNHUB_API_KEY")` and fail gracefully if missing
2. **Add Secret Scanning** - Implement `detect-secrets` or `git-secrets` in pre-commit hooks

---

### 3. Race Condition in Alert State Management

**File:** `src/catalyst_bot/alerts.py:74-114`
- `_alert_downgraded` global accessed across threads without consistent lock protection
- `asyncio.create_task()` at line 1621 may read stale values

**Solutions:**
1. **Always Use Accessors** - Never directly reference `_alert_downgraded`; always use `get_alert_downgraded()` / `set_alert_downgraded()`
2. **Use Thread-Safe Data Structure** - Replace with `threading.local()` or `contextvars.ContextVar`

---

### 4. IndexError in Database Result Unpacking

**Files:** `news_velocity.py:264,403,407,415`, `float_data.py:511`
```python
count = cursor.fetchone()[0]  # Crashes if fetchone() returns None
latest = data[0]              # Crashes if data is empty
```

**Solutions:**
1. **Add Bounds Checking** - `result = cursor.fetchone(); count = result[0] if result else 0`
2. **Use Tuple Unpacking with Default** - `(count,) = cursor.fetchone() or (0,)`

---

### 5. Async Fire-and-Forget Without Error Handling

**File:** `src/catalyst_bot/alerts.py:1621`
```python
asyncio.create_task(_enrich_alert_with_llm(...))  # Exceptions silently lost
```

**Solutions:**
1. **Add Done Callback** - `task = asyncio.create_task(...); task.add_done_callback(handle_task_exception)`
2. **Use TaskGroup (Python 3.11+)** - Wrap in `async with asyncio.TaskGroup() as tg:` for proper exception handling

---

### 6. Missing Dockerfile (CI/CD Will Fail)

**File:** `.github/workflows/trading-bot-ci.yml:280` references `docker/Dockerfile` that doesn't exist

**Solutions:**
1. **Create Dockerfile** - Add `docker/Dockerfile` with Python 3.11 base, requirements installation, and entrypoint
2. **Remove Docker Job** - If containerization not needed, remove the `docker-build` job from CI workflow

---

### 7. Critical Modules Lacking Tests

| Module | LOC | Test Coverage | Risk |
|--------|-----|---------------|------|
| `runner.py` | 4,617 | 1 smoke test | Main loop untested |
| `alerts.py` | 3,816 | 3 partial files | Alert delivery untested |
| `feeds.py` | 3,402 | 2 partial files | Feed processing gaps |
| `classify.py` | 2,649 | 1 file | Classification edge cases |
| `config.py` | 1,624 | 2 config files | Config validation missing |

**Solutions:**
1. **Add Integration Tests** - Create `tests/integration/test_full_cycle.py` testing feed→classify→alert pipeline
2. **Add Error Path Tests** - For each module, add tests for timeout, malformed input, and API failure scenarios

---

### 8. Extremely Complex Functions

| Function | File | Complexity |
|----------|------|------------|
| `_build_discord_embed()` | alerts.py:1739 | 346 |
| `fetch_pr_feeds()` | feeds.py | 217 |
| `_cycle()` | runner.py | 198 |

**Solutions:**
1. **Extract Helper Methods** - Break each function into 5-10 smaller functions with single responsibilities
2. **Use Strategy Pattern** - Create embed builder strategies, feed fetcher strategies to reduce branching

---

## 🟠 HIGH SEVERITY ISSUES

### 9. SQL Injection via String Concatenation

**File:** `src/catalyst_bot/keyword_review_db.py:439-447`
```python
conn.execute(f"""UPDATE keyword_reviews SET {new_status.lower()}_count = ...""")
```

**Solutions:**
1. **Whitelist Validation** - `if new_status.lower() not in ("pending", "approved", "rejected"): raise ValueError()`
2. **Use Column Mapping** - `COLUMN_MAP = {"pending": "pending_count", ...}; col = COLUMN_MAP[new_status]`

---

### 10. Unsafe Pickle Deserialization (RCE Risk)

**Files:** `sector_context.py:437`, `historical_bootstrapper.py:927`, `rag_system.py:263`, `sec_document_fetcher.py:117`, `rvol.py:140`

**Solutions:**
1. **Switch to JSON** - Replace pickle with `json.dump()`/`json.load()` for simple data
2. **Add HMAC Validation** - Before loading, verify cache file integrity with HMAC signature

---

### 11. 156 Root-Level Modules (Flat Namespace)

`src/catalyst_bot/` contains 156 `.py` files at root level - impossible to navigate

**Solutions:**
1. **Reorganize by Domain** - Create directories: `alerts/`, `charts/`, `llm/`, `market/`, `feeds/`, `broker/`
2. **Create Package Facades** - Each directory gets `__init__.py` exporting clean public API

---

### 12. Runner.py Has 14 Dependencies

**File:** `src/catalyst_bot/runner.py:32-99`
- Imports from 14+ internal modules creating tight coupling
- Any change to runner is high risk

**Solutions:**
1. **Dependency Injection** - Pass dependencies as constructor arguments instead of importing
2. **Create Facades** - Import from high-level facades (`from .services import classification_service`) instead of low-level modules

---

### 13. Missing Discord Signature Verification

**File:** `src/catalyst_bot/health_endpoint.py:221-290`
- `/interactions` endpoint processes Discord requests without signature verification

**Solutions:**
1. **Add Verification** - Copy signature verification logic from `interaction_server.py` to `health_endpoint.py`
2. **Extract Shared Module** - Create `discord_security.py` with shared verification function

---

### 14. Incomplete Error Handling in Order Executor

**File:** `src/catalyst_bot/execution/order_executor.py:455-478`
- `_round_price_for_alpaca()` can raise `ValueError` but callers don't catch it
- `current_price` can be None leading to type errors

**Solutions:**
1. **Add Try-Except** - Wrap price calculations in try-except with proper logging
2. **Add None Checks** - `if current_price is None: return None` early in function

---

### 15. Resource Leaks in Broker Client

**File:** `src/catalyst_bot/broker/alpaca_client.py:156-174`
- `ClientSession` not closed if `_test_connection()` fails

**Solutions:**
1. **Add try/finally** - Ensure `session.close()` in finally block
2. **Use async context manager** - `async with aiohttp.ClientSession() as session:`

---

### 16. 770+ Bare Exception Catches

Pattern found across 70+ files: `except Exception:` swallowing all errors

**Solutions:**
1. **Create Exception Hierarchy** - Define `CatalystError`, `FeedError`, `AlertError` etc.
2. **Catch Specific Exceptions** - Replace `except Exception` with specific types; log and re-raise unknown exceptions

---

### 17. Outdated API Client Versions

| Package | Current | Latest |
|---------|---------|--------|
| `anthropic` | >=0.18.0 | 0.35+ |
| `google-generativeai` | >=0.3.0 | 0.7+ |

**Solutions:**
1. **Update requirements.txt** - `anthropic>=0.35.0,<1` and `google-generativeai>=0.7.0,<1`
2. **Add Dependabot** - Create `.github/dependabot.yml` for automatic updates

---

## 🟡 MEDIUM SEVERITY ISSUES

### 18. No Dependency Lock File

All 38 dependencies use loose constraints (`>=X.Y,<Z`) instead of pinned versions

**Solutions:**
1. **Use pip-compile** - Generate `requirements.lock` from `requirements.in`
2. **Add Poetry/PDM** - Modern dependency management with automatic lock files

---

### 19. Fragmented Related Modules

**Alerts:** 6 files scattered (`alerts.py`, `alerts_rate_limit.py`, `alert_guard.py`, etc.)
**Charts:** 8+ files (`charts.py`, `charts_advanced.py`, `chart_cache.py`, etc.)
**LLM:** 14 files across root and services/

**Solutions:**
1. **Create Subsystem Packages** - `catalyst_bot/alerts/`, `catalyst_bot/charts/`, `catalyst_bot/llm/`
2. **Add Facade Modules** - Single entry point (`alerts/__init__.py`) that exports clean API

---

### 20. Missing Type Hints

50+ functions lack parameter types; 34 files use `Any` type

**Solutions:**
1. **Enable Strict MyPy** - Remove `--no-strict-optional` flag from CI
2. **Gradual Typing** - Add `# type: ignore` budget; reduce by 10 per sprint

---

### 21. Magic Numbers/Strings

Examples found:
- `0.45` - rate limit interval (alerts.py:278)
- `240` - Discord title limit (alerts.py:1748)
- `1900`, `1870` - Discord character limits
- `300` - 5-minute window in seconds

**Solutions:**
1. **Define Constants** - `DISCORD_TITLE_MAX_LEN = 240`, `RATE_LIMIT_MIN_INTERVAL = 0.45`
2. **Move to Config** - Add as Settings fields for tunability

---

### 22. Exposed Debug Information in Errors

**File:** `health_endpoint.py:189,262-273`
```python
error_response = {"error": str(e)}  # Exposes internal details
```

**Solutions:**
1. **Generic Client Errors** - Return `{"error": "Internal server error"}` to clients
2. **Log Full Details** - `log.exception("Request failed")` server-side only

---

### 23. No Distributed Tracing

No request IDs, no correlation across components

**Solutions:**
1. **Add Request ID Middleware** - Generate UUID per request, pass through all logs
2. **Integrate OpenTelemetry** - Add tracing spans for major operations

---

### 24. Config.py is God Module (1,624 lines)

Single Settings dataclass with 100+ attributes covering all domains

**Solutions:**
1. **Split by Domain** - `LLMConfig`, `MarketConfig`, `AlertConfig`, `BrokerConfig`
2. **Add Validation** - Use Pydantic with validators for each config section

---

### 25. Test Organization Mismatch

Tests don't mirror source structure; 35 manual tests not in CI

**Solutions:**
1. **Mirror Structure** - `tests/catalyst_bot/alerts/test_alerts.py` matches `src/catalyst_bot/alerts/`
2. **Integrate Manual Tests** - Move critical manual tests to integration suite

---

### 26. Python Version Inconsistency

- `pyproject.toml`: requires `>=3.11`
- CI matrix: tests `3.9`, `3.10`, `3.11`
- `requirements.txt`: has Python 3.9 conditional

**Solutions:**
1. **Align All Files** - Set minimum to 3.11 everywhere
2. **Update CI Matrix** - Only test 3.11 and 3.12

---

### 27. Wrangler Compatibility Date Outdated

**File:** `workers/interactions/wrangler.toml`
```toml
compatibility_date = "2024-01-01"  # Should be 2025-12-01
```

**Solutions:**
1. **Update Date** - Change to `2025-12-01` for latest Cloudflare features
2. **Add to CI** - Validate wrangler.toml in CI pipeline

---

## 📊 Metrics Summary

| Metric | Value | Target | Status |
|--------|-------|--------|--------|
| Largest file | 4,617 lines | <500 lines | 🔴 9x over |
| Max function complexity | 346 | <20 | 🔴 17x over |
| Bare except catches | 770+ | 0 | 🔴 Critical |
| Root-level modules | 156 | <30 | 🔴 5x over |
| Test coverage (critical) | <10% | 80% | 🔴 Critical |
| Type ignore pragmas | 222 | <50 | 🟡 4x over |
| TODO comments | 50+ | 0 | 🟡 Technical debt |

---

## 🎯 Recommended Action Plan

### Phase 1: Critical Fixes (1-2 Weeks)
1. ☐ Remove hardcoded Finnhub API key
2. ☐ Fix IndexError issues in database queries
3. ☐ Add error callbacks to async tasks
4. ☐ Create missing Dockerfile
5. ☐ Update outdated API client versions
6. ☐ Add SQL injection protection

### Phase 2: Structural Refactoring (2-4 Weeks)
1. ☐ Break down runner.py into service classes
2. ☐ Create alerts/, feeds/, llm/ subsystem directories
3. ☐ Implement proper exception hierarchy
4. ☐ Add dependency injection for testability
5. ☐ Split config.py by domain

### Phase 3: Quality Improvements (Ongoing)
1. ☐ Add integration tests for critical paths
2. ☐ Reduce function complexity (<20 per function)
3. ☐ Add type hints progressively
4. ☐ Replace magic numbers with constants
5. ☐ Add distributed tracing

---

## Files Quick Reference

| Issue Type | Key Files |
|------------|-----------|
| God modules | `runner.py`, `alerts.py`, `feeds.py`, `classify.py` |
| Security | `historical_bootstrapper.py`, `keyword_review_db.py`, `storage.py` |
| Pickle RCE | `sector_context.py`, `rag_system.py`, `sec_document_fetcher.py` |
| Missing tests | `runner.py`, `alerts.py`, `feeds.py`, `config.py` |
| Race conditions | `alerts.py:74-114` |
| Index errors | `news_velocity.py`, `float_data.py` |

---

*Report generated by Claude Code - Codebase Health Review*
