# Performance Fix Plan - Stuttering Issue

**Issue:** Rhythmic CPU/GPU usage causing system stuttering
**Status:** URGENT - Production running but impacting system usability
**Next Week Implementation:** WAVE 0.0 - Performance Throttling & Market Hours Detection

---

## Immediate Workaround (Today)

**Option 1: Lower Process Priority (No code changes)**
```powershell
# Find Python process PID
tasklist | findstr python

# Lower priority (run as admin)
wmic process where ProcessId=<PID> CALL setpriority "below normal"
```

**Option 2: Increase Cycle Interval**
```ini
# .env - Change from 60s to 120s
SLEEP_SECONDS=120
```

**Option 3: Disable Heavy Features (Market Closed)**
```ini
# .env - Temporary for tonight
FEATURE_LLM_CLASSIFIER=0
FEATURE_LLM_FALLBACK=0
FEATURE_ADVANCED_CHARTS=0
FEATURE_BREAKOUT_SCANNER=0
```

---

## Week 1 Implementation Plan

### Phase 1: Stuttering Fix (2-3 hours)
**Goal:** Eliminate rhythmic spikes

1. **Process Priority Adjustment**
   - Auto-set Python process to "Below Normal" on startup
   - Add to `runner.py`:
     ```python
     import psutil
     p = psutil.Process()
     p.nice(psutil.BELOW_NORMAL_PRIORITY_CLASS)  # Windows
     ```

2. **Rate Limiting for Heavy Operations**
   - LLM calls: Min 3 seconds between requests
   - Chart generation: Min 2 seconds between charts
   - Add sleep delays in `llm_client.py` and `charts_advanced.py`

3. **Batch Processing Instead of Spikes**
   - Queue LLM requests, process sequentially
   - Queue chart requests, process with delays
   - Already implemented: `llm_batch.py`, `chart_queue.py` (integrate into runner)

### Phase 2: Market Hours Detection (1 day)
**Goal:** Reduce load outside market hours

1. **Market Status Detection**
   - Add `market_hours.py` module
   - Detect: Pre-market, Regular, After-hours, Closed
   - Use system timezone (America/Chicago from .env)

2. **Dynamic Feature Toggling**
   - Market Open (9:30am-4pm ET): All features ON, 60s cycle
   - Extended Hours (4am-9:30am, 4pm-8pm): LLM ON, Charts OFF (use Finviz), 90s cycle
   - Market Closed (8pm-4am): LLM OFF, Charts OFF, Breakout OFF, 180s cycle
   - Pre-open Warmup (7:30am): Re-enable all features

3. **Configuration**
   ```ini
   # New .env settings
   FEATURE_MARKET_HOURS_DETECTION=1
   BOT_PROCESS_PRIORITY=BELOW_NORMAL
   LLM_MIN_INTERVAL_SEC=3
   CHART_MIN_INTERVAL_SEC=2
   MARKET_OPEN_CYCLE_SEC=60
   EXTENDED_HOURS_CYCLE_SEC=90
   MARKET_CLOSED_CYCLE_SEC=180
   PREOPEN_WARMUP_HOURS=2
   ```

---

## Expected Results

**Phase 1 (Immediate):**
- Eliminate stuttering during operation
- Smooth CPU/GPU usage (no spikes)
- System remains fully usable

**Phase 2 (Market Hours):**
- 70-90% resource reduction when market closed
- Automatic feature re-enablement before market open
- Minimal impact during trading hours

---

## Testing Plan

1. **Monitor stuttering** before/after Phase 1
2. **Run overnight** with Phase 2 enabled (market closed mode)
3. **Verify warmup** triggers at 7:30am ET Monday morning
4. **Check alerts** resume normally at market open (9:30am)

---

## Rollback Plan

If performance fix causes issues:

```ini
# .env - Disable new features
FEATURE_MARKET_HOURS_DETECTION=0
BOT_PROCESS_PRIORITY=NORMAL
```

Restart bot - will revert to current behavior.

---

**Priority:** URGENT - Implement Phase 1 next week before next trading day.
