# WAVE 4: DEAD CODE REMOVAL - Comprehensive Analysis & Removal Plan

**Project:** Catalyst Bot Codebase Deduplication
**Wave:** 4 - Dead Code Removal
**Author:** WAVE 4 DOCUMENTATION Agent
**Date:** 2025-12-14
**Status:** Documentation Complete - Awaiting Approval

---

## Executive Summary

This document provides a comprehensive analysis of dead, deprecated, and misplaced code in the Catalyst Bot codebase. The analysis identifies **6 modules** (1,299 total lines) and **4 commented code blocks** ready for removal or relocation.

**Total Impact:**
- **1,299 lines** of module code to be removed/relocated
- **270+ lines** of commented code to be cleaned
- **Estimated cleanup time:** 2-3 hours
- **Risk level:** LOW (with proper verification steps)

---

## Table of Contents

1. [Deprecated Modules](#1-deprecated-modules)
   - [1.1 paper_trader.py](#11-paper_traderpy)
   - [1.2 services/llm_monitor.py](#12-servicesllm_monitorpy)
2. [Unused Modules](#2-unused-modules)
   - [2.1 quickchart_integration.py](#21-quickchart_integrationpy)
   - [2.2 runner_impl.py](#22-runner_implpy)
   - [2.3 llm_slash_commands.py](#23-llm_slash_commandspy)
3. [Misplaced Files](#3-misplaced-files)
   - [3.1 broker/integration_example.py](#31-brokerintegration_examplepy)
4. [Commented Code Blocks](#4-commented-code-blocks)
   - [4.1 alerts.py lines 262-271](#41-alertspy-lines-262-271)
   - [4.2 feeds.py lines 2606-2620](#42-feedspy-lines-2606-2620)
   - [4.3 test_end_to_end.py](#43-test_end_to_endpy)
   - [4.4 test_trading_env.py lines 245-474](#44-test_trading_envpy-lines-245-474)
5. [Implementation Plan](#5-implementation-plan)
6. [Verification Checklist](#6-verification-checklist)
7. [Rollback Procedures](#7-rollback-procedures)

---

## 1. DEPRECATED MODULES

### 1.1 paper_trader.py

**Location:** `/home/user/catalyst-bot/src/catalyst_bot/paper_trader.py`
**Size:** 480 lines
**Status:** ⚠️ DEPRECATED but STILL IN USE

#### Current State Analysis

The module was officially deprecated on **2025-11-26** and marked with clear deprecation warnings at the top of the file. It was replaced by the new `TradingEngine` architecture with improved features:

- **Old System:** Simple paper trading with Alpaca integration
- **New System:** TradingEngine with OrderExecutor, PositionManager, and comprehensive risk management
- **Migration docs:** Available in `docs/LEGACY-TO-TRADINGENGINE-MIGRATION-PLAN.md`

**Key Features (Legacy):**
- Paper trade execution with Alpaca
- Fixed position sizing ($500 default)
- Extended hours support (DAY limit orders)
- Position tracking with stop-loss/take-profit
- Background monitoring thread for automated exits

**Replacement:**
```python
# Old (DEPRECATED)
from .paper_trader import execute_paper_trade
execute_paper_trade(ticker="AAPL", price=150.00, alert_id="abc123")

# New (CURRENT)
from .adapters.trading_engine_adapter import execute_with_trading_engine
execute_with_trading_engine(item=scored_item, ticker="AAPL", ...)
```

#### Dependency Mapping

**CRITICAL - Still has active dependencies:**

1. **runner.py (Line 113)** - Module import:
   ```python
   from . import paper_trader
   ```
   Used on line ~136 for `paper_trader.is_enabled()` check

2. **test_position_management.py (Line 32)** - Test file:
   ```python
   from catalyst_bot import paper_trader
   ```
   Manual test script that validates paper trading functionality

3. **alerts.py** - Legacy wrapper function:
   ```python
   def execute_paper_trade(*args, **kwargs):
       """Legacy wrapper - redirects to TradingEngine via adapter."""
       log.warning("execute_paper_trade_legacy_called")
       return None
   ```
   This is a NO-OP wrapper that just logs a warning

**Dynamic/String References:**
- Documentation files reference it for migration context
- Backup file exists: `paper_trader.py.LEGACY_BACKUP_2025-11-26`

**Git History:**
- Last meaningful commit: 2025-11-26 (deprecation marker added)
- Created: 2025-11-20 with full paper trading implementation
- Age: ~6 days before deprecation

#### Removal Plan

**Status:** ⚠️ CANNOT DELETE IMMEDIATELY - Requires migration first

**Migration Steps:**

1. **Phase 1: Remove runner.py dependency**
   - Replace `paper_trader.is_enabled()` with direct env var check
   - Or create minimal feature flag helper function

   ```python
   # In runner.py, replace:
   if paper_trader.is_enabled():
       # ...

   # With:
   def is_trading_enabled():
       return os.getenv("FEATURE_PAPER_TRADING", "1") == "1" and \
              bool(os.getenv("ALPACA_API_KEY")) and \
              bool(os.getenv("ALPACA_SECRET"))

   if is_trading_enabled():
       # ...
   ```

2. **Phase 2: Update test_position_management.py**
   - Either delete the test (it's a manual script, not automated)
   - Or update to use new TradingEngine adapter

3. **Phase 3: Remove alerts.py wrapper**
   - The NO-OP wrapper can be safely removed
   - Add comment explaining TradingEngine usage

4. **Phase 4: Delete paper_trader.py**
   - Once all dependencies removed
   - Keep backup file for 30 days

**Code Worth Salvaging:**
- ✅ Position sizing logic (already migrated to TradingEngine)
- ✅ Extended hours handling (already in TradingEngine)
- ✅ Alpaca client initialization (in broker/alpaca_wrapper.py)
- ❌ No additional code needs salvaging

**Deletion Order:**
1. Update `runner.py` (remove import)
2. Update/delete `test_position_management.py`
3. Remove wrapper from `alerts.py`
4. Delete `paper_trader.py`

#### Pre-Deletion Verification

**Commands to verify nothing imports the file:**
```bash
# Search for imports
grep -r "from.*paper_trader" src/catalyst_bot/ --include="*.py"
grep -r "import.*paper_trader" src/catalyst_bot/ --include="*.py"

# Search for function calls
grep -r "execute_paper_trade\|paper_trader\." src/catalyst_bot/ --include="*.py"

# Expected: Only matches in files we're updating
```

**Tests to run before deletion:**
```bash
# Run all tests to ensure TradingEngine works
python -m pytest tests/test_*adapter.py -v

# Verify bot starts without paper_trader
python -m catalyst_bot.runner --dry-run

# Check imports work
python -c "from catalyst_bot.adapters.trading_engine_adapter import execute_with_trading_engine"
```

**How to confirm bot still works:**
```bash
# 1. Start bot in dry-run mode
FEATURE_PAPER_TRADING=0 python -m catalyst_bot.runner --dry-run

# 2. Check logs for TradingEngine initialization
grep "trading_engine" logs/catalyst_bot.log

# 3. Verify no paper_trader errors
grep "paper_trader" logs/catalyst_bot.log  # Should be empty
```

#### Rollback Plan

**If deletion causes issues:**

```bash
# Restore from backup
git checkout HEAD~1 -- src/catalyst_bot/paper_trader.py

# Or from backup file
cp src/catalyst_bot/paper_trader.py.LEGACY_BACKUP_2025-11-26 \
   src/catalyst_bot/paper_trader.py

# Verify restoration
python -c "from catalyst_bot import paper_trader; print('OK')"
```

**Recovery time:** < 1 minute

---

### 1.2 services/llm_monitor.py

**Location:** `/home/user/catalyst-bot/src/catalyst_bot/services/llm_monitor.py`
**Size:** 266 lines
**Status:** ⚠️ SUPERSEDED but has one remaining import

#### Current State Analysis

This module was superseded by `llm_usage_monitor.py` which provides enhanced functionality:

**Old System (llm_monitor.py):**
- Basic cost tracking by provider/model/feature
- Daily/monthly budget alerts
- Thread-safe counters
- In-memory state only

**New System (llm_usage_monitor.py):**
- Per-provider token counting
- Persistent logging to JSON (data/logs/llm_usage.jsonl)
- Rate limit monitoring
- Better cost calculation with current pricing
- More detailed breakdowns

**Created:** 2025-11-20 (Unified LLM Service implementation)
**Superseded by:** `llm_usage_monitor.py` (also created 2025-11-20)

#### Dependency Mapping

**Active Dependencies:**

1. **llm_service.py (Line 222)** - Conditional import:
   ```python
   @property
   def monitor(self):
       """Lazy-load monitor."""
       if self._monitor is None and self.config.get("cost_tracking_enabled"):
           try:
               from .llm_monitor import LLMMonitor
               self._monitor = LLMMonitor(self.config)
           except Exception as e:
               log.warning("llm_monitor_init_failed err=%s", str(e))
               self._monitor = None
       return self._monitor
   ```

   **Note:** This is wrapped in try/except, suggesting it's optional/fallback

2. **Documentation references:**
   - `docs/heartbeat-audit/PATCH-01-critical-bugs.md` - Shows usage example

**Actual Usage:**
The `llm_usage_monitor.py` is actively used in 16+ files:
- `runner.py` - `from .llm_usage_monitor import get_monitor`
- `llm_hybrid.py` - `from .llm_usage_monitor import estimate_tokens, get_monitor`
- `historical_bootstrapper.py` - Active usage
- Multiple test files
- Scripts (`llm_usage_report.py`)

**Conclusion:** `llm_monitor.py` appears to be a fallback/legacy version that's no longer the primary monitoring solution.

#### Removal Plan

**Status:** ⚠️ SAFE TO DELETE after updating llm_service.py

**Migration Steps:**

1. **Update llm_service.py** to use `llm_usage_monitor` instead:
   ```python
   # Replace in llm_service.py:
   from .llm_monitor import LLMMonitor

   # With:
   from ..llm_usage_monitor import get_monitor
   ```

2. **Remove the module:**
   ```bash
   git rm src/catalyst_bot/services/llm_monitor.py
   ```

**Code Worth Salvaging:**
- ❌ Budget alert thresholds (already in llm_usage_monitor.py)
- ❌ Thread-safe counters (already implemented better in new version)
- ❌ No unique functionality to preserve

**Deletion Order:**
1. Update `llm_service.py` import
2. Test LLM operations work
3. Delete `llm_monitor.py`

#### Pre-Deletion Verification

**Commands:**
```bash
# Verify only llm_service.py imports it
grep -r "from.*llm_monitor import\|import.*llm_monitor" \
  src/catalyst_bot/ --include="*.py" | grep -v "llm_usage_monitor"

# Should only show llm_service.py

# Verify llm_usage_monitor is working
python -c "from catalyst_bot.llm_usage_monitor import get_monitor; print(get_monitor())"
```

**Tests:**
```bash
# Test LLM service with new monitor
python -m pytest tests/test_cost_optimization_patch.py -v
python -m pytest tests/manual/test_llm_usage_monitor.py -v
```

**Confirmation:**
```bash
# Run a cycle with LLM operations
python -m catalyst_bot.runner --dry-run

# Check that usage is logged
ls -lh data/logs/llm_usage.jsonl  # Should exist and grow
```

#### Rollback Plan

```bash
# Restore file
git checkout HEAD~1 -- src/catalyst_bot/services/llm_monitor.py

# Restore import in llm_service.py
git checkout HEAD~1 -- src/catalyst_bot/services/llm_service.py
```

---

## 2. UNUSED MODULES

### 2.1 quickchart_integration.py

**Location:** `/home/user/catalyst-bot/src/catalyst_bot/quickchart_integration.py`
**Size:** 252 lines
**Status:** ✅ SAFE TO DELETE - Never imported

#### Current State Analysis

This module provides utilities for QuickChart availability checking and fallback logic. However, it is **never imported** in the actual codebase.

**Purpose:**
- Check QuickChart service availability
- Generate chart URLs with fallback
- Cache chart generation
- Log metrics

**Features:**
- `is_quickchart_available()` - Availability check with caching
- `generate_chart_url_with_fallback()` - Main generation function
- `log_chart_generation_metrics()` - Metrics logging
- Integration with `charts_quickchart.py` and `chart_cache.py`

**Created:** Unknown (no specific deprecation marker)

#### Dependency Mapping

**Import Analysis:**
```bash
# Search results: NO MATCHES in source code
grep -r "from.*quickchart_integration\|import.*quickchart_integration" \
  src/catalyst_bot/ --include="*.py"
# Result: No matches
```

**Documentation References:**
- `docs/waves/WAVE_2.1_QUICK_START.md` - Shows example import
- `docs/waves/WAVE_2.1_IMPLEMENTATION_GUIDE.md` - Shows example import

**Actual Chart Implementation:**
The bot uses `charts_quickchart.py` directly (143 lines), which is imported and used:
```python
# In alerts.py and other files:
from .charts_quickchart import get_quickchart_url
```

**Conclusion:** This module was likely written as a wrapper/helper layer but never integrated into the actual codebase. The functionality exists directly in `charts_quickchart.py`.

#### Removal Plan

**Status:** ✅ SAFE TO DELETE IMMEDIATELY

**Steps:**
1. Verify no imports (already confirmed)
2. Delete the file
3. Remove documentation references (optional)

**Code Worth Salvaging:**
- ❌ Availability checking (feature flag in env vars is sufficient)
- ❌ Fallback logic (already handled in charts_quickchart.py)
- ✅ Metrics logging function could be useful, but already exists elsewhere

**Command:**
```bash
git rm src/catalyst_bot/quickchart_integration.py
```

#### Pre-Deletion Verification

**Commands:**
```bash
# Triple-check no imports
grep -r "quickchart_integration" src/catalyst_bot/ --include="*.py"
grep -r "quickchart_integration" tests/ --include="*.py"

# Should only find in: (none)

# Verify charts still work via charts_quickchart.py
grep -r "from.*charts_quickchart import" src/catalyst_bot/ --include="*.py"
# Should find multiple files using it
```

**Tests:**
```bash
# Verify chart generation works
python -c "from catalyst_bot.charts_quickchart import get_quickchart_url; print('OK')"

# Run bot to ensure charts generate
python -m catalyst_bot.runner --dry-run
```

**Confirmation:**
Check that chart URLs are generated in alerts without this module.

#### Rollback Plan

```bash
# Restore file
git checkout HEAD~1 -- src/catalyst_bot/quickchart_integration.py
```

**Recovery time:** < 30 seconds

---

### 2.2 runner_impl.py

**Location:** `/home/user/catalyst-bot/src/catalyst_bot/runner_impl.py`
**Size:** 22 lines
**Status:** ✅ SAFE TO DELETE - Never imported

#### Current State Analysis

This is a tiny utility module that runs the bot for exactly one cycle:

```python
def run_once():
    # Spawn normal loop, capture output, stop at first CYCLE_DONE
    cmd = [sys.executable, "-m", "catalyst_bot.runner", "--loop"]
    env = os.environ.copy()
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                         text=True, env=env)
    for line in p.stdout:
        print(line, end="")
        if "CYCLE_DONE" in line:
            p.terminate()
            try:
                p.wait(3)
            except Exception:
                p.kill()
            return 0
    return p.wait()
```

**Purpose:** Execute one bot cycle then exit (for testing/cron jobs)

**Created:** Unknown
**Last Modified:** Unknown (no recent commits found)

#### Dependency Mapping

**Import Analysis:**
```bash
grep -r "from.*runner_impl\|import.*runner_impl" . --include="*.py"
# Result: No matches found
```

**Usage Analysis:**
- Never imported in source code
- Never imported in tests
- Never mentioned in documentation
- No __main__ block, so can't be run as script

**Conclusion:** This was likely an experimental utility that was never integrated.

#### Removal Plan

**Status:** ✅ SAFE TO DELETE IMMEDIATELY

**Alternative:**
The same functionality can be achieved with:
```bash
# Run one cycle
python -m catalyst_bot.runner --once

# Or with timeout
timeout 300 python -m catalyst_bot.runner --loop
```

**Command:**
```bash
git rm src/catalyst_bot/runner_impl.py
```

#### Pre-Deletion Verification

**Commands:**
```bash
# Verify no references
grep -r "runner_impl" src/ tests/ --include="*.py"
grep -r "run_once" src/ tests/ --include="*.py" | grep -v "def run_once"
```

**Tests:**
```bash
# Verify runner.py works normally
python -m catalyst_bot.runner --help
```

#### Rollback Plan

```bash
git checkout HEAD~1 -- src/catalyst_bot/runner_impl.py
```

---

### 2.3 llm_slash_commands.py

**Location:** `/home/user/catalyst-bot/src/catalyst_bot/llm_slash_commands.py`
**Size:** 15 lines
**Status:** ✅ SAFE TO DELETE - Stub with only TODO

#### Current State Analysis

This is a stub file with only a docstring and a TODO comment:

```python
"""
LLM-Powered Discord Slash Commands
===================================

Natural language interface to bot operations via Discord slash commands.

Examples:
- /ask "Is AAPL a good buy right now?"
- /research TSLA "What catalysts are coming up?"
- /compare NVDA AMD "Which has better momentum?"
- /tune "Increase selectivity for biotech alerts"
"""

# TODO: Implement LLM-powered slash commands
# This module will integrate with llm_hybrid.py for natural language processing
```

**Purpose:** Planned feature for natural language Discord commands
**Status:** Never implemented
**Created:** Unknown

#### Dependency Mapping

**Import Analysis:**
```bash
grep -r "from.*llm_slash_commands\|import.*llm_slash_commands" . --include="*.py"
# Result: No matches found
```

**Conclusion:** This is a placeholder that was never developed.

#### Removal Plan

**Status:** ✅ SAFE TO DELETE IMMEDIATELY

**Decision:**
- If the feature is still desired, track it in GitHub Issues/TODO list
- The stub file provides no value and clutters the codebase

**Command:**
```bash
git rm src/catalyst_bot/llm_slash_commands.py
```

**Code Worth Salvaging:**
- ✅ Feature idea - Add to project backlog/roadmap
- ❌ No actual code to preserve

#### Pre-Deletion Verification

**Commands:**
```bash
# Verify no references
grep -r "llm_slash_commands" src/ tests/ docs/ --include="*.py" --include="*.md"
```

#### Rollback Plan

```bash
git checkout HEAD~1 -- src/catalyst_bot/llm_slash_commands.py
```

---

## 3. MISPLACED FILES

### 3.1 broker/integration_example.py

**Location:** `/home/user/catalyst-bot/src/catalyst_bot/broker/integration_example.py`
**Size:** 489 lines
**Status:** ⚠️ RELOCATE to /examples directory

#### Current State Analysis

This is a comprehensive example/demo file showing how to use the broker integration components. It includes:

**Contents:**
1. `TradingBot` class - Complete trading bot example
2. `demo_simple()` - Simple trading workflow demo
3. `demo_advanced()` - Advanced workflow with multiple signals
4. Full docstrings and usage instructions

**Features Demonstrated:**
- Connecting to broker
- Analyzing trading signals
- Executing trades with position sizing
- Managing open positions
- Monitoring stop-losses/take-profits
- Closing positions and P&L calculation
- Performance reporting

**Purpose:** Educational/example code for developers

#### Dependency Mapping

**Import Analysis:**
```bash
grep -r "from.*integration_example\|import.*integration_example" . --include="*.py"
# Result: No matches found (as expected for example code)
```

**Why it's misplaced:**
- Located in `src/catalyst_bot/broker/` (production source directory)
- Should be in `/examples` directory with other example scripts
- Contains `if __name__ == "__main__"` block for standalone execution
- Has demo functions, not production code

**Current Examples Directory:**
```
/home/user/catalyst-bot/examples/
├── backtest_custom_data_source_example.py
├── fundamental_data_usage.py
├── grid_search_example.py
├── keyword_mining_example.py
└── robust_statistics_demo.py
```

#### Relocation Plan

**Status:** ⚠️ RELOCATE (NOT DELETE)

**Steps:**

1. **Move file to examples directory:**
   ```bash
   git mv src/catalyst_bot/broker/integration_example.py \
          examples/broker_integration_example.py
   ```

2. **Update imports in the file:**
   ```python
   # Change relative imports to absolute:
   from ..logging_utils import get_logger, setup_logging
   # To:
   from catalyst_bot.logging_utils import get_logger, setup_logging

   from .alpaca_client import AlpacaBrokerClient
   # To:
   from catalyst_bot.broker.alpaca_client import AlpacaBrokerClient

   # etc.
   ```

3. **Update documentation references:**
   - Search for references to `broker/integration_example.py`
   - Update to `examples/broker_integration_example.py`

4. **Test the example still runs:**
   ```bash
   python examples/broker_integration_example.py
   ```

#### Pre-Relocation Verification

**Commands:**
```bash
# Verify no production code imports it
grep -r "integration_example" src/catalyst_bot/ --include="*.py"

# Should only find the file itself

# Verify examples directory exists
ls -la examples/

# Check documentation references
grep -r "integration_example" docs/ --include="*.md"
```

**Tests:**
```bash
# Run the example before moving
cd src/catalyst_bot/broker
python integration_example.py  # Should show usage instructions

# Verify imports work
python -c "from catalyst_bot.broker.alpaca_client import AlpacaBrokerClient; print('OK')"
```

#### Post-Relocation Verification

```bash
# After moving, test it runs from new location
python examples/broker_integration_example.py

# Verify old location gone
ls src/catalyst_bot/broker/integration_example.py  # Should not exist
```

#### Rollback Plan

```bash
# Move back to original location
git mv examples/broker_integration_example.py \
       src/catalyst_bot/broker/integration_example.py

# Restore original imports
git checkout HEAD~1 -- src/catalyst_bot/broker/integration_example.py
```

---

## 4. COMMENTED CODE BLOCKS

### 4.1 alerts.py lines 262-271

**Location:** `/home/user/catalyst-bot/src/catalyst_bot/alerts.py:262-271`
**Size:** 10 lines (plus 12 lines of explanatory comments)
**Status:** ⚠️ KEEP - Valuable documentation

#### Current State Analysis

This is a **commented documentation block** explaining the limitations of the in-memory rate limiter:

```python
# SOLUTION FOR MULTI-INSTANCE DEPLOYMENTS:
# For production deployments with multiple bot processes, implement a
# Redis-based rate limiter that shares state across all instances. Example:
#
#   import redis
#   client = redis.Redis(host='localhost', port=6379)
#
#   def _rl_should_wait_distributed(url: str) -> float:
#       key = f"rl:{hashlib.md5(url.encode()).hexdigest()}"
#       next_ok = client.get(key)
#       if next_ok:
#           return max(0, float(next_ok) - time.time())
#       return 0
#
# Until Redis integration is implemented, this limiter is suitable for:
# - Single-process deployments (most common use case)
# - Development/testing environments
# - Low-volume production deployments with a single bot instance
```

#### Removal Plan

**Status:** ✅ KEEP - This is documentation, not dead code

**Reasoning:**
- Explains important architectural limitation
- Provides implementation guidance for future enhancement
- Documents when the current solution is appropriate
- Only 22 lines total (minimal clutter)

**Recommendation:** Keep as-is. This is valuable documentation for future developers.

---

### 4.2 feeds.py lines 2606-2620

**Location:** `/home/user/catalyst-bot/src/catalyst_bot/feeds.py:2606-2620`
**Size:** 15 lines
**Status:** ✅ SAFE TO DELETE - Obsolete performance optimization

#### Current State Analysis

This is commented-out price floor filtering code that was moved elsewhere for performance:

```python
# PERFORMANCE: Price floor filtering moved to runner.py for batch processing
# This eliminates 100+ sequential price lookups, saving 20-30s per cycle
# Skip illiquid penny stocks when a price floor is defined...
# if ticker and price_floor > 0:
#     tick = ticker.strip().upper()
#     try:
#         # Always fetch last price; reuse the snapshot if already looked up
#         last_price, _ = market.get_last_price_snapshot(tick)
#     except Exception:
#         last_price = None
#     if last_price is not None and last_price < price_floor:
#         # Drop micro‑cap ticker; do not alert or enrich...
#         continue
```

**Context Comment (line 2598):**
```python
# PERFORMANCE: Price floor filtering moved to runner.py for batch processing
# This eliminates 100+ sequential price lookups, saving 20-30s per cycle
```

#### Removal Plan

**Status:** ✅ SAFE TO DELETE

**Steps:**

1. Verify the functionality is implemented in runner.py:
   ```bash
   grep -A 10 "price_floor" src/catalyst_bot/runner.py
   ```

2. Delete the commented block (lines 2606-2620)

3. Keep the explanatory comment (line 2598) that explains where it moved

**Rationale:**
- The code was moved for performance (confirmed in comment)
- Keeping commented code "just in case" is bad practice
- Git history preserves the old implementation if needed

#### Pre-Deletion Verification

**Commands:**
```bash
# Verify price floor filtering exists in runner.py
grep -n "price_floor" src/catalyst_bot/runner.py

# Should show active implementation

# Verify feeds.py still works without this block
python -c "from catalyst_bot.feeds import fetch_pr_feeds; print('OK')"
```

**Tests:**
```bash
# Run a full cycle to ensure filtering still works
python -m catalyst_bot.runner --dry-run

# Check that penny stocks are filtered
grep "price_floor" logs/catalyst_bot.log
```

#### Rollback Plan

```bash
# Restore the commented block
git checkout HEAD~1 -- src/catalyst_bot/feeds.py
```

---

### 4.3 test_end_to_end.py

**Location:** `/home/user/catalyst-bot/tests/integration/test_end_to_end.py`
**Size:** 623 lines (mostly commented tests)
**Status:** ⚠️ KEEP OR DELETE ENTIRE FILE

#### Current State Analysis

This is a comprehensive end-to-end test file with **extensive test stubs**:

**Structure:**
- 20+ test functions
- All test bodies are commented out
- Only contains TODO comments and docstrings
- Uses pytest markers: `@pytest.mark.integration`, `@pytest.mark.e2e`

**Test Categories:**
1. Happy Path: Complete Profitable Trade
2. Stop-Loss Path: Complete Losing Trade
3. Risk Limit Path: Circuit Breaker
4. Data Pipeline Test
5. Multiple Concurrent Alerts
6. Alert Score Filtering
7. Position Limits
8. Database Persistence
9. Portfolio Snapshots
10. Error Recovery
11. Market Hours
12. Performance Tests
13. System Shutdown
14. Complete Trading Day Simulation

**Example:**
```python
@pytest.mark.integration
@pytest.mark.e2e
def test_complete_profitable_trade_flow(trading_system, test_db):
    """Test complete trading flow: Alert → Entry → Price rises → Take profit."""
    # ARRANGE
    alert = create_breakout_alert(...)

    # ACT - Process alert
    # order_id = trading_system.process_alert(alert)

    # ASSERT - Order executed
    # assert order_id is not None
    pass  # Everything commented out
```

#### Removal Plan

**Status:** ⚠️ DECISION NEEDED

**Option 1: DELETE THE FILE**
- **Pros:** Removes 623 lines of dead code
- **Cons:** Loses test structure/documentation
- **When:** If the trading system architecture has changed significantly

**Option 2: KEEP AS TEST SPECIFICATION**
- **Pros:** Documents expected behavior and test scenarios
- **Cons:** May confuse developers (looks like tests but doesn't test anything)
- **When:** If planning to implement these tests soon

**Option 3: CONVERT TO DOCUMENTATION**
- **Pros:** Preserves test scenarios in proper format
- **Cons:** Requires effort to convert
- **Steps:**
  1. Create `docs/testing/E2E_TEST_SCENARIOS.md`
  2. Extract test scenarios and assertions
  3. Delete the test file

**Recommendation:** **Option 3** - Convert to documentation

The test scenarios are valuable as specifications, but shouldn't exist as commented-out test code.

#### Migration to Documentation

**Create:** `/home/user/catalyst-bot/docs/testing/E2E_TEST_SCENARIOS.md`

**Content structure:**
```markdown
# End-to-End Test Scenarios

## 1. Complete Profitable Trade Flow

**Scenario:**
1. Receive high-score breakout alert for AAPL
2. Risk validation passes
3. Order executed successfully
4. Position opened and tracked
5. Price rises to take-profit level
6. Position closed automatically
7. Profit recorded in database

**Assertions:**
- Order ID is not None
- Orders list contains AAPL
- Position unrealized P&L > 0
- Position closed with profit
- Database contains trade record
...
```

Then delete the test file:
```bash
git rm tests/integration/test_end_to_end.py
```

#### Pre-Deletion Verification

**Commands:**
```bash
# Check if any actual tests exist
grep -n "assert.*!=" tests/integration/test_end_to_end.py
grep -n "assert.*==" tests/integration/test_end_to_end.py

# Should find: Only commented assertions

# Verify no other files import it
grep -r "test_end_to_end" tests/ src/ --include="*.py"
```

#### Rollback Plan

```bash
git checkout HEAD~1 -- tests/integration/test_end_to_end.py
```

---

### 4.4 test_trading_env.py lines 245-474

**Location:** `/home/user/catalyst-bot/tests/ml/test_trading_env.py:245-474`
**Size:** 230 lines (commented test code)
**Status:** ⚠️ SIMILAR TO test_end_to_end.py

#### Current State Analysis

This file has the same pattern as `test_end_to_end.py`:
- Test stubs with comprehensive docstrings
- All assertions commented out
- Test bodies just `pass`

**Test Categories:**
- Episode termination
- Reward calculation (profitable/losing trades, risk penalty, Sharpe ratio)
- Position management (open/close, insufficient funds)
- Data handling (price data, end of data)
- Performance metrics
- Observation space
- Integration with RL agents

**Example:**
```python
def test_reward_for_profitable_trade():
    """Test reward calculation for profitable trades."""
    # TODO: Define reward function

    # entry_price = 100
    # exit_price = 110
    # pnl = (exit_price - entry_price) * quantity
    # reward = calculate_reward(pnl, portfolio_value=100000)
    # assert reward > 0  # Positive reward for profit
    pass
```

#### Removal Plan

**Status:** ⚠️ SAME OPTIONS AS test_end_to_end.py

**Recommendation:** **Convert to documentation** or **Delete**

Since this is ML/RL-related testing for a trading environment that may not be implemented, the decision depends on:
- Is RL-based trading planned? → Keep as docs
- Is RL abandoned? → Delete

**If converting to docs:**
Create: `docs/testing/ML_TRADING_ENV_TEST_SCENARIOS.md`

**If deleting:**
```bash
git rm tests/ml/test_trading_env.py
```

#### Pre-Deletion Verification

**Commands:**
```bash
# Check for actual test code
grep -n "^[^#]*assert" tests/ml/test_trading_env.py

# Check if TradingEnv class exists
grep -r "class TradingEnv" src/ --include="*.py"

# Check imports
grep -r "from.*test_trading_env\|import.*test_trading_env" . --include="*.py"
```

---

## 5. IMPLEMENTATION PLAN

### Phase 1: Quick Wins (Low Risk, Immediate Deletion)

**Target:** Remove confirmed dead code
**Duration:** 30 minutes
**Risk:** Minimal

```bash
# Step 1: Delete never-imported modules
git rm src/catalyst_bot/quickchart_integration.py
git rm src/catalyst_bot/runner_impl.py
git rm src/catalyst_bot/llm_slash_commands.py

# Step 2: Remove obsolete commented code in feeds.py
# Edit src/catalyst_bot/feeds.py and delete lines 2606-2620

# Step 3: Commit
git add -A
git commit -m "chore: remove dead code (quickchart_integration, runner_impl, llm_slash_commands) and obsolete comments"
```

**Verification:**
```bash
# Run full test suite
python -m pytest tests/ -v

# Run one bot cycle
python -m catalyst_bot.runner --dry-run

# Check for import errors
python -c "from catalyst_bot import runner, feeds; print('OK')"
```

### Phase 2: Relocate Misplaced Files (Medium Risk)

**Target:** Move examples to proper location
**Duration:** 20 minutes
**Risk:** Low

```bash
# Step 1: Move integration example
git mv src/catalyst_bot/broker/integration_example.py \
       examples/broker_integration_example.py

# Step 2: Update imports in the moved file
# Edit examples/broker_integration_example.py:
# - Change all relative imports to absolute imports
# - from ..logging_utils import → from catalyst_bot.logging_utils import
# - from .alpaca_client import → from catalyst_bot.broker.alpaca_client import

# Step 3: Test it works
python examples/broker_integration_example.py

# Step 4: Commit
git add -A
git commit -m "refactor: move integration_example.py to examples/ directory"
```

### Phase 3: Deprecation Cleanup (Higher Risk, Requires Testing)

**Target:** Remove deprecated modules after migration
**Duration:** 1-2 hours
**Risk:** Medium (requires code changes)

#### 3A: Remove llm_monitor.py dependency

```bash
# Step 1: Update llm_service.py
# Edit src/catalyst_bot/services/llm_service.py
# Replace:
#   from .llm_monitor import LLMMonitor
# With:
#   from ..llm_usage_monitor import LLMUsageMonitor

# Step 2: Test LLM operations
python -m pytest tests/test_cost_optimization_patch.py -v
python -m pytest tests/manual/test_llm_usage_monitor.py -v

# Step 3: Delete the old module
git rm src/catalyst_bot/services/llm_monitor.py

# Step 4: Run full bot cycle
python -m catalyst_bot.runner --dry-run

# Step 5: Commit
git add -A
git commit -m "refactor: remove deprecated llm_monitor.py, use llm_usage_monitor.py"
```

#### 3B: Remove paper_trader.py dependency

```bash
# Step 1: Update runner.py
# Edit src/catalyst_bot/runner.py
# Remove line 113: from . import paper_trader
# Replace paper_trader.is_enabled() with direct env check

# Step 2: Update/delete test_position_management.py
# Edit test_position_management.py to use TradingEngine adapter
# Or delete it if it's obsolete

# Step 3: Remove wrapper from alerts.py
# Edit src/catalyst_bot/alerts.py
# Remove the execute_paper_trade() wrapper function

# Step 4: Test trading operations
python -m pytest tests/test_*adapter.py -v

# Step 5: Delete paper_trader.py
git rm src/catalyst_bot/paper_trader.py

# Keep backup for 30 days
# (paper_trader.py.LEGACY_BACKUP_2025-11-26 already exists)

# Step 6: Run full bot cycle
python -m catalyst_bot.runner --dry-run

# Step 7: Commit
git add -A
git commit -m "refactor: remove deprecated paper_trader.py, use TradingEngine"
```

### Phase 4: Test File Cleanup (Optional)

**Target:** Convert test stubs to documentation or delete
**Duration:** 1 hour
**Risk:** None (test files only)

```bash
# Option A: Convert to documentation
# 1. Create docs/testing/E2E_TEST_SCENARIOS.md
# 2. Extract scenarios from test_end_to_end.py
# 3. Create docs/testing/ML_TRADING_ENV_TEST_SCENARIOS.md
# 4. Extract scenarios from test_trading_env.py

# Option B: Delete stub tests
git rm tests/integration/test_end_to_end.py
git rm tests/ml/test_trading_env.py  # Or just delete lines 245-474

# Commit
git add -A
git commit -m "docs: convert test stubs to documentation" # or "chore: remove test stubs"
```

### Full Implementation Timeline

| Phase | Duration | Risk | Verification Time | Total |
|-------|----------|------|-------------------|-------|
| Phase 1: Quick Wins | 30 min | Low | 10 min | 40 min |
| Phase 2: Relocate Files | 20 min | Low | 10 min | 30 min |
| Phase 3A: llm_monitor | 30 min | Medium | 15 min | 45 min |
| Phase 3B: paper_trader | 45 min | Medium | 20 min | 65 min |
| Phase 4: Test Cleanup | 60 min | None | 5 min | 65 min |
| **TOTAL** | | | | **~3-4 hours** |

---

## 6. VERIFICATION CHECKLIST

### Pre-Deletion Verification

Before removing any file, verify:

- [ ] **No active imports** - Search codebase for import statements
  ```bash
  grep -r "from.*MODULE_NAME\|import.*MODULE_NAME" src/ tests/ --include="*.py"
  ```

- [ ] **No string-based imports** - Check for `__import__()` or `importlib`
  ```bash
  grep -r "__import__\|importlib.import_module" src/ --include="*.py" | grep MODULE_NAME
  ```

- [ ] **No dynamic references** - Check for string references
  ```bash
  grep -r "MODULE_NAME" src/ tests/ --include="*.py"
  ```

- [ ] **Test suite passes** - Run all tests before changes
  ```bash
  python -m pytest tests/ -v
  ```

- [ ] **Bot runs successfully** - Dry run before changes
  ```bash
  python -m catalyst_bot.runner --dry-run
  ```

### Post-Deletion Verification

After removing each file:

- [ ] **Imports still work** - Verify no import errors
  ```bash
  python -c "import catalyst_bot; print('OK')"
  ```

- [ ] **Tests still pass** - Re-run full test suite
  ```bash
  python -m pytest tests/ -v
  ```

- [ ] **Bot still runs** - Execute full cycle
  ```bash
  python -m catalyst_bot.runner --dry-run
  ```

- [ ] **No errors in logs** - Check for import/module errors
  ```bash
  grep -i "error\|import\|module" logs/catalyst_bot.log | tail -50
  ```

- [ ] **Core functionality works**:
  - [ ] RSS feed fetching
  - [ ] Alert classification
  - [ ] Trading execution (if enabled)
  - [ ] Chart generation
  - [ ] Discord posting

### Final Acceptance Criteria

Before considering the cleanup complete:

- [ ] All planned files removed/relocated
- [ ] All tests passing
- [ ] Bot runs one complete cycle successfully
- [ ] No import errors in logs
- [ ] No functionality regression
- [ ] Documentation updated
- [ ] Git history preserved (files removed via `git rm`, not manual deletion)

---

## 7. ROLLBACK PROCEDURES

### Individual File Rollback

If deletion of a specific file causes issues:

```bash
# Restore single file from last commit
git checkout HEAD~1 -- path/to/file.py

# Or restore from specific commit
git checkout <commit-hash> -- path/to/file.py

# Verify restoration
python -c "import catalyst_bot.MODULE_NAME; print('Restored')"
```

### Full Wave Rollback

If multiple deletions cause issues:

```bash
# Option 1: Revert the entire commit
git revert <commit-hash>

# Option 2: Reset to before cleanup
git reset --hard <commit-before-cleanup>
git push --force-with-lease  # If already pushed

# Option 3: Restore from backup branch
git checkout backup-before-wave4
git checkout -b wave4-rollback
```

### Backup Strategy

Before starting cleanup:

```bash
# Create backup branch
git checkout -b backup-before-wave4
git push origin backup-before-wave4

# Return to main branch
git checkout main

# Proceed with cleanup...
```

### Emergency Recovery

If bot is broken and needs immediate fix:

```bash
# 1. Stop the bot
pkill -f catalyst_bot

# 2. Quick rollback
git reset --hard origin/main  # Reset to last known good state

# 3. Restart bot
python -m catalyst_bot.runner

# 4. Investigate issue in separate branch
git checkout -b debug-wave4-issue
```

### Partial Rollback

If only one phase caused issues:

```bash
# List recent commits
git log --oneline -10

# Revert specific commit
git revert <commit-hash-of-problematic-phase>

# Example: Revert only paper_trader removal
git log --grep="paper_trader"  # Find commit
git revert abc123  # Revert that commit
```

### Testing After Rollback

After any rollback:

```bash
# 1. Verify imports
python -c "import catalyst_bot; from catalyst_bot import runner; print('OK')"

# 2. Run tests
python -m pytest tests/ -v

# 3. Dry run
python -m catalyst_bot.runner --dry-run

# 4. Check logs
tail -100 logs/catalyst_bot.log | grep -i error
```

---

## APPENDIX A: File Summary Table

| File | Size | Status | Risk | Action | Priority |
|------|------|--------|------|--------|----------|
| `paper_trader.py` | 480 | Deprecated (2025-11-26) | HIGH | Migrate then delete | P2 |
| `services/llm_monitor.py` | 266 | Superseded | LOW | Update import then delete | P1 |
| `quickchart_integration.py` | 252 | Never imported | NONE | Delete | P1 |
| `runner_impl.py` | 22 | Never imported | NONE | Delete | P1 |
| `llm_slash_commands.py` | 15 | Stub only | NONE | Delete | P1 |
| `broker/integration_example.py` | 489 | Misplaced | NONE | Relocate | P1 |
| `alerts.py:262-271` | 10 | Documentation | N/A | Keep | - |
| `feeds.py:2606-2620` | 15 | Obsolete | NONE | Delete | P1 |
| `test_end_to_end.py` | 623 | Test stubs | NONE | Convert to docs or delete | P3 |
| `test_trading_env.py:245-474` | 230 | Test stubs | NONE | Convert to docs or delete | P3 |
| **TOTAL** | **2,402** | | | | |

**Priority Levels:**
- **P1:** Safe to delete/relocate immediately (Quick wins)
- **P2:** Requires migration/testing before deletion
- **P3:** Optional cleanup (test stubs)

---

## APPENDIX B: Command Reference

### Search Commands

```bash
# Find all imports of a module
grep -r "from.*MODULE\|import.*MODULE" src/ tests/ --include="*.py"

# Find string references
grep -r "module_name" src/ tests/ docs/ --include="*.py" --include="*.md"

# Find function calls
grep -r "function_name(" src/ --include="*.py"

# Count lines in file
wc -l path/to/file.py

# Find files by pattern
find . -name "*pattern*.py" -type f
```

### Git Commands

```bash
# Remove file from git
git rm path/to/file.py

# Move/rename file in git
git mv old/path.py new/path.py

# View file history
git log --oneline -- path/to/file.py

# View file at specific commit
git show <commit>:path/to/file.py

# Restore deleted file
git checkout HEAD~1 -- path/to/file.py
```

### Testing Commands

```bash
# Run all tests
python -m pytest tests/ -v

# Run specific test file
python -m pytest tests/test_file.py -v

# Run tests with keyword
python -m pytest -k "test_pattern" -v

# Run bot dry-run
python -m catalyst_bot.runner --dry-run

# Check imports
python -c "import catalyst_bot; print('OK')"
```

---

## APPENDIX C: Risk Assessment

### Risk Matrix

| Component | Deletion Risk | Impact if Wrong | Mitigation |
|-----------|---------------|-----------------|------------|
| quickchart_integration.py | **NONE** | None (never imported) | Search codebase first |
| runner_impl.py | **NONE** | None (never imported) | Search codebase first |
| llm_slash_commands.py | **NONE** | None (stub only) | Search codebase first |
| llm_monitor.py | **LOW** | LLM costs not tracked | Update import first, test extensively |
| feeds.py comments | **NONE** | None (already moved) | Verify runner.py has implementation |
| integration_example.py | **NONE** | Example breaks | Test after relocation |
| paper_trader.py | **MEDIUM** | Trading stops working | Migrate dependencies first, extensive testing |
| test stubs | **NONE** | Lose test specs | Convert to docs first |

### Failure Scenarios & Recovery

| Scenario | Probability | Detection | Recovery Time | Prevention |
|----------|-------------|-----------|---------------|------------|
| Import error after deletion | Low | Immediate | < 1 min | Pre-deletion search |
| Bot crashes on startup | Low | Immediate | < 2 min | Dry run before deletion |
| Tests fail after deletion | Medium | 5-10 min | 2-5 min | Run tests before/after |
| Silent functionality loss | Low | Hours-Days | 10-30 min | Test all features |
| Production outage | Very Low | Immediate | 1-5 min | Deploy to staging first |

### Safety Measures

1. **Always use `git rm`** - Preserves history
2. **Create backup branch** - Quick recovery option
3. **Test incrementally** - One phase at a time
4. **Monitor logs** - Check for errors after changes
5. **Dry run first** - Test in safe environment
6. **Keep backups** - .LEGACY_BACKUP files for 30 days

---

## APPENDIX D: Migration Code Snippets

### Replace paper_trader.is_enabled() in runner.py

**Before:**
```python
from . import paper_trader

# Later in code:
if paper_trader.is_enabled():
    paper_trader.start_position_monitor()
```

**After:**
```python
def is_trading_enabled():
    """Check if paper trading is enabled via env vars."""
    if os.getenv("FEATURE_PAPER_TRADING", "1") != "1":
        return False

    api_key = os.getenv("ALPACA_API_KEY", "").strip()
    api_secret = os.getenv("ALPACA_SECRET", "").strip()

    return bool(api_key and api_secret)

# Later in code:
if is_trading_enabled():
    # Use TradingEngine adapter instead
    from .adapters.trading_engine_adapter import start_trading_monitor
    start_trading_monitor()
```

### Replace llm_monitor in llm_service.py

**Before:**
```python
from .llm_monitor import LLMMonitor

@property
def monitor(self):
    if self._monitor is None and self.config.get("cost_tracking_enabled"):
        try:
            self._monitor = LLMMonitor(self.config)
        except Exception as e:
            log.warning("llm_monitor_init_failed err=%s", str(e))
    return self._monitor
```

**After:**
```python
from ..llm_usage_monitor import get_monitor

@property
def monitor(self):
    if self._monitor is None and self.config.get("cost_tracking_enabled"):
        try:
            self._monitor = get_monitor()
        except Exception as e:
            log.warning("llm_usage_monitor_init_failed err=%s", str(e))
    return self._monitor
```

### Update integration_example.py imports

**Before (relative imports):**
```python
from ..logging_utils import get_logger, setup_logging
from .alpaca_client import AlpacaBrokerClient
from ..execution.order_executor import OrderExecutor
from ..portfolio.position_manager import PositionManager
```

**After (absolute imports):**
```python
from catalyst_bot.logging_utils import get_logger, setup_logging
from catalyst_bot.broker.alpaca_client import AlpacaBrokerClient
from catalyst_bot.execution.order_executor import OrderExecutor
from catalyst_bot.portfolio.position_manager import PositionManager
```

---

## Document Metadata

**Version:** 1.0
**Last Updated:** 2025-12-14
**Review Status:** Pending Review
**Approver:** Project Lead
**Implementation Deadline:** TBD

**Change Log:**
- 2025-12-14: Initial comprehensive analysis completed
- 2025-12-14: All 6 modules analyzed with dependency mapping
- 2025-12-14: Implementation plan and verification procedures documented

**Related Documents:**
- `docs/LEGACY-TO-TRADINGENGINE-MIGRATION-PLAN.md` - Trading engine migration
- `docs/llm/LLM_USAGE_MONITORING.md` - LLM monitoring documentation
- `docs/deployment/broker-integration-scaffolding-complete.md` - Broker integration

---

**END OF DOCUMENTATION**
