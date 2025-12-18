# Priority To-Do List

## Next Session Priorities

### 1. Feedback Loop → SignalGenerator Integration
- Wire `feedback/weight_adjuster.py` into SignalGenerator
- Apply keyword performance multipliers to confidence scores
- Periodically reload multipliers (every N cycles)
- **Purpose:** Adaptive learning from trade outcomes (stepping stone to ML)

### 2. Slippage/Fill Rate Issues
- COCP filled at $0.97, others unfilled (VWAV, WKEY, KWM, AEC)
- Investigate limit order pricing strategy
- Consider market orders for small positions or tighter limit spreads

---

## Completed Fixes (2025-12-18)

### Heartbeat Wiring Bugs - RESOLVED

**Issue 1: Trading Activity showing zeros despite Alpaca orders**
- **Root Cause:** Trading execution code was nested inside `feature_feedback_loop` conditional. Even with `FEATURE_PAPER_TRADING=1`, trades only executed if `FEATURE_FEEDBACK_LOOP=1` was also enabled.
- **Fix:** Moved trading execution block outside the feedback loop conditional in `alerts.py`. Trading now runs independently when paper trading is enabled.
- **Files Changed:** `src/catalyst_bot/alerts.py` (lines 1541-1603)

**Issue 2: Open Positions showing 0 despite filled COCP order**
- **Root Cause:** Heartbeat was reading from local PositionManager which only tracks orders that fill within the `wait_for_fill` timeout. If Alpaca fills an order asynchronously (like COCP at $0.97), the local PositionManager never knew about it.
- **Fix:** Modified `_get_trading_engine_data()` in runner.py to fetch positions directly from Alpaca API (source of truth) instead of local PositionManager.
- **Files Changed:** `src/catalyst_bot/runner.py` (lines 457-503)

**Issue 3: LLM Usage mismatch (6 requests but Gemini: 0, Claude: 0)**
- **Root Cause:** The modern `LLMService` was tracking usage in its own monitor but not bridging to the legacy `LLMUsageMonitor` that heartbeat reads from.
- **Fix:**
  1. Added `latency_ms` and `cost_estimate` parameters to `LLMUsageMonitor.log_usage()`
  2. Added `success=False` to error path bridge call in `LLMService`
- **Files Changed:**
  - `src/catalyst_bot/llm_usage_monitor.py` (log_usage method signature)
  - `src/catalyst_bot/services/llm_service.py` (error path bridge)

**Issue 4: Error tracking not visible in heartbeat**
- **Fix:** Added `_record_and_track_error()` calls to 7 critical exception handlers:
  - SEC batch processing errors
  - Trading engine execution errors
  - Position monitor startup failures
  - SEC monitor startup failures
  - Trading engine startup failures
  - News velocity tracking failures
  - Startup test alert failures
- **Files Changed:** `src/catalyst_bot/runner.py` (multiple locations)

---

## Summary of All Changes

| File | Change Description |
|------|-------------------|
| `alerts.py` | Moved trading execution outside feedback loop conditional |
| `runner.py` | Fetch positions from Alpaca API, added 7 error tracking calls |
| `llm_usage_monitor.py` | Added latency_ms and cost_estimate parameters |
| `llm_service.py` | Added success=False to error path bridge |

---

*Last updated: 2025-12-18*
